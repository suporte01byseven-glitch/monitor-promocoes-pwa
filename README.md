# Monitor de Promocoes — PWA + API

> **Estado deste repositorio:** estrutura inicial de deploy e automacao enviada. O codigo da aplicacao (API `index.py`, backend local `server.py`, frontend `public/` e `web/`, testes e icones) ainda precisa ser enviado para este repositorio antes de importar na Vercel. Nao faca o deploy deste estado parcial.

## Arquitetura prevista

- Frontend PWA em `public/` para hospedagem estatica na Vercel.
- API FastAPI em `index.py` como Vercel Function.
- PostgreSQL gerenciado para persistencia; SQLite fica apenas no modo local.
- Backend local em `server.py`.
- GitHub Actions para executar a verificacao agendada a cada 15 minutos.

## Arquivos de configuracao ja enviados

- `vercel.json`: cabecalhos de seguranca e limite da funcao Python.
- `requirements.txt`: FastAPI e driver PostgreSQL.
- `.env.example`: nomes das variaveis necessarias, sem credenciais reais.
- `.gitignore`: ignora arquivos locais, bancos e segredos.
- `.github/workflows/ci.yml`: validacoes automatizadas.
- `.github/workflows/scheduled-scan.yml`: chamada agendada da API.

## Configuracao apos enviar o codigo completo

Na Vercel, cadastre:

| Variavel | Finalidade |
|---|---|
| `DATABASE_URL` | URL do PostgreSQL com SSL |
| `APP_PASSWORD` | Senha administrativa, minimo 12 caracteres |
| `JWT_SECRET` | Segredo de assinatura, minimo 32 caracteres |
| `CRON_SECRET` | Segredo exclusivo do agendador, minimo 24 caracteres |
| `RSS_FEEDS` | Opcional: lista JSON de feeds RSS HTTPS |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Notificacoes Telegram opcionais |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | E-mail opcional |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Business opcional |

No GitHub Actions, configure `APP_CRON_URL` como variavel e `CRON_SECRET` como secret. A URL deve terminar em `/api/cron/scan`.

**Importante:** nao coloque senhas, tokens, `.env`, `config.json` com credenciais ou banco SQLite no Git.

## Publicacao

1. Envie o codigo completo da aplicacao para a raiz deste repositorio.
2. Importe o repositorio na Vercel usando a raiz como Root Directory.
3. Configure as variaveis acima e conecte um PostgreSQL gerenciado.
4. Execute o workflow CI e valide `/api/health` apos o deploy.

A documentacao completa de rotas, fontes de preco, notificacoes e execucao local esta no pacote do projeto entregue nesta conversa. Epic, GOG, Nuuvem e Amazon nao devem ser consideradas integradas ate que seus adaptadores oficiais sejam implementados e testados.
