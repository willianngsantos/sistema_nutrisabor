"""
Migração v3:
  1. Substitui coluna 'ativo' por 'status' (ENUM: ativo, afastado, ferias, inativo)
     nos colaboradores — preservando os dados existentes.
  2. Adiciona coluna 'atende_local' na tabela clientes.

Execute: python migrar_colaboradores_v3.py
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

    # ── 1. Adiciona coluna 'status' em colaboradores ─────────────
    print("🛠️  Adicionando coluna 'status' em colaboradores...")
    try:
        cursor.execute("""
            ALTER TABLE colaboradores
            ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ativo' AFTER ativo
        """)
        print("   ✅ Coluna 'status' adicionada.")
    except mysql.connector.errors.DatabaseError as e:
        if "Duplicate column name" in str(e):
            print("   ⚠️  Coluna 'status' já existe — pulando.")
        else:
            raise

    # ── 2. Migra dados: ativo=1 → 'ativo', ativo=0 → 'inativo' ──
    print("🔄 Migrando dados de 'ativo' para 'status'...")
    cursor.execute("""
        UPDATE colaboradores
        SET status = CASE
            WHEN ativo = 1 THEN 'ativo'
            ELSE 'inativo'
        END
        WHERE status = 'ativo' OR status = 'inativo'
    """)
    print(f"   ✅ {cursor.rowcount} registros atualizados.")

    # ── 3. Remove coluna 'ativo' (agora substituída por 'status') ─
    print("🗑️  Removendo coluna 'ativo' (substituída por 'status')...")
    try:
        cursor.execute("ALTER TABLE colaboradores DROP COLUMN ativo")
        print("   ✅ Coluna 'ativo' removida.")
    except mysql.connector.errors.DatabaseError as e:
        if "check that column/key exists" in str(e).lower() or "1091" in str(e):
            print("   ⚠️  Coluna 'ativo' já foi removida — pulando.")
        else:
            raise

    # ── 4. Adiciona 'atende_local' em clientes ───────────────────
    print("🛠️  Adicionando coluna 'atende_local' em clientes...")
    try:
        cursor.execute("""
            ALTER TABLE clientes
            ADD COLUMN atende_local TINYINT(1) NOT NULL DEFAULT 0
        """)
        print("   ✅ Coluna 'atende_local' adicionada.")
    except mysql.connector.errors.DatabaseError as e:
        if "Duplicate column name" in str(e):
            print("   ⚠️  Coluna 'atende_local' já existe — pulando.")
        else:
            raise

    conn.commit()
    conn.close()
    print("\n🎉 Migração v3 concluída com sucesso!")

except Exception as e:
    print(f"\n❌ ERRO: {e}")
