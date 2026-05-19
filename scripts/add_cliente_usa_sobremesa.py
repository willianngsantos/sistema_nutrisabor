"""
Migração: adiciona o flag 'usa_sobremesa' na tabela clientes. Quando
desligado, o campo Sobremesa some do formulário de edição do cardápio
e da impressão (PDF) para esse cliente específico.

Padrão: TRUE (todos os clientes existentes continuam exibindo
sobremesa, mantendo compatibilidade com o comportamento atual).

Execute: python scripts/add_cliente_usa_sobremesa.py
Compatível com MySQL 5.7+. Idempotente.
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
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (tabela, coluna))
    return cursor.fetchone()[0] > 0


try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    if col_existe(cursor, 'clientes', 'usa_sobremesa'):
        print("ℹ️  Coluna 'usa_sobremesa' já existe — nada a fazer.")
    else:
        cursor.execute(
            "ALTER TABLE clientes "
            "ADD COLUMN usa_sobremesa TINYINT(1) NOT NULL DEFAULT 1"
        )
        conn.commit()
        print("✅ Coluna 'usa_sobremesa' adicionada em clientes (default = 1).")

    # Mostra estado atual dos clientes Unidade de Trabalho para conferência
    cursor.execute("""
        SELECT id, nome_empresa, atende_local, usa_sobremesa
        FROM clientes
        WHERE atende_local = 1
        ORDER BY nome_empresa
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n📋 Clientes Unidade de Trabalho (que recebem cardápio):")
        for r in rows:
            usa = 'SIM' if r[3] else 'NÃO'
            print(f"   #{r[0]} {r[1]} — usa sobremesa: {usa}")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
