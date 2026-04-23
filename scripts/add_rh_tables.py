"""
Migração: cria tabelas do módulo RH completo
Execute: python scripts/add_rh_tables.py
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

def col_existe(cursor, tabela, coluna):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (tabela, coluna))
    return cursor.fetchone()[0] > 0

def tab_existe(cursor, tabela):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
    """, (tabela,))
    return cursor.fetchone()[0] > 0

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    # data_nascimento em colaboradores
    if not col_existe(cursor, 'colaboradores', 'data_nascimento'):
        cursor.execute("ALTER TABLE colaboradores ADD COLUMN data_nascimento DATE DEFAULT NULL AFTER data_admissao")
        print("✅ Coluna data_nascimento adicionada em colaboradores!")
    else:
        print("ℹ️  data_nascimento já existe.")

    # Exames médicos
    if not tab_existe(cursor, 'rh_exames'):
        cursor.execute("""
            CREATE TABLE rh_exames (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_colaborador INT NOT NULL,
                tipo VARCHAR(100) NOT NULL,
                data_realizado DATE,
                data_vencimento DATE,
                resultado ENUM('apto','apto_com_restricao','inapto') DEFAULT 'apto',
                clinica VARCHAR(150),
                observacoes TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_colaborador) REFERENCES colaboradores(id) ON DELETE CASCADE
            )
        """)
        print("✅ Tabela rh_exames criada!")
    else:
        print("ℹ️  rh_exames já existe.")

    # Documentos da empresa
    if not tab_existe(cursor, 'rh_documentos'):
        cursor.execute("""
            CREATE TABLE rh_documentos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(200) NOT NULL,
                categoria VARCHAR(50) DEFAULT 'outros',
                arquivo_path VARCHAR(300),
                validade DATE,
                responsavel VARCHAR(100),
                observacoes TEXT,
                criado_por VARCHAR(100),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Tabela rh_documentos criada!")
    else:
        print("ℹ️  rh_documentos já existe.")

    # Histórico de reajustes
    if not tab_existe(cursor, 'rh_reajustes'):
        cursor.execute("""
            CREATE TABLE rh_reajustes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_reajuste DATE NOT NULL,
                tipo ENUM('percentual','fixo') NOT NULL,
                valor DECIMAL(10,2) NOT NULL,
                motivo VARCHAR(200),
                aplicado_por VARCHAR(100),
                qtd_colaboradores INT DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Tabela rh_reajustes criada!")
    else:
        print("ℹ️  rh_reajustes já existe.")

    # Jornadas de trabalho
    if not tab_existe(cursor, 'rh_jornadas'):
        cursor.execute("""
            CREATE TABLE rh_jornadas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(100) NOT NULL,
                hora_entrada TIME NOT NULL,
                hora_saida TIME NOT NULL,
                intervalo_min INT DEFAULT 60,
                dias_semana VARCHAR(50) DEFAULT 'seg,ter,qua,qui,sex',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Tabela rh_jornadas criada!")
    else:
        print("ℹ️  rh_jornadas já existe.")

    # Férias
    if not tab_existe(cursor, 'rh_ferias'):
        cursor.execute("""
            CREATE TABLE rh_ferias (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_colaborador INT NOT NULL,
                data_inicio DATE NOT NULL,
                data_fim DATE NOT NULL,
                dias INT NOT NULL DEFAULT 30,
                status ENUM('agendado','em_andamento','concluido','cancelado') DEFAULT 'agendado',
                observacoes TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_colaborador) REFERENCES colaboradores(id) ON DELETE CASCADE
            )
        """)
        print("✅ Tabela rh_ferias criada!")
    else:
        print("ℹ️  rh_ferias já existe.")

    # Folha de ponto
    if not tab_existe(cursor, 'rh_ponto'):
        cursor.execute("""
            CREATE TABLE rh_ponto (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_colaborador INT NOT NULL,
                data DATE NOT NULL,
                tipo ENUM('normal','falta','atestado','feriado','ferias','folga') DEFAULT 'normal',
                hora_entrada TIME,
                hora_saida TIME,
                observacoes VARCHAR(200),
                UNIQUE KEY uk_colab_data (id_colaborador, data),
                FOREIGN KEY (id_colaborador) REFERENCES colaboradores(id) ON DELETE CASCADE
            )
        """)
        print("✅ Tabela rh_ponto criada!")
    else:
        print("ℹ️  rh_ponto já existe.")

    conn.commit()
    conn.close()
    print("\n✅ Migração do módulo RH concluída com sucesso!")
except Exception as e:
    print(f"❌ ERRO: {e}")
