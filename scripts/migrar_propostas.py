"""
Migração: cria tabelas `propostas` e `proposta_itens`
Execute uma única vez: python scripts/migrar_propostas.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# ── Tabela principal de propostas ──────────────────────────────────────────────
cursor.execute("""
    CREATE TABLE IF NOT EXISTS propostas (
        id                  INT AUTO_INCREMENT PRIMARY KEY,
        numero              VARCHAR(20)   NOT NULL UNIQUE,
        id_cliente          INT           NOT NULL,
        data_proposta       DATE          NOT NULL,
        validade            DATE,
        condicoes_pagamento VARCHAR(255),
        observacoes         TEXT,
        status              ENUM('Rascunho','Enviada','Aceita','Recusada','Expirada')
                            NOT NULL DEFAULT 'Rascunho',
        created_at          TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""")
print("✔  Tabela `propostas` OK")

# ── Itens da proposta ──────────────────────────────────────────────────────────
cursor.execute("""
    CREATE TABLE IF NOT EXISTS proposta_itens (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        id_proposta     INT            NOT NULL,
        descricao       VARCHAR(255)   NOT NULL,
        quantidade      DECIMAL(10,2)  NOT NULL DEFAULT 1,
        unidade         VARCHAR(30)    NOT NULL DEFAULT 'un',
        valor_unitario  DECIMAL(12,2)  NOT NULL DEFAULT 0,
        FOREIGN KEY (id_proposta) REFERENCES propostas(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""")
print("✔  Tabela `proposta_itens` OK")

conn.commit()
conn.close()
print("\n✅  Migração concluída com sucesso.")
