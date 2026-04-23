"""
Migração v2 — Colaboradores:
  1. Adiciona colunas vale_refeicao e diversos na tabela colaboradores
  2. Cria tabela colaborador_unidades (vínculo N:N com clientes)

Execute: python migrar_colaboradores_v2.py
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

    # ── 1. Novos campos em colaboradores ────────────────────────────
    print("🛠️  Adicionando colunas vale_refeicao e diversos...")

    for col, definition in [
        ("vale_refeicao", "DECIMAL(10,2) DEFAULT 0.00 AFTER vale_transporte"),
        ("diversos",      "DECIMAL(10,2) DEFAULT 0.00 AFTER vale_refeicao"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE colaboradores ADD COLUMN {col} {definition}")
            print(f"   ✅ Coluna '{col}' adicionada.")
        except mysql.connector.errors.DatabaseError as e:
            if "Duplicate column name" in str(e):
                print(f"   ⚠️  Coluna '{col}' já existe — pulando.")
            else:
                raise

    # ── 2. Tabela de vínculo colaborador ↔ unidade (cliente) ────────
    print("🛠️  Criando tabela 'colaborador_unidades'...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS colaborador_unidades (
            id_colaborador INT NOT NULL,
            id_cliente     INT NOT NULL,
            PRIMARY KEY (id_colaborador, id_cliente),
            CONSTRAINT fk_cu_colaborador FOREIGN KEY (id_colaborador)
                REFERENCES colaboradores(id) ON DELETE CASCADE,
            CONSTRAINT fk_cu_cliente FOREIGN KEY (id_cliente)
                REFERENCES clientes(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    print("   ✅ Tabela 'colaborador_unidades' pronta.")

    conn.commit()
    conn.close()
    print("\n🎉 Migração concluída! Sistema pronto para uso.")

except Exception as e:
    print(f"\n❌ ERRO: {e}")
