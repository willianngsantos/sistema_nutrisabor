"""
Migração: coluna texto_abertura em propostas
Execute: python scripts/add_proposta_texto_abertura.py
Compatível com MySQL 5.7+

Texto de apresentação que sai ANTES da tabela de itens. Existe porque
'observacoes' é renderizado no rodapé, depois dos preços — posição errada para
uma carta de reajuste, onde o cliente precisa ler o motivo antes de ver os
valores novos.

Nullable e sem default: proposta que não preencher sai exatamente como hoje.
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
          AND TABLE_NAME = 'propostas'
          AND COLUMN_NAME = 'texto_abertura'
    """)
    if cursor.fetchone()[0]:
        print("ℹ️  Coluna texto_abertura já existe em propostas — nada a fazer.")
    else:
        cursor.execute("ALTER TABLE propostas ADD COLUMN texto_abertura TEXT NULL")
        conn.commit()
        print("✅ Coluna texto_abertura adicionada em propostas.")
    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
