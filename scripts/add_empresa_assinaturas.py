"""
Migração: adiciona à tabela empresa os dados de assinatura usados no
Demonstrativo de Faturamento (banco):
  - dois sócios/proprietários (nome + CPF)
  - contador responsável (nome + CRC)

Semeia os nomes/CRC já informados; os CPFs ficam em branco para preencher
na tela "Minha Empresa". Idempotente.

Execute: python scripts/add_empresa_assinaturas.py
"""
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

db_config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'nutrisabor'),
}

COLUNAS = [
    ("socio1_nome",   "VARCHAR(120) DEFAULT NULL"),
    ("socio1_cpf",    "VARCHAR(20)  DEFAULT NULL"),
    ("socio2_nome",   "VARCHAR(120) DEFAULT NULL"),
    ("socio2_cpf",    "VARCHAR(20)  DEFAULT NULL"),
    ("contador_nome", "VARCHAR(120) DEFAULT NULL"),
    ("contador_crc",  "VARCHAR(40)  DEFAULT NULL"),
]

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    for nome, tipo in COLUNAS:
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'empresa' AND COLUMN_NAME = %s
        """, (nome,))
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"ALTER TABLE empresa ADD COLUMN {nome} {tipo}")
            print(f"  + coluna {nome} adicionada")
    conn.commit()

    # Semeia os valores informados (só onde ainda estiver vazio)
    seeds = {
        'socio1_nome':   'WILLIAN GOMES DOS SANTOS',
        'socio2_nome':   'GIUCIMAR FLAVIANO DE PIETRO',
        'contador_nome': 'Agnaldo Bertachini',
        'contador_crc':  '1SP219627/O-0',
    }
    for col, val in seeds.items():
        cursor.execute(
            f"UPDATE empresa SET {col}=%s WHERE id=1 AND ({col} IS NULL OR {col}='')",
            (val,)
        )
    conn.commit()
    conn.close()
    print("✅ Campos de assinatura prontos (nomes/CRC semeados; preencha os CPFs em Minha Empresa).")
except Exception as e:
    print(f"❌ ERRO: {e}")
