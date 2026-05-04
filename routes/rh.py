import os
from datetime import date, datetime
from calendar import monthrange
from werkzeug.utils import secure_filename
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app)
from flask_login import login_required, current_user
from database import get_db_connection
from utils.permissions import admin_only, rh_access
from utils.audit import log_action, format_field_diff

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

def _data_extenso_pt(d=None):
    """Retorna data no formato 'TAQUARITINGA, 30 DE SETEMBRO DE 2025.'
    usado em documentos formais. Se d for None, usa hoje."""
    if d is None:
        d = date.today()
    return f"TAQUARITINGA, {d.day:02d} DE {MESES_PT[d.month - 1].upper()} DE {d.year}."
DIAS_SEMANA_LABELS = {
    'seg': 'Seg', 'ter': 'Ter', 'qua': 'Qua',
    'qui': 'Qui', 'sex': 'Sex', 'sab': 'Sáb', 'dom': 'Dom'
}
DIAS_ORDEM = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom']


# ─── HELPERS JORNADAS ─────────────────────────────────────────────
def _fmt_hhmm(t):
    """Converte timedelta / time / None em string 'HH:MM'."""
    if t is None:
        return ''
    if hasattr(t, 'total_seconds'):        # timedelta (é como MySQL TIME chega)
        total_s = int(t.total_seconds())
    else:                                   # datetime.time
        total_s = t.hour * 3600 + t.minute * 60
    h = total_s // 3600
    m = (total_s % 3600) // 60
    return f"{h:02d}:{m:02d}"


def _carga_min(entrada_hhmm, saida_hhmm, intervalo_min):
    """Minutos úteis entre entrada e saída descontando intervalo."""
    try:
        eh, em = [int(x) for x in entrada_hhmm.split(':')]
        sh, sm = [int(x) for x in saida_hhmm.split(':')]
        return max(0, (sh * 60 + sm) - (eh * 60 + em) - (intervalo_min or 0))
    except (ValueError, AttributeError):
        return 0


def _fmt_duracao(total_min):
    """Formata minutos como '44h 30min' ou '40h'."""
    h = total_min // 60
    m = total_min % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m:02d}min"


def _agrupa_dias(dias_ordenados):
    """Agrupa dias CONSECUTIVOS com mesmo horário/intervalo.
    Ex: [seg,ter,qua,qui,sex com 6:30-14:30] + [sáb com 6:30-13:30]
        → [{label:'Seg-Sex',...}, {label:'Sáb',...}]
    """
    if not dias_ordenados:
        return []
    ordem = {d: i for i, d in enumerate(DIAS_ORDEM)}
    grupos = []
    atual = None
    for d in dias_ordenados:
        key = (d['entrada'], d['saida'], d['intervalo'])
        consecutive = (atual and atual['_key'] == key
                       and ordem.get(d['dia_semana'], -1) == ordem.get(atual['_dias'][-1], -2) + 1)
        if consecutive:
            atual['_dias'].append(d['dia_semana'])
        else:
            atual = {
                '_key': key,
                '_dias': [d['dia_semana']],
                'entrada': d['entrada'], 'saida': d['saida'],
                'intervalo': d['intervalo'], 'carga_min': d['carga_min'],
            }
            grupos.append(atual)
    for g in grupos:
        if len(g['_dias']) == 1:
            g['label'] = DIAS_SEMANA_LABELS[g['_dias'][0]]
        else:
            g['label'] = f"{DIAS_SEMANA_LABELS[g['_dias'][0]]}-{DIAS_SEMANA_LABELS[g['_dias'][-1]]}"
    return grupos


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
@rh_access
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
@rh_access
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
@rh_access
def add_exame():
    id_colab    = request.form.get('id_colaborador')
    tipo        = request.form.get('tipo')
    data_real   = request.form.get('data_realizado') or None
    data_venc   = request.form.get('data_vencimento') or None
    resultado   = request.form.get('resultado', 'apto')
    clinica     = request.form.get('clinica', '').strip() or None
    obs         = request.form.get('observacoes', '').strip() or None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if id_colab == 'todos':
        # Insere o exame para TODOS os colaboradores ativos
        cursor.execute("SELECT id FROM colaboradores WHERE status != 'inativo'")
        ids = [row['id'] for row in cursor.fetchall()]
        for cid in ids:
            cursor.execute("""
                INSERT INTO rh_exames
                    (id_colaborador, tipo, data_realizado, data_vencimento, resultado, clinica, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (cid, tipo, data_real, data_venc, resultado, clinica, obs))
        conn.commit()
        conn.close()
        log_action('create', entity_type='rh_exame',
                   descricao=f"Criou exame '{tipo}' ({resultado}) para {len(ids)} colaborador(es)")
        flash(f"Exame registrado para {len(ids)} colaborador(es)!", "success")
    else:
        cursor.execute("""
            INSERT INTO rh_exames
                (id_colaborador, tipo, data_realizado, data_vencimento, resultado, clinica, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_colab, tipo, data_real, data_venc, resultado, clinica, obs))
        novo_id = cursor.lastrowid
        cursor.execute("SELECT nome FROM colaboradores WHERE id=%s", (id_colab,))
        colab = cursor.fetchone()
        conn.commit()
        conn.close()
        log_action('create', entity_type='rh_exame', entity_id=novo_id,
                   descricao=f"Criou exame '{tipo}' ({resultado}) para colaborador '{colab['nome'] if colab else id_colab}'")
        flash("Exame registrado com sucesso!", "success")

    return redirect(url_for('rh.exames'))


@rh_bp.route("/rh/exames/editar", methods=["POST"])
@login_required
@rh_access
def editar_exame():
    id_exame = request.form.get('id_exame')
    depois = {
        'tipo': request.form.get('tipo'),
        'data_realizado': request.form.get('data_realizado') or None,
        'data_vencimento': request.form.get('data_vencimento') or None,
        'resultado': request.form.get('resultado', 'apto'),
        'clinica': request.form.get('clinica', '').strip() or None,
        'observacoes': request.form.get('observacoes', '').strip() or None,
    }
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT tipo, data_realizado, data_vencimento, resultado, clinica, observacoes
        FROM rh_exames WHERE id=%s
    """, (id_exame,))
    antes = cursor.fetchone() or {}
    for k in ('data_realizado', 'data_vencimento'):
        if antes.get(k) is not None:
            antes[k] = antes[k].strftime('%Y-%m-%d')
    cursor.execute("""
        UPDATE rh_exames SET tipo=%s, data_realizado=%s, data_vencimento=%s,
               resultado=%s, clinica=%s, observacoes=%s WHERE id=%s
    """, (depois['tipo'], depois['data_realizado'], depois['data_vencimento'],
          depois['resultado'], depois['clinica'], depois['observacoes'], id_exame))
    conn.commit()
    conn.close()
    log_action('update', entity_type='rh_exame', entity_id=int(id_exame),
               descricao=f"Editou exame #{id_exame} — {format_field_diff(antes, depois)}")
    flash("Exame atualizado!", "success")
    return redirect(url_for('rh.exames'))


@rh_bp.route("/rh/exames/excluir/<int:id_exame>", methods=["POST"])
@login_required
@rh_access
def excluir_exame(id_exame):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT e.tipo, c.nome AS colaborador
        FROM rh_exames e LEFT JOIN colaboradores c ON c.id = e.id_colaborador
        WHERE e.id = %s
    """, (id_exame,))
    info = cursor.fetchone() or {}
    cursor.execute("DELETE FROM rh_exames WHERE id = %s", (id_exame,))
    conn.commit()
    conn.close()
    log_action('delete', entity_type='rh_exame', entity_id=int(id_exame),
               descricao=f"Excluiu exame '{info.get('tipo') or '—'}' de '{info.get('colaborador') or '—'}'")
    flash("Exame removido.", "success")
    return redirect(url_for('rh.exames'))


# ══════════════════════════════════════════════════════════════════
# REAJUSTE SALARIAL
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/reajuste")
@login_required
@admin_only
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
@admin_only
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

    cursor2 = conn.cursor(dictionary=True)
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
    id_reajuste = cursor2.lastrowid

    conn.commit()
    conn.close()
    label = f"{valor}%" if tipo == 'percentual' else f"R$ {valor:.2f}".replace('.', ',')
    log_action('create', entity_type='rh_reajuste', entity_id=id_reajuste,
               descricao=f"Aplicou reajuste {tipo} de {label} em {qtd} colaborador(es). Motivo: {motivo or '—'}")
    flash(f"Reajuste de {label} aplicado a {qtd} colaborador(es).", "success")
    return redirect(url_for('rh.reajuste'))


# ══════════════════════════════════════════════════════════════════
# DOCUMENTOS DA EMPRESA
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/documentos")
@login_required
@rh_access
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
@rh_access
def upload_documento():
    arquivo = request.files.get('arquivo')
    arquivo_path = None
    if arquivo and arquivo.filename and _allowed_file(arquivo.filename):
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(arquivo.filename)}"
        arquivo.save(os.path.join(_upload_path(), filename))
        arquivo_path = f"uploads/rh_docs/{filename}"

    nome_doc = request.form.get('nome', '').strip()
    categoria = request.form.get('categoria', 'outros')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        INSERT INTO rh_documentos (nome, categoria, arquivo_path, validade, responsavel, observacoes, criado_por)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        nome_doc,
        categoria,
        arquivo_path,
        request.form.get('validade') or None,
        request.form.get('responsavel', '').strip() or None,
        request.form.get('observacoes', '').strip() or None,
        current_user.nome,
    ))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_action('create', entity_type='rh_documento', entity_id=novo_id,
               descricao=f"Cadastrou documento '{nome_doc}' (cat: {categoria}, arq: {arquivo_path or 'nenhum'})")
    flash("Documento cadastrado com sucesso!", "success")
    return redirect(url_for('rh.documentos'))


@rh_bp.route("/rh/documentos/excluir/<int:id_doc>", methods=["POST"])
@login_required
@rh_access
def excluir_documento(id_doc):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome, arquivo_path FROM rh_documentos WHERE id = %s", (id_doc,))
    doc = cursor.fetchone() or {}
    nome_antigo = doc.get('nome') or f'#{id_doc}'
    if doc.get('arquivo_path'):
        full = os.path.join(current_app.root_path, 'static', doc['arquivo_path'])
        if os.path.exists(full):
            os.remove(full)
    cursor.execute("DELETE FROM rh_documentos WHERE id = %s", (id_doc,))
    conn.commit()
    conn.close()
    log_action('delete', entity_type='rh_documento', entity_id=int(id_doc),
               descricao=f"Excluiu documento '{nome_antigo}'")
    flash("Documento removido.", "success")
    return redirect(url_for('rh.documentos'))


# ══════════════════════════════════════════════════════════════════
# JORNADAS DE TRABALHO
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/jornadas")
@login_required
@rh_access
def jornadas():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Puxa jornadas + seus dias em uma query só (LEFT JOIN para incluir
    # jornadas sem dias cadastrados)
    cursor.execute("""
        SELECT j.id, j.nome,
               d.dia_semana, d.hora_entrada, d.hora_saida, d.intervalo_min
        FROM rh_jornadas j
        LEFT JOIN rh_jornada_dias d ON d.id_jornada = j.id
        ORDER BY j.nome,
                 FIELD(d.dia_semana, 'seg','ter','qua','qui','sex','sab','dom')
    """)
    rows = cursor.fetchall()
    conn.close()

    # Agrupa linhas em estrutura por jornada
    jmap = {}
    for r in rows:
        jid = r['id']
        if jid not in jmap:
            jmap[jid] = {'id': jid, 'nome': r['nome'], 'dias': []}
        if r['dia_semana']:
            ent = _fmt_hhmm(r['hora_entrada'])
            sai = _fmt_hhmm(r['hora_saida'])
            iv = r['intervalo_min'] or 0
            jmap[jid]['dias'].append({
                'dia_semana': r['dia_semana'],
                'entrada': ent, 'saida': sai, 'intervalo': iv,
                'carga_min': _carga_min(ent, sai, iv),
            })

    lista = sorted(jmap.values(), key=lambda x: x['nome'].lower())
    for j in lista:
        j['grupos'] = _agrupa_dias(j['dias'])
        j['total_min'] = sum(d['carga_min'] for d in j['dias'])
        j['total_fmt'] = _fmt_duracao(j['total_min'])
        # Mapa por dia para popular o modal de edição
        j['dias_por_nome'] = {d['dia_semana']: d for d in j['dias']}

    return render_template('rh_jornadas.html', jornadas=lista,
                           dias_ordem=DIAS_ORDEM,
                           dias_labels=DIAS_SEMANA_LABELS)


def _coletar_dias_do_form():
    """Extrai do request.form os dias ativos com seus horários.
    Retorna lista de tuplas (dia, entrada, saida, intervalo). Ignora dias
    inválidos ou sem entrada/saida.
    """
    coletados = []
    for dia in DIAS_ORDEM:
        if not request.form.get(f'ativo_{dia}'):
            continue
        entrada = (request.form.get(f'entrada_{dia}') or '').strip()
        saida = (request.form.get(f'saida_{dia}') or '').strip()
        if not entrada or not saida:
            continue
        try:
            intervalo = int(request.form.get(f'intervalo_{dia}', 0) or 0)
        except ValueError:
            intervalo = 0
        coletados.append((dia, entrada, saida, intervalo))
    return coletados


@rh_bp.route("/rh/jornadas/salvar", methods=["POST"])
@login_required
@rh_access
def salvar_jornada():
    """Endpoint único de create/update. Se id_jornada vier vazio → cria nova;
    se vier preenchido → atualiza existente. Evita precisar trocar o `action`
    do form via JS (o que causa quirks com CSRF em certos browsers)."""
    nome = request.form.get('nome', '').strip()
    id_jornada = (request.form.get('id_jornada') or '').strip()
    dias = _coletar_dias_do_form()
    if not nome or not dias:
        flash("Informe o nome e pelo menos um dia com entrada/saída.", "warning")
        return redirect(url_for('rh.jornadas'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    total = sum(_carga_min(ent, sai, iv) for _, ent, sai, iv in dias)

    if id_jornada:
        cursor.execute("SELECT nome FROM rh_jornadas WHERE id=%s", (id_jornada,))
        existente = cursor.fetchone()
        if not existente:
            conn.close()
            flash("Jornada não encontrada.", "danger")
            return redirect(url_for('rh.jornadas'))
        nome_antigo = existente['nome']
        cursor.execute("UPDATE rh_jornadas SET nome=%s WHERE id=%s", (nome, id_jornada))
        cursor.execute("DELETE FROM rh_jornada_dias WHERE id_jornada=%s", (id_jornada,))
        for d, ent, sai, iv in dias:
            cursor.execute("""
                INSERT INTO rh_jornada_dias (id_jornada, dia_semana, hora_entrada, hora_saida, intervalo_min)
                VALUES (%s, %s, %s, %s, %s)
            """, (id_jornada, d, ent, sai, iv))
        conn.commit()
        conn.close()
        descr = f"Editou jornada '{nome}' ({len(dias)} dia(s), total semanal {_fmt_duracao(total)})"
        if nome_antigo != nome:
            descr += f" — nome: '{nome_antigo}'→'{nome}'"
        log_action('update', entity_type='rh_jornada', entity_id=int(id_jornada), descricao=descr)
        flash("Jornada atualizada!", "success")
    else:
        # Passamos valores dummy em hora_entrada/hora_saida porque as colunas
        # legacy em rh_jornadas são NOT NULL sem default — os dados reais vão
        # todos para rh_jornada_dias. As legacy podem ser dropadas em migração
        # futura sem afetar o código novo.
        cursor.execute("""
            INSERT INTO rh_jornadas (nome, hora_entrada, hora_saida)
            VALUES (%s, '00:00:00', '00:00:00')
        """, (nome,))
        novo_id = cursor.lastrowid
        for d, ent, sai, iv in dias:
            cursor.execute("""
                INSERT INTO rh_jornada_dias (id_jornada, dia_semana, hora_entrada, hora_saida, intervalo_min)
                VALUES (%s, %s, %s, %s, %s)
            """, (novo_id, d, ent, sai, iv))
        conn.commit()
        conn.close()
        log_action('create', entity_type='rh_jornada', entity_id=novo_id,
                   descricao=f"Criou jornada '{nome}' ({len(dias)} dia(s), total semanal {_fmt_duracao(total)})")
        flash("Jornada cadastrada!", "success")

    return redirect(url_for('rh.jornadas'))


@rh_bp.route("/rh/jornadas/excluir/<int:id_jornada>", methods=["POST"])
@login_required
@rh_access
def excluir_jornada(id_jornada):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome FROM rh_jornadas WHERE id = %s", (id_jornada,))
    j = cursor.fetchone() or {}
    nome_antigo = j.get('nome') or f'#{id_jornada}'
    cursor.execute("DELETE FROM rh_jornadas WHERE id = %s", (id_jornada,))
    conn.commit()
    conn.close()
    log_action('delete', entity_type='rh_jornada', entity_id=int(id_jornada),
               descricao=f"Excluiu jornada '{nome_antigo}'")
    flash("Jornada removida.", "success")
    return redirect(url_for('rh.jornadas'))


# ══════════════════════════════════════════════════════════════════
# FÉRIAS
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/ferias")
@login_required
@rh_access
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
@rh_access
def add_ferias():
    data_inicio = request.form.get('data_inicio')
    data_fim = request.form.get('data_fim')
    id_colaborador = request.form.get('id_colaborador')
    try:
        dias = (datetime.strptime(data_fim, '%Y-%m-%d') - datetime.strptime(data_inicio, '%Y-%m-%d')).days + 1
    except Exception:
        dias = int(request.form.get('dias', 30))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        INSERT INTO rh_ferias (id_colaborador, data_inicio, data_fim, dias, observacoes)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        id_colaborador,
        data_inicio, data_fim, dias,
        request.form.get('observacoes', '').strip() or None,
    ))
    novo_id = cursor.lastrowid
    cursor.execute("SELECT nome FROM colaboradores WHERE id=%s", (id_colaborador,))
    colab = cursor.fetchone()
    conn.commit()
    conn.close()
    log_action('create', entity_type='rh_ferias', entity_id=novo_id,
               descricao=f"Agendou férias para '{colab['nome'] if colab else id_colaborador}' ({data_inicio} a {data_fim}, {dias} dias)")
    flash("Férias agendadas com sucesso!", "success")
    return redirect(url_for('rh.ferias'))


@rh_bp.route("/rh/ferias/status/<int:id_ferias>/<string:novo_status>", methods=["POST"])
@login_required
@rh_access
def status_ferias(id_ferias, novo_status):
    if novo_status not in {'agendado', 'em_andamento', 'concluido', 'cancelado'}:
        flash("Status inválido.", "danger")
        return redirect(url_for('rh.ferias'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT f.status, c.nome FROM rh_ferias f
        LEFT JOIN colaboradores c ON c.id = f.id_colaborador
        WHERE f.id=%s
    """, (id_ferias,))
    info = cursor.fetchone() or {}
    cursor.execute("UPDATE rh_ferias SET status=%s WHERE id=%s", (novo_status, id_ferias))
    conn.commit()
    conn.close()
    log_action('update', entity_type='rh_ferias', entity_id=int(id_ferias),
               descricao=f"Férias de '{info.get('nome') or '—'}': status {info.get('status') or '—'}→{novo_status}")
    flash("Status atualizado.", "success")
    return redirect(url_for('rh.ferias'))


@rh_bp.route("/rh/ferias/excluir/<int:id_ferias>", methods=["POST"])
@login_required
@rh_access
def excluir_ferias(id_ferias):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT f.data_inicio, f.data_fim, c.nome FROM rh_ferias f
        LEFT JOIN colaboradores c ON c.id = f.id_colaborador
        WHERE f.id=%s
    """, (id_ferias,))
    info = cursor.fetchone() or {}
    cursor.execute("DELETE FROM rh_ferias WHERE id=%s", (id_ferias,))
    conn.commit()
    conn.close()
    log_action('delete', entity_type='rh_ferias', entity_id=int(id_ferias),
               descricao=f"Excluiu férias de '{info.get('nome') or '—'}' "
                         f"({info.get('data_inicio')} a {info.get('data_fim')})")
    flash("Registro de férias removido.", "success")
    return redirect(url_for('rh.ferias'))


# ══════════════════════════════════════════════════════════════════
# FOLHA DE PONTO
# ══════════════════════════════════════════════════════════════════
@rh_bp.route("/rh/ponto")
@login_required
@rh_access
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
@rh_access
def registrar_ponto():
    id_colaborador = request.form.get('id_colaborador')
    mes = request.form.get('mes', date.today().month)
    ano = request.form.get('ano', date.today().year)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    qtd_dias = 0
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
            qtd_dias += 1

    cursor.execute("SELECT nome FROM colaboradores WHERE id=%s", (id_colaborador,))
    colab = cursor.fetchone()
    conn.commit()
    conn.close()
    log_action('update', entity_type='rh_ponto', entity_id=int(id_colaborador) if id_colaborador else None,
               descricao=f"Registrou ponto de '{colab['nome'] if colab else id_colaborador}' em {mes}/{ano}: {qtd_dias} dia(s)")
    flash("Ponto salvo com sucesso!", "success")
    return redirect(url_for('rh.ponto', colab_id=id_colaborador, mes=mes, ano=ano))


@rh_bp.route("/rh/ponto/imprimir")
@login_required
@rh_access
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
@rh_access
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


# ══════════════════════════════════════════════════════════════════
# ADMISSÃO — geração de documentos relacionados ao processo de
# admissão de novos colaboradores. Restrito a admin.
# ══════════════════════════════════════════════════════════════════

def _buscar_colaborador_completo(cursor, id_colab):
    """Carrega todos os dados de um colaborador. Retorna dict ou None."""
    cursor.execute("""
        SELECT id, nome, funcao, status, rg, cpf, crn3,
               endereco_cep, endereco_logradouro, endereco_numero,
               endereco_complemento, endereco_bairro,
               endereco_cidade, endereco_uf
        FROM colaboradores WHERE id = %s
    """, (id_colab,))
    return cursor.fetchone()


def _validar_dados_conta_salario(colab, nutri):
    """Retorna lista de erros (vazia se tudo OK)."""
    erros = []
    if not colab:
        return ["Colaborador não encontrado."]
    if not nutri:
        return ["Nutricionista não encontrada."]
    if not colab.get('rg'):
        erros.append(f"Cadastre o RG de {colab['nome']}.")
    if not colab.get('cpf'):
        erros.append(f"Cadastre o CPF de {colab['nome']}.")
    if not (colab.get('endereco_logradouro') and colab.get('endereco_numero')
            and colab.get('endereco_bairro') and colab.get('endereco_cep')
            and colab.get('endereco_cidade') and colab.get('endereco_uf')):
        erros.append(f"Endereço residencial de {colab['nome']} está incompleto (logradouro, número, bairro, CEP, cidade e UF).")
    if nutri.get('funcao') != 'Nutricionista':
        erros.append(f"{nutri['nome']} não está cadastrada com função 'Nutricionista'.")
    if not nutri.get('crn3'):
        erros.append(f"Cadastre o CRN3 de {nutri['nome']}.")
    return erros


@rh_bp.route("/rh/admissao")
@login_required
@admin_only
def admissao_hub():
    """Hub com cards para os documentos de admissão disponíveis."""
    return render_template('rh_admissao.html')


@rh_bp.route("/rh/admissao/conta-salario")
@login_required
@admin_only
def admissao_conta_salario_seletor():
    """Tela com 2 dropdowns (colaborador + nutricionista). O dropdown de
    colaborador mostra apenas quem AINDA NÃO tem agência+conta cadastradas
    — quem já abriu a conta não precisa solicitar de novo."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, nome, funcao FROM colaboradores
        WHERE status != 'inativo'
          AND (agencia IS NULL OR agencia = '' OR conta IS NULL OR conta = '')
        ORDER BY nome
    """)
    colaboradores = cursor.fetchall()
    cursor.execute("""
        SELECT id, nome, crn3 FROM colaboradores
        WHERE status = 'ativo' AND funcao = 'Nutricionista' AND crn3 IS NOT NULL AND crn3 != ''
        ORDER BY nome
    """)
    nutricionistas = cursor.fetchall()
    conn.close()
    return render_template('rh_admissao_conta_salario.html',
                           colaboradores=colaboradores,
                           nutricionistas=nutricionistas)


@rh_bp.route("/rh/admissao/conta-salario/gerar")
@login_required
@admin_only
def admissao_conta_salario_gerar():
    """Renderiza o documento de Solicitação de Conta Salário pronto pra
    impressão. Recebe colab_id e nutri_id por query string."""
    colab_id = request.args.get('colab_id', type=int)
    nutri_id = request.args.get('nutri_id', type=int)
    if not colab_id or not nutri_id:
        flash("Selecione um colaborador e uma nutricionista responsável.", "warning")
        return redirect(url_for('rh.admissao_conta_salario_seletor'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    colab = _buscar_colaborador_completo(cursor, colab_id)
    nutri = _buscar_colaborador_completo(cursor, nutri_id)
    conn.close()

    erros = _validar_dados_conta_salario(colab, nutri)
    if erros:
        # Renderiza tela de erro em vez de redirect, pois o form usa
        # target="_blank" — um redirect deixaria a nova aba só com o
        # seletor "vazio" e o flash invisível.
        return render_template('doc_erro_dados.html',
                               titulo='Solicitação de Conta Salário',
                               erros=erros,
                               colab=colab, nutri=nutri,
                               voltar_url=url_for('rh.admissao_conta_salario_seletor'))

    return render_template('doc_conta_salario.html',
                           colab=colab, nutri=nutri,
                           data_extenso=_data_extenso_pt())


@rh_bp.route("/rh/admissao/documentos")
@login_required
@admin_only
def admissao_documentos_seletor():
    """Tela com seletor opcional de colaborador para personalizar a lista
    de documentos exigidos na admissão."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, nome, funcao FROM colaboradores
        WHERE status != 'inativo'
        ORDER BY nome
    """)
    colaboradores = cursor.fetchall()
    conn.close()
    return render_template('rh_admissao_documentos.html',
                           colaboradores=colaboradores)


@rh_bp.route("/rh/admissao/documentos/gerar")
@login_required
@admin_only
def admissao_documentos_gerar():
    """Renderiza a Relação de Documentos para Admissão. Se colab_id for
    fornecido, personaliza com o nome do colaborador; senão fica genérica."""
    colab_id = request.args.get('colab_id', type=int)
    colab = None
    if colab_id:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, nome, funcao FROM colaboradores WHERE id = %s", (colab_id,))
        colab = cursor.fetchone()
        conn.close()
    return render_template('doc_lista_admissao.html', colab=colab)
