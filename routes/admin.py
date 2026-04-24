"""
Área administrativa: agrupa funcionalidades restritas ao perfil Admin.

Hospeda a página de Log de Atividade (audit trail). As telas de Equipe
(auth.listar_usuarios) e Minha Empresa (auth.configuracao_empresa)
continuam em auth.py; apenas o navbar aponta para elas a partir do
menu Admin.
"""
from flask import Blueprint, render_template, request
from flask_login import login_required
from database import get_db_connection
from utils.permissions import admin_only

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


ACTION_TYPES = ['view', 'login', 'login_failed', 'logout',
                'create', 'update', 'delete']


@admin_bp.route('/log')
@login_required
@admin_only
def log_atividade():
    """Listagem paginada do audit_log com filtros por usuário, período e ação."""
    # Filtros
    f_user = request.args.get('user_id', '').strip()
    f_acao = request.args.get('action_type', '').strip()
    f_inicio = request.args.get('data_inicio', '').strip()
    f_fim = request.args.get('data_fim', '').strip()
    f_busca = request.args.get('busca', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Monta WHERE dinâmico
    where_sql = ""
    params = []

    if f_user:
        where_sql += " AND user_id = %s"
        params.append(f_user)
    if f_acao and f_acao in ACTION_TYPES:
        where_sql += " AND action_type = %s"
        params.append(f_acao)
    if f_inicio:
        where_sql += " AND DATE(timestamp) >= %s"
        params.append(f_inicio)
    if f_fim:
        where_sql += " AND DATE(timestamp) <= %s"
        params.append(f_fim)
    if f_busca:
        where_sql += " AND (descricao LIKE %s OR entity_type LIKE %s)"
        params.extend([f"%{f_busca}%", f"%{f_busca}%"])

    # Paginação
    per_page = 100
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    cursor.execute(f"SELECT COUNT(*) AS total FROM audit_log WHERE 1=1 {where_sql}",
                   tuple(params))
    total_count = cursor.fetchone()['total']
    total_pages = max(1, -(-total_count // per_page))  # ceil

    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    cursor.execute(f"""
        SELECT id, user_id, user_nome, tipo_usuario,
               DATE_FORMAT(timestamp, '%d/%m/%Y %H:%i:%s') AS timestamp_fmt,
               action_type, entity_type, entity_id, descricao,
               ip_address, user_agent
        FROM audit_log
        WHERE 1=1 {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT %s OFFSET %s
    """, tuple(params) + (per_page, offset))
    registros = cursor.fetchall()

    # Lista de usuários para o filtro (distinct do próprio audit_log —
    # pega inclusive usuários já deletados que aparecem no log)
    cursor.execute("""
        SELECT user_id, user_nome
        FROM audit_log
        WHERE user_id IS NOT NULL AND user_nome IS NOT NULL
        GROUP BY user_id, user_nome
        ORDER BY user_nome
    """)
    usuarios_log = cursor.fetchall()

    conn.close()

    return render_template('admin_log.html',
                           registros=registros,
                           usuarios_log=usuarios_log,
                           action_types=ACTION_TYPES,
                           f_user=f_user, f_acao=f_acao,
                           f_inicio=f_inicio, f_fim=f_fim, f_busca=f_busca,
                           page=page, total_pages=total_pages,
                           total_count=total_count, per_page=per_page)
