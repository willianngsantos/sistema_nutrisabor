#!/usr/bin/env bash
# Baixa os arquivos woff2 da fonte Inter (300, 400, 600, 700)
# do Google Fonts e salva em static/fonts/inter/.
#
# Depois de rodar este script, voce ainda precisa:
#   1) Editar templates/base.html: trocar o <link> do Google Fonts por
#      um <link> para static/css/inter.css (gerado abaixo)
#   2) Commit + push + deploy.sh
#
# Uso: bash scripts/download_inter.sh
set -euo pipefail

cd "$(dirname "$0")/.."

DEST="static/fonts/inter"
CSS_DEST="static/css/inter.css"
mkdir -p "$DEST"

# Baixa o CSS do Google Fonts simulando User-Agent do Mac
# (sem isso o GF retorna fontes em formato truetype antigo).
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
GF_URL="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap"

echo "==> Buscando lista de arquivos woff2 do Google Fonts..."
GF_CSS=$(curl -fsSL -A "$UA" "$GF_URL")

# Extrai URLs dos woff2 e o weight associado a cada bloco @font-face
# (assume ordem 300, 400, 600, 700 conforme a query)
echo "$GF_CSS" > /tmp/inter_gf.css

# Para cada peso, baixa o latin (subset Western European)
# O CSS do GF tem varios @font-face por peso (latin-ext, cyrillic, etc).
# Pegamos apenas o latin (ultimo bloco de cada peso, o mais comum).

python3 - <<'PY'
import re, urllib.request, os
css = open('/tmp/inter_gf.css').read()
# blocos @font-face delimitados
blocks = re.split(r'\}\s*', css)
weights_seen = {}
for b in blocks:
    m_weight = re.search(r'font-weight:\s*(\d+)', b)
    m_url = re.search(r'url\((https://[^)]+\.woff2)\)', b)
    m_range = re.search(r'unicode-range:\s*([^;]+)', b)
    if not m_weight or not m_url:
        continue
    w = m_weight.group(1)
    rng = m_range.group(1) if m_range else ''
    # priorizar bloco "latin" (range cobrindo U+0000-00FF aprox)
    is_latin = 'U+0000' in rng or 'U+0100' in rng or 'latin' in b.lower()
    # quando ha varios candidatos, ficamos com o ultimo "latin"
    if is_latin or w not in weights_seen:
        weights_seen[w] = m_url.group(1)

for w, url in sorted(weights_seen.items()):
    fname = f"static/fonts/inter/Inter-{w}.woff2"
    print(f"==> Baixando peso {w}: {url}")
    urllib.request.urlretrieve(url, fname)
    print(f"    salvo em {fname} ({os.path.getsize(fname)} bytes)")
PY

echo "==> Gerando $CSS_DEST"
cat > "$CSS_DEST" <<'CSS'
/* Inter self-hosted — gerado por scripts/download_inter.sh
   Os arquivos .woff2 ficam em static/fonts/inter/ */
@font-face {
    font-family: 'Inter';
    font-style: normal;
    font-weight: 300;
    font-display: swap;
    src: url('../fonts/inter/Inter-300.woff2') format('woff2');
}
@font-face {
    font-family: 'Inter';
    font-style: normal;
    font-weight: 400;
    font-display: swap;
    src: url('../fonts/inter/Inter-400.woff2') format('woff2');
}
@font-face {
    font-family: 'Inter';
    font-style: normal;
    font-weight: 600;
    font-display: swap;
    src: url('../fonts/inter/Inter-600.woff2') format('woff2');
}
@font-face {
    font-family: 'Inter';
    font-style: normal;
    font-weight: 700;
    font-display: swap;
    src: url('../fonts/inter/Inter-700.woff2') format('woff2');
}
CSS

echo ""
echo "✅ Pronto! Arquivos em static/fonts/inter/:"
ls -lh static/fonts/inter/
echo ""
echo "📋 Proximos passos manuais em templates/base.html:"
echo "   1) Trocar o <link href=\"https://fonts.googleapis.com/css2?...\"> por:"
echo "      <link href=\"{{ url_for('static', filename='css/inter.css') }}\" rel=\"stylesheet\">"
echo "   2) git add static/fonts/inter/ static/css/inter.css templates/base.html"
echo "   3) git commit + ./deploy.sh"
