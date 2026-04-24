# Deploy NutriSabor — DigitalOcean + nutrisabor.sistemaswgs.com.br

Guia completo para subir o sistema em produção.  
URL final: `https://nutrisabor.sistemaswgs.com.br`

---

## FASE 1 — Criar o Droplet na DigitalOcean

1. Acesse [digitalocean.com](https://digitalocean.com) e crie uma conta
2. Clique em **Create → Droplets**
3. Configure:
   - **Distro:** Ubuntu 24.04 LTS x64
   - **Plano:** Basic → Regular → **$6/mês** (1 vCPU / 1 GB RAM / 25 GB SSD)
   - **Região:** New York (mais próximo do Brasil com boa latência)
   - **Autenticação:** Password (crie uma senha forte) ou SSH Key (recomendado)
4. Clique em **Create Droplet**
5. Anote o **IP do servidor** que aparecer (ex: `164.90.xxx.xxx`)

---

## FASE 2 — Apontar o DNS na KingHost

No painel da KingHost, acesse **DNS / Zona DNS** do domínio `sistemaswgs.com.br` e adicione:

| Tipo | Nome        | Valor           | TTL  |
|------|-------------|-----------------|------|
| A    | nutrisabor  | IP_DO_DROPLET   | 3600 |

Aguarde até 1 hora para propagar. Pode testar com: `ping nutrisabor.sistemaswgs.com.br`

---

## FASE 3 — Configuração inicial do servidor

Conecte via SSH no Mac:

```bash
ssh root@IP_DO_DROPLET
```

Atualize o sistema e instale as dependências:

```bash
apt update && apt upgrade -y

apt install -y python3 python3-pip python3-venv git nginx \
  certbot python3-certbot-nginx mysql-server ufw \
  libxrender1 libxext6 libfontconfig1
```

### Configurar firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
# Confirme com "y"
```

---

## FASE 4 — Configurar o MySQL

```bash
mysql_secure_installation
# Responda: N, No, No, Yes, Yes, Yes, Yes
```

Crie o banco e o usuário da aplicação:

```bash
mysql -u root -p
```

Dentro do MySQL:

```sql
CREATE DATABASE nutrisabor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nutrisabor_user'@'localhost' IDENTIFIED BY 'SENHA_FORTE_AQUI';
GRANT ALL PRIVILEGES ON nutrisabor.* TO 'nutrisabor_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> ⚠️ Substitua `SENHA_FORTE_AQUI` por uma senha real e anote-a.

---

## FASE 5 — Enviar o projeto para o servidor

No **Mac**, dentro da pasta do projeto:

```bash
# Exportar o banco de dados do Mac
mysqldump -u root -p nutrisabor > nutrisabor_backup.sql

# Enviar o projeto e o backup para o servidor
scp -r /caminho/para/sistema_nutrisabor root@IP_DO_DROPLET:/var/www/nutrisabor
scp nutrisabor_backup.sql root@IP_DO_DROPLET:/root/
```

> Substitua `/caminho/para/sistema_nutrisabor` pelo caminho real no seu Mac  
> (ex: `~/Documents/WiLL/sistema_nutrisabor`)

---

## FASE 6 — Importar o banco de dados

De volta ao servidor (SSH):

```bash
mysql -u nutrisabor_user -p nutrisabor < /root/nutrisabor_backup.sql
rm /root/nutrisabor_backup.sql
```

---

## FASE 7 — Configurar o ambiente Python

```bash
cd /var/www/nutrisabor

# Remover o venv do Mac (incompatível)
rm -rf venv

# Criar venv novo no servidor
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

deactivate
```

---

## FASE 8 — Configurar o .env de produção

```bash
nano /var/www/nutrisabor/.env
```

Conteúdo do arquivo (ajuste os valores):

```env
SECRET_KEY=GERE_UMA_CHAVE_ALEATORIA_LONGA_AQUI
DB_HOST=localhost
DB_USER=nutrisabor_user
DB_PASSWORD=SENHA_FORTE_AQUI
DB_NAME=nutrisabor
DB_PORT=3306
DB_POOL_SIZE=5
```

> Para gerar uma SECRET_KEY segura, rode no Mac:  
> `python3 -c "import secrets; print(secrets.token_hex(32))"`

Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.

### Proteger o arquivo .env

```bash
chmod 600 /var/www/nutrisabor/.env
chown www-data:www-data /var/www/nutrisabor/.env
```

---

## FASE 9 — Permissões da pasta

```bash
chown -R www-data:www-data /var/www/nutrisabor
chmod -R 755 /var/www/nutrisabor
chmod -R 775 /var/www/nutrisabor/static/uploads
```

---

## FASE 10 — Testar o Flask diretamente

```bash
cd /var/www/nutrisabor
source venv/bin/activate
python app.py
```

Se aparecer `Running on http://0.0.0.0:5001` sem erros, está tudo certo.  
Pare com `Ctrl+C` e saia do venv:

```bash
deactivate
```

---

## FASE 11 — Criar o serviço systemd (auto-start)

```bash
nano /etc/systemd/system/nutrisabor.service
```

Conteúdo:

```ini
[Unit]
Description=NutriSabor Flask App
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/nutrisabor
Environment="PATH=/var/www/nutrisabor/venv/bin"
EnvironmentFile=/var/www/nutrisabor/.env
ExecStart=/var/www/nutrisabor/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:5001 \
    --timeout 120 \
    --access-logfile /var/log/nutrisabor/access.log \
    --error-logfile /var/log/nutrisabor/error.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Salve e ative:

```bash
mkdir -p /var/log/nutrisabor
chown www-data:www-data /var/log/nutrisabor

systemctl daemon-reload
systemctl enable nutrisabor
systemctl start nutrisabor

# Verificar se está rodando:
systemctl status nutrisabor
```

---

## FASE 12 — Configurar o Nginx

```bash
nano /etc/nginx/sites-available/nutrisabor
```

Conteúdo:

```nginx
server {
    listen 80;
    server_name nutrisabor.sistemaswgs.com.br;

    # Logs
    access_log /var/log/nginx/nutrisabor_access.log;
    error_log  /var/log/nginx/nutrisabor_error.log;

    # Tamanho máximo de upload (logos dos clientes)
    client_max_body_size 5M;

    # Arquivos estáticos servidos diretamente pelo Nginx
    location /static/ {
        alias /var/www/nutrisabor/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Tudo mais vai para o Flask via Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_set_header   Host              $http_host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Ative e teste:

```bash
ln -s /etc/nginx/sites-available/nutrisabor /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

---

## FASE 13 — SSL com Let's Encrypt (HTTPS gratuito)

> ⚠️ O DNS precisa já estar propagado antes deste passo.

```bash
certbot --nginx -d nutrisabor.sistemaswgs.com.br
```

Siga o assistente:
- Informe seu e-mail
- Aceite os termos (A)
- Escolha redirecionar HTTP para HTTPS (2)

O Certbot configura o Nginx automaticamente. Renovação é automática.

---

## FASE 14 — Verificação final

```bash
# Status do serviço Flask
systemctl status nutrisabor

# Ver logs em tempo real
journalctl -u nutrisabor -f

# Testar localmente no servidor
curl -I http://127.0.0.1:5001
```

Acesse no navegador: **https://nutrisabor.sistemaswgs.com.br**

---

## WORKFLOW DE ATUALIZAÇÕES (do Mac para produção)

Toda vez que fizer alterações no Mac e quiser atualizar o servidor:

```bash
# 1. No Mac — enviar os arquivos alterados
scp -r /caminho/sistema_nutrisabor/templates root@IP_DO_DROPLET:/var/www/nutrisabor/
scp -r /caminho/sistema_nutrisabor/routes root@IP_DO_DROPLET:/var/www/nutrisabor/
scp -r /caminho/sistema_nutrisabor/static root@IP_DO_DROPLET:/var/www/nutrisabor/

# 2. No servidor — reiniciar o serviço
ssh root@IP_DO_DROPLET "systemctl restart nutrisabor"
```

> **Dica:** depois que o sistema estiver estável, configure um repositório Git privado  
> (GitHub/GitLab) e o deploy vira um simples `git pull` no servidor.

---

## COMANDOS ÚTEIS NO SERVIDOR

```bash
# Ver logs de erro do Flask
tail -f /var/log/nutrisabor/error.log

# Ver logs do Nginx
tail -f /var/log/nginx/nutrisabor_error.log

# Reiniciar Flask após atualizações
systemctl restart nutrisabor

# Reiniciar Nginx
systemctl reload nginx

# Ver uso de memória/CPU
htop
```

---

## RESUMO DOS SERVIÇOS

| Serviço    | Porta  | Função                              |
|------------|--------|-------------------------------------|
| Gunicorn   | 5001   | Servidor Python/Flask (interno)     |
| Nginx      | 80/443 | Proxy reverso + SSL + arquivos estáticos |
| MySQL      | 3306   | Banco de dados (interno)            |
| Certbot    | —      | Renovação automática do SSL         |
