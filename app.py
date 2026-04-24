import os
from flask import Flask, render_template, redirect, url_for, request, session
from datetime import datetime, timedelta
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from database import get_db_connection
from models import User
from routes.auth import auth_bp
from routes.cadastros import cadastros_bp
from routes.vendas import vendas_bp
from routes.colaboradores import colaboradores_bp
from routes.propostas import propostas_bp
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30) # Expira em 30 minutos

# --- CSRF PROTECTION ---
csrf = CSRFProtect(app)

# --- FILTROS ---
@app.template_filter('real')
def format_real(value):
    try:
        val = float(value) if value else 0.0
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

@app.template_filter('cpf_cnpj')
def format_cpf_cnpj(value):
    """Formata automaticamente CPF ou CNPJ baseado nos dígitos"""
    if not value: return ""
    
    # Remove tudo que não for número
    digits = re.sub(r'\D', '', str(value))
    
    # CPF (11 dígitos)
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    
    # CNPJ (14 dígitos)
    elif len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    
    # Retorna original se não casar com os padrões
    return value

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, email, tipo FROM usuarios WHERE id = %s", (user_id,))
    data = cursor.fetchone()
    conn.close()
    if data:
        # Agora ele passa o 'tipo' para o modelo!
        return User(id=data['id'], nome=data['nome'], email=data['email'], tipo=data.get('tipo', 'vendedor'))
    return None

# --- ROTA RAIZ ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.tipo == 'nutricionista':
            return redirect(url_for('cardapios.index'))
        return redirect(url_for('home'))
    return redirect(url_for('auth.login'))

# --- DASHBOARD (HOME) ---
@app.route('/home')
@login_required
def home():
    # 1. Proteção: Nutricionista é barrada aqui e vai para Cardápios
    if current_user.tipo == 'nutricionista':
        return redirect(url_for('cardapios.index'))

    # 2. Conexão com o banco (Essas eram as linhas que tinham sumido! rs)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 3. INDICADORES FINANCEIROS — regime de caixa (somente faturas PAGAS,
    # usando data_pagamento como referência para o período).
    cursor.execute("""
        SELECT SUM(i.quantidade * i.preco_praticado) as total
        FROM itens_pedido i JOIN pedidos p ON i.id_pedido = p.id
        WHERE p.status = 'Pago'
          AND p.data_pagamento IS NOT NULL
          AND MONTH(p.data_pagamento) = MONTH(CURRENT_DATE())
          AND YEAR(p.data_pagamento) = YEAR(CURRENT_DATE())
    """)
    fat_mes_atual = cursor.fetchone()['total'] or 0

    cursor.execute("""
        SELECT SUM(i.quantidade * i.preco_praticado) as total
        FROM itens_pedido i JOIN pedidos p ON i.id_pedido = p.id
        WHERE p.status = 'Pago'
          AND p.data_pagamento IS NOT NULL
          AND MONTH(p.data_pagamento) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH)
          AND YEAR(p.data_pagamento) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)
    """)
    fat_mes_passado = cursor.fetchone()['total'] or 0

    cursor.execute("""
        SELECT SUM(i.quantidade * i.preco_praticado) as total
        FROM itens_pedido i JOIN pedidos p ON i.id_pedido = p.id
        WHERE p.status = 'Pago'
          AND p.data_pagamento IS NOT NULL
          AND YEAR(p.data_pagamento) = YEAR(CURRENT_DATE())
    """)
    fat_ano_atual = cursor.fetchone()['total'] or 0

    # 4. MOTOR DE FILTRO
    hoje = datetime.now()
    
    if 'mes' in request.args:
        f_mes = request.args.get('mes', '')
        f_ano = request.args.get('ano', '')
        f_status = request.args.get('status', '')
        f_cliente = request.args.get('cliente_id', '')
        
        session['filtro_mes'] = f_mes
        session['filtro_ano'] = f_ano
        session['filtro_status'] = f_status
        session['filtro_cliente'] = f_cliente
    else:
        f_mes = session.get('filtro_mes', str(hoje.month))
        f_ano = session.get('filtro_ano', str(hoje.year))
        f_status = session.get('filtro_status', '')
        f_cliente = session.get('filtro_cliente', '')

    # Monta o WHERE uma vez só — reutilizado pelo COUNT e pelo SELECT
    where_sql = ""
    params = []

    if f_mes:
        where_sql += " AND MONTH(p.data_fim) = %s"
        params.append(f_mes)
    if f_ano:
        where_sql += " AND YEAR(p.data_fim) = %s"
        params.append(f_ano)
    if f_cliente:
        where_sql += " AND p.id_cliente = %s"
        params.append(f_cliente)
    if f_status:
        if f_status == 'com_nf':
            where_sql += " AND p.numero_nf IS NOT NULL AND p.numero_nf != ''"
        elif f_status == 'sem_nf':
            where_sql += " AND (p.numero_nf IS NULL OR p.numero_nf = '')"
        else:
            where_sql += " AND p.status = %s"
            params.append(f_status)

    # 5. PAGINAÇÃO (50/pág, preservando filtros)
    per_page = 50
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    cursor.execute(f"""
        SELECT COUNT(*) AS total
        FROM pedidos p
        JOIN clientes c ON p.id_cliente = c.id
        WHERE 1=1 {where_sql}
    """, tuple(params))
    total_count = cursor.fetchone()['total']
    total_pages = max(1, -(-total_count // per_page))  # ceil

    # Se a página pedida passou do total (ex: mudou filtro), volta pra última válida
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    sql_pedidos = f"""
        SELECT p.id, p.codigo_fatura, c.nome_empresa, p.status,
               DATE_FORMAT(p.data_emissao, '%d/%m/%Y') as data_emissao,
               DATE_FORMAT(p.data_fim, '%d/%m/%Y') as data_competencia,
               DATE_FORMAT(p.data_pagamento, '%d/%m/%Y') as data_pagamento_fmt,
               DATE_FORMAT(p.data_pagamento, '%Y-%m-%d') as data_pagamento_iso,
               p.numero_nf
        FROM pedidos p
        JOIN clientes c ON p.id_cliente = c.id
        WHERE 1=1 {where_sql}
        ORDER BY p.data_fim DESC, p.id DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(sql_pedidos, tuple(params) + (per_page, offset))
    ultimos_pedidos = cursor.fetchall()

    cursor.execute("SELECT DISTINCT YEAR(data_fim) as ano FROM pedidos WHERE data_fim IS NOT NULL ORDER BY ano DESC")
    anos_db = cursor.fetchall()
    anos_disponiveis = [str(a['ano']) for a in anos_db]
    if not anos_disponiveis:
        anos_disponiveis = [str(hoje.year)]

    cursor.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    lista_clientes = cursor.fetchall()

    conn.close()
    
    return render_template('home.html', usuario=current_user,
                           fat_mes_atual=fat_mes_atual,
                           fat_mes_passado=fat_mes_passado,
                           fat_ano_atual=fat_ano_atual,
                           ultimos_pedidos=ultimos_pedidos,
                           clientes=lista_clientes,
                           f_mes=f_mes, f_ano=f_ano, f_status=f_status, f_cliente=f_cliente,
                           anos_disponiveis=anos_disponiveis,
                           page=page, total_pages=total_pages,
                           total_count=total_count, per_page=per_page)
                           

# Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(cadastros_bp)
app.register_blueprint(vendas_bp)
app.register_blueprint(colaboradores_bp)
app.register_blueprint(propostas_bp)

from routes.cardapios import cardapios_bp
app.register_blueprint(cardapios_bp)

from routes.rh import rh_bp
app.register_blueprint(rh_bp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)