import os
import re
from datetime import date, datetime
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, make_response, current_app, jsonify)
from flask_login import login_required, current_user
from database import get_db_connection
import pdfkit

# ── wkhtmltopdf ───────────────────────────────────────────────────────────────
def _pdfkit_config():
    for c in ['/opt/homebrew/bin/wkhtmltopdf',
              '/usr/local/bin/wkhtmltopdf',
              '/usr/bin/wkhtmltopdf']:
        if os.path.isfile(c):
            return pdfkit.configuration(wkhtmltopdf=c)
    return None

def _fix_static_paths(html):
    static_dir = os.path.join(current_app.root_path, 'static')
    return html.replace('/static/', f'file://{static_dir}/')

_PDF_OPTIONS = {
    'page-size':                'A4',
    'margin-top':               '0mm',
    'margin-right':             '0mm',
    'margin-bottom':            '0mm',
    'margin-left':              '0mm',
    'encoding':                 'UTF-8',
    'print-media-type':         None,
    'no-outline':               None,
    'disable-smart-shrinking':  None,
    'quiet':                    None,
    'load-error-handling':      'ignore',
    'load-media-error-handling':'ignore',
    'enable-local-file-access': None,
}

# ── Blueprint ─────────────────────────────────────────────────────────────────
propostas_bp = Blueprint('propostas', __name__)

# ── Decorator admin-only ──────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.tipo not in ['admin', 'gerencial']:
            flash("Acesso restrito.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

# ── Unidades de medida disponíveis ────────────────────────────────────────────
UNIDADES = [
    ('un',        'Unidade'),
    ('kg',        'Quilograma (kg)'),
    ('g',         'Grama (g)'),
    ('L',         'Litro (L)'),
    ('ml',        'Mililitro (ml)'),
    ('h',         'Hora (h)'),
    ('mês',       'Mês'),
    ('refeição',  'Refeição'),
    ('porção',    'Porção'),
    ('pacote',    'Pacote'),
    ('caixa',     'Caixa'),
    ('diária',    'Diária'),
    ('serviço',   'Serviço'),
]

# ── Gera número automático PROP-YYYY-NNN ──────────────────────────────────────
def _gerar_numero():
    ano = date.today().year
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT numero FROM propostas
        WHERE numero LIKE %s
        ORDER BY id DESC LIMIT 1
    """, (f"PROP-{ano}-%",))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            seq = int(row['numero'].split('-')[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1
    return f"PROP-{ano}-{seq:03d}"

# ── Helper: lê empresa para PDF ───────────────────────────────────────────────
def _get_empresa():
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM empresa LIMIT 1")
    emp = cur.fetchone()
    conn.close()
    return emp or {}

# ─────────────────────────────────────────────────────────────────────────────
#  LISTAGEM
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas')
@login_required
@admin_required
def listar():
    filtro_status  = request.args.get('status', '')
    filtro_cliente = request.args.get('cliente_id', '')
    filtro_ano     = request.args.get('ano', str(date.today().year))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    sql = """
        SELECT p.*, c.nome_empresa AS cliente_nome,
               COALESCE(SUM(pi.quantidade * pi.valor_unitario), 0) AS total_proposta
        FROM propostas p
        JOIN clientes c ON c.id = p.id_cliente
        LEFT JOIN proposta_itens pi ON pi.id_proposta = p.id
        WHERE YEAR(p.data_proposta) = %s
    """
    params = [filtro_ano]

    if filtro_status:
        sql += " AND p.status = %s"
        params.append(filtro_status)
    if filtro_cliente:
        sql += " AND p.id_cliente = %s"
        params.append(filtro_cliente)

    sql += " GROUP BY p.id ORDER BY p.id DESC"
    cur.execute(sql, params)
    propostas = cur.fetchall()

    cur.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    clientes = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT YEAR(data_proposta) AS ano
        FROM propostas ORDER BY ano DESC
    """)
    anos = [str(r['ano']) for r in cur.fetchall()] or [str(date.today().year)]

    # Contadores por status (no ano filtrado)
    cur.execute("""
        SELECT status, COUNT(*) AS total
        FROM propostas
        WHERE YEAR(data_proposta) = %s
        GROUP BY status
    """, (filtro_ano,))
    contadores = {r['status']: r['total'] for r in cur.fetchall()}

    conn.close()
    return render_template('propostas.html',
                           propostas=propostas, clientes=clientes,
                           anos=anos, contadores=contadores,
                           filtro_status=filtro_status,
                           filtro_cliente=filtro_cliente,
                           filtro_ano=filtro_ano,
                           today=date.today(),
                           unidades=UNIDADES)


# ─────────────────────────────────────────────────────────────────────────────
#  NOVA PROPOSTA
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/nova', methods=['GET', 'POST'])
@login_required
@admin_required
def nova():
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    clientes = cur.fetchall()

    if request.method == 'POST':
        id_cliente          = request.form.get('id_cliente')
        data_proposta       = request.form.get('data_proposta')
        validade            = request.form.get('validade') or None
        condicoes_pagamento = request.form.get('condicoes_pagamento', '').strip()
        observacoes         = request.form.get('observacoes', '').strip()

        descricoes  = request.form.getlist('descricao[]')
        quantidades = request.form.getlist('quantidade[]')
        unids       = request.form.getlist('unidade[]')
        valores     = request.form.getlist('valor_unitario[]')

        if not id_cliente or not data_proposta:
            flash("Cliente e data são obrigatórios.", "warning")
            conn.close()
            return render_template('proposta_form.html', clientes=clientes,
                                   unidades=UNIDADES, proposta=None)

        numero = _gerar_numero()
        cur.execute("""
            INSERT INTO propostas
                (numero, id_cliente, data_proposta, validade,
                 condicoes_pagamento, observacoes, status)
            VALUES (%s,%s,%s,%s,%s,%s,'Rascunho')
        """, (numero, id_cliente, data_proposta, validade,
              condicoes_pagamento, observacoes))
        id_proposta = cur.lastrowid

        for desc, qtd, und, vunit in zip(descricoes, quantidades, unids, valores):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qtd   = float(str(qtd).replace(',', '.'))
                vunit = float(str(vunit).replace(',', '.'))
            except Exception:
                qtd   = 1.0
                vunit = 0.0
            cur.execute("""
                INSERT INTO proposta_itens
                    (id_proposta, descricao, quantidade, unidade, valor_unitario)
                VALUES (%s,%s,%s,%s,%s)
            """, (id_proposta, desc, qtd, und, vunit))

        conn.commit()
        conn.close()
        flash(f"Proposta {numero} criada com sucesso!", "success")
        return redirect(url_for('propostas.listar'))

    conn.close()
    return render_template('proposta_form.html', clientes=clientes,
                           unidades=UNIDADES, proposta=None,
                           hoje=date.today().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
#  EDITAR PROPOSTA
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/editar/<int:id_proposta>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM propostas WHERE id = %s", (id_proposta,))
    proposta = cur.fetchone()
    if not proposta:
        flash("Proposta não encontrada.", "warning")
        conn.close()
        return redirect(url_for('propostas.listar'))

    cur.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    clientes = cur.fetchall()

    if request.method == 'POST':
        id_cliente          = request.form.get('id_cliente')
        data_proposta       = request.form.get('data_proposta')
        validade            = request.form.get('validade') or None
        condicoes_pagamento = request.form.get('condicoes_pagamento', '').strip()
        observacoes         = request.form.get('observacoes', '').strip()
        status              = request.form.get('status', proposta['status'])

        cur.execute("""
            UPDATE propostas SET
                id_cliente=%s, data_proposta=%s, validade=%s,
                condicoes_pagamento=%s, observacoes=%s, status=%s
            WHERE id=%s
        """, (id_cliente, data_proposta, validade,
              condicoes_pagamento, observacoes, status, id_proposta))

        # Recria itens (delete → insert)
        cur.execute("DELETE FROM proposta_itens WHERE id_proposta = %s", (id_proposta,))

        descricoes  = request.form.getlist('descricao[]')
        quantidades = request.form.getlist('quantidade[]')
        unids       = request.form.getlist('unidade[]')
        valores     = request.form.getlist('valor_unitario[]')

        for desc, qtd, und, vunit in zip(descricoes, quantidades, unids, valores):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qtd   = float(str(qtd).replace(',', '.'))
                vunit = float(str(vunit).replace(',', '.'))
            except Exception:
                qtd   = 1.0
                vunit = 0.0
            cur.execute("""
                INSERT INTO proposta_itens
                    (id_proposta, descricao, quantidade, unidade, valor_unitario)
                VALUES (%s,%s,%s,%s,%s)
            """, (id_proposta, desc, qtd, und, vunit))

        conn.commit()
        conn.close()
        flash("Proposta atualizada com sucesso!", "success")
        return redirect(url_for('propostas.listar'))

    cur.execute("""
        SELECT * FROM proposta_itens WHERE id_proposta = %s ORDER BY id
    """, (id_proposta,))
    itens = cur.fetchall()
    conn.close()

    return render_template('proposta_form.html', clientes=clientes,
                           unidades=UNIDADES, proposta=proposta,
                           itens=itens, hoje=date.today().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
#  ATUALIZAR STATUS (AJAX)
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/status/<int:id_proposta>', methods=['POST'])
@login_required
@admin_required
def atualizar_status(id_proposta):
    novo_status = request.form.get('status')
    validos = {'Rascunho', 'Enviada', 'Aceita', 'Recusada', 'Expirada'}
    if novo_status not in validos:
        return jsonify({'ok': False, 'msg': 'Status inválido'}), 400

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("UPDATE propostas SET status=%s WHERE id=%s", (novo_status, id_proposta))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'status': novo_status})


# ─────────────────────────────────────────────────────────────────────────────
#  DELETAR
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/deletar/<int:id_proposta>', methods=['POST'])
@login_required
@admin_required
def deletar(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT numero FROM propostas WHERE id=%s", (id_proposta,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM propostas WHERE id=%s", (id_proposta,))
        conn.commit()
        flash(f"Proposta {row['numero']} excluída.", "success")
    conn.close()
    return redirect(url_for('propostas.listar'))


# ─────────────────────────────────────────────────────────────────────────────
#  VER PROPOSTA (HTML)
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/ver/<int:id_proposta>')
@login_required
@admin_required
def ver(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*, c.nome_empresa, c.cnpj, c.email, c.celular, c.apelido
        FROM propostas p
        JOIN clientes c ON c.id = p.id_cliente
        WHERE p.id = %s
    """, (id_proposta,))
    proposta = cur.fetchone()
    if not proposta:
        flash("Proposta não encontrada.", "warning")
        conn.close()
        return redirect(url_for('propostas.listar'))

    cur.execute("""
        SELECT *, (quantidade * valor_unitario) AS subtotal
        FROM proposta_itens WHERE id_proposta = %s ORDER BY id
    """, (id_proposta,))
    itens = cur.fetchall()
    conn.close()

    total = sum(float(i['subtotal'] or 0) for i in itens)
    empresa = _get_empresa()
    return render_template('proposta_pdf.html',
                           proposta=proposta, itens=itens,
                           total=total, empresa=empresa,
                           modo='preview')


# ─────────────────────────────────────────────────────────────────────────────
#  DOWNLOAD PDF
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/pdf/<int:id_proposta>')
@login_required
@admin_required
def download_pdf(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*, c.nome_empresa, c.cnpj, c.email, c.celular, c.apelido
        FROM propostas p
        JOIN clientes c ON c.id = p.id_cliente
        WHERE p.id = %s
    """, (id_proposta,))
    proposta = cur.fetchone()
    if not proposta:
        flash("Proposta não encontrada.", "warning")
        conn.close()
        return redirect(url_for('propostas.listar'))

    cur.execute("""
        SELECT *, (quantidade * valor_unitario) AS subtotal
        FROM proposta_itens WHERE id_proposta = %s ORDER BY id
    """, (id_proposta,))
    itens = cur.fetchall()
    conn.close()

    total = sum(float(i['subtotal'] or 0) for i in itens)
    empresa = _get_empresa()

    try:
        html = render_template('proposta_pdf.html',
                               proposta=proposta, itens=itens,
                               total=total, empresa=empresa,
                               modo='pdf')
        html = _fix_static_paths(html)

        nome_limpo  = re.sub(r'[^\w\s-]', '', proposta['nome_empresa']).strip().replace(' ', '_')
        nome_arquivo = f"Proposta_{proposta['numero']}_{nome_limpo}.pdf"

        cfg = _pdfkit_config()
        pdf = pdfkit.from_string(html, False,
                                 options=_PDF_OPTIONS,
                                 configuration=cfg if cfg else pdfkit.configuration())
        response = make_response(pdf)
        response.headers['Content-Type']        = 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
        return response
    except Exception as e:
        flash(f"Erro ao gerar PDF: {e}. Verifique se o wkhtmltopdf está instalado.", "danger")
        return redirect(url_for('propostas.ver', id_proposta=id_proposta))
