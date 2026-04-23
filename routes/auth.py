import random
import string
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection
from models import User
from email_utils import email_codigo

auth_bp = Blueprint('auth', __name__)


def _gerar_token(n=6):
    """Gera um código numérico de N dígitos."""
    return ''.join(random.choices(string.digits, k=n))


def _criar_token(cursor, conn, email: str, tipo: str) -> str:
    """Invalida tokens anteriores, gera novo e salva no banco. Retorna o código."""
    # Invalida tokens anteriores do mesmo tipo para este e-mail
    cursor.execute(
        "UPDATE tokens_acesso SET usado=1 WHERE email=%s AND tipo=%s AND usado=0",
        (email, tipo)
    )
    codigo = _gerar_token()
    expira_em = datetime.now() + timedelta(minutes=15)
    cursor.execute(
        "INSERT INTO tokens_acesso (email, token, tipo, expira_em) VALUES (%s,%s,%s,%s)",
        (email, codigo, tipo, expira_em)
    )
    conn.commit()
    return codigo


# ─────────────────────────────────────────────────────────
#  LOGIN / LOGOUT
# ─────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nome, email, senha_hash, tipo FROM usuarios WHERE email = %s",
            (email,)
        )
        usuario_db = cursor.fetchone()
        conn.close()

        # Usuário sem senha cadastrada ainda → redireciona para Primeiro Acesso
        if usuario_db and not usuario_db['senha_hash']:
            flash('Você ainda não definiu uma senha. Use "Primeiro Acesso" abaixo.', 'warning')
            return redirect(url_for('auth.login'))

        if usuario_db and usuario_db['senha_hash'] and check_password_hash(usuario_db['senha_hash'], senha):
            usuario_objeto = User(
                id=usuario_db['id'],
                nome=usuario_db['nome'],
                email=usuario_db['email'],
                tipo=usuario_db.get('tipo', 'vendedor')
            )
            session.permanent = False
            login_user(usuario_objeto, remember=False)
            return redirect(url_for('home'))
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────
#  PRIMEIRO ACESSO
# ─────────────────────────────────────────────────────────

@auth_bp.route('/primeiro_acesso', methods=['GET', 'POST'])
def primeiro_acesso():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, senha_hash FROM usuarios WHERE email = %s",
            (email,)
        )
        usuario = cursor.fetchone()

        if not usuario:
            flash('E-mail não encontrado. Contate o administrador.', 'danger')
            conn.close()
            return redirect(url_for('auth.primeiro_acesso'))

        if usuario['senha_hash']:
            flash('Este e-mail já possui uma senha definida. Use "Esqueci minha senha" se precisar redefinir.', 'warning')
            conn.close()
            return redirect(url_for('auth.login'))

        codigo = _criar_token(cursor, conn, email, 'primeiro_acesso')
        conn.close()

        enviado = email_codigo(email, codigo, 'primeiro_acesso')
        if enviado:
            flash('Código enviado! Verifique sua caixa de entrada.', 'success')
        else:
            flash('Erro ao enviar e-mail. Tente novamente ou contate o suporte.', 'danger')
            return redirect(url_for('auth.primeiro_acesso'))

        session['verificacao_email'] = email
        session['verificacao_tipo'] = 'primeiro_acesso'
        return redirect(url_for('auth.validar_codigo'))

    return render_template('solicitar_codigo.html', tipo='primeiro_acesso')


# ─────────────────────────────────────────────────────────
#  ESQUECI MINHA SENHA
# ─────────────────────────────────────────────────────────

@auth_bp.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
        usuario = cursor.fetchone()

        # Segurança: não revela se o e-mail existe ou não
        if usuario:
            codigo = _criar_token(cursor, conn, email, 'reset_senha')
            conn.close()
            email_codigo(email, codigo, 'reset_senha')
        else:
            conn.close()

        flash('Se o e-mail estiver cadastrado, você receberá o código em instantes.', 'info')
        session['verificacao_email'] = email
        session['verificacao_tipo'] = 'reset_senha'
        return redirect(url_for('auth.validar_codigo'))

    return render_template('solicitar_codigo.html', tipo='reset_senha')


# ─────────────────────────────────────────────────────────
#  VALIDAR CÓDIGO + DEFINIR NOVA SENHA
# ─────────────────────────────────────────────────────────

@auth_bp.route('/validar_codigo', methods=['GET', 'POST'])
def validar_codigo():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    email = session.get('verificacao_email')
    tipo = session.get('verificacao_tipo')

    if not email or not tipo:
        flash('Sessão expirada. Comece novamente.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        codigo_digitado = request.form.get('codigo', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        if nova_senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return render_template('validar_codigo.html', email=email, tipo=tipo)

        if len(nova_senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
            return render_template('validar_codigo.html', email=email, tipo=tipo)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id FROM tokens_acesso
            WHERE email=%s AND token=%s AND tipo=%s AND usado=0 AND expira_em > NOW()
            ORDER BY criado_em DESC LIMIT 1
        """, (email, codigo_digitado, tipo))
        token_row = cursor.fetchone()

        if not token_row:
            conn.close()
            flash('Código inválido ou expirado. Solicite um novo.', 'danger')
            return render_template('validar_codigo.html', email=email, tipo=tipo)

        # Marca token como usado e salva nova senha
        cursor.execute(
            "UPDATE tokens_acesso SET usado=1 WHERE id=%s",
            (token_row['id'],)
        )
        senha_hash = generate_password_hash(nova_senha)
        cursor.execute(
            "UPDATE usuarios SET senha_hash=%s WHERE email=%s",
            (senha_hash, email)
        )
        conn.commit()
        conn.close()

        session.pop('verificacao_email', None)
        session.pop('verificacao_tipo', None)

        flash('Senha definida com sucesso! Faça o login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('validar_codigo.html', email=email, tipo=tipo)


# ─────────────────────────────────────────────────────────
#  GERENCIAR USUÁRIOS
# ─────────────────────────────────────────────────────────

@auth_bp.route("/usuarios")
@login_required
def listar_usuarios():
    if current_user.tipo != 'admin':
        flash("Acesso negado. Área restrita a administradores.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, email, tipo, senha_hash FROM usuarios")
    lista_usuarios = cursor.fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=lista_usuarios)


@auth_bp.route("/add_usuario", methods=["POST"])
@login_required
def add_usuario():
    if current_user.tipo != 'admin':
        return redirect(url_for('home'))

    nome = request.form["nome"]
    email = request.form["email"].strip().lower()
    senha_plana = request.form.get("senha", "").strip()
    tipo = request.form["tipo"]

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if senha_plana:
            senha_segura = generate_password_hash(senha_plana)
            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s)",
                (nome, email, senha_segura, tipo)
            )
        else:
            # Sem senha: usuário deverá usar "Primeiro Acesso"
            cursor.execute(
                "INSERT INTO usuarios (nome, email, tipo) VALUES (%s, %s, %s)",
                (nome, email, tipo)
            )
        conn.commit()
        flash(f"Usuário {nome} criado com sucesso! Oriente-o a usar 'Primeiro Acesso' na tela de login.", "success")
    except Exception:
        flash("Erro ao criar usuário. E-mail já pode estar em uso.", "danger")
    finally:
        conn.close()
    return redirect(url_for('auth.listar_usuarios'))


@auth_bp.route("/editar_usuario", methods=["POST"])
@login_required
def editar_usuario():
    if current_user.tipo != 'admin':
        return redirect(url_for('home'))

    id_usuario = request.form["id_usuario"]
    nome       = request.form["nome"].strip()
    email      = request.form["email"].strip()
    tipo       = request.form["tipo"]
    senha      = request.form.get("senha", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if senha:
            senha_hash = generate_password_hash(senha)
            cursor.execute("""
                UPDATE usuarios SET nome=%s, email=%s, tipo=%s, senha_hash=%s WHERE id=%s
            """, (nome, email, tipo, senha_hash, id_usuario))
        else:
            cursor.execute("""
                UPDATE usuarios SET nome=%s, email=%s, tipo=%s WHERE id=%s
            """, (nome, email, tipo, id_usuario))
        conn.commit()
        flash("Usuário atualizado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar usuário: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('auth.listar_usuarios'))


@auth_bp.route("/excluir_usuario/<int:id_user>")
@login_required
def excluir_usuario(id_user):
    if current_user.tipo != 'admin':
        return redirect(url_for('home'))

    if id_user == current_user.id:
        flash("Você não pode excluir a sua própria conta!", "warning")
        return redirect(url_for('auth.listar_usuarios'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (id_user,))
        conn.commit()
        flash("Usuário removido com sucesso!", "success")
    except Exception:
        flash("Erro ao remover usuário.", "danger")
    finally:
        conn.close()
    return redirect(url_for('auth.listar_usuarios'))


@auth_bp.route("/configuracao_empresa", methods=["GET", "POST"])
@login_required
def configuracao_empresa():
    if current_user.tipo != 'admin':
        flash("Acesso negado. Apenas administradores configuram a empresa.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        dados = (
            request.form["razao_social"], request.form["cnpj"], request.form["cep"],
            request.form["endereco"], request.form["cidade"], request.form["estado"],
            request.form["telefone"], request.form["email"], request.form["banco_nome"],
            request.form["agencia"], request.form["conta"], request.form["pix_chave"]
        )
        cursor.execute("""
            UPDATE empresa
            SET razao_social=%s, cnpj=%s, cep=%s, endereco=%s, cidade=%s, estado=%s,
                telefone=%s, email=%s, banco_nome=%s, agencia=%s, conta=%s, pix_chave=%s
            WHERE id=1
        """, dados)
        conn.commit()
        flash("Dados da empresa atualizados com sucesso!", "success")

    cursor.execute("SELECT * FROM empresa WHERE id = 1")
    empresa = cursor.fetchone()
    conn.close()

    return render_template("config_empresa.html", empresa=empresa)
