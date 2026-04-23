"""
Migração: adiciona campos de horário de almoço na folha de ponto
Execute: python scripts/add_ponto_almoco.py
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

def col_existe(cursor, tabela, coluna):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (tabela, coluna))
    return cursor.fetchone()[0] > 0

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    if not col_existe(cursor, 'rh_ponto', 'hora_saida_almoco'):
        cursor.execute("""
            ALTER TABLE rh_ponto
            ADD COLUMN hora_saida_almoco TIME DEFAULT NULL AFTER hora_entrada
        """)
        print("✅ Coluna hora_saida_almoco adicionada!")
    else:
        print("ℹ️  hora_saida_almoco já existe.")

    if not col_existe(cursor, 'rh_ponto', 'hora_retorno_almoco'):
        cursor.execute("""
            ALTER TABLE rh_ponto
            ADD COLUMN hora_retorno_almoco TIME DEFAULT NULL AFTER hora_saida_almoco
        """)
        print("✅ Coluna hora_retorno_almoco adicionada!")
    else:
        print("ℹ️  hora_retorno_almoco já existe.")

    conn.commit()
    conn.close()
    print("✅ Migração concluída!")
except Exception as e:
    print(f"❌ ERRO: {e}")
