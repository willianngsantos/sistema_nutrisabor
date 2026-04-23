"""
Migração: adiciona coluna data_pagamento em pedidos
Execute: python scripts/add_data_pagamento.py
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

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'pedidos'
          AND COLUMN_NAME = 'data_pagamento'
    """)
    existe = cursor.fetchone()[0]

    if existe:
        print("ℹ️  Coluna data_pagamento já existe em pedidos — nada a fazer.")
    else:
        cursor.execute("""
            ALTER TABLE pedidos
            ADD COLUMN data_pagamento DATE DEFAULT NULL AFTER numero_nf
        """)
        conn.commit()
        print("✅ Coluna data_pagamento adicionada em pedidos!")

        # Backfill: para faturas já marcadas como Pago, preenche com data_fim
        # como melhor aproximação retroativa (usuário pode ajustar depois)
        cursor.execute("""
            UPDATE pedidos
            SET data_pagamento = data_fim
            WHERE status = 'Pago' AND data_pagamento IS NULL
        """)
        afetados = cursor.rowcount
        conn.commit()
        if afetados:
            print(f"ℹ️  Backfill: {afetados} fatura(s) Paga(s) receberam data_pagamento = data_fim.")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
