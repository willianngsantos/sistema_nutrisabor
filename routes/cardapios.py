from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db_connection
from datetime import datetime, timedelta, date

cardapios_bp = Blueprint('cardapios', __name__)

# Dias da semana em português
DIAS_SEMANA = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

@cardapios_bp.route("/cardapios")
@login_required
def index():
    if current_user.tipo not in ['admin', 'nutricionista', 'gerencial']:
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Lista cardápios com nome do cliente (inclui data_fim raw para comparação)
    cursor.execute("""
        SELECT ca.id, c.nome_empresa,
               DATE_FORMAT(ca.data_inicio, '%d/%m/%Y') as inicio,
               DATE_FORMAT(ca.data_fim, '%d/%m/%Y') as fim,
               ca.data_fim as data_fim_raw,
               ca.editado_por,
               DATE_FORMAT(ca.editado_em, '%d/%m/%Y às %H:%i') as editado_em
        FROM cardapios ca
        JOIN clientes c ON ca.id_cliente = c.id
        ORDER BY ca.data_fim DESC
    """)
    todos = cursor.fetchall()

    hoje = date.today()
    cardapios_ativos   = [c for c in todos if c['data_fim_raw'] >= hoje]
    cardapios_passados = [c for c in todos if c['data_fim_raw'] <  hoje]

    # Busca apenas clientes com Unidade de Trabalho para o Modal de "Novo Cardápio"
    cursor.execute("SELECT id, nome_empresa FROM clientes WHERE atende_local = 1 ORDER BY nome_empresa")
    clientes = cursor.fetchall()

    conn.close()
    return render_template("cardapios.html",
                           cardapios_ativos=cardapios_ativos,
                           cardapios_passados=cardapios_passados,
                           clientes=clientes)

@cardapios_bp.route("/cardapios/novo", methods=["POST"])
@login_required
def novo_cardapio():
    id_cliente = request.form.get("id_cliente")
    data_inicio_str = request.form.get("data_inicio")
    dias_qnt = int(request.form.get("dias_qnt", 5)) # Pode ser 5 (Seg-Sex) ou 6 (Seg-Sab)

    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d')
        data_fim = data_inicio + timedelta(days=(dias_qnt - 1))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Cria o Cardápio "Pai"
        cursor.execute("INSERT INTO cardapios (id_cliente, data_inicio, data_fim) VALUES (%s, %s, %s)", 
                       (id_cliente, data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d')))
        id_cardapio = cursor.lastrowid
        
        # Cria os dias da semana automaticamente!
        for i in range(dias_qnt):
            data_dia = data_inicio + timedelta(days=i)
            nome_dia = DIAS_SEMANA[data_dia.weekday()]
            
            cursor.execute("""
                INSERT INTO itens_cardapio (id_cardapio, dia_semana, data_dia, base) 
                VALUES (%s, %s, %s, 'Arroz e Feijão')
            """, (id_cardapio, nome_dia, data_dia.strftime('%Y-%m-%d')))
            
        conn.commit()
        conn.close()
        
        flash("Estrutura do cardápio gerada! Agora preencha os pratos.", "success")
        return redirect(url_for('cardapios.montar_cardapio', id_cardapio=id_cardapio))
    except Exception as e:
        flash(f"Erro ao gerar cardápio: {e}", "danger")
        return redirect(url_for('cardapios.index'))

@cardapios_bp.route("/cardapios/montar/<int:id_cardapio>")
@login_required
def montar_cardapio(id_cardapio):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT ca.*, c.nome_empresa 
        FROM cardapios ca JOIN clientes c ON ca.id_cliente = c.id 
        WHERE ca.id = %s
    """, (id_cardapio,))
    cardapio = cursor.fetchone()
    
    cursor.execute("SELECT * FROM itens_cardapio WHERE id_cardapio = %s ORDER BY data_dia", (id_cardapio,))
    itens = cursor.fetchall()
    
    conn.close()
    return render_template("form_cardapio.html", cardapio=cardapio, itens=itens)

@cardapios_bp.route("/cardapios/salvar_itens/<int:id_cardapio>", methods=["POST"])
@login_required
def salvar_itens(id_cardapio):
    observacoes = request.form.get("observacoes", "")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Atualiza observações + registra quem editou e quando
    cursor.execute("""
        UPDATE cardapios
        SET observacoes = %s, editado_por = %s, editado_em = NOW()
        WHERE id = %s
    """, (observacoes, current_user.nome, id_cardapio))

    # Atualiza cada dia
    cursor.execute("SELECT id FROM itens_cardapio WHERE id_cardapio = %s", (id_cardapio,))
    dias = cursor.fetchall()

    for dia in dias:
        dia_id = dia['id']
        base = request.form.get(f"base_{dia_id}")
        p1 = request.form.get(f"p1_{dia_id}")
        p2 = request.form.get(f"p2_{dia_id}")
        guarnicao = request.form.get(f"guarnicao_{dia_id}")
        salada = request.form.get(f"salada_{dia_id}")
        sobremesa = request.form.get(f"sobremesa_{dia_id}")
        bebida = request.form.get(f"bebida_{dia_id}")
        feriado = 1 if request.form.get(f"feriado_{dia_id}") else 0

        cursor.execute("""
            UPDATE itens_cardapio
            SET base=%s, principal1=%s, principal2=%s, guarnicao=%s, salada=%s, sobremesa=%s, bebida=%s, feriado=%s
            WHERE id=%s
        """, (base, p1, p2, guarnicao, salada, sobremesa, bebida, feriado, dia_id))
        
    conn.commit()
    conn.close()
    flash("Cardápio salvo com sucesso!", "success")
    return redirect(url_for('cardapios.index'))

@cardapios_bp.route("/cardapios/imprimir/<int:id_cardapio>")
@login_required
def imprimir_cardapio(id_cardapio):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT ca.*, c.nome_empresa, c.logo_path
        FROM cardapios ca JOIN clientes c ON ca.id_cliente = c.id
        WHERE ca.id = %s
    """, (id_cardapio,))
    cardapio = cursor.fetchone()

    cursor.execute("SELECT * FROM itens_cardapio WHERE id_cardapio = %s ORDER BY data_dia", (id_cardapio,))
    itens = cursor.fetchall()

    cursor.execute("SELECT razao_social FROM empresa WHERE id = 1")
    empresa = cursor.fetchone()

    conn.close()
    return render_template("imprimir_cardapio.html", cardapio=cardapio, itens=itens, empresa=empresa)


@cardapios_bp.route("/cardapios/excluir/<int:id_cardapio>", methods=["POST"])
@login_required
def excluir_cardapio(id_cardapio):
    if current_user.tipo != 'admin':
        flash("Apenas administradores podem excluir cardápios.", "danger")
        return redirect(url_for('cardapios.index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM itens_cardapio WHERE id_cardapio = %s", (id_cardapio,))
    cursor.execute("DELETE FROM cardapios WHERE id = %s", (id_cardapio,))
    conn.commit()
    conn.close()

    flash("Cardápio excluído com sucesso.", "success")
    return redirect(url_for('cardapios.index'))