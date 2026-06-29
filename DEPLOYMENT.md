# SynMed Deployment Checklist

This project has three deployable parts:

1. FastAPI web backend: `web.backend.app.main:app`
2. Vite/React frontend: `web/frontend`
3. Telegram bot worker: `bot.py`

## Recommended First Deployment

Deploy the backend and frontend first. Deploy the Telegram bot worker after the web app is stable.

## Backend

Start command:

```bash
uvicorn web.backend.app.main:app --host 0.0.0.0 --port $PORT
```

Install command:

```bash
pip install -r requirements.txt -r web/backend/requirements.txt
```

Required environment variables:

```text
DATABASE_PATH=/var/data/synmed.db
SYNMED_STORAGE_ROOT=/var/data/storage
AUTH_SECRET_KEY=<generate a long random secret>
AUTH_DEV_OTP_VISIBLE=0
FRONTEND_BASE_URL=https://your-frontend-domain
AUTH_VERIFY_BASE_URL=https://your-frontend-domain/patient/verify-email
BACKEND_CORS_ORIGINS=https://your-frontend-domain
BOT_TOKEN=<telegram bot token>
ADMIN_IDS=<comma separated telegram/admin ids>
PAYSTACK_SECRET_KEY=<paystack secret>
PAYSTACK_PUBLIC_KEY=<paystack public key>
PAYSTACK_CURRENCY=NGN
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=<sender email>
SMTP_PASSWORD=<app password>
SMTP_FROM_EMAIL=<sender email>
SMTP_USE_TLS=0
SMTP_USE_SSL=1
```

## Frontend

Build command:

```bash
npm ci && npm run build
```

Publish directory:

```text
web/frontend/dist
```

Required environment variable:

```text
VITE_API_BASE_URL=https://your-backend-domain
```

## Telegram Bot Worker

Existing worker command:

```bash
python bot.py
```

Use the same `BOT_TOKEN`, `ADMIN_IDS`, Paystack, SMTP, and database environment values as the backend if the bot and web backend need to share the same data.

## Important Notes

- Do not upload `.env` to a public repository or deployment image.
- Do not rely on the local `synmed.db` file for production.
- Use persistent storage for SQLite, or move to a managed database before heavy real usage.
- `SYNMED_STORAGE_ROOT` controls where generated PDFs, consultation media, and doctor licence uploads are saved.
- On Render, keep `SYNMED_STORAGE_ROOT` on the persistent disk, for example `/var/data/storage`.
- Those files can later move to durable object storage by replacing the adapter in `services/storage_service.py`.
- After deployment, update `BACKEND_CORS_ORIGINS`, `FRONTEND_BASE_URL`, `AUTH_VERIFY_BASE_URL`, and `VITE_API_BASE_URL` with the final live domains.
