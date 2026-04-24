"""
Migração: cria tabela rh_jornada_dias para permitir horários diferentes por
dia dentro de uma mesma jornada. A tabela rh_jornadas preserva o esquema
atual (colunas hora_entrada/hora_saida/intervalo_min/dias_semana ficam lá
como legado — o código novo não as usa, mas também não removemos em DROP
pra evitar operações destrutivas em produção).

Execute: python scripts/add_jornada_dias.py
Compatível com MySQL 5.7+.
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
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'rh_jornada_dias'
    """)
    existe = cursor.fetchone()[0]

    if existe:
        print("ℹ️  Tabela rh_jornada_dias já existe — nada a fazer.")
    else:
        cursor.execute("""
            CREATE TABLE rh_jornada_dias (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                id_jornada      INT NOT NULL,
                dia_semana      VARCHAR(3) NOT NULL,
                hora_entrada    TIME NOT NULL,
                hora_saida      TIME NOT NULL,
                intervalo_min   INT NOT NULL DEFAULT 0,
                UNIQUE KEY uk_jornada_dia (id_jornada, dia_semana),
                CONSTRAINT fk_jornada FOREIGN KEY (id_jornada)
                    REFERENCES rh_jornadas(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("✅ Tabela rh_jornada_dias criada!")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
