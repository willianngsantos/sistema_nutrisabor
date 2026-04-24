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

echo "📦 Instalando/atualizando dependências Python..."
ssh "$SERVER" "cd $REMOTE_PATH && source venv/bin/activate && pip install -r requirements.txt"

echo "🔄 Rodando migrações pendentes..."
ssh "$SERVER" "cd $REMOTE_PATH && source venv/bin/activate && python scripts/add_tokens_acesso.py 2>/dev/null || true && python scripts/add_feriado_cardapio.py 2>/dev/null || true && python scripts/add_editado_por_cardapio.py 2>/dev/null || true && python scripts/add_rh_tables.py 2>/dev/null || true && python scripts/add_ponto_almoco.py 2>/dev/null || true && python scripts/add_data_pagamento.py 2>/dev/null || true && python scripts/add_audit_log.py 2>/dev/null || true && python scripts/add_jornada_dias.py 2>/dev/null || true"

echo "🔄 Ajustando permissões e reiniciando serviço..."
ssh "$SERVER" "chown -R www-data:www-data $REMOTE_PATH && systemctl restart nutrisabor && systemctl status nutrisabor --no-pager -l"

echo "✅ Deploy concluído! Acesse https://nutrisabor.sistemaswgs.com.br"
