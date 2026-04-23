import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app
from flask_login import login_required
from database import get_db_connection
from datetime import datetime
import pdfkit

# ── Detecta o caminho do wkhtmltopdf automaticamente (macOS Intel / Apple Silicon / Linux)
def _pdfkit_config():
    caminhos = [
        '/opt/homebrew/bin/wkhtmltopdf',   # macOS Apple Silicon
        '/usr/local/bin/wkhtmltopdf',       # macOS Intel / Linux
        '/usr/bin/wkhtmltopdf',             # Linux apt
    ]
    for c in caminhos:
        if os.path.isfile(c):
            return pdfkit.configuration(wkhtmltopdf=c)
    return None

_PDF_OPTIONS = {
    'page-size':               'A4',
    'margin-top':              '0mm',
    'margin-right':            '0mm',
    'margin-bottom':           '0mm',
    'margin-left':             '0mm',
    'encoding':                'UTF-8',
    'print-media-type':        None,   # respeita @media print (oculta .no-print)
    'no-outline':              None,
    'disable-smart-shrinking': None,
    'quiet':                   None,
    'load-error-handling':     'ignore',       # ignora falhas de CDN/SSL
    'load-media-error-handling': 'ignore',
    'enable-local-file-access': None,          # permite carregar file:// locais
}

def _fix_static_paths(html):
    """Substitui /static/ por file:// absoluto para wkhtmltopdf achar os assets locais."""
    static_dir = os.path.join(current_app.root_path, 'static')
    return html.replace('/static/', f'file://{static_dir}/')

vendas_bp = Blueprint('vendas', __name__)

def gerar_codigo_quinzena(data_str):
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d')
        quinzena = "01" if data.day <= 15 else "02"
        mes = data.strftime('%m')
        ano = data.strftime('%Y')
        return f"{quinzena}{mes}{ano}"
    except:
        return ""

@vendas_bp.route("/negociar/<int:id_cliente>")
@login_required
def negociar(id_cliente):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM clientes WHERE id = %s", (id_cliente,))
    cliente = cursor.fetchone()
    
    query = """
        SELECT p.id, p.nome, p.unidade, p.custo_base, t.preco_venda
        FROM produtos p
        LEFT JOIN tabela_precos t ON p.id = t.id_produto AND t.id_cliente = %s
        ORDER BY p.nome
    """
    cursor.execute(query, (id_cliente,))
    produtos = cursor.fetchall()
    conn.close()
    return render_template("negociar.html", cliente=cliente, produtos=produtos)

@vendas_bp.route("/salvar_precos/<int:id_cliente>", methods=["POST"])
@login_required
def salvar_precos(id_cliente):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    for key, valor in request.form.items():
        if key.startswith("preco_"):
            id_produto = key.split("_")[1]
            if valor:
                cursor.execute("SELECT id FROM tabela_precos WHERE id_cliente=%s AND id_produto=%s", (id_cliente, id_produto))
                existe = cursor.fetchone()
                if existe:
                    cursor.execute("UPDATE tabela_precos SET preco_venda=%s WHERE id=%s", (valor, existe['id']))
                else:
                    cursor.execute("INSERT INTO tabela_precos (id_cliente, id_produto, preco_venda) VALUES (%s, %s, %s)", (id_cliente, id_produto, valor))
    conn.commit()
    conn.close()
    flash("Tabela de preços atualizada!", "success")
    return redirect(url_for('vendas.negociar', id_cliente=id_cliente))

@vendas_bp.route("/pedidos")
@login_required
def selecionar_cliente_pedido():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    clientes = cursor.fetchall()

    cursor.execute("""
        SELECT p.id, c.nome_empresa, p.codigo_fatura, DATE_FORMAT(p.data_emissao, '%d/%m/%Y') AS data_emissao_fmt
        FROM pedidos p
        JOIN clientes c ON p.id_cliente = c.id
        ORDER BY p.id DESC LIMIT 5
    """)
    recentes = cursor.fetchall()

    conn.close()
    return render_template("selecionar_cliente.html", clientes=clientes, recentes=recentes)

@vendas_bp.route("/abrir_pedido", methods=["POST"])
@login_required
def abrir_pedido():
    id_cliente = request.form.get("id_cliente")
    return redirect(url_for('vendas.fazer_pedido', id_cliente=id_cliente))

@vendas_bp.route("/fazer_pedido/<int:id_cliente>")
@vendas_bp.route("/editar_pedido/<int:id_pedido>")
@login_required
def fazer_pedido(id_cliente=None, id_pedido=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    pedido_atual = None
    itens_atuais = {} 
    
    if id_pedido:
        cursor.execute("SELECT id, id_cliente, status, DATE_FORMAT(data_inicio, '%Y-%m-%d') as data_inicio, DATE_FORMAT(data_fim, '%Y-%m-%d') as data_fim FROM pedidos WHERE id=%s", (id_pedido,))
        pedido_atual = cursor.fetchone()
        if pedido_atual and pedido_atual['status'] != 'Pendente':
            conn.close()
            return redirect(url_for('home'))
        id_cliente = pedido_atual['id_cliente']
        
        cursor.execute("SELECT id_produto, quantidade FROM itens_pedido WHERE id_pedido=%s", (id_pedido,))
        for row in cursor.fetchall():
            itens_atuais[row['id_produto']] = row['quantidade']
            
    cursor.execute("SELECT id, nome_empresa, cnpj, email, celular, id_grupo FROM clientes WHERE id = %s", (id_cliente,))
    cliente = cursor.fetchone()
    
    query = """
        SELECT 
            p.id, p.nome, p.unidade, p.custo_base, 
            COALESCE(tc.preco_venda, tg.preco_venda, p.custo_base) as preco_final,
            CASE
                WHEN tc.preco_venda IS NOT NULL THEN 'CLIENTE'
                WHEN tg.preco_venda IS NOT NULL THEN 'GRUPO'
                ELSE 'PADRÃO'
            END as origem_preco
        FROM produtos p
        LEFT JOIN tabela_precos tc ON p.id = tc.id_produto AND tc.id_cliente = %s
        LEFT JOIN tabela_precos_grupos tg ON p.id = tg.id_produto AND tg.id_grupo = %s
        ORDER BY p.nome
    """
    
    cursor.execute(query, (id_cliente, cliente['id_grupo']))
    produtos = cursor.fetchall()
    conn.close()
    
    hoje = datetime.today().strftime('%Y-%m-%d')
    return render_template("formulario_pedido.html", 
                           cliente=cliente, produtos=produtos, hoje=hoje, 
                           pedido=pedido_atual, itens_atuais=itens_atuais)

@vendas_bp.route("/salvar_pedido", methods=["POST"])
@login_required
def salvar_pedido():
    id_cliente = request.form["id_cliente"]
    id_pedido = request.form.get("id_pedido")
    data_inicio = request.form["data_inicio"]
    data_fim = request.form["data_fim"]
    codigo_fatura = gerar_codigo_quinzena(data_fim)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    itens_para_salvar = []
    total_pedido = 0

    for key, valor in request.form.items():
        if key.startswith("qtd_"):
            id_prod = key.split("_")[1]
            try:
                qtd = int(float(valor)) if valor else 0
                if qtd > 0:
                    preco_str = request.form.get(f"preco_{id_prod}") or "0"
                    preco_str = preco_str.replace(".", "").replace(",", ".")
                    preco = float(preco_str)
                    
                    total_pedido += (qtd * preco)
                    itens_para_salvar.append((id_prod, qtd, preco))
            except Exception as e: 
                print(f"Erro ao processar item {id_prod}: {e}")
                continue

    if total_pedido <= 0:
        flash("❌ Erro: Fatura com valor zero.", "danger")
        conn.close()
        return redirect(url_for('vendas.fazer_pedido', id_cliente=id_cliente))

    if id_pedido:
        cursor.execute("UPDATE pedidos SET data_inicio=%s, data_fim=%s, codigo_fatura=%s WHERE id=%s", (data_inicio, data_fim, codigo_fatura, id_pedido))
        cursor.execute("DELETE FROM itens_pedido WHERE id_pedido=%s", (id_pedido,))
        p_id = id_pedido
    else:
        cursor.execute("INSERT INTO pedidos (id_cliente, data_inicio, data_fim, codigo_fatura, status) VALUES (%s, %s, %s, %s, 'Pendente')", (id_cliente, data_inicio, data_fim, codigo_fatura))
        p_id = cursor.lastrowid

    for item in itens_para_salvar:
        cursor.execute("INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_praticado) VALUES (%s, %s, %s, %s)", (p_id, item[0], item[1], item[2]))
    
    conn.commit()
    conn.close()
    flash("✅ Fatura salva!", "success")
    return redirect(url_for('home'))

@vendas_bp.route("/mudar_status/<int:id_pedido>/<string:novo_status>", methods=["POST"])
@login_required
def mudar_status(id_pedido, novo_status):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE pedidos SET status = %s WHERE id = %s", (novo_status, id_pedido))
    conn.commit()
    conn.close()
    flash(f"Status da fatura #{id_pedido} atualizado!", "success")
    return redirect(url_for('home'))

@vendas_bp.route("/excluir_pedido/<int:id_pedido>", methods=["POST"])
@login_required
def excluir_pedido(id_pedido):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("DELETE FROM itens_pedido WHERE id_pedido = %s", (id_pedido,))
        cursor.execute("DELETE FROM pedidos WHERE id = %s", (id_pedido,))
        conn.commit()
        flash(f"Pedido #{id_pedido} excluído com sucesso.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('home'))

@vendas_bp.route("/salvar_nf/<int:id_pedido>", methods=["POST"])
@login_required
def salvar_nf(id_pedido):
    numero_nf = request.form.get("numero_nf", "").strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE pedidos SET numero_nf = %s WHERE id = %s", (numero_nf if numero_nf else None, id_pedido))
    conn.commit()
    conn.close()
    
    if numero_nf:
        flash(f"Nota Fiscal {numero_nf} vinculada à fatura #{id_pedido}!", "success")
    else:
        flash(f"Nota Fiscal removida da fatura #{id_pedido}.", "info")
        
    return redirect(url_for('home'))

# ==============================================================================
# ROTA DE PDF E VISUALIZAÇÃO
# ==============================================================================
@vendas_bp.route("/fatura/pdf/<int:id_pedido>")
@login_required
def baixar_pdf(id_pedido):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, id_cliente, DATE_FORMAT(data_emissao, '%d/%m/%Y') as emissao,
               DATE_FORMAT(data_inicio, '%d/%m/%Y') as inicio, DATE_FORMAT(data_fim, '%d/%m/%Y') as fim,
               codigo_fatura, status, numero_nf
        FROM pedidos WHERE id = %s""", (id_pedido,))
    pedido = cursor.fetchone()

    cursor.execute("SELECT id, nome_empresa, cnpj, email, celular, id_grupo, apelido FROM clientes WHERE id = %s", (pedido['id_cliente'],))
    cliente = cursor.fetchone()

    grupo_info = None
    if cliente and cliente['id_grupo']:
        cursor.execute("SELECT chave_pix, pix_nome, pix_banco FROM grupos_clientes WHERE id = %s", (cliente['id_grupo'],))
        grupo_info = cursor.fetchone()

    cursor.execute("""
        SELECT prod.nome, prod.unidade, i.quantidade, i.preco_praticado, (i.quantidade * i.preco_praticado) as subtotal
        FROM itens_pedido i JOIN produtos prod ON i.id_produto = prod.id
        WHERE i.id_pedido = %s""", (id_pedido,))
    itens = cursor.fetchall()

    cursor.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor.fetchone()
    conn.close()

    total = sum(item['subtotal'] for item in itens)
    total_whatsapp = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    html = render_template("fatura.html", pedido=pedido, cliente=cliente, itens=itens,
                           empresa=empresa, total_geral=total, total_whatsapp=total_whatsapp,
                           grupo_info=grupo_info)
    html = _fix_static_paths(html)   # resolve logo e assets locais para wkhtmltopdf

    nome_doc = 'RESUMO' if pedido['status'] == 'Pendente' else 'FATURA'
    nome_cliente_arquivo = cliente['apelido'] if cliente['apelido'] else cliente['nome_empresa']
    nome_cliente_limpo = "".join(x for x in nome_cliente_arquivo if x.isalnum() or x in " _-").strip().replace(" ", "_")
    nome_arquivo_final = f"{nome_doc}_{nome_cliente_limpo}_Ref{pedido['codigo_fatura']}.pdf"

    try:
        cfg = _pdfkit_config()
        pdf = pdfkit.from_string(html, False, options=_PDF_OPTIONS,
                                 configuration=cfg if cfg else pdfkit.configuration())
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename="{nome_arquivo_final}"'
        return response
    except Exception as e:
        flash(f"Erro ao gerar PDF: {e}. Verifique se o wkhtmltopdf está instalado.", "danger")
        return redirect(url_for('vendas.ver_fatura', id_pedido=id_pedido))

@vendas_bp.route("/fatura/<int:id_pedido>")
@login_required
def ver_fatura(id_pedido):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, id_cliente, DATE_FORMAT(data_emissao, '%d/%m/%Y') as emissao,
               DATE_FORMAT(data_inicio, '%d/%m/%Y') as inicio, DATE_FORMAT(data_fim, '%d/%m/%Y') as fim,
               codigo_fatura, status, numero_nf
        FROM pedidos WHERE id = %s
    """, (id_pedido,))
    pedido = cursor.fetchone()

    if not pedido:
        conn.close()
        flash("Fatura não encontrada.", "danger")
        return redirect(url_for('home'))

    cursor.execute("SELECT id, nome_empresa, cnpj, email, celular, id_grupo, apelido FROM clientes WHERE id = %s", (pedido['id_cliente'],))
    cliente = cursor.fetchone()

    grupo_info = None
    if cliente and cliente['id_grupo']:
        cursor.execute("SELECT chave_pix, pix_nome, pix_banco FROM grupos_clientes WHERE id = %s", (cliente['id_grupo'],))
        grupo_info = cursor.fetchone()

    cursor.execute("""
        SELECT prod.nome, prod.unidade, i.quantidade, i.preco_praticado, (i.quantidade * i.preco_praticado) as subtotal
        FROM itens_pedido i JOIN produtos prod ON i.id_produto = prod.id
        WHERE i.id_pedido = %s
    """, (id_pedido,))
    itens = cursor.fetchall()

    cursor.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor.fetchone()
    conn.close()

    total_geral = sum(item['subtotal'] for item in itens)
    total_formatado = f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return render_template("fatura.html", pedido=pedido, cliente=cliente, itens=itens, empresa=empresa, total_geral=total_geral, total_whatsapp=total_formatado, grupo_info=grupo_info)

@vendas_bp.route("/relatorios", methods=["GET", "POST"])
@login_required
def relatorios():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    lista_clientes = cursor.fetchall()
    
    resultados = []
    
    total_periodo = 0
    total_recebido = 0
    total_a_receber = 0
    f_inicio = f_fim = f_cliente = f_status = ""
    
    if request.method == "POST":
        f_inicio = request.form.get("data_inicio")
        f_fim = request.form.get("data_fim")
        f_cliente = request.form.get("cliente_id")
        f_status = request.form.get("status")
        
        sql = """
            SELECT p.id, c.nome_empresa, p.codigo_fatura, DATE_FORMAT(p.data_fim, '%d/%m/%Y') as data,
                   p.status, COALESCE(SUM(i.quantidade * i.preco_praticado), 0) as total
            FROM pedidos p
            JOIN clientes c ON p.id_cliente = c.id
            LEFT JOIN itens_pedido i ON p.id = i.id_pedido
            WHERE 1=1 
        """
        params = []
        
        if f_inicio and f_fim:
            data1 = min(f_inicio, f_fim)
            data2 = max(f_inicio, f_fim)
            sql += " AND p.data_fim BETWEEN %s AND %s"
            params.extend([data1, data2])
            
        if f_cliente:
            sql += " AND p.id_cliente = %s"
            params.append(f_cliente)
            
        if f_status:
            sql += " AND p.status = %s"
            params.append(f_status)
            
        sql += " GROUP BY p.id, c.nome_empresa, p.codigo_fatura, p.data_fim, p.status ORDER BY p.data_fim DESC"
        
        cursor.execute(sql, tuple(params))
        resultados = cursor.fetchall()
        
        if resultados:
            total_periodo = sum(r['total'] for r in resultados)
            total_recebido = sum(r['total'] for r in resultados if r['status'] == 'Pago')
            total_a_receber = sum(r['total'] for r in resultados if r['status'] in ['Aprovado', 'Pendente'])
            
    conn.close()
    
    return render_template("relatorios.html", resultados=resultados, 
                           total_periodo=total_periodo, 
                           total_recebido=total_recebido,
                           total_a_receber=total_a_receber,
                           clientes=lista_clientes, 
                           f_inicio=f_inicio, f_fim=f_fim, 
                           f_cliente=f_cliente, f_status=f_status)