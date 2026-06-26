import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db_connection
from datetime import datetime
from utils.permissions import admin_only
from utils.audit import log_action
from utils.constants import MESES_PT

logger = logging.getLogger(__name__)
vendas_bp = Blueprint('vendas', __name__)

def gerar_codigo_quinzena(data_str):
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d')
        quinzena = "01" if data.day <= 15 else "02"
        mes = data.strftime('%m')
        ano = data.strftime('%Y')
        return f"{quinzena}{mes}{ano}"
    except (ValueError, TypeError):
        return ""

@vendas_bp.route("/negociar/<int:id_cliente>")
@login_required
@admin_only
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
    return render_template("negociar.html", cliente=cliente, produtos=produtos)

@vendas_bp.route("/salvar_precos/<int:id_cliente>", methods=["POST"])
@login_required
@admin_only
def salvar_precos(id_cliente):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome_empresa FROM clientes WHERE id=%s", (id_cliente,))
    cli = cursor.fetchone()
    nome_cli = cli['nome_empresa'] if cli else f'#{id_cliente}'
    qtd_definidos = 0
    qtd_removidos = 0
    for key, valor in request.form.items():
        if not key.startswith("preco_"):
            continue
        id_produto = key.split("_")[1]

        # Normaliza o valor digitado (aceita vírgula como decimal)
        preco = None
        v = (valor or "").strip().replace(".", "").replace(",", ".") if (valor and "," in valor) else (valor or "").strip()
        if v:
            try:
                preco = float(v)
            except ValueError:
                preco = None

        cursor.execute("SELECT id FROM tabela_precos WHERE id_cliente=%s AND id_produto=%s", (id_cliente, id_produto))
        existe = cursor.fetchone()

        if preco is not None and preco > 0:
            # Define/atualiza o preço diferenciado (vira "favorito")
            if existe:
                cursor.execute("UPDATE tabela_precos SET preco_venda=%s WHERE id=%s", (preco, existe['id']))
            else:
                cursor.execute("INSERT INTO tabela_precos (id_cliente, id_produto, preco_venda) VALUES (%s, %s, %s)", (id_cliente, id_produto, preco))
            qtd_definidos += 1
        elif existe:
            # Campo vazio (ou 0) e havia preço → REMOVE o preço diferenciado
            cursor.execute("DELETE FROM tabela_precos WHERE id=%s", (existe['id'],))
            qtd_removidos += 1

    conn.commit()
    log_action('update', entity_type='tabela_precos_cliente', entity_id=int(id_cliente),
               descricao=f"Tabela de preços do cliente '{nome_cli}': {qtd_definidos} definido(s), {qtd_removidos} removido(s)")
    if qtd_removidos:
        flash(f"Tabela atualizada! {qtd_definidos} preço(s) definido(s) e {qtd_removidos} removido(s).", "success")
    else:
        flash("Tabela de preços atualizada!", "success")
    return redirect(url_for('vendas.negociar', id_cliente=id_cliente))

@vendas_bp.route("/reajustar_precos_cliente/<int:id_cliente>", methods=["POST"])
@login_required
@admin_only
def reajustar_precos_cliente(id_cliente):
    """Aplica um percentual sobre TODOS os preços já cadastrados na tabela
    deste cliente de uma vez. Aceita percentual negativo (redução). Nunca
    deixa o preço ficar negativo."""
    try:
        pct = float(request.form.get('percentual', '0').replace(',', '.'))
    except ValueError:
        flash("Percentual inválido.", "danger")
        return redirect(url_for('vendas.negociar', id_cliente=id_cliente))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome_empresa FROM clientes WHERE id=%s", (id_cliente,))
    cli = cursor.fetchone()
    nome = cli['nome_empresa'] if cli else f'#{id_cliente}'
    cursor.execute("""
        UPDATE tabela_precos
        SET preco_venda = ROUND(GREATEST(0, preco_venda * (1 + %s/100)), 2)
        WHERE id_cliente = %s AND preco_venda IS NOT NULL
    """, (pct, id_cliente))
    n = cursor.rowcount
    conn.commit()
    log_action('update', entity_type='tabela_precos_cliente', entity_id=int(id_cliente),
               descricao=f"Reajuste em lote de {pct:+.2f}% na tabela do cliente '{nome}': {n} preço(s)")
    flash(f"Reajuste de {pct:+.2f}% aplicado a {n} preço(s) do cliente.".replace('.', ','), "success")
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
            return redirect(url_for('home'))
        id_cliente = pedido_atual['id_cliente']
        
        cursor.execute("SELECT id_produto, quantidade FROM itens_pedido WHERE id_pedido=%s", (id_pedido,))
        for row in cursor.fetchall():
            itens_atuais[row['id_produto']] = row['quantidade']
            
    cursor.execute("SELECT id, nome_empresa, cnpj, email, celular, id_grupo FROM clientes WHERE id = %s", (id_cliente,))
    cliente = cursor.fetchone()
    
    # NULLIF(..., 0): um preço cadastrado como 0 é tratado como "sem preço
    # negociado" (cai no preço padrão e NÃO recebe o selo CLIENTE/GRUPO).
    # Assim, zerar um item equivale a removê-lo dos preços diferenciados.
    query = """
        SELECT
            p.id, p.nome, p.unidade, p.custo_base,
            COALESCE(NULLIF(tc.preco_venda, 0), NULLIF(tg.preco_venda, 0), p.custo_base) as preco_final,
            CASE
                WHEN NULLIF(tc.preco_venda, 0) IS NOT NULL THEN 'CLIENTE'
                WHEN NULLIF(tg.preco_venda, 0) IS NOT NULL THEN 'GRUPO'
                ELSE 'PADRÃO'
            END as origem_preco
        FROM produtos p
        LEFT JOIN tabela_precos tc ON p.id = tc.id_produto AND tc.id_cliente = %s
        LEFT JOIN tabela_precos_grupos tg ON p.id = tg.id_produto AND tg.id_grupo = %s
        ORDER BY p.nome
    """
    
    cursor.execute(query, (id_cliente, cliente['id_grupo']))
    produtos = cursor.fetchall()
    
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
            except (ValueError, TypeError) as e:
                logger.warning("Erro ao processar item %s no pedido: %s", id_prod, e)
                continue

    if total_pedido <= 0:
        flash("❌ Erro: Fatura com valor zero.", "danger")
        return redirect(url_for('vendas.fazer_pedido', id_cliente=id_cliente))

    is_update = bool(id_pedido)
    if is_update:
        cursor.execute("UPDATE pedidos SET data_inicio=%s, data_fim=%s, codigo_fatura=%s WHERE id=%s", (data_inicio, data_fim, codigo_fatura, id_pedido))
        cursor.execute("DELETE FROM itens_pedido WHERE id_pedido=%s", (id_pedido,))
        p_id = id_pedido
    else:
        cursor.execute("INSERT INTO pedidos (id_cliente, data_inicio, data_fim, codigo_fatura, status) VALUES (%s, %s, %s, %s, 'Pendente')", (id_cliente, data_inicio, data_fim, codigo_fatura))
        p_id = cursor.lastrowid

    for item in itens_para_salvar:
        cursor.execute("INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_praticado) VALUES (%s, %s, %s, %s)", (p_id, item[0], item[1], item[2]))

    # Busca nome do cliente para descricao mais util
    cursor.execute("SELECT nome_empresa FROM clientes WHERE id=%s", (id_cliente,))
    cli = cursor.fetchone()
    nome_cli = cli['nome_empresa'] if cli else f'#{id_cliente}'

    conn.commit()

    log_action('update' if is_update else 'create', entity_type='fatura', entity_id=int(p_id),
               descricao=f"{'Editou' if is_update else 'Criou'} fatura #{codigo_fatura} cliente '{nome_cli}': "
                         f"{len(itens_para_salvar)} itens, total R${total_pedido:.2f}, "
                         f"período {data_inicio} a {data_fim}")
    flash("✅ Fatura salva!", "success")
    return redirect(url_for('home'))

@vendas_bp.route("/fatura/editar_pagamento/<int:id_pedido>", methods=["POST"])
@login_required
@admin_only
def editar_data_pagamento(id_pedido):
    """Permite ajustar manualmente a data_pagamento de uma fatura ja marcada
    como Pago (ex: usuario lembrou de marcar como paga depois da data real
    do recebimento)."""
    nova_data = request.form.get('data_pagamento', '').strip()
    if not nova_data:
        flash("Informe uma data válida.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, status, codigo_fatura, DATE_FORMAT(data_pagamento,'%d/%m/%Y') AS pagamento_atual FROM pedidos WHERE id = %s", (id_pedido,))
    pedido = cursor.fetchone()
    if not pedido:
        flash("Fatura não encontrada.", "danger")
        return redirect(url_for('home'))
    if pedido['status'] != 'Pago':
        flash("Só é possível ajustar a data de pagamento em faturas marcadas como Pago.", "warning")
        return redirect(url_for('home'))

    cursor.execute("UPDATE pedidos SET data_pagamento = %s WHERE id = %s", (nova_data, id_pedido))
    conn.commit()

    log_action('update', entity_type='fatura', entity_id=int(id_pedido),
               descricao=f"Ajustou data de pagamento da fatura #{pedido['codigo_fatura']}: "
                         f"{pedido.get('pagamento_atual') or 'NULL'}→{nova_data}")
    flash(f"Data de pagamento da fatura #{pedido['codigo_fatura']} atualizada.", "success")
    return redirect(url_for('home'))


@vendas_bp.route("/mudar_status/<int:id_pedido>/<string:novo_status>", methods=["POST"])
@login_required
def mudar_status(id_pedido, novo_status):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Carrega o status atual para aplicar a regra de reversão:
    # sair de 'Pago' para qualquer outro status (estornar recebimento) é
    # restrito a admin. Outras transições continuam liberadas para qualquer
    # usuário autenticado.
    cursor.execute("SELECT status, codigo_fatura FROM pedidos WHERE id = %s", (id_pedido,))
    atual = cursor.fetchone()
    if not atual:
        flash("Fatura não encontrada.", "danger")
        return redirect(url_for('home'))
    if atual['status'] == 'Pago' and novo_status != 'Pago' and current_user.tipo != 'admin':
        flash("Somente administradores podem estornar uma fatura já paga.", "warning")
        return redirect(url_for('home'))

    # data_pagamento: auto-preenche com CURDATE() ao marcar Pago;
    # limpa (NULL) ao sair de Pago para qualquer outro status.
    if novo_status == 'Pago':
        cursor.execute(
            "UPDATE pedidos SET status = %s, data_pagamento = CURDATE() WHERE id = %s",
            (novo_status, id_pedido)
        )
    else:
        cursor.execute(
            "UPDATE pedidos SET status = %s, data_pagamento = NULL WHERE id = %s",
            (novo_status, id_pedido)
        )
    conn.commit()

    log_action('update', entity_type='fatura', entity_id=int(id_pedido),
               descricao=f"Fatura #{atual['codigo_fatura']}: status {atual['status']}→{novo_status}")
    flash(f"Status da fatura #{id_pedido} atualizado!", "success")
    return redirect(url_for('home'))

@vendas_bp.route("/excluir_pedido/<int:id_pedido>", methods=["POST"])
@login_required
@admin_only
def excluir_pedido(id_pedido):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT codigo_fatura, status FROM pedidos WHERE id = %s", (id_pedido,))
    ped = cursor.fetchone() or {}
    codigo = ped.get('codigo_fatura') or f'#{id_pedido}'
    status = ped.get('status') or '—'
    try:
        cursor.execute("DELETE FROM itens_pedido WHERE id_pedido = %s", (id_pedido,))
        cursor.execute("DELETE FROM pedidos WHERE id = %s", (id_pedido,))
        conn.commit()
        log_action('delete', entity_type='fatura', entity_id=int(id_pedido),
                   descricao=f"Excluiu fatura #{codigo} (status {status})")
        flash(f"Pedido #{id_pedido} excluído com sucesso.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {e}", "danger")
    return redirect(url_for('home'))

@vendas_bp.route("/salvar_nf/<int:id_pedido>", methods=["POST"])
@login_required
def salvar_nf(id_pedido):
    numero_nf = request.form.get("numero_nf", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT codigo_fatura, numero_nf FROM pedidos WHERE id = %s", (id_pedido,))
    ped = cursor.fetchone() or {}
    codigo = ped.get('codigo_fatura') or f'#{id_pedido}'
    nf_antiga = ped.get('numero_nf') or 'NULL'
    cursor.execute("UPDATE pedidos SET numero_nf = %s WHERE id = %s", (numero_nf if numero_nf else None, id_pedido))
    conn.commit()

    log_action('update', entity_type='fatura', entity_id=int(id_pedido),
               descricao=f"Fatura #{codigo}: NF {nf_antiga}→{numero_nf or 'NULL'}")
    if numero_nf:
        flash(f"Nota Fiscal {numero_nf} vinculada à fatura #{id_pedido}!", "success")
    else:
        flash(f"Nota Fiscal removida da fatura #{id_pedido}.", "info")

    return redirect(url_for('home'))

# ==============================================================================
# VISUALIZAÇÃO DA FATURA (para salvar como PDF, usar o botão 'Imprimir' na
# tela de visualização e escolher 'Salvar como PDF' no diálogo do navegador)
# ==============================================================================
@vendas_bp.route("/fatura/<int:id_pedido>")
@login_required
def ver_fatura(id_pedido):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, id_cliente, DATE_FORMAT(data_emissao, '%d/%m/%Y') as emissao,
               DATE_FORMAT(data_inicio, '%d/%m/%Y') as inicio, DATE_FORMAT(data_fim, '%d/%m/%Y') as fim,
               DATE_FORMAT(data_pagamento, '%d/%m/%Y') as pagamento,
               codigo_fatura, status, numero_nf
        FROM pedidos WHERE id = %s
    """, (id_pedido,))
    pedido = cursor.fetchone()

    if not pedido:
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

    total_geral = sum(item['subtotal'] for item in itens)
    total_formatado = f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return render_template("fatura.html", pedido=pedido, cliente=cliente, itens=itens, empresa=empresa, total_geral=total_geral, total_whatsapp=total_formatado, grupo_info=grupo_info)

def _filtros_relatorio(form):
    """Monta o WHERE + params do relatório a partir dos campos do formulário.
    Compartilhado entre a tela de relatórios e a exportação CSV para a regra
    de filtro nunca divergir. Retorna (where_sql, params)."""
    where_sql = ""
    params = []
    f_inicio = form.get("data_inicio")
    f_fim = form.get("data_fim")
    if f_inicio and f_fim:
        where_sql += " AND p.data_fim BETWEEN %s AND %s"
        params.extend([min(f_inicio, f_fim), max(f_inicio, f_fim)])
    if form.get("cliente_id"):
        where_sql += " AND p.id_cliente = %s"
        params.append(form.get("cliente_id"))
    if form.get("grupo_id"):
        where_sql += " AND c.id_grupo = %s"
        params.append(form.get("grupo_id"))
    if form.get("status"):
        where_sql += " AND p.status = %s"
        params.append(form.get("status"))
    return where_sql, params


@vendas_bp.route("/relatorios", methods=["GET", "POST"])
@login_required
def relatorios():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome_empresa FROM clientes ORDER BY nome_empresa")
    lista_clientes = cursor.fetchall()
    cursor.execute("SELECT id, nome FROM grupos_clientes ORDER BY nome")
    lista_grupos = cursor.fetchall()
    # Anos com faturas (para o atalho "Ano inteiro")
    cursor.execute("SELECT DISTINCT YEAR(data_fim) AS ano FROM pedidos WHERE data_fim IS NOT NULL ORDER BY ano DESC")
    anos_disponiveis = [str(r['ano']) for r in cursor.fetchall()]

    resultados = []
    por_mes = []
    por_cliente = []

    total_periodo = 0
    total_recebido = 0
    total_a_receber = 0
    f_inicio = f_fim = f_cliente = f_grupo = f_status = ""

    if request.method == "POST":
        f_inicio = request.form.get("data_inicio")
        f_fim = request.form.get("data_fim")
        f_cliente = request.form.get("cliente_id")
        f_grupo = request.form.get("grupo_id")
        f_status = request.form.get("status")

        # WHERE compartilhado pelas 3 consultas (detalhe, por mês, por cliente)
        where_sql, params = _filtros_relatorio(request.form)

        # Soma por status reaproveitada nas duas agregações
        col_total     = "COALESCE(SUM(i.quantidade * i.preco_praticado), 0)"
        col_recebido  = "COALESCE(SUM(CASE WHEN p.status='Pago' THEN i.quantidade*i.preco_praticado ELSE 0 END), 0)"
        col_areceber  = "COALESCE(SUM(CASE WHEN p.status IN ('Aprovado','Pendente') THEN i.quantidade*i.preco_praticado ELSE 0 END), 0)"

        # 1) Detalhamento (lista de faturas)
        cursor.execute(f"""
            SELECT p.id, c.nome_empresa, p.codigo_fatura, DATE_FORMAT(p.data_fim, '%d/%m/%Y') as data,
                   p.status, {col_total} as total
            FROM pedidos p
            JOIN clientes c ON p.id_cliente = c.id
            LEFT JOIN itens_pedido i ON p.id = i.id_pedido
            WHERE 1=1 {where_sql}
            GROUP BY p.id, c.nome_empresa, p.codigo_fatura, p.data_fim, p.status
            ORDER BY p.data_fim DESC
        """, tuple(params))
        resultados = cursor.fetchall()

        # 2) Resumo por MÊS (competência)
        cursor.execute(f"""
            SELECT DATE_FORMAT(p.data_fim, '%Y-%m') AS ym,
                   {col_total} AS total, {col_recebido} AS recebido,
                   {col_areceber} AS a_receber, COUNT(DISTINCT p.id) AS qtd
            FROM pedidos p
            JOIN clientes c ON p.id_cliente = c.id
            LEFT JOIN itens_pedido i ON p.id = i.id_pedido
            WHERE 1=1 {where_sql}
            GROUP BY ym ORDER BY ym
        """, tuple(params))
        por_mes = cursor.fetchall()
        for m in por_mes:
            ano, mes = m['ym'].split('-')
            m['label'] = f"{MESES_PT[int(mes) - 1]}/{ano}"

        # 3) Resumo por CLIENTE
        cursor.execute(f"""
            SELECT c.nome_empresa,
                   {col_total} AS total, {col_recebido} AS recebido,
                   {col_areceber} AS a_receber, COUNT(DISTINCT p.id) AS qtd
            FROM pedidos p
            JOIN clientes c ON p.id_cliente = c.id
            LEFT JOIN itens_pedido i ON p.id = i.id_pedido
            WHERE 1=1 {where_sql}
            GROUP BY c.id, c.nome_empresa ORDER BY total DESC
        """, tuple(params))
        por_cliente = cursor.fetchall()

        if resultados:
            total_periodo = sum(r['total'] for r in resultados)
            total_recebido = sum(r['total'] for r in resultados if r['status'] == 'Pago')
            total_a_receber = sum(r['total'] for r in resultados if r['status'] in ['Aprovado', 'Pendente'])

    return render_template("relatorios.html", resultados=resultados,
                           por_mes=por_mes, por_cliente=por_cliente,
                           total_periodo=total_periodo,
                           total_recebido=total_recebido,
                           total_a_receber=total_a_receber,
                           clientes=lista_clientes, grupos=lista_grupos,
                           anos_disponiveis=anos_disponiveis,
                           f_inicio=f_inicio, f_fim=f_fim,
                           f_cliente=f_cliente, f_grupo=f_grupo, f_status=f_status)


@vendas_bp.route("/relatorios/exportar", methods=["POST"])
@login_required
def exportar_relatorio_csv():
    """Exporta o detalhamento do relatório (respeitando os filtros) em CSV.
    Formato amigável ao Excel-BR: separador ';', decimal com vírgula e BOM
    UTF-8 para os acentos abrirem corretos."""
    import csv
    import io
    from flask import Response

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    where_sql, params = _filtros_relatorio(request.form)
    cursor.execute(f"""
        SELECT p.codigo_fatura, c.nome_empresa, COALESCE(g.nome, '') AS grupo,
               DATE_FORMAT(p.data_fim, '%d/%m/%Y') AS competencia, p.status,
               DATE_FORMAT(p.data_pagamento, '%d/%m/%Y') AS pago_em,
               COALESCE(SUM(i.quantidade * i.preco_praticado), 0) AS total
        FROM pedidos p
        JOIN clientes c ON p.id_cliente = c.id
        LEFT JOIN grupos_clientes g ON c.id_grupo = g.id
        LEFT JOIN itens_pedido i ON p.id = i.id_pedido
        WHERE 1=1 {where_sql}
        GROUP BY p.id, p.codigo_fatura, c.nome_empresa, g.nome,
                 p.data_fim, p.status, p.data_pagamento
        ORDER BY p.data_fim DESC, c.nome_empresa
    """, tuple(params))
    linhas = cursor.fetchall()

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Fatura', 'Cliente', 'Grupo', 'Competência', 'Status', 'Pago em', 'Total (R$)'])
    total_geral = 0.0
    for r in linhas:
        total = float(r['total'] or 0)
        total_geral += total
        w.writerow([
            r['codigo_fatura'] or '', r['nome_empresa'] or '', r['grupo'] or '',
            r['competencia'] or '', r['status'] or '', r['pago_em'] or '',
            f"{total:.2f}".replace('.', ','),
        ])
    w.writerow([])
    w.writerow(['', '', '', '', '', 'TOTAL', f"{total_geral:.2f}".replace('.', ',')])

    conteudo = '\ufeff' + buf.getvalue()  # BOM para o Excel reconhecer UTF-8
    log_action('view', entity_type='relatorio',
               descricao=f"Exportou relatório CSV ({len(linhas)} fatura(s))")
    return Response(conteudo, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=relatorio_nutrisabor.csv'})


@vendas_bp.route("/relatorios/demonstrativo")
@login_required
def demonstrativo_faturamento():
    """Demonstrativo de Faturamento (mês a mês, por competência/data_fim) —
    documento de impressão para enviar ao banco.

    Dois modos:
      - SEM ?ano: últimos 12 meses (janela móvel até o mês atual) — padrão.
      - COM ?ano=AAAA: o ano inteiro (Jan–Dez; no ano corrente vai só até o
        mês atual para não exibir meses futuros zerados).
    """
    hoje = datetime.now()
    ano_param = request.args.get('ano')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    linhas, total = [], 0.0

    if ano_param:
        # ── Modo ANO ───────────────────────────────────────────────
        try:
            ano = int(ano_param)
        except (ValueError, TypeError):
            ano = hoje.year
        cursor.execute("""
            SELECT MONTH(p.data_fim) AS m,
                   COALESCE(SUM(i.quantidade * i.preco_praticado), 0) AS total
            FROM pedidos p JOIN itens_pedido i ON i.id_pedido = p.id
            WHERE p.data_fim IS NOT NULL AND YEAR(p.data_fim) = %s
            GROUP BY m
        """, (ano,))
        mapa = {r['m']: float(r['total'] or 0) for r in cursor.fetchall()}
        ultimo = hoje.month if ano == hoje.year else 12
        for m in range(1, ultimo + 1):
            v = round(mapa.get(m, 0.0), 2)
            linhas.append({'mes': MESES_PT[m - 1], 'ano': ano, 'total': v})
            total += v
        periodo_label = f"{MESES_PT[0]} a {MESES_PT[ultimo - 1]} de {ano}"
        modo_sel = str(ano)
    else:
        # ── Modo ÚLTIMOS 12 MESES (janela móvel) ───────────────────
        cursor.execute("""
            SELECT YEAR(p.data_fim) AS y, MONTH(p.data_fim) AS m,
                   COALESCE(SUM(i.quantidade * i.preco_praticado), 0) AS total
            FROM pedidos p JOIN itens_pedido i ON i.id_pedido = p.id
            WHERE p.data_fim IS NOT NULL
              AND p.data_fim >= DATE_FORMAT(CURRENT_DATE() - INTERVAL 11 MONTH, '%Y-%m-01')
            GROUP BY y, m
        """)
        mapa = {(r['y'], r['m']): float(r['total'] or 0) for r in cursor.fetchall()}
        yy, mm = hoje.year, hoje.month - 11
        while mm <= 0:
            mm += 12
            yy -= 1
        y, m = yy, mm
        for _ in range(12):
            v = round(mapa.get((y, m), 0.0), 2)
            linhas.append({'mes': MESES_PT[m - 1], 'ano': y, 'total': v})
            total += v
            m += 1
            if m > 12:
                m = 1
                y += 1
        periodo_label = (f"{linhas[0]['mes']}/{linhas[0]['ano']} a "
                         f"{linhas[-1]['mes']}/{linhas[-1]['ano']}")
        modo_sel = '12m'

    cursor.execute("SELECT DISTINCT YEAR(data_fim) AS ano FROM pedidos WHERE data_fim IS NOT NULL ORDER BY ano DESC")
    anos = [r['ano'] for r in cursor.fetchall()] or [hoje.year]
    cursor.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor.fetchone()

    log_action('view', entity_type='demonstrativo',
               descricao=f"Gerou demonstrativo de faturamento ({periodo_label}, total R${total:.2f})")
    return render_template('demonstrativo.html',
                           linhas=linhas, total=total, anos=anos, modo_sel=modo_sel,
                           empresa=empresa, periodo_label=periodo_label,
                           media=(total / len(linhas)) if linhas else 0,
                           gerado_em=hoje.strftime('%d/%m/%Y às %H:%M'))