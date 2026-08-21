"""
Imagens embutidas (data URI) para documentos impressos.

Logo referenciada por URL (<img src="/static/...">) depende de o navegador
buscar o arquivo no momento da impressão. Quando isso falha — cache frio,
rede lenta, Ctrl+P em vez do botão que espera as imagens carregarem — o
documento sai SEM a marca, e o usuário só descobre no papel/PDF.

Embutir os bytes no próprio HTML remove essa dependência: o documento chega
completo, não há segunda requisição para dar errado.

O arquivo é lido do disco uma vez por processo e guardado em memória; o mtime
entra na chave, então trocar a logo (deploy ou novo upload) invalida o cache
sozinho.
"""
import base64
import os
import threading

from flask import current_app

_cache = {}
_lock = threading.Lock()
_LIMITE_CACHE = 50          # logos distintas em memória; acima disso, recomeça

_TIPOS = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
}


def imagem_data_uri(caminho_relativo):
    """Devolve a imagem de static/ como data URI pronta para o src.

    `caminho_relativo` é o caminho dentro de static/ ('img/logo_print.png' ou
    'uploads/logos/x.png'); aceita também com o prefixo '/static/'.

    Devolve string vazia — nunca levanta exceção — quando o arquivo não existe
    ou não pode ser lido: logo ausente não pode derrubar a emissão de um
    documento. Quem chama decide o fallback (ex.: mostrar o placeholder).
    """
    if not caminho_relativo:
        return ''

    rel = str(caminho_relativo).strip().lstrip('/')
    if rel.startswith('static/'):
        rel = rel[len('static/'):]

    raiz = os.path.realpath(current_app.static_folder)
    caminho = os.path.realpath(os.path.join(raiz, rel))
    # Só serve arquivo de dentro de static/ (bloqueia '..' e caminho absoluto)
    if not caminho.startswith(raiz + os.sep):
        return ''

    try:
        mtime = os.path.getmtime(caminho)
    except OSError:
        return ''

    chave = (caminho, mtime)
    with _lock:
        cacheado = _cache.get(chave)
    if cacheado is not None:
        return cacheado

    try:
        with open(caminho, 'rb') as arq:
            dados = arq.read()
    except OSError:
        return ''

    mime = _TIPOS.get(os.path.splitext(caminho)[1].lower())
    if not mime:
        return ''
    uri = 'data:%s;base64,%s' % (mime, base64.b64encode(dados).decode('ascii'))

    with _lock:
        if len(_cache) >= _LIMITE_CACHE:
            _cache.clear()
        _cache[chave] = uri
    return uri
