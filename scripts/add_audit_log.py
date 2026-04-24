"""
Migração: cria tabela audit_log para registrar acessos e alterações.
Execute: python scripts/add_audit_log.py
Compatível com MySQL 5.7+.

Campos:
- id: PK autoincrement
- user_id: FK para usuarios.id (mas sem FK constraint, para permitir
  manter o registro mesmo se o usuário for deletado)
- user_nome: desnormalizado — preserva o nome no momento do evento
- tipo_usuario: desnormalizado — admin/gerencial/nutricionista/vendedor
- timestamp: DATETIME com DEFAULT CURRENT_TIMESTAMP
- action_type: 'view', 'login', 'login_failed', 'logout', 'create',
  'update', 'delete'
- entity_type: 'fatura', 'cliente', 'colaborador', 'produto', 'page', etc.
- entity_id: id do objeto afetado (NULL para page views ou login)
- descricao: texto humano da ação
- ip_address, user_agent: metadados do request

Índices:
- (user_id, timestamp DESC) — consulta 'o que o fulano fez'
- (timestamp DESC) — consulta cronológica geral
- (entity_type, entity_id) — consulta 'o que aconteceu com essa entidade'
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
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_log'
    """)
    existe = cursor.fetchone()[0]

    if existe:
        print("ℹ️  Tabela audit_log já existe — nada a fazer.")
    else:
        cursor.execute("""
            CREATE TABLE audit_log (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                user_id         INT NULL,
                user_nome       VARCHAR(150) NULL,
                tipo_usuario    VARCHAR(30) NULL,
                timestamp       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action_type     VARCHAR(30) NOT NULL,
                entity_type     VARCHAR(50) NULL,
                entity_id       INT NULL,
                descricao       VARCHAR(500) NULL,
                ip_address      VARCHAR(45) NULL,
                user_agent      VARCHAR(300) NULL,
                INDEX idx_user_time  (user_id, timestamp),
                INDEX idx_time       (timestamp),
                INDEX idx_entity     (entity_type, entity_id),
                INDEX idx_action     (action_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("✅ Tabela audit_log criada com índices!")

    conn.close()
except Exception as e:
    print(f"❌ ERRO: {e}")
