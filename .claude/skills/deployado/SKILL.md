---
name: deployado
description: Valida em PRODUÇÃO, somente leitura, que o último deploy do NutriSabor foi aplicado por completo e funciona. Use SEMPRE que o Willian disser "Deployado" (ou "deployei", "fiz o deploy", "subiu pra produção") ou chamar /deployado. Conecta no servidor, confere arquivos byte a byte contra o repo local, serviço, logs, HTTP, dependências, crons e backup, e depois prova uma a uma cada mudança feita desde a última validação.
---

# Deployado — validação de produção

Willian faz o deploy (`git push origin main && ./deploy.sh`) e avisa com "Deployado".
Seu trabalho é **provar** que tudo chegou e funciona — não presumir. "O deploy
rodou sem erro" não basta: nesta base já houve código novo em disco com processo
antigo em memória, e cron "configurado" que nunca rodou.

## Regra de ouro: só leitura

Nesta skill você **não altera produção**: nada de reiniciar serviço, rodar
migração, editar crontab, gravar arquivo, rodar `deploy.sh` ou fazer POST.
Encontrou problema → mostre a evidência, diga a causa provável e proponha a
correção. Só aja depois que o Willian aprovar.

Também não exiba segredos: nunca imprima o `.env` nem senhas, mesmo do servidor.

## Passo 1 — checagens mecânicas

Da raiz do repo:

```bash
bash .claude/skills/deployado/verificar_prod.sh
```

Cobre: acesso SSH, git local (sujo/não enviado), **paridade de arquivos por
conteúdo** (rsync `--dry-run --checksum` com as mesmas exclusões do
`deploy.sh`), serviço ativo e **reiniciado depois do arquivo mais novo**, erros
no log desde o restart, HTTP público, dependências do `requirements.txt`,
WeasyPrint, crontab sem caracteres estranhos, idade do último backup, e a lista
de commits desde a última validação.

Se sair com código 2 (sem SSH): a chave é `~/.ssh/nutrisabor_servidor`
(entrada no `~/.ssh/config`). Não peça senha do servidor; avise o Willian.

## Passo 2 — provar cada novidade

Para **cada commit** listado em "Novidades", leia `git show --stat <hash>` e
faça **uma checagem que prove que a mudança está viva em produção**, não só
que o arquivo chegou (isso o Passo 1 já cobre). Escolha pela natureza:

| Mudança | Como provar (somente leitura) |
|---|---|
| Migração nova (`scripts/add_*.py`) | Leia o script, veja o objeto que ele cria e confira no banco de produção via `INFORMATION_SCHEMA` (coluna/índice/tabela). Rode Python no venv do servidor lendo o `.env` com `load_dotenv`; **guarde a conexão numa variável** antes de criar o cursor (senão: "weakly-referenced object no longer exists"). |
| Rota/página pública ou arquivo estático | `curl` na URL de produção e procure no corpo um trecho que só existe na versão nova. |
| Página que exige login | Não autentique nem simule usuário (gravaria no audit_log). Confirme o trecho novo no template/rota já em disco no servidor (`grep`) — junto com o restart pós-deploy do Passo 1, isso prova que está servido. |
| Cron | `crontab -l` + `od -c` na linha; confira no syslog/journal que o horário passou e rodou, e o log/artefato que ele gera. |
| Script de manutenção/backup | Confira artefato e log recentes. Só execute se for comprovadamente read-only. |
| Dependência nova | Import no venv do servidor. |
| Só docs/testes | Diga que não há o que validar em produção. |

## Passo 3 — relatório

Curto, em português, nesta forma:

```
DEPLOYADO — <hash curto> · <data/hora>
Infra:      ✅/❌ por área do Passo 1 (uma linha cada; detalhe só no que falhou)
Novidades:  ✅/❌ <hash> <assunto> — evidência em 1 linha
Veredito:   TUDO APLICADO  |  N PROBLEMA(S) → causa provável + correção proposta
```

Avisos (⚠️) não reprovam o deploy, mas mencione: commit não enviado ao GitHub
significa que produção roda código que não existe no GitHub.

## Passo 4 — registrar a validação

Só se **tudo** passou (Passo 1 sem ❌ e todas as novidades ✅):

```bash
git rev-parse HEAD > "$(git rev-parse --git-dir)/deployado_ultimo"
```

Fica dentro de `.git/` — local, não vai pro GitHub nem pro servidor. A próxima
validação parte daqui. Se algo falhou, **não** atualize: as mesmas novidades
voltam a ser checadas depois da correção.
