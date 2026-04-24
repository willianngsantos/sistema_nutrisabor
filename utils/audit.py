"""
Registro de atividade (audit log).

Função `log_action` escreve uma linha na tabela audit_log. É chamada por
dois caminhos:

1. Automaticamente por `@app.before_request` em cada GET autenticado
   (registra visualizações de página com action_type='view').
2. Manualmente pelas rotas de mutação ao final de um create/update/delete
   bem-sucedido, com descrição humana do que aconteceu.

Falhas de log não derrubam a operação original — capturamos e silenciamos
qualquer exceção para evitar quebrar fluxos críticos por conta do log.
"""
from flask import request
from flask_login import current_user
from database import get_db_connection


def _client_ip():
    """Retorna o IP do cliente, respeitando cabeçalho X-Forwarded-For caso
    a app esteja atrás de proxy/nginx."""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        # Pega o primeiro IP da cadeia (o mais próximo do cliente real)
        return xff.split(',')[0].strip()
    return request.remote_addr or ''


def log_action(action_type, entity_type=None, entity_id=None, descricao=None):
    """Registra uma ação no audit_log.

    Args:
        action_type: 'view', 'login', 'login_failed', 'logout',
                     'create', 'update', 'delete'
        entity_type: string do tipo de entidade (ex: 'cliente', 'fatura').
                     Para page views, costuma ser 'page' com descricao=url.
        entity_id: id numérico da entidade afetada, se aplicável.
        descricao: texto humano descrevendo a ação.
    """
    try:
        user_id = None
        user_nome = None
        tipo_usuario = None
        if current_user and current_user.is_authenticated:
            user_id = getattr(current_user, 'id', None)
            user_nome = getattr(current_user, 'nome', None)
            tipo_usuario = getattr(current_user, 'tipo', None)

        user_agent = (request.user_agent.string or '')[:300] if request else ''
        ip = _client_ip()[:45] if request else ''

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_log
                (user_id, user_nome, tipo_usuario, action_type,
                 entity_type, entity_id, descricao, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, user_nome, tipo_usuario, action_type,
            entity_type, entity_id,
            (descricao or '')[:500],
            ip, user_agent,
        ))
        conn.commit()
        conn.close()
    except Exception:
        # Audit log nunca deve derrubar a operação chamadora.
        # Em produção seria bom mandar para um logger estruturado;
        # por ora silenciamos para não vazar erros no flash do usuário.
        pass
