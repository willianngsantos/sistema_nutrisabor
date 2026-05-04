"""
Migração: adiciona campos de dados bancários do colaborador (agência e
conta), preenchidos depois que a conta é aberta no banco. Quando ambos
estão preenchidos, o colaborador deixa de aparecer no dropdown de
'Solicitação de Conta Salário'.

Execute: python scripts/add_colab_dados_bancarios.py
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


COLUNAS = [
    ('agencia', "VARCHAR(20) DEFAULT NULL"),
    ('conta',   "VARCHAR(30) DEFAULT NULL"),
    # Banco: guardado como "<código> - <nome>" (ex: "033 - Santander").
    # Mantemos como string única para evitar tabela de domínio só pra isso.
    ('banco',   "VARCHAR(80) DEFAULT NULL"),
]

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    adicionadas = []
    ja_existiam = []
    for col, defn in COLUNAS:
        if col_existe(cursor, 'colaboradores', col):
            ja_existiam.append(col)
        else:
            cursor.execute(f"ALTER TABLE colaboradores ADD COLUMN {col} {defn}")
            adicionadas.append(col)

    conn.commit()
    if adicionadas:
        print(f"✅ Colunas adicionadas: {', '.join(adicionadas)}")
    if ja_existiam:
        print(f"ℹ️  Já existiam: {', '.join(ja_existiam)}")
    if not adicionadas and not ja_existiam:
        print("⚠️  Nada a fazer.")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
