"""
Migração: adiciona coluna logo_path na tabela clientes
Execute uma vez: python scripts/add_logo_cliente.py
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

    cursor.execute("SHOW COLUMNS FROM clientes LIKE 'logo_path'")
    if cursor.fetchone():
        print("✅ Coluna logo_path já existe. Nada a fazer.")
    else:
        cursor.execute("ALTER TABLE clientes ADD COLUMN logo_path VARCHAR(255) DEFAULT NULL")
        conn.commit()
        print("✅ Coluna logo_path adicionada com sucesso!")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
