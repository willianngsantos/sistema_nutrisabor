#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  puxar_backup.sh — Traz o que só existe no servidor para esta
#  máquina: dump do banco de produção + uploads.
#
#  O código já está salvo no GitHub. O que NÃO está em lugar
#  nenhum além do droplet é:
#    • o banco de produção
#    • static/uploads (logos de clientes, atestados, docs de RH)
#  Se o droplet sumir, isso é perda irreversível.
#
#  Uso:
#    bash scripts/puxar_backup.sh
#
#  Variáveis opcionais (defaults entre colchetes):
#    DESTINO        [~/Backups/NutriSabor]
#    RETENCAO_DIAS  [60]
#
#  O destino fica FORA da pasta do projeto de propósito: apagar o
#  projeto (como aconteceu em 05/10/2026) não pode levar o backup
#  junto.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SERVER="${SERVER:-root@157.245.80.194}"
REMOTE_PATH="${REMOTE_PATH:-/var/www/nutrisabor}"
REMOTE_BACKUPS="${REMOTE_BACKUPS:-/var/backups/nutrisabor}"
DESTINO="${DESTINO:-$HOME/Backups/NutriSabor}"
RETENCAO_DIAS="${RETENCAO_DIAS:-60}"

STAMP="$(date +%Y%m%d_%H%M%S)"
DIR="$DESTINO/$STAMP"
mkdir -p "$DIR"

# Se algo falhar no meio, não deixa uma pasta pela metade parecendo
# um backup bom.
ok=0
limpar() {
  if [ "$ok" -eq 0 ]; then
    echo "✋ Backup incompleto — removendo $DIR para não parecer válido." >&2
    rm -rf "$DIR"
  fi
}
trap limpar EXIT

echo "🗄️  1/4 — Gerando dump no servidor..."
ssh "$SERVER" "bash $REMOTE_PATH/scripts/backup_db.sh"

echo
echo "⬇️  2/4 — Trazendo o dump mais recente..."
ULTIMO="$(ssh "$SERVER" "ls -t $REMOTE_BACKUPS/*.sql.gz 2>/dev/null | head -1")"
[ -n "$ULTIMO" ] || { echo "❌ Nenhum dump encontrado em $REMOTE_BACKUPS." >&2; exit 1; }
scp -q "$SERVER:$ULTIMO" "$DIR/"
DUMP="$DIR/$(basename "$ULTIMO")"

echo "⬇️  3/4 — Trazendo os uploads (logos, atestados, docs de RH)..."
rsync -az --delete "$SERVER:$REMOTE_PATH/static/uploads/" "$DIR/uploads/"

echo
echo "🔍 4/4 — Conferindo o que foi baixado..."
# Backup que ninguém testa não é backup: valida o gzip e confirma
# que as tabelas principais estão mesmo lá dentro.
gzip -t "$DUMP" || { echo "❌ Dump corrompido (gzip inválido)." >&2; exit 1; }

faltando=""
for t in usuarios clientes produtos pedidos itens_pedido colaboradores cardapios propostas; do
  gzip -dc "$DUMP" | grep -q "CREATE TABLE \`$t\`" || faltando="$faltando $t"
done
[ -z "$faltando" ] || { echo "❌ Dump sem as tabelas:$faltando" >&2; exit 1; }

LINHAS="$(gzip -dc "$DUMP" | grep -c '^INSERT INTO' || true)"
TAM="$(du -h "$DUMP" | cut -f1)"
ARQS="$(find "$DIR/uploads" -type f 2>/dev/null | wc -l | tr -d ' ')"

echo "   ✅ dump íntegro: $TAM, $LINHAS comando(s) INSERT, 8 tabelas principais presentes"
echo "   ✅ uploads: $ARQS arquivo(s)"

ok=1
echo
echo "✅ Backup salvo em: $DIR"

# Retenção local
APAGADOS="$(find "$DESTINO" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENCAO_DIAS" -print -exec rm -rf {} + 2>/dev/null | wc -l | tr -d ' ')"
echo "🧹 Retenção: $APAGADOS backup(s) com mais de ${RETENCAO_DIAS} dias removido(s)."
echo "📦 Total guardado: $(find "$DESTINO" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') backup(s) em $DESTINO"
