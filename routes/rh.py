import os
from datetime import date, datetime
from calendar import monthrange
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app)
from flask_login import login_required, current_user
from database import get_db_connection

rh_bp = Blueprint('rh', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'}
CATEGORIAS_DOC = ['saude', 'seguranca', 'legal', 'treinamento', 'outros']
TIPOS_EXAME = [
    'ASO Admissional', 'ASO Periódico', 'ASO Demissional',
    'ASO Retorno ao Trabalho', 'ASO Mudança de Risco',
    'Audiometria', 'Acuidade Visual', 'Espirometria', 'EEG', 'Outros'
]
MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
            'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
DIAS_SEMANA_LABELS = {
    'seg': 'Seg', 'ter': 'Ter', 'qua': 'Qua',
    'qui': 'Qui', 'sex': 'Sex', 'sab': 'Sáb', 'dom': 'Dom'
}


# ─── GUARDS ───────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.tipo not in ['admin', 'gerencial']:
            flash("Acesso restrito.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


# ─── HELPERS ──────────────────────────────────────────────────────
def _upload_path():
    path = os.path.join(current_app.root_path, 'static', 'uploads', 'rh_docs')
    os.makedirs(path, exist_ok=True)
    return path

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _fmt_date(d):
    """Formata um objeto date/datetime como dd/mm/aaaa. Retorna '' se None."""
    if not d:
        return ''
    try:
        return d.strftime('%d/%m/%Y')
    except AttributeError:
        # Se já for string (raro), devolve como está
        return str(d)


# ══════════════════════════════════════════════════════════════════
# HUB
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh")
@login_required
@admin_required
def hub():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    hoje = date.today()

    cursor.execute("SELECT COUNT(*) as total FROM colaboradores WHERE status='ativo'")
    total_ativos = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM colaboradores WHERE status='ferias'")
    total_ferias = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM colaboradores WHERE status='afastado'")
    total_afastados = cursor.fetchone()['total']

    try:
        cursor.execute("""
            SELECT COUNT(*) as total FROM rh_exames
            WHERE data_vencimento BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        """)
        exames_vencendo = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM rh_exames WHERE data_vencimento < CURDATE()")
        exames_vencidos = cursor.fetchone()['total']
    except Exception:
        exames_vencendo = exames_vencidos = 0

    try:
        cursor.execute("""
            SELECT col.nome, col.funcao, col.data_nascimento,
                   DAY(col.data_nascimento) as dia
            FROM colaboradores col
            WHERE MONTH(col.data_nascimento) = %s AND col.status = 'ativo'
            ORDER BY DAY(col.data_nascimento)
        """, (hoje.month,))
        aniversariantes = cursor.fetchall()
    except Exception:
        aniversariantes = []

    try:
        cursor.execute("""
            SELECT COUNT(*) as total FROM rh_ferias
            WHERE status IN ('agendado','em_andamento')
        """)
        ferias_ativas = cursor.fetchone()['total']
    except Exception:
        ferias_ativas = 0

    try:
        cursor.execute("""
            SELECT COUNT(*) as total FROM rh_documentos
            WHERE validade IS NOT NULL AND validade < DATE_ADD(CURDATE(), INTERVAL 60 DAY)
              AND validade >= CURDATE()
        """)
        docs_vencendo = cursor.fetchone()['total']
        cursor.execute("""
            SELECT COUNT(*) as total FROM rh_documentos
            WHERE validade IS NOT NULL AND validade < CURDATE()
        """)
        docs_vencidos = cursor.fetchone()['total']
    except Exception:
        docs_vencendo = docs_vencidos = 0

    conn.close()
    return render_template('rh_hub.html',
        total_ativos=total_ativos,
        total_ferias=total_ferias,
        total_afastados=total_afastados,
        exames_vencendo=exames_vencendo,
        exames_vencidos=exames_vencidos,
        aniversariantes=aniversariantes,
        ferias_ativas=ferias_ativas,
        docs_vencendo=docs_vencendo,
        docs_vencidos=docs_vencidos,
        mes_atual=MESES_PT[hoje.month - 1]
    )


# ══════════════════════════════════════════════════════════════════
# EXAMES MÉDICOS
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/exames")
@login_required
@admin_required
def exames():
    filtro_colab = request.args.get('colab_id', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    sql_exames = """
        SELECT e.*, col.nome AS nome_colaborador, col.funcao,
               DATEDIFF(e.data_vencimento, CURDATE()) AS dias_vencimento
        FROM rh_exames e
        JOIN colaboradores col ON e.id_colaborador = col.id
        {where}
        ORDER BY e.data_vencimento ASC
    """
    if filtro_colab:
        cursor.execute(sql_exames.format(where="WHERE e.id_colaborador = %s"), (filtro_colab,))
    else:
        cursor.execute(sql_exames.format(where=""))
    lista_exames = cursor.fetchall()
    # Formata datas em Python (evita bug de %%/%% com mysql-connector)
    for ex in lista_exames:
        ex['data_realizado_fmt']   = _fmt_date(ex.get('data_realizado'))
        ex['data_vencimento_fmt']  = _fmt_date(ex.get('data_vencimento'))

    cursor.execute("SELECT id, nome FROM colaboradores WHERE status != 'inativo' ORDER BY nome")
    colaboradores = cursor.fetchall()
    conn.close()

    return render_template('rh_exames.html',
        exames=lista_exames, colaboradores=colaboradores,
        tipos=TIPOS_EXAME, filtro_colab=filtro_colab)


@rh_bp.route("/rh/exames/add", methods=["POST"])
@login_required
@admin_required
def add_exame():
    id_colab    = request.form.get('id_colaborador')
    tipo        = request.form.get('tipo')
    data_real   = request.form.get('data_realizado') or None
    data_venc   = request.form.get('data_vencimento') or None
    resultado   = request.form.get('resultado', 'apto')
    clinica     = request.form.get('clinica', '').strip() or None
    obs         = request.form.get('observacoes', '').strip() or None

    conn = get_db_connection()
    cursor = conn.cursor()

    if id_colab == 'todos':
        # Insere o exame para TODOS os colaboradores ativos
        cursor.execute("SELECT id FROM colaboradores WHERE status != 'inativo'")
        ids = [row[0] for row in cursor.fetchall()]
        for cid in ids:
            cursor.execute("""
                INSERT INTO rh_exames
                    (id_colaborador, tipo, data_realizado, data_vencimento, resultado, clinica, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (cid, tipo, data_real, data_venc, resultado, clinica, obs))
        flash(f"Exame registrado para {len(ids)} colaborador(es)!", "success")
    else:
        cursor.execute("""
            INSERT INTO rh_exames
                (id_colaborador, tipo, data_realizado, data_vencimento, resultado, clinica, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_colab, tipo, data_real, data_venc, resultado, clinica, obs))
        flash("Exame registrado com sucesso!", "success")

    conn.commit()
    conn.close()
    return redirect(url_for('rh.exames'))


@rh_bp.route("/rh/exames/editar", methods=["POST"])
@login_required
@admin_required
def editar_exame():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE rh_exames SET tipo=%s, data_realizado=%s, data_vencimento=%s,
               resultado=%s, clinica=%s, observacoes=%s WHERE id=%s
    """, (
        request.form.get('tipo'),
        request.form.get('data_realizado') or None,
        request.form.get('data_vencimento') or None,
        request.form.get('resultado', 'apto'),
        request.form.get('clinica', '').strip() or None,
        request.form.get('observacoes', '').strip() or None,
        request.form.get('id_exame'),
    ))
    conn.commit()
    conn.close()
    flash("Exame atualizado!", "success")
    return redirect(url_for('rh.exames'))


@rh_bp.route("/rh/exames/excluir/<int:id_exame>", methods=["POST"])
@login_required
@admin_required
def excluir_exame(id_exame):
    conn = get_db_connection()
    conn.cursor().execute("DELETE FROM rh_exames WHERE id = %s", (id_exame,))
    conn.commit()
    conn.close()
    flash("Exame removido.", "success")
    return redirect(url_for('rh.exames'))


# ══════════════════════════════════════════════════════════════════
# REAJUSTE SALARIAL
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/reajuste")
@login_required
@admin_required
def reajuste():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, funcao, salario_bruto, status FROM colaboradores WHERE status != 'inativo' ORDER BY nome")
    colaboradores = cursor.fetchall()
    cursor.execute("""
        SELECT *
        FROM rh_reajustes ORDER BY data_reajuste DESC LIMIT 15
    """)
    historico = cursor.fetchall()
    for r in historico:
        r['data_fmt'] = _fmt_date(r.get('data_reajuste'))
    conn.close()
    return render_template('rh_reajuste.html', colaboradores=colaboradores, historico=historico)


@rh_bp.route("/rh/reajuste/aplicar", methods=["POST"])
@login_required
@admin_required
def aplicar_reajuste():
    tipo = request.form.get('tipo')
    motivo = request.form.get('motivo', '').strip()
    data_reajuste = request.form.get('data_reajuste') or date.today().isoformat()
    selecionados = request.form.getlist('colaboradores')
    try:
        valor = float(request.form.get('valor', '0').replace(',', '.'))
    except ValueError:
        flash("Valor inválido.", "danger")
        return redirect(url_for('rh.reajuste'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if selecionados:
        fmt = ','.join(['%s'] * len(selecionados))
        cursor.execute(f"SELECT id, salario_bruto FROM colaboradores WHERE id IN ({fmt})", selecionados)
    else:
        cursor.execute("SELECT id, salario_bruto FROM colaboradores WHERE status != 'inativo'")
    colaboradores = cursor.fetchall()

    cursor2 = conn.cursor()
    qtd = 0
    for col in colaboradores:
        sal = float(col['salario_bruto'] or 0)
        novo = round(sal * (1 + valor / 100) if tipo == 'percentual' else sal + valor, 2)
        cursor2.execute("UPDATE colaboradores SET salario_bruto = %s WHERE id = %s", (novo, col['id']))
        qtd += 1

    cursor2.execute("""
        INSERT INTO rh_reajustes (data_reajuste, tipo, valor, motivo, aplicado_por, qtd_colaboradores)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data_reajuste, tipo, valor, motivo, current_user.nome, qtd))

    conn.commit()
    conn.close()
    label = f"{valor}%" if tipo == 'percentual' else f"R$ {valor:.2f}".replace('.', ',')
    flash(f"Reajuste de {label} aplicado a {qtd} colaborador(es).", "success")
    return redirect(url_for('rh.reajuste'))


# ══════════════════════════════════════════════════════════════════
# DOCUMENTOS DA EMPRESA
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/documentos")
@login_required
@admin_required
def documentos():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT *, DATEDIFF(validade, CURDATE()) AS dias_validade
        FROM rh_documentos ORDER BY categoria, nome
    """)
    docs = cursor.fetchall()
    for d in docs:
        d['validade_fmt'] = _fmt_date(d.get('validade'))
        d['criado_fmt']   = _fmt_date(d.get('criado_em'))
    conn.close()
    return render_template('rh_documentos.html', documentos=docs, categorias=CATEGORIAS_DOC)


@rh_bp.route("/rh/documentos/upload", methods=["POST"])
@login_required
@admin_required
def upload_documento():
    arquivo = request.files.get('arquivo')
    arquivo_path = None
    if arquivo and arquivo.filename and _allowed_file(arquivo.filename):
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(arquivo.filename)}"
        arquivo.save(os.path.join(_upload_path(), filename))
        arquivo_path = f"uploads/rh_docs/{filename}"

    conn = get_db_connection()
    conn.cursor().execute("""
        INSERT INTO rh_documentos (nome, categoria, arquivo_path, validade, responsavel, observacoes, criado_por)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        request.form.get('nome', '').strip(),
        request.form.get('categoria', 'outros'),
        arquivo_path,
        request.form.get('validade') or None,
        request.form.get('responsavel', '').strip() or None,
        request.form.get('observacoes', '').strip() or None,
        current_user.nome,
    ))
    conn.commit()
    conn.close()
    flash("Documento cadastrado com sucesso!", "success")
    return redirect(url_for('rh.documentos'))


@rh_bp.route("/rh/documentos/excluir/<int:id_doc>", methods=["POST"])
@login_required
@admin_required
def excluir_documento(id_doc):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT arquivo_path FROM rh_documentos WHERE id = %s", (id_doc,))
    doc = cursor.fetchone()
    if doc and doc['arquivo_path']:
        full = os.path.join(current_app.root_path, 'static', doc['arquivo_path'])
        if os.path.exists(full):
            os.remove(full)
    conn.cursor().execute("DELETE FROM rh_documentos WHERE id = %s", (id_doc,))
    conn.commit()
    conn.close()
    flash("Documento removido.", "success")
    return redirect(url_for('rh.documentos'))


# ══════════════════════════════════════════════════════════════════
# JORNADAS DE TRABALHO
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/jornadas")
@login_required
@admin_required
def jornadas():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rh_jornadas ORDER BY nome")
    lista = cursor.fetchall()
    conn.close()
    return render_template('rh_jornadas.html', jornadas=lista,
                           dias_labels=DIAS_SEMANA_LABELS)


@rh_bp.route("/rh/jornadas/add", methods=["POST"])
@login_required
@admin_required
def add_jornada():
    dias = ','.join(request.form.getlist('dias_semana'))
    conn = get_db_connection()
    conn.cursor().execute("""
        INSERT INTO rh_jornadas (nome, hora_entrada, hora_saida, intervalo_min, dias_semana)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        request.form.get('nome', '').strip(),
        request.form.get('hora_entrada'),
        request.form.get('hora_saida'),
        int(request.form.get('intervalo_min', 60)),
        dias,
    ))
    conn.commit()
    conn.close()
    flash("Jornada cadastrada!", "success")
    return redirect(url_for('rh.jornadas'))


@rh_bp.route("/rh/jornadas/editar", methods=["POST"])
@login_required
@admin_required
def editar_jornada():
    dias = ','.join(request.form.getlist('dias_semana'))
    conn = get_db_connection()
    conn.cursor().execute("""
        UPDATE rh_jornadas
        SET nome=%s, hora_entrada=%s, hora_saida=%s, intervalo_min=%s, dias_semana=%s
        WHERE id=%s
    """, (
        request.form.get('nome', '').strip(),
        request.form.get('hora_entrada'),
        request.form.get('hora_saida'),
        int(request.form.get('intervalo_min', 60)),
        dias,
        request.form.get('id_jornada'),
    ))
    conn.commit()
    conn.close()
    flash("Jornada atualizada!", "success")
    return redirect(url_for('rh.jornadas'))


@rh_bp.route("/rh/jornadas/excluir/<int:id_jornada>", methods=["POST"])
@login_required
@admin_required
def excluir_jornada(id_jornada):
    conn = get_db_connection()
    conn.cursor().execute("DELETE FROM rh_jornadas WHERE id = %s", (id_jornada,))
    conn.commit()
    conn.close()
    flash("Jornada removida.", "success")
    return redirect(url_for('rh.jornadas'))


# ══════════════════════════════════════════════════════════════════
# FÉRIAS
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/ferias")
@login_required
@admin_required
def ferias():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT f.*, col.nome AS nome_colaborador, col.funcao,
               DATEDIFF(f.data_inicio, CURDATE()) AS dias_ate_inicio
        FROM rh_ferias f
        JOIN colaboradores col ON f.id_colaborador = col.id
        ORDER BY FIELD(f.status,'em_andamento','agendado','concluido','cancelado'), f.data_inicio DESC
    """)
    lista = cursor.fetchall()
    for f in lista:
        f['inicio_fmt'] = _fmt_date(f.get('data_inicio'))
        f['fim_fmt']    = _fmt_date(f.get('data_fim'))
    cursor.execute("SELECT id, nome FROM colaboradores WHERE status != 'inativo' ORDER BY nome")
    colaboradores = cursor.fetchall()
    conn.close()
    return render_template('rh_ferias.html', ferias=lista, colaboradores=colaboradores)


@rh_bp.route("/rh/ferias/add", methods=["POST"])
@login_required
@admin_required
def add_ferias():
    data_inicio = request.form.get('data_inicio')
    data_fim = request.form.get('data_fim')
    try:
        dias = (datetime.strptime(data_fim, '%Y-%m-%d') - datetime.strptime(data_inicio, '%Y-%m-%d')).days + 1
    except Exception:
        dias = int(request.form.get('dias', 30))

    conn = get_db_connection()
    conn.cursor().execute("""
        INSERT INTO rh_ferias (id_colaborador, data_inicio, data_fim, dias, observacoes)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        request.form.get('id_colaborador'),
        data_inicio, data_fim, dias,
        request.form.get('observacoes', '').strip() or None,
    ))
    conn.commit()
    conn.close()
    flash("Férias agendadas com sucesso!", "success")
    return redirect(url_for('rh.ferias'))


@rh_bp.route("/rh/ferias/status/<int:id_ferias>/<string:novo_status>", methods=["POST"])
@login_required
@admin_required
def status_ferias(id_ferias, novo_status):
    if novo_status not in {'agendado', 'em_andamento', 'concluido', 'cancelado'}:
        flash("Status inválido.", "danger")
        return redirect(url_for('rh.ferias'))
    conn = get_db_connection()
    conn.cursor().execute("UPDATE rh_ferias SET status=%s WHERE id=%s", (novo_status, id_ferias))
    conn.commit()
    conn.close()
    flash("Status atualizado.", "success")
    return redirect(url_for('rh.ferias'))


@rh_bp.route("/rh/ferias/excluir/<int:id_ferias>", methods=["POST"])
@login_required
@admin_required
def excluir_ferias(id_ferias):
    conn = get_db_connection()
    conn.cursor().execute("DELETE FROM rh_ferias WHERE id=%s", (id_ferias,))
    conn.commit()
    conn.close()
    flash("Registro de férias removido.", "success")
    return redirect(url_for('rh.ferias'))


# ══════════════════════════════════════════════════════════════════
# FOLHA DE PONTO
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/ponto")
@login_required
@admin_required
def ponto():
    hoje = date.today()
    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
        if not 1 <= mes <= 12:
            mes = hoje.month
    except ValueError:
        mes, ano = hoje.month, hoje.year

    colab_id = request.args.get('colab_id', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome FROM colaboradores WHERE status != 'inativo' ORDER BY nome")
    colaboradores = cursor.fetchall()
    colab_sel = None
    if colab_id:
        cursor.execute("SELECT id, nome, funcao FROM colaboradores WHERE id = %s", (colab_id,))
        colab_sel = cursor.fetchone()
    conn.close()

    return render_template('rh_ponto.html',
        colaboradores=colaboradores, colab_sel=colab_sel, colab_id=colab_id,
        mes=mes, ano=ano, MESES_PT=MESES_PT)


@rh_bp.route("/rh/ponto/registrar", methods=["POST"])
@login_required
@admin_required
def registrar_ponto():
    id_colaborador = request.form.get('id_colaborador')
    mes = request.form.get('mes', date.today().month)
    ano = request.form.get('ano', date.today().year)

    conn = get_db_connection()
    cursor = conn.cursor()
    # Processa cada dia enviado no form
    for key, value in request.form.items():
        if key.startswith('tipo_'):
            dia = key.replace('tipo_', '')
            tipo = value
            hora_entrada       = request.form.get(f'entrada_{dia}')        or None
            hora_saida_almoco  = request.form.get(f'saida_almoco_{dia}')   or None
            hora_retorno_almoco= request.form.get(f'retorno_almoco_{dia}') or None
            hora_saida         = request.form.get(f'saida_{dia}')          or None
            obs = request.form.get(f'obs_{dia}', '').strip() or None
            data_str = f"{ano}-{int(mes):02d}-{int(dia):02d}"
            cursor.execute("""
                INSERT INTO rh_ponto
                    (id_colaborador, data, tipo, hora_entrada, hora_saida_almoco, hora_retorno_almoco, hora_saida, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    tipo=%s, hora_entrada=%s, hora_saida_almoco=%s,
                    hora_retorno_almoco=%s, hora_saida=%s, observacoes=%s
            """, (id_colaborador, data_str, tipo,
                  hora_entrada, hora_saida_almoco, hora_retorno_almoco, hora_saida, obs,
                  tipo, hora_entrada, hora_saida_almoco, hora_retorno_almoco, hora_saida, obs))
    conn.commit()
    conn.close()
    flash("Ponto salvo com sucesso!", "success")
    return redirect(url_for('rh.ponto', colab_id=id_colaborador, mes=mes, ano=ano))


@rh_bp.route("/rh/ponto/imprimir")
@login_required
@admin_required
def imprimir_ponto():
    """Impressão individual: formulário em branco para preenchimento manual."""
    hoje = date.today()
    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
        if not 1 <= mes <= 12:
            mes = hoje.month
    except ValueError:
        mes, ano = hoje.month, hoje.year

    colab_id = request.args.get('colab_id', '')
    if not colab_id:
        flash("Selecione um colaborador para imprimir.", "warning")
        return redirect(url_for('rh.ponto'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, funcao FROM colaboradores WHERE id = %s", (colab_id,))
    colab_sel = cursor.fetchone()
    conn.close()

    _, dias_mes = monthrange(ano, mes)
    dias = []
    for d in range(1, dias_mes + 1):
        dt_obj = date(ano, mes, d)
        dias.append({'num': d, 'weekday': dt_obj.weekday()})

    from datetime import datetime as dt
    return render_template('rh_ponto_imprimir.html',
        colab_sel=colab_sel, colab_id=colab_id,
        mes=mes, ano=ano, dias=dias, MESES_PT=MESES_PT,
        gerado_em=dt.now().strftime('%d/%m/%Y às %H:%M'))


@rh_bp.route("/rh/ponto/imprimir_geral")
@login_required
@admin_required
def imprimir_ponto_geral():
    """Impressão geral: formulários em branco para todos os colaboradores."""
    hoje = date.today()
    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
        if not 1 <= mes <= 12:
            mes = hoje.month
    except ValueError:
        mes, ano = hoje.month, hoje.year

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, funcao FROM colaboradores WHERE status != 'inativo' ORDER BY nome")
    colaboradores = cursor.fetchall()
    conn.close()

    _, dias_mes = monthrange(ano, mes)
    dias = []
    for d in range(1, dias_mes + 1):
        dt_obj = date(ano, mes, d)
        dias.append({'num': d, 'weekday': dt_obj.weekday()})

    from datetime import datetime as dt
    return render_template('rh_ponto_imprimir_geral.html',
        colaboradores=colaboradores,
        mes=mes, ano=ano, dias=dias, MESES_PT=MESES_PT,
        gerado_em=dt.now().strftime('%d/%m/%Y às %H:%M'))
