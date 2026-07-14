"""
Migração: índice UNIQUE em tabela_precos (id_cliente, id_produto)
Execute: python scripts/add_tabela_precos_unique.py
Compatível com MySQL 5.7+

Um cliente não pode ter dois preços para o mesmo produto (o preço praticado
ficaria ambíguo). A gravação já é DELETE+INSERT, mas o índice fecha a porta para
duplicata por concorrência/falha parcial. Idempotente; se houver duplicata
legada, NÃO aborta o deploy — apenas avisa.
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
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'tabela_precos'
          AND INDEX_NAME = 'uq_tabela_precos_cli_prod'
    """)
    if cursor.fetchone()[0]:
        print("ℹ️  Índice uq_tabela_precos_cli_prod já existe — nada a fazer.")
    else:
        cursor.execute("""
            SELECT id_cliente, id_produto, COUNT(*) c FROM tabela_precos
            GROUP BY id_cliente, id_produto HAVING c > 1
        """)
        dups = cursor.fetchall()
        if dups:
            print(f"⚠️  {len(dups)} par(es) cliente/produto duplicado(s) em "
                  "tabela_precos — índice UNIQUE NÃO criado. Limpe e rode de novo.")
        else:
            cursor.execute(
                "ALTER TABLE tabela_precos "
                "ADD UNIQUE INDEX uq_tabela_precos_cli_prod (id_cliente, id_produto)")
            conn.commit()
            print("✅ Índice UNIQUE uq_tabela_precos_cli_prod criado.")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
