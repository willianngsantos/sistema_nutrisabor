"""
Migração: adiciona campos CBO e CTPS no cadastro do colaborador, e
o vínculo opcional com uma jornada de trabalho (FK em rh_jornadas).

  - cbo         VARCHAR(15)  — Classificação Brasileira de Ocupações
                               (formato típico: '5132-25').
  - ctps        VARCHAR(30)  — Número da Carteira de Trabalho.
  - id_jornada  INT NULL FK  — jornada vinculada (ON DELETE SET NULL,
                               para nunca quebrar o cadastro caso a
                               jornada seja apagada acidentalmente).

Padrão: tudo NULL — colaboradores existentes continuam funcionando
normalmente. Quem precisar, edita pelo cadastro.

Execute: python scripts/add_colab_cbo_ctps_jornada.py
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


def fk_existe(cursor, tabela, coluna):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """, (tabela, coluna))
    return cursor.fetchone()[0] > 0


COLUNAS = [
    ('cbo',        "VARCHAR(15) DEFAULT NULL"),
    ('ctps',       "VARCHAR(30) DEFAULT NULL"),
    ('id_jornada', "INT DEFAULT NULL"),
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

    # Foreign key separada (mais robusta — só cria se ainda não existir)
    if col_existe(cursor, 'colaboradores', 'id_jornada') and not fk_existe(cursor, 'colaboradores', 'id_jornada'):
        try:
            cursor.execute("""
                ALTER TABLE colaboradores
                ADD CONSTRAINT fk_colab_jornada
                FOREIGN KEY (id_jornada) REFERENCES rh_jornadas(id)
                ON DELETE SET NULL
            """)
            print("✅ FK fk_colab_jornada criada (colaboradores.id_jornada → rh_jornadas.id)")
        except mysql.connector.Error as fe:
            # Pode acontecer se a tabela rh_jornadas ainda não existir
            # nesse banco. Não é fatal — apenas avisa.
            print(f"⚠️  Não foi possível criar a FK (tabela rh_jornadas existe?): {fe}")

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
