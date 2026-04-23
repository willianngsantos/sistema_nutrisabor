import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

load_dotenv()

# Configuração Centralizada com Pooling — credenciais via variáveis de ambiente
db_config = {
    'host':     os.environ['DB_HOST'],
    'user':     os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ['DB_NAME'],
}

# Cria um pool de conexões simultâneas (tamanho configurável via .env)
connection_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="nutrisabor_pool",
    pool_size=int(os.environ.get('DB_POOL_SIZE', 5)),
    **db_config
)

def get_db_connection():
    """Retorna uma conexão do pool (muito mais rápido)."""
    return connection_pool.get_connection()