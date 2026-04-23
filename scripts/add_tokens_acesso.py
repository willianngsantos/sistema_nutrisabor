"""
Migração: cria tabela tokens_acesso e torna senha_hash opcional em usuarios
Execute uma vez: python scripts/add_tokens_acesso.py
"""
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

db_config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'nutrisabor'),
}

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    # Tabela de tokens
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens_acesso (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            email       VARCHAR(120) NOT NULL,
            token       VARCHAR(6) NOT NULL,
            tipo        ENUM('primeiro_acesso','reset_senha') NOT NULL,
            expira_em   DATETIME NOT NULL,
            usado       TINYINT(1) DEFAULT 0,
            criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Tabela tokens_acesso criada!")

    # Torna senha_hash opcional (para usuários sem senha ainda)
    cursor.execute("""
        ALTER TABLE usuarios MODIFY COLUMN senha_hash VARCHAR(255) NULL DEFAULT NULL
    """)
    print("✅ Coluna senha_hash agora é opcional!")

    conn.commit()
    conn.close()
    print("\n🎉 Migração concluída com sucesso!")

except Exception as e:
    print(f"❌ ERRO: {e}")
