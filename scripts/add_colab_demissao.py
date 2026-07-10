"""
Migração: adiciona a coluna data_demissao em colaboradores.

O status 'demitido' passa a existir ao lado de ativo/ferias/afastado/inativo.
A coluna `status` já é VARCHAR(20), então aceita o novo valor sem alteração de
tipo — só falta guardar a data do desligamento.

Idempotente. Execute: python scripts/add_colab_demissao.py
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

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'colaboradores' AND COLUMN_NAME = 'data_demissao'
    """)
    if cursor.fetchone()[0]:
        print("ℹ️  Coluna data_demissao já existe — nada a fazer.")
    else:
        cursor.execute("""
            ALTER TABLE colaboradores
            ADD COLUMN data_demissao DATE DEFAULT NULL AFTER data_admissao
        """)
        conn.commit()
        print("✅ Coluna data_demissao adicionada em colaboradores.")

    # Garante que a coluna status comporta 'demitido' (8 chars)
    cursor.execute("""
        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'colaboradores' AND COLUMN_NAME = 'status'
    """)
    row = cursor.fetchone()
    if row:
        tipo, tam = row[0].lower(), row[1] or 0
        if tipo == 'enum' or (tipo in ('varchar', 'char') and tam < 10):
            cursor.execute("ALTER TABLE colaboradores MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ativo'")
            conn.commit()
            print(f"✅ Coluna status ajustada para VARCHAR(20) (era {tipo}).")
        else:
            print(f"ℹ️  Coluna status já comporta 'demitido' ({tipo}({tam})).")

    conn.close()
    print("✅ Migração concluída.")
except Exception as e:
    print(f"❌ ERRO: {e}")
