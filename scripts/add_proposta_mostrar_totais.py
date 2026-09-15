"""
Migração: coluna mostrar_totais em propostas
Execute: python scripts/add_proposta_mostrar_totais.py
Compatível com MySQL 5.7+

Proposta tem dois usos diferentes:
  - Orçamento: quantidade × valor unitário faz sentido somar (ex.: "600 L de
    café"). Mostra Qtd, Subtotal e Total.
  - Tabela de preços: reajuste ou oferta de serviço novo, onde só o valor
    unitário interessa. Somar itens distintos (café + marmita + almoço) produz
    um número sem significado comercial.

Default 1 para NÃO mudar as propostas já emitidas.
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
          AND COLUMN_NAME = 'mostrar_totais'
    """)
    if cursor.fetchone()[0]:
        print("ℹ️  Coluna mostrar_totais já existe em propostas — nada a fazer.")
    else:
        cursor.execute("""
            ALTER TABLE propostas
            ADD COLUMN mostrar_totais TINYINT(1) NOT NULL DEFAULT 1
        """)
        conn.commit()
        print("✅ Coluna mostrar_totais adicionada em propostas (default 1).")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
