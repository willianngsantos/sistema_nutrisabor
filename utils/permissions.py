"""
Decorators de autorização compartilhados entre blueprints.

Antes cada arquivo tinha sua própria versão de `admin_required` com comportamento
levemente diferente. Este módulo centraliza as regras de acesso para facilitar
mudanças e evitar inconsistência.
"""
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def admin_only(f):
    """Restringe a rota a usuários com tipo='admin'.

    Use em rotas que alteram dados mestre (clientes, produtos, colaboradores,
    propostas, equipe) ou que executam operações sensíveis (reverter status
    de fatura paga, editar data de pagamento).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.tipo != 'admin':
            flash("Acesso restrito. Somente administradores podem executar esta ação.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


def rh_access(f):
    """Permite acesso a usuários de RH: admin, gerencial e nutricionista.

    Use em rotas de RH que são de consulta ou operação não-crítica (lançar
    exame, agendar férias, registrar ponto). Rotas de edição destrutiva ou
    de dados master (colaboradores CRUD, reajuste salarial) devem usar
    `admin_only`.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.tipo not in ('admin', 'gerencial', 'nutricionista'):
            flash("Acesso restrito.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated


def admin_or_gerencial(f):
    """Permite acesso a admin ou gerencial (exclui nutricionista e vendedor).

    Use em rotas de consulta a dados mestre/gerenciais que nutricionista não
    deve ver (ex: listagem de colaboradores com dados salariais).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.tipo not in ('admin', 'gerencial'):
            flash("Acesso restrito.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated
