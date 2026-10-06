#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  verificar_prod.sh — checagens mecânicas da skill "deployado".
#
#  SOMENTE LEITURA: não reinicia serviço, não roda migração, não
#  grava nada no servidor. rsync roda em --dry-run.
#
#  Uso (da raiz do repo): bash .claude/skills/deployado/verificar_prod.sh
#  Saída: 0 = tudo OK | 1 = alguma falha | 2 = sem acesso ao servidor
# ─────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

# Lê destino e exclusões do PRÓPRIO deploy.sh: a verificação nunca diverge
# do que o deploy de fato envia.
SERVER="$(grep -E '^SERVER=' deploy.sh | head -1 | cut -d'"' -f2)"
REMOTE="$(grep -E '^REMOTE_PATH=' deploy.sh | head -1 | cut -d'"' -f2)"
URL="$(grep -oE 'https://[a-z0-9.-]+' deploy.sh | head -1)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "$SERVER")

falhas=0; avisos=0
ok()    { echo "  ✅ $*"; }
falha() { echo "  ❌ $*"; falhas=$((falhas+1)); }
aviso() { echo "  ⚠️  $*"; avisos=$((avisos+1)); }
secao() { echo; echo "── $* ──"; }

secao "Acesso"
if "${SSH[@]}" true 2>/dev/null; then ok "SSH em $SERVER (chave, sem senha)"
else echo "  ❌ Sem acesso SSH a $SERVER (BatchMode). Conferir ~/.ssh/config / chave nutrisabor_servidor."; exit 2; fi

secao "Git local"
git fetch -q origin 2>/dev/null || aviso "não consegui dar fetch no GitHub"
sujos="$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
[ "$sujos" -eq 0 ] && ok "sem alterações não commitadas" \
  || aviso "$sujos arquivo(s) alterado(s) sem commit — o deploy (rsync do working tree) pode ter levado código que não está no GitHub"
naoenv="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo '?')"
[ "$naoenv" = "0" ] && ok "HEAD $(git rev-parse --short HEAD) está no GitHub" \
  || aviso "$naoenv commit(s) ainda não enviados ao GitHub (git push)"

secao "Paridade de arquivos (local x produção, por conteúdo)"
EXCL=()
while IFS= read -r e; do EXCL+=(--exclude "$e"); done \
  < <(grep -oE -- "--exclude '[^']+'" deploy.sh | sed -E "s/--exclude '//; s/'$//")
EXCL+=(--exclude '.DS_Store')
dif="$(rsync -rcn --itemize-changes "${EXCL[@]}" ./ "$SERVER:$REMOTE/" 2>&1 | grep -E '^<f|^cd' || true)"
if [ -z "$dif" ]; then ok "todos os arquivos de produção idênticos aos locais"
else
  falha "$(echo "$dif" | grep -c '^<f') arquivo(s) diferentes ou ausentes em produção (deploy não aplicado?):"
  echo "$dif" | sed -E 's/^[^ ]+ /       /' | head -25
fi
extras="$(rsync -rcn --delete --itemize-changes "${EXCL[@]}" ./ "$SERVER:$REMOTE/" 2>&1 | grep '^\*deleting' | sed 's/^\*deleting */       /' || true)"
[ -n "$extras" ] && aviso "arquivos que existem só em produção (o deploy não apaga nada — conferir se são lixo):" && echo "$extras" | head -15

secao "Serviço"
estado="$("${SSH[@]}" systemctl is-active nutrisabor 2>/dev/null)"
[ "$estado" = "active" ] && ok "nutrisabor: active" || falha "nutrisabor: $estado"
ts_restart="$("${SSH[@]}" 'date -d "$(systemctl show nutrisabor -p ActiveEnterTimestamp --value)" +%s')"
mais_novo="$("${SSH[@]}" "find $REMOTE -path $REMOTE/venv -prune -o -path $REMOTE/static/uploads -prune -o -name __pycache__ -prune -o -type f \( -name '*.py' -o -name '*.html' -o -name '*.css' -o -name '*.js' \) -printf '%T@\n' | sort -n | tail -1")"
mais_novo="${mais_novo%.*}"
if [ "$ts_restart" -ge "${mais_novo:-0}" ]; then
  ok "reiniciado em $(date -r "$ts_restart" '+%d/%m %H:%M'), depois do arquivo mais novo ($(date -r "${mais_novo:-0}" '+%d/%m %H:%M'))"
else
  falha "serviço reiniciou ($(date -r "$ts_restart" '+%d/%m %H:%M')) ANTES do arquivo mais novo ($(date -r "$mais_novo" '+%d/%m %H:%M')) — templates/código antigos podem estar em memória"
fi
erros="$("${SSH[@]}" "journalctl -u nutrisabor --since @$ts_restart --no-pager 2>/dev/null | grep -cE 'Traceback|ERROR|CRITICAL'")"
[ "${erros:-0}" -eq 0 ] && ok "log do serviço sem erros desde o restart" \
  || { falha "$erros linha(s) de erro no log desde o restart:"; "${SSH[@]}" "journalctl -u nutrisabor --since @$ts_restart --no-pager | grep -E -A3 'Traceback|ERROR|CRITICAL' | tail -15" | sed 's/^/       /'; }

secao "HTTP (de fora, como o usuário vê)"
for caminho in /login /static/img/icones/apple-touch-icon.png /static/manifest.json /static/vendor/bootstrap.min.css; do
  cod="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$URL$caminho")"
  case "$cod" in 200|302) ok "$caminho → $cod" ;; *) falha "$caminho → $cod" ;; esac
done

secao "Dependências"
freeze="$("${SSH[@]}" "cd $REMOTE && venv/bin/pip freeze 2>/dev/null" | tr 'A-Z_' 'a-z-')"
faltando="$(grep -E '^[A-Za-z0-9_.-]+==' requirements.txt | tr 'A-Z_' 'a-z-' | while read -r req; do grep -qx "$req" <<<"$freeze" || echo "$req"; done)"
[ -z "$faltando" ] && ok "versões do requirements.txt instaladas em produção" \
  || { falha "pacotes ausentes/versão diferente em produção:"; echo "$faltando" | sed 's/^/       /'; }
"${SSH[@]}" "cd $REMOTE && venv/bin/python -c 'import weasyprint' 2>/dev/null" \
  && ok "WeasyPrint importa (botão Baixar PDF operante)" \
  || falha "WeasyPrint NÃO importa — faltam libs de sistema; Baixar PDF degrada para HTML"

secao "Crons e backup"
nao_ascii="$("${SSH[@]}" "crontab -l 2>/dev/null | grep -v '^#' | LC_ALL=C grep -n '[^[:print:][:space:]]'")"
[ -z "$nao_ascii" ] && ok "linhas do crontab sem caracteres estranhos" \
  || falha "crontab com caractere não-ASCII (foi isso que matou o backup até 06/10/2026):"$'\n'"$nao_ascii"
idade="$("${SSH[@]}" "f=\$(ls -t /var/backups/nutrisabor/*.sql.gz 2>/dev/null | head -1); [ -n \"\$f\" ] && echo \$(( (\$(date +%s) - \$(stat -c %Y \"\$f\")) / 3600 ))")"
if [ -z "$idade" ]; then falha "nenhum dump em /var/backups/nutrisabor"
elif [ "$idade" -le 26 ]; then ok "último backup do banco há ${idade}h"
else falha "último backup do banco há ${idade}h (o cron das 02:30 deveria gerar um por dia)"; fi

secao "Novidades desde a última validação (checar uma a uma)"
marca="$(git rev-parse --git-dir)/deployado_ultimo"
if [ -s "$marca" ] && git cat-file -e "$(cat "$marca")" 2>/dev/null; then
  base="$(cat "$marca")"; echo "  última validação OK: $(git log -1 --format='%h %s' "$base")"
  git log --format='  • %h %s' "$base"..HEAD
  [ -z "$(git log --format=%h "$base"..HEAD)" ] && echo "  (nenhum commit novo)"
else
  echo "  (sem validação anterior registrada — últimos 5 commits)"
  git log -5 --format='  • %h %s'
fi

echo
echo "════ RESULTADO MECÂNICO: $falhas falha(s), $avisos aviso(s) ════"
[ "$falhas" -eq 0 ]
