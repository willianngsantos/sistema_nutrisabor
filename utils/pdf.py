"""
Geração de PDF no servidor.

No celular, o "Imprimir / Salvar PDF" do navegador não entrega um arquivo: no
iPhone o diálogo do Safari não tem uma opção clara de salvar em PDF. Como a
necessidade real é anexar o documento no WhatsApp, quem gera o arquivo passa a
ser o servidor — o celular recebe um PDF pronto para compartilhar.

O import do WeasyPrint é PREGUIÇOSO e protegido de propósito: ele depende de
bibliotecas de sistema (pango/cairo/gdk-pixbuf). Se faltarem no servidor, o app
tem que continuar de pé e só a geração de PDF falhar com um aviso claro — um
import no topo derrubaria o site inteiro.
"""
import logging
import os
import re

from flask import Response, current_app

_logger = logging.getLogger('nutrisabor.pdf')

# Dependências de sistema (Ubuntu/Debian). Citadas no erro para o aviso já
# dizer o que rodar no servidor.
APT_NECESSARIO = (
    "apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b "
    "libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info"
)

_motor = None   # None = ainda não tentou; False = indisponível; senão, weasyprint.HTML


def _carregar_motor():
    """Importa o WeasyPrint uma vez. Nunca levanta — devolve False se faltar."""
    global _motor
    if _motor is not None:
        return _motor
    try:
        from weasyprint import HTML
        _motor = HTML
    except Exception as e:
        _logger.error("Geração de PDF indisponível (%s). No servidor, rode: %s",
                      e, APT_NECESSARIO)
        _motor = False
    return _motor


def pdf_disponivel():
    """True se dá para gerar PDF neste ambiente (usado para mostrar o botão)."""
    return bool(_carregar_motor())


# Os documentos referenciam Bootstrap/ícones por CDN. Buscar CSS pela rede na
# hora de gerar o PDF é lento e, se o CDN falhar, o layout quebra (as colunas
# da grade empilham). Trocamos pela cópia local em static/vendor.
_LINK_CDN = re.compile(r'<link[^>]+?href="https://cdn\.jsdelivr\.net[^"]*"[^>]*>', re.I)


def _trocar_cdn_por_local(html):
    html, trocados = _LINK_CDN.subn('', html)
    if not trocados:
        return html
    css = os.path.join(current_app.static_folder, 'vendor', 'bootstrap.min.css')
    if not os.path.exists(css):
        _logger.warning("static/vendor/bootstrap.min.css ausente — layout do PDF pode sair torto.")
        return html
    tag = '<link rel="stylesheet" href="file://%s">' % css
    return html.replace('</head>', tag + '</head>', 1)


def gerar_pdf(html):
    """HTML já renderizado → bytes do PDF. Devolve None se o motor faltar."""
    HTML = _carregar_motor()
    if not HTML:
        return None
    try:
        return HTML(string=_trocar_cdn_por_local(html),
                    base_url=current_app.root_path).write_pdf()
    except Exception:
        _logger.exception("Falha ao gerar PDF")
        return None


def responder_pdf(html, nome_arquivo):
    """Devolve o PDF para o navegador, ou None se não foi possível gerar.

    Content-Disposition inline: no celular o PDF abre no visualizador e o botão
    de compartilhar manda direto para o WhatsApp — menos passos do que baixar,
    procurar em Arquivos e só então compartilhar.
    """
    dados = gerar_pdf(html)
    if dados is None:
        return None
    nome = re.sub(r'[^A-Za-z0-9._-]', '_', nome_arquivo) or 'documento.pdf'
    return Response(dados, mimetype='application/pdf', headers={
        'Content-Disposition': 'inline; filename="%s"' % nome,
        'Cache-Control': 'no-store',
    })
