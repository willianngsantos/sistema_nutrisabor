"""
Sincroniza o status de colaboradores e dos registros de férias com a data de
hoje. As telas de RH já fazem isso ao serem abertas, mas este script cobre a
"virada de data" na madrugada — quando uma férias começa ou termina e ninguém
abriu o sistema ainda.

Usa exatamente a mesma função do app (routes.rh.sincronizar_status_ferias),
então não há risco de a regra divergir.

Agendar diariamente (crontab -e), ex.: 01:15:
  15 1 * * * cd /var/www/nutrisabor && venv/bin/python scripts/sync_status_ferias.py >> /var/log/nutrisabor_ferias.log 2>&1
"""
import os
import sys
from datetime import datetime

# Garante que a raiz do projeto está no path (para importar database/routes)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection          # noqa: E402
from routes.rh import sincronizar_status_ferias  # noqa: E402


def main():
    # Fora de app context, get_db_connection() devolve uma conexão avulsa do pool
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        afetadas = sincronizar_status_ferias(cursor)
        conn.commit()
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] Sync de férias OK — {afetadas} linha(s) ajustada(s).")
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ERRO no sync de férias: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
