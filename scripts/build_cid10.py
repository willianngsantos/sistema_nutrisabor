"""
(Re)gera data/cid10.json a partir das tabelas oficiais CID-10 do DATASUS.

Fonte: github.com/cleytonferrari/CidDataSus (CSVs do DATASUS, ISO-8859-1).
O JSON resultante (código → descrição) é embutido no app e consultado por
utils/cid10.py. Rode só quando quiser atualizar a base (precisa de internet).

Uso: python scripts/build_cid10.py
"""
import csv
import io
import json
import os
import urllib.request

BASE = ("https://raw.githubusercontent.com/cleytonferrari/CidDataSus/master/"
        "CIDImport/Repositorio/Resources/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, 'data', 'cid10.json')


def _baixar(nome):
    with urllib.request.urlopen(BASE + nome, timeout=60) as r:
        return r.read().decode('iso-8859-1')


def main():
    cid = {}
    # Categorias: CAT;CLASSIF;DESCRICAO;...
    for row in csv.reader(io.StringIO(_baixar('CID-10-CATEGORIAS.CSV')), delimiter=';'):
        if len(row) >= 3 and row[0].strip() and row[0].strip().upper() != 'CAT':
            cid[row[0].strip().upper()] = row[2].strip()
    # Subcategorias: SUBCAT;CLASSIF;RESTRSEXO;CAUSAOBITO;DESCRICAO;...
    for row in csv.reader(io.StringIO(_baixar('CID-10-SUBCATEGORIAS.CSV')), delimiter=';'):
        if len(row) >= 5 and row[0].strip() and row[0].strip().upper() != 'SUBCAT':
            cid[row[0].strip().upper()] = row[4].strip()

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, 'w', encoding='utf-8') as f:
        json.dump(cid, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print(f"✅ {DEST} gerado com {len(cid)} códigos CID-10.")


if __name__ == "__main__":
    main()
