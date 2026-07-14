#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  backup_db.sh — Backup do MySQL de produção com retenção.
#
#  Faz um dump consistente (InnoDB, sem travar a aplicação),
#  comprime, valida que não saiu vazio e apaga backups antigos.
#  As credenciais são lidas do .env e passadas via arquivo
#  temporário (não aparecem no `ps`/histórico).
#
#  Uso manual no servidor:
#    bash /var/www/nutrisabor/scripts/backup_db.sh
#
#  Agendar diariamente (ex.: 02:30) — rode `crontab -e` e adicione:
#    30 2 * * * /bin/bash /var/www/nutrisabor/scripts/backup_db.sh >> /var/log/nutrisabor_backup.log 2>&1
#
#  Variáveis opcionais (defaults entre colchetes):
#    APP_DIR        [/var/www/nutrisabor]   onde está o .env
#    BACKUP_DIR     [/var/backups/nutrisabor]
#    RETENCAO_DIAS  [30]
# ─────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/nutrisabor}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/nutrisabor}"
RETENCAO_DIAS="${RETENCAO_DIAS:-30}"
ENV_FILE="$APP_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE não encontrado." >&2
  exit 1
fi

# Lê uma chave do .env SEM dar `source` no arquivo inteiro — algumas linhas
# (ex.: MAIL_FROM=NutriSabor <onboarding@resend.dev>) têm caracteres que o
# bash interpretaria como redirecionamento. Pegamos só o necessário.
get_env() {
  # última ocorrência da chave; remove aspas e CR do final (CRLF)
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- \
    | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/\r$//'
}

DB_USER="$(get_env DB_USER)"
DB_PASSWORD="$(get_env DB_PASSWORD)"
DB_NAME="$(get_env DB_NAME)"
DB_HOST="$(get_env DB_HOST)"; DB_HOST="${DB_HOST:-localhost}"

: "${DB_USER:?DB_USER não definido no .env}"
: "${DB_PASSWORD:?DB_PASSWORD não definido no .env}"
: "${DB_NAME:?DB_NAME não definido no .env}"

mkdir -p "$BACKUP_DIR"

# Arquivo de credenciais temporário (evita senha no ps/histórico).
# TMP_ARQ guarda o dump em andamento: se o mysqldump falhar (set -e aborta
# antes da validação), o trap remove o parcial e nunca fica um .gz truncado
# com o nome final.
CNF="$(mktemp)"
TMP_ARQ=""
cleanup() { rm -f "$CNF"; [ -n "$TMP_ARQ" ] && rm -f "$TMP_ARQ"; }
trap cleanup EXIT
chmod 600 "$CNF"
cat > "$CNF" <<EOF
[client]
user=$DB_USER
password=$DB_PASSWORD
host=$DB_HOST
EOF

STAMP="$(date +%Y%m%d_%H%M%S)"
ARQ="$BACKUP_DIR/nutrisabor_${DB_NAME}_${STAMP}.sql.gz"
TMP_ARQ="$ARQ.tmp"

echo "🗄️  Gerando backup de '$DB_NAME'..."
# Escreve no .tmp; só vira o arquivo final após validar. Se o mysqldump falhar,
# pipefail+set -e abortam e o trap remove o .tmp (nunca sobra dump parcial).
mysqldump --defaults-extra-file="$CNF" \
  --single-transaction --quick --routines --triggers --events \
  --default-character-set=utf8mb4 \
  "$DB_NAME" | gzip > "$TMP_ARQ"

# Valida que o arquivo não ficou vazio (dump falho geraria gz minúsculo)
if [ ! -s "$TMP_ARQ" ] || [ "$(gzip -dc "$TMP_ARQ" | head -c 1 | wc -c)" -eq 0 ]; then
  echo "❌ Backup vazio/inválido — removendo." >&2
  exit 1
fi

# Publica de forma atômica e desarma a limpeza do parcial
mv "$TMP_ARQ" "$ARQ"
TMP_ARQ=""

TAM="$(du -h "$ARQ" | cut -f1)"
echo "✅ Backup OK: $ARQ ($TAM)"

# Retenção: apaga backups com mais de RETENCAO_DIAS dias
APAGADOS="$(find "$BACKUP_DIR" -name "nutrisabor_${DB_NAME}_*.sql.gz" -mtime +"$RETENCAO_DIAS" -print -delete | wc -l | tr -d ' ')"
echo "🧹 Retenção: $APAGADOS backup(s) com mais de ${RETENCAO_DIAS} dias removido(s)."
echo "📦 Total atual: $(find "$BACKUP_DIR" -name "nutrisabor_${DB_NAME}_*.sql.gz" | wc -l | tr -d ' ') arquivo(s) em $BACKUP_DIR"
