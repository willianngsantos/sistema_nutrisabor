"""
Migração: adiciona coluna 'beneficio' em rh_reajustes.

Antes o reajuste só atingia o salário; agora pode atingir salário, vale
transporte, vale refeição ou diversos. A coluna registra qual benefício foi
reajustado em cada lançamento do histórico. Também garante que a coluna 'tipo'
comporte o novo modo 'final' (valor final/absoluto).

Execute: python scripts/add_reajuste_beneficio.py
Idempotente — pode rodar várias vezes.
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

    # 1) Coluna 'beneficio'
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'rh_reajustes'
          AND COLUMN_NAME = 'beneficio'
    """)
    if cursor.fetchone()[0]:
        print("ℹ️  Coluna 'beneficio' já existe em rh_reajustes — nada a fazer.")
    else:
        cursor.execute("""
            ALTER TABLE rh_reajustes
            ADD COLUMN beneficio VARCHAR(30) NOT NULL DEFAULT 'salario_bruto' AFTER tipo
        """)
        conn.commit()
        print("✅ Coluna 'beneficio' adicionada (default 'salario_bruto' p/ histórico antigo).")

    # 2) Garante que 'tipo' seja VARCHAR largo o bastante para 'percentual'/'fixo'/'final'
    cursor.execute("""
        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'rh_reajustes' AND COLUMN_NAME = 'tipo'
    """)
    row = cursor.fetchone()
    if row:
        data_type, maxlen = row[0], row[1]
        # ENUM('percentual','fixo') NÃO aceitaria o novo modo 'final'.
        # Convertemos para VARCHAR(20) — comporta qualquer modo futuro.
        if data_type.lower() == 'enum' or (data_type.lower() in ('varchar', 'char') and (maxlen or 0) < 12):
            cursor.execute("ALTER TABLE rh_reajustes MODIFY COLUMN tipo VARCHAR(20) NOT NULL")
            conn.commit()
            print(f"✅ Coluna 'tipo' convertida para VARCHAR(20) (era {data_type}).")
        else:
            print(f"ℹ️  Coluna 'tipo' já comporta os valores ({data_type}({maxlen})).")

    conn.close()
    print("✅ Migração concluída.")
except Exception as e:
    print(f"❌ ERRO: {e}")
