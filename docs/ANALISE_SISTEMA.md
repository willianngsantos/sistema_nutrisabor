# 📊 Análise Técnica — Sistema NutriSabor
> Gerado em: 06/04/2026 | Revisado por: Claude (Cowork)

---

## 1. Visão Geral

O **Sistema NutriSabor** é uma aplicação web construída em **Python/Flask** com banco **MySQL**, voltada para a gestão operacional e financeira de uma cozinha industrial/serviço de alimentação. O sistema está funcional e bem estruturado para o porte atual.

**Stack principal:**
- Backend: Python 3.13 + Flask 3.1.2
- Banco de dados: MySQL (via `mysql-connector-python` com connection pool)
- Autenticação: Flask-Login 0.6.3 + Werkzeug (bcrypt hash)
- Frontend: Bootstrap 5 + Bootstrap Icons
- PDF: pdfkit (depende do `wkhtmltopdf` instalado no OS)

---

## 2. Módulos e Funcionalidades

### 2.1 Autenticação (`routes/auth.py`)
- Login com hash seguro de senha (Werkzeug `check_password_hash`)
- Sessão permanente com expiração em 30 minutos
- Logout com limpeza de sessão
- Gerenciamento de usuários restrito ao Admin
- Configurações da empresa (Admin)

### 2.2 Cadastros (`routes/cadastros.py`)
- CRUD de **Grupos de Clientes** (com dados de PIX por grupo)
- CRUD de **Clientes** (com vínculo a grupo e apelido)
- CRUD de **Produtos** (com custo base e unidade)
- **Tabela de Preços por Cliente** (negociação individual)
- **Tabela de Preços por Grupo** (preço coletivo)

### 2.3 Vendas / Faturas (`routes/vendas.py`)
- Criação e edição de pedidos/faturas com itens
- Sistema de preço inteligente: prioridade **Cliente → Grupo → Padrão**
- Fluxo de status: `Pendente → Aprovado → Pago`
- Geração de PDF das faturas (via pdfkit/wkhtmltopdf)
- Vinculação de Nota Fiscal (NF) às faturas
- Relatórios com filtro por período, cliente e status
- Código de fatura automático por quinzena

### 2.4 Cardápios (`routes/cardapios.py`)
- Criação de cardápios semanais (5 ou 6 dias) por cliente
- Preenchimento de pratos por dia (base, principal 1/2, guarnição, salada, sobremesa, bebida)
- Template de impressão de cardápio
- Acesso restrito a Admin e Nutricionista

### 2.5 Dashboard (`app.py`)
- KPIs financeiros: faturamento do mês atual, mês anterior e ano
- Listagem de faturas com filtro por mês/ano/cliente/status/NF
- Persistência do filtro na sessão do usuário

### 2.6 Papéis de Usuário
| Papel | Acesso |
|-------|--------|
| `admin` | Tudo — incluindo usuários, empresa, cardápios, faturas |
| `vendedor` | Dashboard, faturas, clientes, produtos, relatórios |
| `nutricionista` | Apenas cardápios |

---

## 3. ⚠️ Problemas Críticos de Segurança

### 3.1 🔴 Credenciais expostas no código-fonte
**Arquivos:** `database.py` e `setup_empresa.py`

As credenciais do banco de dados estão escritas diretamente no código:
```python
'password': 'Wgs010203'
```
Se este código for versionado no Git ou compartilhado, a senha fica exposta.

**Solução:** Usar variáveis de ambiente com `python-dotenv`.

### 3.2 🔴 `secret_key` fraca e hardcoded
**Arquivo:** `app.py`

```python
app.secret_key = 'CHAVE_SUPER_SECRETA_DO_WILL'
```
Chaves hardcoded são vulneráveis e previsíveis.

**Solução:** Gerar uma chave aleatória segura e carregá-la via `.env`.

### 3.3 🟠 Mudanças de estado via requisição GET (risco de CSRF)
**Arquivo:** `routes/vendas.py`

Rotas como `/mudar_status/<id>/<status>` e `/excluir_pedido/<id>` alteram dados via GET. Isso significa que um simples link externo ou imagem incorporada pode acionar essas ações sem que o usuário perceba.

**Solução:** Converter para POST com confirmação e adicionar proteção CSRF (Flask-WTF).

---

## 4. 🐛 Bugs e Inconsistências

### 4.1 Conflito de rota na raiz "/"
`app.py` registra `@app.route('/')` (função `index`) e `cadastros.py` registra `@cadastros_bp.route("/")` (função `home`) **sem prefixo de URL**. Em Flask, a última rota registrada sobrescreve a anterior — o comportamento do sistema na rota `/` pode ser imprevisível.

**Solução:** Definir um `url_prefix` para o blueprint de cadastros (ex: `/cadastros`) ou remover a rota duplicada.

### 4.2 Cursor misto: `dictionary=True` vs tupla
Ao longo das rotas, algumas queries usam `cursor(dictionary=True)` e outras usam o cursor padrão (tuplas), até dentro da mesma função (`vendas.py/baixar_pdf` usa os dois). Isso gera código inconsistente e propenso a erros de índice vs chave.

**Solução:** Padronizar para `dictionary=True` em todo o projeto.

### 4.3 Scripts de migração na raiz do projeto
Os arquivos `atualizar_banco_*.py`, `reset_db.py`, `reparar_senha.py` e `setup_empresa.py` são scripts avulsos misturados com o código da aplicação. Isso polui o projeto e pode ser executado acidentalmente.

**Solução:** Criar uma pasta `/migrations` ou `/scripts` e movê-los para lá.

### 4.4 `except: pass` silencioso
Em `routes/cadastros.py`, alguns blocos `except` não logam o erro, dificultando o diagnóstico de problemas em produção.

### 4.5 Arquivo `requirements.txt` ausente
Não há um `requirements.txt` na raiz do projeto. Isso dificulta a instalação em outro ambiente.

---

## 5. 💡 Melhorias Sugeridas (Prioridade Alta)

### 5.1 Gráfico de Faturamento no Dashboard
O painel atual mostra apenas 3 cards de KPI (texto). Um gráfico de barras mensal (usando Chart.js, que já está disponível no Bootstrap CDN) tornaria a evolução do negócio visualmente clara.

### 5.2 Paginação na lista de faturas
A query do dashboard traz **todas** as faturas sem limite. Com o crescimento dos dados, isso pode lentificar a página. Adicionar paginação (10-20 por página) é essencial.

### 5.3 Data de Pagamento
O fluxo atual registra apenas que uma fatura foi "Paga", mas não **quando** foi recebido. Adicionar um campo `data_pagamento` na tabela `pedidos` permitiria relatórios de fluxo de caixa real.

### 5.4 Envio de Fatura por WhatsApp/E-mail
A fatura já tem um botão "Ver/Enviar", mas aparentemente abre apenas a visualização. Integrar um botão de compartilhamento direto via WhatsApp Web (`https://wa.me/?text=...`) ou envio por e-mail (Flask-Mail) eliminaria etapas manuais.

### 5.5 Busca de CEP automática
No formulário de configuração da empresa, adicionar busca automática via API ViaCEP ao digitar o CEP preencheria endereço/cidade/estado automaticamente.

---

## 6. 💡 Melhorias Sugeridas (Prioridade Média)

### 6.1 Exportação para Excel
Adicionar um botão "Exportar" nos relatórios geraria um `.xlsx` dos dados filtrados. Útil para contabilidade e controles externos.

### 6.2 Log de Auditoria
Registrar quem fez cada ação (aprovação, pagamento, exclusão) em uma tabela `log_atividades`. Fundamental para rastreabilidade.

### 6.3 Confirmação antes de mudanças críticas
Ações como "Aprovar" e "Marcar como Pago" não pedem confirmação. Adicionar um modal de confirmação para essas ações evitaria cliques acidentais.

### 6.4 Validação de formulários no backend
Alguns campos (CNPJ, e-mail, valores) não são validados no servidor antes de serem salvos no banco. Uma biblioteca como `WTForms` ou validações manuais evitariam dados inconsistentes.

### 6.5 Imagem/logo nos cardápios impressos
O template de impressão de cardápio poderia incluir o logo da empresa (já existe em `static/img/logo.png`) para um aspecto mais profissional ao entregar para os clientes.

---

## 7. 💡 Novas Funcionalidades Potenciais

### 7.1 Portal do Cliente (MVP Futuro)
Uma área simplificada onde o cliente pode visualizar suas faturas e o cardápio da semana — sem acesso ao painel administrativo.

### 7.2 Geração de Cardápio em PDF
Assim como existe para faturas, um botão "Imprimir PDF" no cardápio semanal com layout formatado e logo seria muito útil para enviar para os clientes.

### 7.3 Notificações de Vencimento
Um sistema de alertas no dashboard ou por e-mail avisando sobre faturas aprovadas há mais de X dias ainda sem pagamento.

### 7.4 Faturamento Recorrente
Para clientes com pedidos mensais fixos, uma opção de "clonar fatura do mês anterior" economizaria tempo no dia a dia.

### 7.5 Múltiplos Usuários Vendedores com Comissão
Se o negócio crescer para ter mais de um vendedor, rastrear qual usuário criou cada pedido (campo `id_usuario` em `pedidos`) permitiria calcular comissões.

---

## 8. Resumo Executivo

| Área | Avaliação |
|------|-----------|
| Arquitetura geral | ✅ Boa — Flask + Blueprints bem separados |
| Segurança | 🔴 Crítico — credenciais e secret_key expostos |
| Funcionalidades core | ✅ Completas e funcionais |
| Qualidade do código | 🟡 Média — inconsistências pontuais |
| Escalabilidade | 🟡 Limitada — sem paginação, sem logs |
| UX / Interface | ✅ Boa — Bootstrap 5 bem aplicado |
| Manutenibilidade | 🟡 Média — sem requirements.txt, scripts misturados |

**Próximos passos recomendados (em ordem):**
1. Mover credenciais para `.env` (segurança imediata)
2. Corrigir conflito de rota `/`
3. Padronizar cursors para `dictionary=True`
4. Adicionar campo `data_pagamento` + gráfico de faturamento no dashboard
5. Implementar paginação na lista de faturas

---
*Análise gerada por Claude via Cowork — NutriSabor © 2026*
