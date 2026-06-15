"""
Limpeza: remove "preços fantasmas" — linhas em tabela_precos / tabela_precos_grupos
com preço <= 0. Um preço 0 não é um preço negociado válido; era criado quando o
usuário "zerava" um item antes de existir a remoção de verdade. Com preço 0 a
linha continuava aparecendo como item negociado (selo CLIENTE/GRUPO) por R$ 0,00.

Idempotente — pode rodar várias vezes.
Execute: python scripts/limpar_precos_zerados.py
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

    cursor.execute("DELETE FROM tabela_precos WHERE preco_venda <= 0")
    n_cli = cursor.rowcount
    cursor.execute("DELETE FROM tabela_precos_grupos WHERE preco_venda <= 0")
    n_grp = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"✅ Limpeza concluída: {n_cli} preço(s) de cliente e {n_grp} de grupo removido(s) (eram 0).")
except Exception as e:
    print(f"❌ ERRO: {e}")
