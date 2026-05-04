"""
Migração: adiciona campos pessoais e de endereço à tabela colaboradores,
necessários para a geração de documentos legais (ex: solicitação de
abertura de conta salário ao banco).

Campos adicionados (todos opcionais — NULL):
- rg                   identidade
- cpf
- endereco_cep
- endereco_logradouro  (rua/av)
- endereco_numero
- endereco_complemento (apto, bloco, etc — opcional)
- endereco_bairro
- endereco_cidade
- endereco_uf          (2 chars)
- crn3                 conselho regional (apenas para função=Nutricionista)

Execute: python scripts/add_colab_dados_completos.py
Compatível com MySQL 5.7+. Idempotente (verifica cada coluna antes de criar).
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
    ('rg',                   "VARCHAR(20) DEFAULT NULL"),
    ('cpf',                  "VARCHAR(14) DEFAULT NULL"),
    ('endereco_cep',         "VARCHAR(10) DEFAULT NULL"),
    ('endereco_logradouro',  "VARCHAR(200) DEFAULT NULL"),
    ('endereco_numero',      "VARCHAR(20) DEFAULT NULL"),
    ('endereco_complemento', "VARCHAR(100) DEFAULT NULL"),
    ('endereco_bairro',      "VARCHAR(100) DEFAULT NULL"),
    ('endereco_cidade',      "VARCHAR(100) DEFAULT NULL"),
    ('endereco_uf',          "VARCHAR(2) DEFAULT NULL"),
    ('crn3',                 "VARCHAR(20) DEFAULT NULL"),
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
