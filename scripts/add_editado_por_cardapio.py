"""
Migração: adiciona colunas editado_por e editado_em em cardapios
Execute: python scripts/add_editado_por_cardapio.py
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

def coluna_existe(cursor, tabela, coluna):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (tabela, coluna))
    return cursor.fetchone()[0] > 0

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    if not coluna_existe(cursor, 'cardapios', 'editado_por'):
        cursor.execute("ALTER TABLE cardapios ADD COLUMN editado_por VARCHAR(120) DEFAULT NULL")
        print("✅ Coluna editado_por adicionada em cardapios!")
    else:
        print("ℹ️  editado_por já existe.")

    if not coluna_existe(cursor, 'cardapios', 'editado_em'):
        cursor.execute("ALTER TABLE cardapios ADD COLUMN editado_em DATETIME DEFAULT NULL")
        print("✅ Coluna editado_em adicionada em cardapios!")
    else:
        print("ℹ️  editado_em já existe.")

    conn.commit()
    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
