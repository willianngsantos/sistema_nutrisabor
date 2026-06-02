import os
import mysql.connector
from mysql.connector import pooling
from flask import g, has_app_context
from dotenv import load_dotenv

load_dotenv()

# Configuração Centralizada com Pooling — credenciais via variáveis de ambiente
db_config = {
    'host':     os.environ['DB_HOST'],
    'user':     os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ['DB_NAME'],
    # consume_results: ao compartilhar UMA conexão por requisição (via flask.g),
    # vários cursores podem coexistir. Isso garante que resultados não lidos de
    # um SELECT anterior sejam consumidos automaticamente antes do próximo
    # execute, evitando o erro "Unread result found" do mysql-connector.
    'consume_results': True,
}

# Cria um pool de conexões simultâneas (tamanho configurável via .env)
connection_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="nutrisabor_pool",
    pool_size=int(os.environ.get('DB_POOL_SIZE', 5)),
    **db_config
)


def get_db_connection():
    """Retorna uma conexão do pool.

    Dentro de uma requisição (app context), a conexão é única por requisição
    e fica guardada em ``flask.g`` — todas as chamadas no mesmo request
    reaproveitam a mesma conexão, que é devolvida ao pool automaticamente
    pelo ``teardown`` registrado em ``app.py`` (ver ``close_db_connection``).
    Isso elimina vazamentos de conexão quando uma rota levanta exceção antes
    de fechar a conexão manualmente.

    Fora de um app context (ex.: scripts em ``scripts/``), devolve uma conexão
    avulsa do pool — o chamador é responsável por fechá-la.
    """
    if has_app_context():
        if 'db_conn' not in g:
            g.db_conn = connection_pool.get_connection()
        return g.db_conn
    return connection_pool.get_connection()


def close_db_connection(exc=None):
    """Devolve a conexão da requisição ao pool. Registrado como
    ``teardown_appcontext`` — roda SEMPRE ao final da requisição, mesmo
    quando há exceção. Faz rollback de qualquer transação não commitada
    (no-op se a rota já deu commit), evitando que uma conexão volte ao
    pool carregando uma transação pela metade."""
    conn = g.pop('db_conn', None)
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.close()  # devolve ao pool
    except Exception:
        pass
