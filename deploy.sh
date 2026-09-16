#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — Sobe as alterações do Mac para produção
#  Uso: ./deploy.sh
# ─────────────────────────────────────────────────────────────

SERVER="root@157.245.80.194"
REMOTE_PATH="/var/www/nutrisabor"
LOCAL_PATH="$(dirname "$0")"

echo "🚀 Iniciando deploy para produção..."

# Sincroniza arquivos (exclui venv, __pycache__, .env, uploads)
rsync -avz --progress \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'static/uploads/' \
  --exclude '.git/' \
  "$LOCAL_PATH/" "$SERVER:$REMOTE_PATH/"

echo "📦 Garantindo bibliotecas de sistema do gerador de PDF..."
# WeasyPrint (botão "Baixar PDF") precisa destas libs. É idempotente — se já
# estiverem instaladas, o apt não faz nada. Falha aqui NÃO aborta o deploy: o
# site continua no ar e apenas o PDF fica indisponível (o app degrada sozinho).
ssh "$SERVER" "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 \
  libgdk-pixbuf-2.0-0 shared-mime-info > /dev/null 2>&1" \
  || echo "⚠️  Não instalou as libs de PDF — site segue normal, só o 'Baixar PDF' fica fora."

echo "📦 Instalando/atualizando dependências Python..."
ssh "$SERVER" "cd $REMOTE_PATH && source venv/bin/activate && pip install -r requirements.txt"

echo "🔄 Rodando migrações pendentes..."
# Runner que PARA no primeiro erro (fim do "|| true" que engolia falhas).
# Se a migração falhar, o deploy é abortado ANTES de reiniciar o serviço.
ssh "$SERVER" "cd $REMOTE_PATH && source venv/bin/activate && python scripts/run_migrations.py" \
  || { echo "❌ Migração falhou — deploy abortado (serviço NÃO reiniciado)."; exit 1; }

echo "🔄 Ajustando permissões e reiniciando serviço..."
ssh "$SERVER" "chown -R www-data:www-data $REMOTE_PATH && systemctl restart nutrisabor && systemctl status nutrisabor --no-pager -l"

echo "✅ Deploy concluído! Acesse https://nutrisabor.sistemaswgs.com.br"
