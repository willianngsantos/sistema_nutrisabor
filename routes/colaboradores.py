from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db_connection
from utils.permissions import admin_only, admin_or_gerencial
from utils.audit import log_action, format_field_diff

colaboradores_bp = Blueprint('colaboradores', __name__)

STATUS_VALIDOS = {'ativo', 'afastado', 'ferias', 'inativo'}


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────


def _parse_moeda(valor_str):
    try:
        return float(str(valor_str).replace(".", "").replace(",", ".")) if valor_str else 0.0
    except ValueError:
        return 0.0


def _salvar_unidades(cursor, id_colaborador, ids_clientes):
    """Recria os vínculos de unidades para um colaborador."""
    cursor.execute("DELETE FROM colaborador_unidades WHERE id_colaborador = %s", (id_colaborador,))
    for id_cliente in ids_clientes:
        cursor.execute(
            "INSERT INTO colaborador_unidades (id_colaborador, id_cliente) VALUES (%s, %s)",
            (id_colaborador, int(id_cliente))
        )


# ──────────────────────────────────────────────
# LISTAR
# ──────────────────────────────────────────────

@colaboradores_bp.route("/colaboradores")
@login_required
@admin_or_gerencial
def listar():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            col.id, col.nome, col.funcao, col.status,
            col.salario_bruto, col.vale_transporte,
            col.vale_refeicao, col.diversos,
            col.data_admissao,
            GROUP_CONCAT(c.nome_empresa ORDER BY c.nome_empresa SEPARATOR '||') AS unidades_nomes,
            GROUP_CONCAT(c.id            ORDER BY c.id           SEPARATOR ',')  AS unidades_ids,
            col.recebe_vt
        FROM colaboradores col
        LEFT JOIN colaborador_unidades cu ON col.id = cu.id_colaborador
        LEFT JOIN clientes c ON cu.id_cliente = c.id
        GROUP BY col.id
        ORDER BY FIELD(col.status, 'ativo', 'ferias', 'afastado', 'inativo'), col.nome
    """)
    colaboradores = cursor.fetchall()

    for c in colaboradores:
        c['unidades_lista']   = c['unidades_nomes'].split('||') if c['unidades_nomes'] else []
        c['unidades_ids_set'] = set(c['unidades_ids'].split(',')) if c['unidades_ids'] else set()
        # Formata data em Python (evita bug com DATE_FORMAT + %% no mysql-connector)
        c['data_admissao_fmt'] = c['data_admissao'].strftime('%d/%m/%Y') if c.get('data_admissao') else ''

    # Apenas clientes marcados como unidade de trabalho
    cursor.execute("""
        SELECT id, nome_empresa
        FROM clientes
        WHERE atende_local = 1
        ORDER BY nome_empresa
    """)
    clientes = cursor.fetchall()

    conn.close()
    return render_template("colaboradores.html", colaboradores=colaboradores, clientes=clientes)


# ──────────────────────────────────────────────
# ADICIONAR
# ──────────────────────────────────────────────

@colaboradores_bp.route("/add_colaborador", methods=["POST"])
@login_required
@admin_only
def add_colaborador():
    nome          = request.form.get("nome", "").strip()
    funcao        = request.form.get("funcao", "").strip() or None
    status        = request.form.get("status", "ativo")
    salario       = _parse_moeda(request.form.get("salario_bruto", ""))
    vt            = _parse_moeda(request.form.get("vale_transporte", ""))
    vr            = _parse_moeda(request.form.get("vale_refeicao", ""))
    diversos      = _parse_moeda(request.form.get("diversos", ""))
    data_admissao = request.form.get("data_admissao") or None
    ids_unidades  = request.form.getlist("unidades")
    recebe_vt     = 1 if request.form.get("recebe_vt") else 0

    if status not in STATUS_VALIDOS:
        status = 'ativo'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            INSERT INTO colaboradores
                (nome, funcao, status, salario_bruto, vale_transporte, vale_refeicao, diversos, data_admissao, recebe_vt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (nome, funcao, status, salario, vt, vr, diversos, data_admissao, recebe_vt))
        id_novo = cursor.lastrowid
        _salvar_unidades(cursor, id_novo, ids_unidades)
        conn.commit()
        log_action('create', entity_type='colaborador', entity_id=id_novo,
                   descricao=f"Criou colaborador '{nome}' ({funcao or '—'}) salário R${salario:.2f}")
        flash(f"✅ Colaborador {nome} cadastrado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar colaborador: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('colaboradores.listar'))


# ──────────────────────────────────────────────
# EDITAR
# ──────────────────────────────────────────────

@colaboradores_bp.route("/editar_colaborador", methods=["POST"])
@login_required
@admin_only
def editar_colaborador():
    id_colab      = request.form.get("id_colaborador")
    nome          = request.form.get("nome", "").strip()
    funcao        = request.form.get("funcao", "").strip() or None
    status        = request.form.get("status", "ativo")
    salario       = _parse_moeda(request.form.get("salario_bruto", ""))
    vt            = _parse_moeda(request.form.get("vale_transporte", ""))
    vr            = _parse_moeda(request.form.get("vale_refeicao", ""))
    diversos      = _parse_moeda(request.form.get("diversos", ""))
    data_admissao = request.form.get("data_admissao") or None
    ids_unidades  = request.form.getlist("unidades")
    recebe_vt     = 1 if request.form.get("recebe_vt") else 0

    if status not in STATUS_VALIDOS:
        status = 'ativo'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT nome, funcao, status, salario_bruto, vale_transporte,
                   vale_refeicao, diversos, data_admissao, recebe_vt
            FROM colaboradores WHERE id=%s
        """, (id_colab,))
        antes = cursor.fetchone() or {}
        # Normaliza decimais para comparar com floats
        for k in ('salario_bruto', 'vale_transporte', 'vale_refeicao', 'diversos'):
            if antes.get(k) is not None:
                antes[k] = float(antes[k])
        # data_admissao vem como date, depois vem como string; normaliza
        if antes.get('data_admissao') is not None:
            antes['data_admissao'] = antes['data_admissao'].strftime('%Y-%m-%d')
        depois = {
            'nome': nome, 'funcao': funcao, 'status': status,
            'salario_bruto': salario, 'vale_transporte': vt,
            'vale_refeicao': vr, 'diversos': diversos,
            'data_admissao': data_admissao, 'recebe_vt': recebe_vt,
        }
        cursor.execute("""
            UPDATE colaboradores
            SET nome=%s, funcao=%s, status=%s,
                salario_bruto=%s, vale_transporte=%s, vale_refeicao=%s, diversos=%s,
                data_admissao=%s, recebe_vt=%s
            WHERE id=%s
        """, (nome, funcao, status, salario, vt, vr, diversos, data_admissao, recebe_vt, id_colab))
        _salvar_unidades(cursor, id_colab, ids_unidades)
        conn.commit()
        log_action('update', entity_type='colaborador', entity_id=int(id_colab),
                   descricao=f"Editou colaborador '{nome}' — {format_field_diff(antes, depois)}")
        flash("✅ Colaborador atualizado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar colaborador: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('colaboradores.listar'))


# ──────────────────────────────────────────────
# MUDAR STATUS (acesso rápido via dropdown)
# ──────────────────────────────────────────────

@colaboradores_bp.route("/status_colaborador/<int:id_colab>/<string:novo_status>", methods=["POST"])
@login_required
@admin_only
def mudar_status(id_colab, novo_status):
    if novo_status not in STATUS_VALIDOS:
        flash("Status inválido.", "danger")
        return redirect(url_for('colaboradores.listar'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome, status FROM colaboradores WHERE id = %s", (id_colab,))
    colab = cursor.fetchone()

    if colab:
        status_antigo = colab['status']
        cursor2 = conn.cursor(dictionary=True)
        cursor2.execute("UPDATE colaboradores SET status = %s WHERE id = %s", (novo_status, id_colab))
        conn.commit()
        labels = {'ativo': 'Ativo', 'afastado': 'Afastado', 'ferias': 'Férias', 'inativo': 'Inativo'}
        log_action('update', entity_type='colaborador', entity_id=int(id_colab),
                   descricao=f"Colaborador '{colab['nome']}': status {status_antigo}→{novo_status}")
        flash(f"{colab['nome']} → {labels.get(novo_status, novo_status)}.", "info")

    conn.close()
    return redirect(url_for('colaboradores.listar'))


# ──────────────────────────────────────────────
# RECIBO DE VALE TRANSPORTE
# ──────────────────────────────────────────────

MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]


@colaboradores_bp.route("/recibo_vt/<int:id_colab>")
@login_required
@admin_only
def recibo_vt(id_colab):
    hoje = date.today()

    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
        if not (1 <= mes <= 12):
            mes = hoje.month
    except ValueError:
        mes, ano = hoje.month, hoje.year

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            col.id, col.nome, col.funcao, col.recebe_vt,
            col.vale_transporte, col.vale_refeicao, col.diversos,
            GROUP_CONCAT(c.nome_empresa ORDER BY c.nome_empresa SEPARATOR ', ') AS unidades
        FROM colaboradores col
        LEFT JOIN colaborador_unidades cu ON col.id = cu.id_colaborador
        LEFT JOIN clientes c ON cu.id_cliente = c.id
        WHERE col.id = %s
        GROUP BY col.id
    """, (id_colab,))
    colab = cursor.fetchone()

    if not colab:
        conn.close()
        flash("Colaborador não encontrado.", "danger")
        return redirect(url_for('colaboradores.listar'))

    if not colab.get('recebe_vt'):
        conn.close()
        flash(f"{colab['nome']} não está configurado para receber Vale Transporte.", "warning")
        return redirect(url_for('colaboradores.listar'))

    cursor2 = conn.cursor(dictionary=True)
    cursor2.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor2.fetchone()
    conn.close()

    periodo = f"{MESES_PT[mes - 1]}/{ano}"

    return render_template(
        "recibo_vt.html",
        colab=colab,
        empresa=empresa,
        mes=mes,
        ano=ano,
        periodo=periodo,
        MESES=MESES_PT,
    )


# ──────────────────────────────────────────────
# LOTE DE RECIBOS VT (todos ou por unidade)
# ──────────────────────────────────────────────

@colaboradores_bp.route("/recibos_vt/lote")
@login_required
@admin_only
def recibos_vt_lote():
    hoje = date.today()

    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
        if not (1 <= mes <= 12):
            mes = hoje.month
    except ValueError:
        mes, ano = hoje.month, hoje.year

    unidade_id = request.args.get('unidade_id', '')  # '' = todas

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Unidades disponíveis para o filtro
    cursor.execute("""
        SELECT id, nome_empresa
        FROM clientes
        WHERE atende_local = 1
        ORDER BY nome_empresa
    """)
    unidades = cursor.fetchall()

    # Monta a query base de colaboradores ativos/afastados/férias
    # "inativo" fica de fora — não faz sentido gerar recibo pra quem saiu
    if unidade_id:
        cursor.execute("""
            SELECT
                col.id, col.nome, col.funcao, col.status,
                col.vale_transporte, col.vale_refeicao, col.diversos,
                cl_filtro.nome_empresa AS grupo_unidade,
                GROUP_CONCAT(c.nome_empresa ORDER BY c.nome_empresa SEPARATOR ', ') AS unidades
            FROM colaboradores col
            JOIN colaborador_unidades cu_filtro
                ON col.id = cu_filtro.id_colaborador AND cu_filtro.id_cliente = %s
            JOIN clientes cl_filtro
                ON cl_filtro.id = %s
            LEFT JOIN colaborador_unidades cu ON col.id = cu.id_colaborador
            LEFT JOIN clientes c ON cu.id_cliente = c.id
            WHERE col.status != 'inativo' AND col.recebe_vt = 1
            GROUP BY col.id, cl_filtro.nome_empresa
            ORDER BY col.nome
        """, (unidade_id, unidade_id))
    else:
        # Todos — agrupa pelo nome da primeira unidade (ordem alfabética)
        # para exibir seções na tela; cada colaborador aparece uma única vez
        cursor.execute("""
            SELECT
                col.id, col.nome, col.funcao, col.status,
                col.vale_transporte, col.vale_refeicao, col.diversos,
                MIN(c.nome_empresa) AS grupo_unidade,
                GROUP_CONCAT(c.nome_empresa ORDER BY c.nome_empresa SEPARATOR ', ') AS unidades
            FROM colaboradores col
            LEFT JOIN colaborador_unidades cu ON col.id = cu.id_colaborador
            LEFT JOIN clientes c ON cu.id_cliente = c.id
            WHERE col.status != 'inativo' AND col.recebe_vt = 1
            GROUP BY col.id
            ORDER BY MIN(c.nome_empresa), col.nome
        """)

    colaboradores_raw = cursor.fetchall()

    # Agrupa em seções por unidade para o template
    grupos = []
    grupo_atual = None
    for colab in colaboradores_raw:
        nome_grupo = colab.get('grupo_unidade') or 'Sem Unidade'
        if grupo_atual is None or grupo_atual['unidade_nome'] != nome_grupo:
            grupo_atual = {'unidade_nome': nome_grupo, 'colaboradores': []}
            grupos.append(grupo_atual)
        grupo_atual['colaboradores'].append(colab)

    cursor2 = conn.cursor(dictionary=True)
    cursor2.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor2.fetchone()
    conn.close()

    periodo = f"{MESES_PT[mes - 1]}/{ano}"
    total_recibos = len(colaboradores_raw)

    return render_template(
        "recibos_vt_lote.html",
        grupos=grupos,
        empresa=empresa,
        mes=mes,
        ano=ano,
        periodo=periodo,
        MESES=MESES_PT,
        unidades=unidades,
        unidade_id_sel=unidade_id,
        total_recibos=total_recibos,
    )


# ──────────────────────────────────────────────
# EXCLUIR
# ──────────────────────────────────────────────

@colaboradores_bp.route("/excluir_colaborador/<int:id_colab>", methods=["POST"])
@login_required
@admin_only
def excluir_colaborador(id_colab):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome, funcao FROM colaboradores WHERE id=%s", (id_colab,))
    colab = cursor.fetchone() or {}
    nome_antigo = colab.get('nome') or f'#{id_colab}'
    try:
        cursor.execute("DELETE FROM colaboradores WHERE id = %s", (id_colab,))
        conn.commit()
        log_action('delete', entity_type='colaborador', entity_id=int(id_colab),
                   descricao=f"Excluiu colaborador '{nome_antigo}' ({colab.get('funcao') or '—'})")
        flash("Colaborador removido.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover colaborador: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('colaboradores.listar'))
