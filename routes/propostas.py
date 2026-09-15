from datetime import date, datetime
import mysql.connector
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify)
from flask_login import login_required, current_user
from database import get_db_connection
from utils.permissions import admin_only
from utils.audit import log_action, format_field_diff
from utils.validators import parse_moeda_br

# ── Blueprint ─────────────────────────────────────────────────────────────────
propostas_bp = Blueprint('propostas', __name__)

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

# A unidade do produto é cadastrada livre ('UN', 'LT', ...) e precisa casar com
# um dos valores do select acima. O que não estiver no mapa cai em 'un'.
_MAPA_UNIDADES = {
    'UN': 'un', 'UND': 'un', 'UNID': 'un', 'UNIDADE': 'un', 'PC': 'un',
    'KG': 'kg', 'QUILO': 'kg', 'G': 'g', 'GR': 'g', 'GRAMA': 'g',
    'L': 'L', 'LT': 'L', 'LITRO': 'L', 'ML': 'ml',
    'H': 'h', 'HR': 'h', 'HORA': 'h',
    'MES': 'mês', 'MÊS': 'mês',
    'REFEICAO': 'refeição', 'REFEIÇÃO': 'refeição', 'REF': 'refeição',
    'PORCAO': 'porção', 'PORÇÃO': 'porção',
    'PACOTE': 'pacote', 'PCT': 'pacote',
    'CAIXA': 'caixa', 'CX': 'caixa',
    'DIARIA': 'diária', 'DIÁRIA': 'diária',
    'SERVICO': 'serviço', 'SERVIÇO': 'serviço',
}


def _unidade_proposta(unidade_produto):
    return _MAPA_UNIDADES.get((unidade_produto or '').strip().upper(), 'un')

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
    return emp or {}


# ── Expiração automática de propostas ─────────────────────────────────────────
def expirar_propostas_vencidas(cursor):
    """Marca como 'Expirada' as propostas cuja validade já passou e que ainda
    estavam em 'Rascunho' ou 'Enviada'. Não toca em Aceita/Recusada/Expirada.

    Idempotente — o caller faz o commit. Retorna o nº de propostas expiradas.
    Roda ao abrir a listagem e via cron (scripts/expirar_propostas.py)."""
    cursor.execute("""
        UPDATE propostas
        SET status = 'Expirada'
        WHERE status IN ('Rascunho', 'Enviada')
          AND validade IS NOT NULL
          AND validade < CURDATE()
    """)
    return cursor.rowcount


# ─────────────────────────────────────────────────────────────────────────────
#  LISTAGEM
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas')
@login_required
@admin_only
def listar():
    filtro_status  = request.args.get('status', '')
    filtro_cliente = request.args.get('cliente_id', '')
    filtro_ano     = request.args.get('ano', str(date.today().year))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    # Expira automaticamente as propostas vencidas antes de listar/contar
    expirar_propostas_vencidas(cur)
    conn.commit()

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

    return render_template('propostas.html',
                           propostas=propostas, clientes=clientes,
                           anos=anos, contadores=contadores,
                           filtro_status=filtro_status,
                           filtro_cliente=filtro_cliente,
                           filtro_ano=filtro_ano,
                           today=date.today(),
                           unidades=UNIDADES)


# ─────────────────────────────────────────────────────────────────────────────
#  ITENS JÁ NEGOCIADOS COM O CLIENTE (base da proposta de reajuste)
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/itens_cliente/<int:id_cliente>')
@login_required
@admin_only
def itens_cliente(id_cliente):
    """Itens 'favoritos' do cliente com o valor praticado HOJE.

    Favorito = produto que já tem preço negociado para esse cliente (tabela
    individual dele) ou para o grupo dele — a mesma definição do filtro
    "Mostrar apenas itens com preço negociado" da tela de lançamento, com a
    mesma prioridade de preço (cliente > grupo) e o mesmo NULLIF(...,0), que
    trata preço zerado como "sem preço".

    Serve para pré-preencher a Nova Proposta quando ela é de reajuste: parte-se
    do que o cliente paga hoje em vez de redigitar item por item.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id_grupo FROM clientes WHERE id = %s", (id_cliente,))
    cliente = cur.fetchone()
    if not cliente:
        return jsonify({'itens': []}), 404

    cur.execute("""
        SELECT p.nome, p.unidade,
               COALESCE(NULLIF(tc.preco_venda, 0), NULLIF(tg.preco_venda, 0)) AS preco
        FROM produtos p
        LEFT JOIN tabela_precos tc
               ON p.id = tc.id_produto AND tc.id_cliente = %s
        LEFT JOIN tabela_precos_grupos tg
               ON p.id = tg.id_produto AND tg.id_grupo = %s
        WHERE COALESCE(NULLIF(tc.preco_venda, 0), NULLIF(tg.preco_venda, 0)) IS NOT NULL
        ORDER BY p.nome
    """, (id_cliente, cliente['id_grupo']))

    itens = [{
        'descricao':      r['nome'],
        'quantidade':     1,
        'unidade':        _unidade_proposta(r['unidade']),
        'valor_unitario': float(r['preco']),
    } for r in cur.fetchall()]
    return jsonify({'itens': itens})


# ─────────────────────────────────────────────────────────────────────────────
#  NOVA PROPOSTA
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/nova', methods=['GET', 'POST'])
@login_required
@admin_only
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
        # Marcado = orçamento (Qtd/Subtotal/Total no PDF). Desmarcado = tabela
        # de preços, onde somar itens distintos não significa nada.
        mostrar_totais = 1 if request.form.get('mostrar_totais') else 0

        if not id_cliente or not data_proposta:
            flash("Cliente e data são obrigatórios.", "warning")
            return render_template('proposta_form.html', clientes=clientes,
                                   unidades=UNIDADES, proposta=None)

        # Gera o número e insere; se dois cadastros simultâneos colidirem no
        # mesmo sequencial, o índice UNIQUE (uq_propostas_numero) rejeita e a
        # gente tenta o próximo número. Backstop de 5 tentativas.
        id_proposta = None
        for _ in range(5):
            numero = _gerar_numero()
            try:
                cur.execute("""
                    INSERT INTO propostas
                        (numero, id_cliente, data_proposta, validade,
                         condicoes_pagamento, observacoes, status, mostrar_totais)
                    VALUES (%s,%s,%s,%s,%s,%s,'Rascunho',%s)
                """, (numero, id_cliente, data_proposta, validade,
                      condicoes_pagamento, observacoes, mostrar_totais))
                id_proposta = cur.lastrowid
                break
            except mysql.connector.IntegrityError:
                conn.rollback()
                continue
        if id_proposta is None:
            flash("Não foi possível gerar o número da proposta. Tente novamente.", "danger")
            return redirect(url_for('propostas.listar'))

        for desc, qtd, und, vunit in zip(descricoes, quantidades, unids, valores):
            desc = desc.strip()
            if not desc:
                continue
            # Parser único do sistema: entende "1.234,56" (Real) e "24.30".
            # Antes, um valor com milhar caía no except e o preço ia para 0
            # sem ninguém perceber.
            qtd   = parse_moeda_br(qtd) or 1.0
            vunit = parse_moeda_br(vunit)
            cur.execute("""
                INSERT INTO proposta_itens
                    (id_proposta, descricao, quantidade, unidade, valor_unitario)
                VALUES (%s,%s,%s,%s,%s)
            """, (id_proposta, desc, qtd, und, vunit))

        cur.execute("SELECT nome_empresa FROM clientes WHERE id=%s", (id_cliente,))
        cli = cur.fetchone()
        conn.commit()
        log_action('create', entity_type='proposta', entity_id=id_proposta,
                   descricao=f"Criou proposta {numero} para '{cli['nome_empresa'] if cli else id_cliente}' com {len(descricoes)} item(s)")
        flash(f"Proposta {numero} criada com sucesso!", "success")
        return redirect(url_for('propostas.listar'))

    return render_template('proposta_form.html', clientes=clientes,
                           unidades=UNIDADES, proposta=None,
                           hoje=date.today().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
#  EDITAR PROPOSTA
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/editar/<int:id_proposta>', methods=['GET', 'POST'])
@login_required
@admin_only
def editar(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM propostas WHERE id = %s", (id_proposta,))
    proposta = cur.fetchone()
    if not proposta:
        flash("Proposta não encontrada.", "warning")
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
        mostrar_totais      = 1 if request.form.get('mostrar_totais') else 0

        cur.execute("""
            UPDATE propostas SET
                id_cliente=%s, data_proposta=%s, validade=%s,
                condicoes_pagamento=%s, observacoes=%s, status=%s,
                mostrar_totais=%s
            WHERE id=%s
        """, (id_cliente, data_proposta, validade,
              condicoes_pagamento, observacoes, status, mostrar_totais, id_proposta))

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
            # Parser único do sistema: entende "1.234,56" (Real) e "24.30".
            # Antes, um valor com milhar caía no except e o preço ia para 0
            # sem ninguém perceber.
            qtd   = parse_moeda_br(qtd) or 1.0
            vunit = parse_moeda_br(vunit)
            cur.execute("""
                INSERT INTO proposta_itens
                    (id_proposta, descricao, quantidade, unidade, valor_unitario)
                VALUES (%s,%s,%s,%s,%s)
            """, (id_proposta, desc, qtd, und, vunit))

        conn.commit()
        log_action('update', entity_type='proposta', entity_id=int(id_proposta),
                   descricao=f"Editou proposta {proposta.get('numero')} (status {proposta.get('status')}→{status}, "
                             f"{len(descricoes)} item(s))")
        flash("Proposta atualizada com sucesso!", "success")
        return redirect(url_for('propostas.listar'))

    cur.execute("""
        SELECT * FROM proposta_itens WHERE id_proposta = %s ORDER BY id
    """, (id_proposta,))
    itens = cur.fetchall()

    return render_template('proposta_form.html', clientes=clientes,
                           unidades=UNIDADES, proposta=proposta,
                           itens=itens, hoje=date.today().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
#  ATUALIZAR STATUS (AJAX)
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/status/<int:id_proposta>', methods=['POST'])
@login_required
@admin_only
def atualizar_status(id_proposta):
    novo_status = request.form.get('status')
    validos = {'Rascunho', 'Enviada', 'Aceita', 'Recusada', 'Expirada'}
    if novo_status not in validos:
        return jsonify({'ok': False, 'msg': 'Status inválido'}), 400

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT numero, status FROM propostas WHERE id=%s", (id_proposta,))
    p = cur.fetchone()
    if not p:
        return jsonify({'ok': False, 'msg': 'Proposta não encontrada'}), 404
    cur.execute("UPDATE propostas SET status=%s WHERE id=%s", (novo_status, id_proposta))
    conn.commit()
    log_action('update', entity_type='proposta', entity_id=int(id_proposta),
               descricao=f"Proposta {p.get('numero') or id_proposta}: status {p.get('status') or '—'}→{novo_status}")
    return jsonify({'ok': True, 'status': novo_status})


# ─────────────────────────────────────────────────────────────────────────────
#  DELETAR
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/deletar/<int:id_proposta>', methods=['POST'])
@login_required
@admin_only
def deletar(id_proposta):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT numero, status FROM propostas WHERE id=%s", (id_proposta,))
    row = cur.fetchone()
    if not row:
        flash("Proposta não encontrada.", "warning")
        return redirect(url_for('propostas.listar'))
    # Proposta Aceita é registro de negócio fechado: não pode ser apagada
    # (evita sumir com o histórico do que virou contrato).
    if row.get('status') == 'Aceita':
        flash(f"Proposta {row['numero']} está Aceita e não pode ser excluída. "
              "Mude o status antes, se realmente precisar.", "warning")
        return redirect(url_for('propostas.listar'))
    cur.execute("DELETE FROM proposta_itens WHERE id_proposta=%s", (id_proposta,))
    cur.execute("DELETE FROM propostas WHERE id=%s", (id_proposta,))
    conn.commit()
    log_action('delete', entity_type='proposta', entity_id=int(id_proposta),
               descricao=f"Excluiu proposta {row['numero']} (status {row.get('status') or '—'})")
    flash(f"Proposta {row['numero']} excluída.", "success")
    return redirect(url_for('propostas.listar'))


# ─────────────────────────────────────────────────────────────────────────────
#  VER PROPOSTA (HTML)
# ─────────────────────────────────────────────────────────────────────────────
@propostas_bp.route('/propostas/ver/<int:id_proposta>')
@login_required
@admin_only
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
        return redirect(url_for('propostas.listar'))

    cur.execute("""
        SELECT *, (quantidade * valor_unitario) AS subtotal
        FROM proposta_itens WHERE id_proposta = %s ORDER BY id
    """, (id_proposta,))
    itens = cur.fetchall()

    total = sum(float(i['subtotal'] or 0) for i in itens)
    empresa = _get_empresa()
    return render_template('proposta_pdf.html',
                           proposta=proposta, itens=itens,
                           total=total, empresa=empresa,
                           modo='preview')


# ─────────────────────────────────────────────────────────────────────────────
#  (rota /propostas/pdf/<id> removida: usar 'Imprimir / Salvar PDF' na tela de
#  visualização (propostas.ver) que gera PDF via dialogo nativo do navegador)
# ─────────────────────────────────────────────────────────────────────────────
