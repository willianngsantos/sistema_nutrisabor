"""
Expira automaticamente as propostas vencidas (validade < hoje) que ainda
estavam em 'Rascunho' ou 'Enviada'. A listagem de propostas já faz isso ao
ser aberta; este script cobre a virada de data via cron.

Usa a mesma função do app (routes.propostas.expirar_propostas_vencidas).

Agendar diariamente (crontab -e), ex.: 01:20:
  20 1 * * * cd /var/www/nutrisabor && venv/bin/python scripts/expirar_propostas.py >> /var/log/nutrisabor_propostas.log 2>&1
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection                      # noqa: E402
from routes.propostas import expirar_propostas_vencidas      # noqa: E402


def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        n = expirar_propostas_vencidas(cursor)
        conn.commit()
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] Propostas expiradas: {n}.")
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ERRO ao expirar propostas: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
