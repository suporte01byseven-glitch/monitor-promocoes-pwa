# Monitor de Promoções 3.0 — PWA + API serverless

Aplicação PWA para acompanhar preços, registrar histórico, criar alertas e exportar alertas em CSV. O projeto possui modo local (Python + SQLite) e modo produção na Vercel (FastAPI + PostgreSQL).

A API usa autenticação por senha e token de sessão. O frontend está em `public/`, o backend serverless em `index.py` e o backend local em `server.py`.

## Deploy

1. Crie um PostgreSQL gerenciado e configure `DATABASE_URL`.
2. Configure na Vercel `APP_PASSWORD` (mínimo 12 caracteres), `JWT_SECRET` (32+ caracteres) e `CRON_SECRET` (24+ caracteres).
3. Importe este repositório na Vercel usando a raiz como diretório do projeto.
4. Configure no GitHub Actions `APP_CRON_URL` e `CRON_SECRET` para habilitar a varredura automática a cada 15 minutos.

Veja este README completo no próximo commit para a lista de rotas, integrações, execução local e limites conhecidos.