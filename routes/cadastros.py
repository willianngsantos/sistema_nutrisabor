from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from database import get_db_connection
from utils.permissions import admin_only
from utils.audit import log_action, format_field_diff
import os
import uuid
from werkzeug.utils import secure_filename

ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def allowed_logo(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS

def save_logo(file):
    """Salva o logo do cliente e retorna o caminho relativo."""
    if not file or file.filename == '':
        return None
    if not allowed_logo(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, filename))
    return f"uploads/logos/{filename}"

cadastros_bp = Blueprint('cadastros', __name__)

@cadastros_bp.route("/cadastros/")
@login_required
def home():
    # Rota legada — redireciona para o dashboard principal
    return redirect(url_for('home'))

# ==========================================
# GESTÃO DE GRUPOS DE CLIENTES
# ==========================================
@cadastros_bp.route("/grupos")
@login_required
def grupos():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # CORRIGIDO PARA PLURAL AQUI
    cursor.execute("SELECT id, nome, chave_pix, pix_nome, pix_banco FROM grupos_clientes ORDER BY nome")
    lista_grupos = cursor.fetchall()
    conn.close()
    return render_template("grupos.html", grupos=lista_grupos)

@cadastros_bp.route("/add_grupo", methods=["POST"])
@login_required
@admin_only
def add_grupo():
    nome = request.form["nome"]
    chave_pix = request.form.get("chave_pix", "").strip()
    pix_nome = request.form.get("pix_nome", "").strip()
    pix_banco = request.form.get("pix_banco", "").strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        INSERT INTO grupos_clientes (nome, chave_pix, pix_nome, pix_banco)
        VALUES (%s, %s, %s, %s)
    """, (nome,
          chave_pix if chave_pix else None,
          pix_nome if pix_nome else None,
          pix_banco if pix_banco else None))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_action('create', entity_type='grupo', entity_id=novo_id,
               descricao=f"Criou grupo '{nome}'")
    flash("Grupo cadastrado com sucesso!", "success")
    return redirect(url_for('cadastros.grupos'))

@cadastros_bp.route("/editar_grupo", methods=["POST"])
@login_required
@admin_only
def editar_grupo():
    id_grupo = request.form["id_grupo"]
    nome = request.form["nome"]
    chave_pix = request.form.get("chave_pix", "").strip()
    pix_nome = request.form.get("pix_nome", "").strip()
    pix_banco = request.form.get("pix_banco", "").strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome, chave_pix, pix_nome, pix_banco FROM grupos_clientes WHERE id=%s", (id_grupo,))
    antes = cursor.fetchone() or {}
    depois = {
        'nome': nome,
        'chave_pix': chave_pix or None,
        'pix_nome': pix_nome or None,
        'pix_banco': pix_banco or None,
    }
    cursor.execute("""
        UPDATE grupos_clientes
        SET nome=%s, chave_pix=%s, pix_nome=%s, pix_banco=%s
        WHERE id=%s
    """, (depois['nome'], depois['chave_pix'], depois['pix_nome'], depois['pix_banco'], id_grupo))
    conn.commit()
    conn.close()

    log_action('update', entity_type='grupo', entity_id=int(id_grupo),
               descricao=f"Editou grupo '{nome}' — {format_field_diff(antes, depois)}")
    flash("Grupo atualizado com sucesso!", "success")
    return redirect(url_for('cadastros.grupos'))

@cadastros_bp.route("/excluir_grupo/<int:id_grupo>", methods=["POST"])
@login_required
@admin_only
def excluir_grupo(id_grupo):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome FROM grupos_clientes WHERE id=%s", (id_grupo,))
    grupo = cursor.fetchone()
    nome_antigo = grupo['nome'] if grupo else f'#{id_grupo}'
    try:
        cursor.execute("DELETE FROM grupos_clientes WHERE id=%s", (id_grupo,))
        conn.commit()
        log_action('delete', entity_type='grupo', entity_id=int(id_grupo),
                   descricao=f"Excluiu grupo '{nome_antigo}'")
        flash("Grupo excluído com sucesso!", "success")
    except Exception:
        flash("Erro: Este grupo possui clientes vinculados e não pode ser excluído.", "danger")
    finally:
        conn.close()
    return redirect(url_for('cadastros.grupos'))


# ==========================================
# GESTÃO DE CLIENTES
# ==========================================
@cadastros_bp.route("/clientes")
@login_required
def clientes():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.id, c.nome_empresa, c.cnpj, c.email, c.celular, g.nome AS nome_grupo, c.id_grupo, c.apelido, c.atende_local, c.logo_path
        FROM clientes c
        LEFT JOIN grupos_clientes g ON c.id_grupo = g.id
        ORDER BY c.nome_empresa
    """)
    lista_clientes = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM grupos_clientes ORDER BY nome")
    lista_grupos = cursor.fetchall()

    conn.close()
    return render_template("clientes.html", clientes=lista_clientes, grupos=lista_grupos)

@cadastros_bp.route("/add_cliente", methods=["POST"])
@login_required
@admin_only
def add_cliente():
    nome = request.form["nome_empresa"]
    apelido = request.form.get("apelido", "").strip()
    cnpj = request.form["cnpj"]
    email = request.form["email"]
    celular = request.form["celular"]
    id_grupo = request.form.get("id_grupo")
    logo_path = save_logo(request.files.get("logo_cliente"))

    if not id_grupo: id_grupo = None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        INSERT INTO clientes (nome_empresa, cnpj, email, celular, id_grupo, apelido, logo_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (nome, cnpj, email, celular, id_grupo, apelido if apelido else None, logo_path))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_action('create', entity_type='cliente', entity_id=novo_id,
               descricao=f"Criou cliente '{nome}' (CNPJ {cnpj})")
    flash("Cliente cadastrado com sucesso!", "success")
    return redirect(url_for('cadastros.clientes'))

@cadastros_bp.route("/editar_cliente", methods=["POST"])
@login_required
@admin_only
def editar_cliente():
    id_cliente = request.form["id_cliente"]
    nome = request.form["nome_empresa"]
    apelido = request.form.get("apelido", "").strip()
    cnpj = request.form["cnpj"]
    email = request.form["email"]
    celular = request.form["celular"]
    id_grupo = request.form.get("id_grupo")
    novo_logo = save_logo(request.files.get("logo_cliente"))
    remover_logo = request.form.get("remover_logo") == "1"

    if not id_grupo: id_grupo = None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Estado ANTES (para diff + pegar logo atual)
    cursor.execute("""
        SELECT nome_empresa, cnpj, email, celular, id_grupo, apelido, logo_path
        FROM clientes WHERE id=%s
    """, (id_cliente,))
    antes = cursor.fetchone() or {}
    logo_atual = antes.get('logo_path')

    if remover_logo:
        logo_path = None
        if logo_atual:
            try:
                os.remove(os.path.join(current_app.root_path, 'static', logo_atual))
            except Exception:
                pass
    elif novo_logo:
        logo_path = novo_logo
        if logo_atual:
            try:
                os.remove(os.path.join(current_app.root_path, 'static', logo_atual))
            except Exception:
                pass
    else:
        logo_path = logo_atual  # mantém o logo existente

    depois = {
        'nome_empresa': nome, 'cnpj': cnpj, 'email': email, 'celular': celular,
        'id_grupo': int(id_grupo) if id_grupo else None,
        'apelido': apelido if apelido else None,
        'logo_path': logo_path,
    }
    cursor2 = conn.cursor(dictionary=True)
    cursor2.execute("""
        UPDATE clientes SET nome_empresa=%s, cnpj=%s, email=%s, celular=%s, id_grupo=%s, apelido=%s, logo_path=%s
        WHERE id=%s
    """, (nome, cnpj, email, celular, id_grupo, apelido if apelido else None, logo_path, id_cliente))
    conn.commit()
    conn.close()

    log_action('update', entity_type='cliente', entity_id=int(id_cliente),
               descricao=f"Editou cliente '{nome}' — {format_field_diff(antes, depois)}")
    flash("Cliente atualizado com sucesso!", "success")
    return redirect(url_for('cadastros.clientes'))

@cadastros_bp.route("/toggle_unidade/<int:id_cliente>", methods=["POST"])
@login_required
@admin_only
def toggle_unidade(id_cliente):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome_empresa, atende_local FROM clientes WHERE id = %s", (id_cliente,))
    cliente = cursor.fetchone()
    if cliente:
        novo = 0 if cliente['atende_local'] else 1
        cursor2 = conn.cursor(dictionary=True)
        cursor2.execute("UPDATE clientes SET atende_local = %s WHERE id = %s", (novo, id_cliente))
        conn.commit()
        acao = "marcado como Unidade de Trabalho" if novo else "removido das Unidades de Trabalho"
        log_action('update', entity_type='cliente', entity_id=int(id_cliente),
                   descricao=f"Cliente '{cliente['nome_empresa']}' {acao}")
        flash(f"{cliente['nome_empresa']} foi {acao}.", "info")
    conn.close()
    return redirect(url_for('cadastros.clientes'))


@cadastros_bp.route("/excluir_cliente/<int:id_cliente>", methods=["POST"])
@login_required
@admin_only
def excluir_cliente(id_cliente):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome_empresa, cnpj FROM clientes WHERE id=%s", (id_cliente,))
    cli = cursor.fetchone() or {}
    nome_antigo = cli.get('nome_empresa') or f'#{id_cliente}'
    try:
        cursor.execute("DELETE FROM tabela_precos WHERE id_cliente=%s", (id_cliente,))
        cursor.execute("DELETE FROM clientes WHERE id=%s", (id_cliente,))
        conn.commit()
        log_action('delete', entity_type='cliente', entity_id=int(id_cliente),
                   descricao=f"Excluiu cliente '{nome_antigo}' (CNPJ {cli.get('cnpj') or '—'})")
        flash("Cliente excluído com sucesso!", "success")
    except Exception:
        conn.rollback()
        flash("Erro: Este cliente possui faturas no histórico e não pode ser excluído.", "danger")
    finally:
        conn.close()
    return redirect(url_for('cadastros.clientes'))


# ==========================================
# GESTÃO DE PRODUTOS
# ==========================================
@cadastros_bp.route("/produtos")
@login_required
def produtos():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, unidade, custo_base FROM produtos ORDER BY nome")
    lista_produtos = cursor.fetchall()
    conn.close()
    return render_template("produtos.html", produtos=lista_produtos)

@cadastros_bp.route("/add_produto", methods=["POST"])
@login_required
@admin_only
def add_produto():
    nome = request.form["nome"]
    unidade = request.form["unidade"]
    custo_str = request.form.get("custo", "").strip()
    
    if not custo_str:
        custo = 0.00
    else:
        try:
            custo = float(custo_str.replace(",", "."))
        except ValueError:
            custo = 0.00
            
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO produtos (nome, unidade, custo_base) VALUES (%s, %s, %s)", (nome, unidade, custo))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_action('create', entity_type='produto', entity_id=novo_id,
               descricao=f"Criou produto '{nome}' ({unidade}) custo R${custo:.2f}")
    flash("Produto adicionado com sucesso!", "success")
    return redirect(url_for('cadastros.produtos'))

@cadastros_bp.route("/editar_produto", methods=["POST"])
@login_required
@admin_only
def editar_produto():
    id_produto = request.form["id_produto"]
    nome = request.form["nome"]
    unidade = request.form["unidade"]
    custo_str = request.form.get("custo", "").strip()
    
    if not custo_str:
        custo = 0.00
    else:
        try:
            custo = float(custo_str.replace(",", "."))
        except ValueError:
            custo = 0.00
            
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome, unidade, custo_base FROM produtos WHERE id=%s", (id_produto,))
    antes = cursor.fetchone() or {}
    if antes.get('custo_base') is not None:
        antes['custo_base'] = float(antes['custo_base'])
    depois = {'nome': nome, 'unidade': unidade, 'custo_base': custo}
    cursor.execute("UPDATE produtos SET nome=%s, unidade=%s, custo_base=%s WHERE id=%s", (nome, unidade, custo, id_produto))
    conn.commit()
    conn.close()

    log_action('update', entity_type='produto', entity_id=int(id_produto),
               descricao=f"Editou produto '{nome}' — {format_field_diff(antes, depois)}")
    flash("Produto atualizado com sucesso!", "success")
    return redirect(url_for('cadastros.produtos'))

@cadastros_bp.route("/excluir_produto/<int:id_prod>", methods=["POST"])
@login_required
@admin_only
def excluir_produto(id_prod):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nome FROM produtos WHERE id=%s", (id_prod,))
    prod = cursor.fetchone()
    nome_antigo = prod['nome'] if prod else f'#{id_prod}'
    try:
        cursor.execute("DELETE FROM produtos WHERE id=%s", (id_prod,))
        conn.commit()
        log_action('delete', entity_type='produto', entity_id=int(id_prod),
                   descricao=f"Excluiu produto '{nome_antigo}'")
        flash("Produto removido!", "success")
    except Exception:
        flash("Erro: Produto vinculado a pedidos.", "danger")
    finally:
        conn.close()
    return redirect(url_for('cadastros.produtos'))

# ==========================================
# NEGOCIAÇÃO DE PREÇOS POR GRUPO
# ==========================================
@cadastros_bp.route("/negociar_grupo/<int:id_grupo>")
@login_required
@admin_only
def negociar_grupo(id_grupo):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True) 
    
    # CORRIGIDO PARA PLURAL AQUI
    cursor.execute("SELECT id, nome FROM grupos_clientes WHERE id = %s", (id_grupo,))
    grupo = cursor.fetchone()
    
    query = """
        SELECT p.id, p.nome, p.unidade, p.custo_base, t.preco_venda 
        FROM produtos p
        LEFT JOIN tabela_precos_grupos t ON p.id = t.id_produto AND t.id_grupo = %s
        ORDER BY p.nome
    """
    cursor.execute(query, (id_grupo,))
    produtos = cursor.fetchall()
    
    conn.close()
    return render_template("negociar_grupo.html", grupo=grupo, produtos=produtos)

@cadastros_bp.route("/salvar_precos_grupo/<int:id_grupo>", methods=["POST"])
@login_required
@admin_only
def salvar_precos_grupo(id_grupo):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT nome FROM grupos_clientes WHERE id=%s", (id_grupo,))
    grupo = cursor.fetchone()
    nome_grupo = grupo['nome'] if grupo else f'#{id_grupo}'

    cursor.execute("DELETE FROM tabela_precos_grupos WHERE id_grupo = %s", (id_grupo,))

    cursor.execute("SELECT id FROM produtos")
    produtos = cursor.fetchall()

    qtd_salvos = 0
    for p in produtos:
        prod_id = p['id']
        preco_str = request.form.get(f"preco_{prod_id}", "").strip()

        if preco_str:
            try:
                preco_venda = float(preco_str.replace(",", "."))
                cursor.execute("""
                    INSERT INTO tabela_precos_grupos (id_grupo, id_produto, preco_venda)
                    VALUES (%s, %s, %s)
                """, (id_grupo, prod_id, preco_venda))
                qtd_salvos += 1
            except ValueError:
                pass

    conn.commit()
    conn.close()

    log_action('update', entity_type='tabela_precos_grupo', entity_id=int(id_grupo),
               descricao=f"Atualizou tabela de preços do grupo '{nome_grupo}': {qtd_salvos} produto(s) com preço")
    flash("Tabela de preços do grupo atualizada com sucesso!", "success")
    return redirect(url_for('cadastros.grupos'))