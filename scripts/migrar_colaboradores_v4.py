"""
Migração v4 – Adiciona coluna `recebe_vt` à tabela colaboradores.

  recebe_vt TINYINT(1) NOT NULL DEFAULT 1

  1 = colaborador recebe Vale Transporte (padrão — mantém comportamento atual)
  0 = colaborador NÃO recebe VT (ex.: nutricionista, sócio, etc.)

Execute uma única vez:
    python scripts/migrar_colaboradores_v4.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            ALTER TABLE colaboradores
            ADD COLUMN recebe_vt TINYINT(1) NOT NULL DEFAULT 1
        """)
        conn.commit()
        print("✅ Coluna `recebe_vt` adicionada com sucesso (todos marcados como 1 por padrão).")
    except Exception as e:
        if "Duplicate column name" in str(e) or "already exists" in str(e).lower():
            print("ℹ️  Coluna `recebe_vt` já existe — nenhuma alteração necessária.")
        else:
            print(f"❌ Erro inesperado: {e}")
            conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
