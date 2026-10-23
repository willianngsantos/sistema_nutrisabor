"""
Migração: quantidades padrão por dia da semana + lançamentos diários
Execute: python scripts/add_lancamentos_diarios.py
Compatível com MySQL 5.7+

Antes, o controle de "quantos por dia" era feito fora do sistema e a fatura
recebia só o total do período. Agora:

- qtd_padrao_cliente: quantidade sugerida por produto e dia da semana
  (0=segunda ... 6=domingo, igual ao date.weekday() do Python). Serve SÓ para
  pré-preencher os lançamentos — mudar o padrão não altera dias já lançados.
- lancamentos_diarios: o que foi efetivamente servido em cada dia. É a
  referência da fatura: dia sem lançamento não entra na soma. Feriado = dia
  lançado com quantidade 0.

Idempotente (CREATE TABLE IF NOT EXISTS).
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
        CREATE TABLE IF NOT EXISTS qtd_padrao_cliente (
            id_cliente  INT NOT NULL,
            id_produto  INT NOT NULL,
            dia_semana  TINYINT NOT NULL,
            quantidade  INT UNSIGNED NOT NULL DEFAULT 0,
            PRIMARY KEY (id_cliente, id_produto, dia_semana),
            KEY idx_qpc_produto (id_produto),
            CONSTRAINT fk_qpc_cliente FOREIGN KEY (id_cliente) REFERENCES clientes (id),
            CONSTRAINT fk_qpc_produto FOREIGN KEY (id_produto) REFERENCES produtos (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos_diarios (
            id           INT NOT NULL AUTO_INCREMENT,
            id_cliente   INT NOT NULL,
            id_produto   INT NOT NULL,
            data         DATE NOT NULL,
            quantidade   INT UNSIGNED NOT NULL DEFAULT 0,
            lancado_por  VARCHAR(100) DEFAULT NULL,
            lancado_em   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                         ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_lanc_cli_prod_data (id_cliente, id_produto, data),
            KEY idx_lanc_cli_data (id_cliente, data),
            KEY idx_lanc_produto (id_produto),
            CONSTRAINT fk_lanc_cliente FOREIGN KEY (id_cliente) REFERENCES clientes (id),
            CONSTRAINT fk_lanc_produto FOREIGN KEY (id_produto) REFERENCES produtos (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    print("✅ Tabelas qtd_padrao_cliente e lancamentos_diarios prontas (criadas ou já existentes).")
    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
