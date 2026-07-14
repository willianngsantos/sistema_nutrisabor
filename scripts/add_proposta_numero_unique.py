"""
Migração: índice UNIQUE em propostas.numero
Execute: python scripts/add_proposta_numero_unique.py
Compatível com MySQL 5.7+

Impede que duas propostas fiquem com o mesmo número (corrida ao gerar o
sequencial). Idempotente: não recria o índice se já existir. Se houver números
duplicados legados, NÃO aborta o deploy — apenas avisa (o índice fica pendente
até a duplicidade ser resolvida à mão).
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
          AND TABLE_NAME = 'propostas'
          AND INDEX_NAME = 'uq_propostas_numero'
    """)
    existe = cursor.fetchone()[0]

    if existe:
        print("ℹ️  Índice uq_propostas_numero já existe — nada a fazer.")
    else:
        # Confere duplicatas antes de tentar criar o índice único
        cursor.execute("""
            SELECT numero, COUNT(*) c FROM propostas
            GROUP BY numero HAVING c > 1
        """)
        dups = cursor.fetchall()
        if dups:
            # Não usa "❌" de propósito: não queremos abortar o deploy por dado
            # legado; o índice entra depois que os números forem corrigidos.
            print(f"⚠️  {len(dups)} número(s) de proposta duplicado(s): "
                  + ", ".join(d[0] for d in dups[:5])
                  + " — índice UNIQUE NÃO criado. Corrija e rode de novo.")
        else:
            cursor.execute(
                "ALTER TABLE propostas ADD UNIQUE INDEX uq_propostas_numero (numero)")
            conn.commit()
            print("✅ Índice UNIQUE uq_propostas_numero criado em propostas.")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
