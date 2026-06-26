"""
Migração: cria a tabela rh_atestados (controle de atestados médicos).

Campos: colaborador, data de início, dias concedidos pelo médico e data_fim
calculada. Extras opcionais (sugestão sênior): CID, médico, observações e
anexo do atestado (arquivo). Idempotente (CREATE TABLE IF NOT EXISTS).

Execute: python scripts/add_rh_atestados.py
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rh_atestados (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_colaborador INT NOT NULL,
            data_inicio DATE NOT NULL,
            dias INT NOT NULL DEFAULT 1,
            data_fim DATE NOT NULL,
            cid VARCHAR(20) DEFAULT NULL,
            medico VARCHAR(120) DEFAULT NULL,
            observacoes VARCHAR(500) DEFAULT NULL,
            arquivo_path VARCHAR(255) DEFAULT NULL,
            criado_por VARCHAR(100) DEFAULT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_atestado_colab (id_colaborador),
            INDEX idx_atestado_inicio (data_inicio),
            CONSTRAINT fk_atestado_colab FOREIGN KEY (id_colaborador)
                REFERENCES colaboradores(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    conn.close()
    print("✅ Tabela rh_atestados pronta (criada ou já existente).")
except Exception as e:
    print(f"❌ ERRO: {e}")
