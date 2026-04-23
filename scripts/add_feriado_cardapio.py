"""
Migração: adiciona coluna feriado em itens_cardapio
Execute: python scripts/add_feriado_cardapio.py
Compatível com MySQL 5.7+
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

    # Verifica se a coluna já existe (compatível com MySQL 5.7+)
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'itens_cardapio'
          AND COLUMN_NAME = 'feriado'
    """)
    existe = cursor.fetchone()[0]

    if existe:
        print("ℹ️  Coluna feriado já existe em itens_cardapio — nada a fazer.")
    else:
        cursor.execute("""
            ALTER TABLE itens_cardapio
            ADD COLUMN feriado TINYINT(1) NOT NULL DEFAULT 0
        """)
        conn.commit()
        print("✅ Coluna feriado adicionada em itens_cardapio!")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
