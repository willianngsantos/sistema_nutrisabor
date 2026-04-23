"""
Script de migração: cria a tabela 'colaboradores'.
Execute uma única vez: python setup_colaboradores.py
"""
import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

db_config = {
    'host':     os.environ['DB_HOST'],
    'user':     os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ['DB_NAME'],
}

try:
    print("🔄 Conectando ao banco...")
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    print("🛠️  Criando tabela 'colaboradores'...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS colaboradores (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            nome            VARCHAR(150) NOT NULL,
            funcao          VARCHAR(100),
            salario_bruto   DECIMAL(10,2) DEFAULT 0.00,
            vale_transporte DECIMAL(10,2) DEFAULT 0.00,
            data_admissao   DATE,
            ativo           TINYINT(1) DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    conn.commit()
    conn.close()
    print("\n✅ Tabela 'colaboradores' criada com sucesso!")
    print("   Pode rodar o sistema normalmente agora.")

except Exception as e:
    print(f"\n❌ ERRO: {e}")
