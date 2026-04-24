"""
Área administrativa: agrupa funcionalidades restritas ao perfil Admin.

Por enquanto hospeda apenas a página de Log de Atividade (placeholder).
A implementação completa do audit log (tabela, middleware, instrumentação
de rotas, filtros, paginação) será feita em iteração separada — Task #16.

As telas de Equipe (auth.listar_usuarios) e Minha Empresa
(auth.configuracao_empresa) continuam em auth.py, apenas o navbar aponta
para elas a partir do novo menu Admin.
"""
from flask import Blueprint, render_template
from flask_login import login_required
from utils.permissions import admin_only

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/log')
@login_required
@admin_only
def log_atividade():
    """Log de atividade dos usuários. Placeholder até o Task #16."""
    return render_template('admin_log.html')
