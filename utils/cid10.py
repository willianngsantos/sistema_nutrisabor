"""
Consulta à tabela CID-10 (Classificação Internacional de Doenças, DATASUS).

A base (data/cid10.json — código → descrição) é carregada UMA vez em memória
sob demanda. Aceita códigos com ou sem ponto e em qualquer caixa:
'J11', 'j11.1', 'J111' funcionam. Se a subcategoria não existir, faz fallback
para a categoria (3 primeiros caracteres).
"""
import json
import os
import re
import threading

_CID = None
_LOCK = threading.Lock()


def _carregar():
    global _CID
    if _CID is None:
        with _LOCK:
            if _CID is None:
                path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'data', 'cid10.json')
                try:
                    with open(path, encoding='utf-8') as f:
                        _CID = json.load(f)
                except (OSError, ValueError):
                    _CID = {}
    return _CID


def _norm(codigo):
    return re.sub(r'[^A-Za-z0-9]', '', codigo or '').upper()


def descricao_cid(codigo):
    """Retorna a descrição do CID informado, ou None se não encontrado."""
    if not codigo:
        return None
    cid = _carregar()
    c = _norm(codigo)
    if not c:
        return None
    if c in cid:
        return cid[c]
    # fallback: categoria (3 primeiros caracteres) — ex.: 'J119' sem subcat -> 'J11'
    if len(c) > 3 and c[:3] in cid:
        return cid[c[:3]]
    return None
