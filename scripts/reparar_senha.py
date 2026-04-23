import mysql.connector
from werkzeug.security import generate_password_hash

# Configuração do Banco
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Wgs010203',
    'database': 'cozinha_industrial'
}

try:
    print("🔄 Conectando ao banco de dados...")
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    # Dados do Admin
    email_admin = "admin@nutrisabor.com"
    senha_nova = "admin123"
    
    # GERA O HASH USANDO O SEU COMPUTADOR
    # Isso garante compatibilidade total
    hash_correto = generate_password_hash(senha_nova)

    # Verifica se o usuário já existe
    cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email_admin,))
    existe = cursor.fetchone()

    if existe:
        print(f"👤 Usuário {email_admin} encontrado. Atualizando a senha...")
        cursor.execute("UPDATE usuarios SET senha_hash = %s WHERE email = %s", (hash_correto, email_admin))
    else:
        print(f"➕ Usuário não existia. Criando {email_admin} agora...")
        cursor.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)", 
                       ("Administrador", email_admin, hash_correto))

    conn.commit()
    print("✅ SUCESSO TOTAL!")
    print(f"Sua senha foi redefinida para: {senha_nova}")

except Exception as e:
    print(f"❌ Erro ao tentar corrigir: {e}")

finally:
    if 'conn' in locals() and conn.is_connected():
        conn.close()