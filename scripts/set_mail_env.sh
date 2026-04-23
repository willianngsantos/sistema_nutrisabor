#!/bin/bash
# Configura as variáveis de e-mail (Resend) no .env de produção
# Execute: bash scripts/set_mail_env.sh re_SUA_API_KEY_AQUI

SERVER="root@157.245.80.194"
REMOTE_PATH="/var/www/nutrisabor"
RESEND_KEY="${1}"

if [ -z "$RESEND_KEY" ]; then
  echo "❌ Uso: bash scripts/set_mail_env.sh re_SUA_API_KEY"
  exit 1
fi

echo "📧 Configurando e-mail (Resend) no servidor..."

ssh "$SERVER" "
  # Remove entradas antigas
  sed -i '/^MAIL_USER=/d' $REMOTE_PATH/.env
  sed -i '/^MAIL_PASSWORD=/d' $REMOTE_PATH/.env
  sed -i '/^RESEND_API_KEY=/d' $REMOTE_PATH/.env
  sed -i '/^MAIL_FROM=/d' $REMOTE_PATH/.env
  sed -i '/^# E-mail/d' $REMOTE_PATH/.env

  # Adiciona as novas
  echo '' >> $REMOTE_PATH/.env
  echo '# E-mail (Resend)' >> $REMOTE_PATH/.env
  echo 'RESEND_API_KEY=$RESEND_KEY' >> $REMOTE_PATH/.env
  echo 'MAIL_FROM=NutriSabor <onboarding@resend.dev>' >> $REMOTE_PATH/.env

  # Instala o pacote resend no venv
  cd $REMOTE_PATH && source venv/bin/activate && pip install resend==2.10.0 -q

  echo '✅ Configuração concluída!'
  grep -E 'RESEND|MAIL' $REMOTE_PATH/.env
"
