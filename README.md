# Monitor de Promoções 3.0 — PWA + API serverless

Aplicação PWA para acompanhar preços, registrar histórico, criar alertas e exportar alertas em CSV. O projeto agora possui dois modos de execução:

1. **Local:** frontend em `web/`, backend Python tradicional (`server.py`) e SQLite.
2. **Produção na Vercel:** frontend estático em `public/`, API FastAPI (`index.py`) como Vercel Function e PostgreSQL gerenciado.

A interface usa as mesmas rotas `/api/*` nos dois modos. Na Vercel, a API exige autenticação por senha e token de sessão; no modo local, permanece limitada ao computador local.

## Estrutura

```text
monitor-promocoes-pwa/
├── index.py                 # API FastAPI serverless
├── server.py                # Backend local SQLite
├── requirements.txt         # Dependências da API Vercel
├── .python-version
├── .env.example             # Modelo de variáveis (sem segredos reais)
├── vercel.json              # Cabeçalhos + cron
├── public/                  # Arquivos estáticos publicados pela Vercel
├── web/                     # Cópia usada pelo backend local
├── tests/
└── .github/workflows/ci.yml
```

## Deploy na Vercel

O backend FastAPI e os arquivos estáticos são publicados no mesmo projeto e domínio. A interface chama `/api/*` na mesma origem, sem precisar configurar CORS nem `API_BASE_URL`.

### 1. Criar um PostgreSQL

Crie um banco PostgreSQL gerenciado, por exemplo Neon ou Supabase. Copie a URL de conexão com SSL e use preferencialmente o endpoint/pooler indicado pelo provedor para workloads serverless.

A API cria as tabelas `items`, `offers` e `alerts` automaticamente na primeira requisição. A documentação interativa do FastAPI fica desabilitada na implantação pública. Não use SQLite na Vercel: o filesystem de funções não é armazenamento persistente.

### 2. Configurar variáveis na Vercel

No projeto Vercel, abra **Settings → Environment Variables** e cadastre os valores abaixo em Production (e também Preview/Development se for testar nesses ambientes):

| Variável | Obrigatória | Uso |
|---|---:|---|
| `DATABASE_URL` | Sim | URL PostgreSQL com SSL |
| `APP_PASSWORD` | Sim | Senha para entrar na PWA; mínimo 12 caracteres |
| `JWT_SECRET` | Sim | Segredo aleatório com pelo menos 32 caracteres |
| `CRON_SECRET` | Sim | Segredo aleatório com pelo menos 24 caracteres |
| `RSS_FEEDS` | Não | Lista JSON de feeds RSS HTTPS confiáveis |
| `TELEGRAM_BOT_TOKEN` | Não | Token do bot Telegram |
| `TELEGRAM_CHAT_ID` | Não | Chat padrão Telegram |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Não | Envio de e-mail |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION` | Não | WhatsApp Business Cloud API |

Gere os segredos localmente, por exemplo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Execute o comando separadamente para `JWT_SECRET` e `CRON_SECRET`. Não coloque valores reais no Git, no frontend ou neste README. `APP_PASSWORD` é a senha que o usuário digita na tela de login; não é enviada ao navegador depois da autenticação.

### 3. Publicar

1. Envie o projeto para um repositório GitHub.
2. Na Vercel, importe esse repositório.
3. Use a raiz do repositório como **Root Directory**.
4. Deixe o Framework Preset em `Other` ou permita a detecção automática do FastAPI.
5. Não defina `Output Directory` como `web`; os arquivos estáticos já estão em `public/` e a API FastAPI está no `index.py` da raiz.
6. Configure as variáveis de ambiente e faça o deploy.

A Vercel detecta a aplicação FastAPI exportada como `app` em `index.py`; o runtime Python atual da Vercel suporta FastAPI. Consulte a documentação oficial antes do deploy: [Python Runtime](https://vercel.com/docs/functions/runtimes/python) e [FastAPI na Vercel](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel).

### 4. Agendamento automático

O agendamento é feito por GitHub Actions, não por um processo persistente dentro da Vercel. O workflow `.github/workflows/scheduled-scan.yml` chama `GET /api/cron/scan` a cada 15 minutos e também pode ser executado manualmente. A rota exige `Authorization: Bearer <CRON_SECRET>` e consulta itens ativos cujo `next_check` venceu. O processamento é idempotente para evitar alertas repetidos no mesmo dia.

Depois de conectar o repositório ao GitHub, configure em **Settings → Secrets and variables → Actions**:

- Variável `APP_CRON_URL`: URL completa da rota, por exemplo `https://seu-projeto.vercel.app/api/cron/scan`.
- Secret `CRON_SECRET`: exatamente o mesmo valor configurado nas variáveis de ambiente da Vercel.

O agendamento do GitHub Actions é best-effort e pode sofrer atrasos de fila; não é um relógio de precisão. A frequência efetiva de cada item é limitada pela execução desse workflow. O `vercel.json` define até 60 segundos para a função de API, respeitando os limites do plano Vercel.

### 5. Verificar a API

Após o deploy:

- `https://SEU-DOMINIO/api/health` — estado da API e do banco.
- Abra a raiz do domínio, informe a senha `APP_PASSWORD` e cadastre um item.

A tela de login guarda o token de sessão no armazenamento local do navegador. O token expira em sete dias; depois disso, basta entrar novamente. Use senha forte e não compartilhe o acesso.

## Executar localmente

O modo local continua disponível sem instalar bibliotecas externas:

### Windows

1. Extraia o projeto.
2. Execute `INICIAR_WINDOWS.bat`.
3. Acesse `http://127.0.0.1:8765`.

### Linux/macOS

```bash
chmod +x INICIAR_LINUX_MAC.sh
./INICIAR_LINUX_MAC.sh
```

Ou execute `python3 server.py`. A janela do terminal precisa permanecer aberta enquanto o monitoramento automático estiver ativo. O banco local fica em `data/monitor.db`.

A aplicação detecta `localhost` e `127.0.0.1` e não solicita login no modo local. Isso não deve ser usado para expor o backend local publicamente.

## Rotas da API

Todas as rotas, exceto login e health, exigem `Authorization: Bearer <token>` na Vercel.

| Método | Rota | Função |
|---|---|---|
| GET | `/api/health` | Saúde da API e conexão PostgreSQL |
| POST | `/api/auth/login` | Autenticar com `APP_PASSWORD` e emitir token |
| GET | `/api/auth/check` | Validar sessão |
| GET | `/api/items` | Listar monitoramentos |
| POST | `/api/items` | Criar monitoramento |
| PATCH | `/api/items/{id}` | Pausar/ativar ou alterar frequência |
| DELETE | `/api/items/{id}` | Remover monitoramento, ofertas e alertas |
| GET | `/api/offers/{id}` | Consultar histórico de ofertas |
| GET | `/api/alerts` | Listar alertas |
| POST | `/api/scan` | Executar pesquisa manual |
| GET | `/api/cron/scan` | Executar pesquisas agendadas (somente CRON_SECRET) |

## Fontes de preços

- **Steam:** pesquisa no catálogo e consulta preços regionais em BRL.
- **CheapShark:** ofertas de jogos em USD; o preço-alvo em BRL não é comparado com valores em USD.
- **RSS:** feeds configurados em `RSS_FEEDS` (JSON). Para registrar uma oferta, título/descrição precisa conter preço explícito em `R$` ou `BRL`.
- **Epic Games, GOG, Nuuvem e Amazon:** aparecem como opções na interface, mas os adaptadores ainda não estão implementados. A API retorna aviso de integração não configurada; não inventa ofertas.

Configure apenas feeds RSS HTTPS confiáveis e autorizados. Credenciais e feeds são variáveis de ambiente do backend, nunca valores no `runtime-config.js`.

## Notificações

Telegram, SMTP e WhatsApp Business Cloud API são suportados quando as variáveis correspondentes estiverem configuradas na Vercel. Destinos por monitoramento são informados na interface.

## Regras de negócio

- Alerta quando o preço BRL fica abaixo do preço-alvo **ou** quando o desconto alcança o mínimo.
- Não há conversão automática entre moedas.
- Alertas repetidos com mesmo item, URL e preço no mesmo dia são deduplicados.
- A pesquisa manual consulta fontes reais; erros de provedores são retornados sem dados sintéticos.
- O histórico fica no PostgreSQL na Vercel e no SQLite no modo local.

## Testes

```bash
pip install -r requirements.txt
python -m py_compile index.py server.py
python -m unittest discover -s tests -v
node --check public/app.js
node --check public/pwa.js
node --check public/sw.js
```

Os testes automatizados não substituem a configuração real de `DATABASE_URL`, segredos e integrações externas. O health check com banco só ficará verde depois que as variáveis forem configuradas e o projeto estiver implantado.

## Segurança e limites conhecidos

- API serverless protegida por senha e tokens HMAC com expiração de sete dias.
- Segredos mantidos somente em variáveis de ambiente; `.env`, banco local e `config.json` são ignorados pelo Git.
- Cron protegido por segredo próprio.
- Rotas de dados exigem autenticação; health e login são públicos por necessidade operacional.
- O token de sessão é armazenado no navegador; proteja a conta e evite extensões não confiáveis.
- O login ainda depende de rate limiting/firewall no provedor para proteção adicional contra tentativas automatizadas.
- Feeds RSS são configurados pelo administrador; use somente domínios confiáveis.
- Fontes externas podem aplicar limites, indisponibilidade e restrições regionais.
- A PWA funciona offline apenas para o app shell; pesquisas, histórico, alertas e notificações exigem conexão.

