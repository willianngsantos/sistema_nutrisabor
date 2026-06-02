#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  aplicar_ajustes_servidor.sh
#  Roda NO SERVIDOR de produção, como root, DEPOIS do ./deploy.sh.
#
#  Aplica os ajustes que o deploy tradicional NÃO cobre, porque
#  dependem do .env (que é gitignored e não vai no rsync):
#    - SESSION_COOKIE_SECURE=1  (cookie de sessão só por HTTPS)
#    - FLASK_DEBUG=0            (garante debugger desligado)
#  Também reinstala dependências (pega o Flask-Limiter novo) e
#  reinicia o serviço.
#
#  ⚠️  NÃO há mudança de banco nestas correções — nenhum SQL a rodar.
#
#  Uso (no servidor):
#    cd /var/www/nutrisabor && bash scripts/aplicar_ajustes_servidor.sh
#  É idempotente: pode rodar quantas vezes quiser.
# ─────────────────────────────────────────────────────────────
set -e

APP_DIR="/var/www/nutrisabor"
ENV_FILE="$APP_DIR/.env"
SERVICE="nutrisabor"

cd "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE não encontrado. Abortando."
  exit 1
fi

# Garante uma variável KEY=VAL no .env (atualiza se existe, adiciona se não).
ensure_env () {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    echo "  ~ ${key} ajustado para ${val}"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
    echo "  + ${key}=${val} adicionado"
  fi
}

echo "🔧 Ajustando variáveis de ambiente..."
ensure_env SESSION_COOKIE_SECURE 1
ensure_env FLASK_DEBUG 0

echo "📦 Garantindo dependências Python (Flask-Limiter etc.)..."
source venv/bin/activate && pip install -r requirements.txt >/dev/null
echo "  ok"

echo "🔄 Reiniciando o serviço $SERVICE..."
systemctl restart "$SERVICE"
systemctl status "$SERVICE" --no-pager -l | head -n 6

echo ""
echo "✅ Ajustes aplicados. Nenhum script SQL necessário."
