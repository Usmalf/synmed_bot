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
SYNMED_BACKUP_ROOT=/var/data/backups
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
- `SYNMED_BACKUP_ROOT` controls where generated backup files are staged. On Render, keep it on the persistent disk, for example `/var/data/backups`.
- Those files can later move to durable object storage by replacing the adapter in `services/storage_service.py`.
- After deployment, update `BACKEND_CORS_ORIGINS`, `FRONTEND_BASE_URL`, `AUTH_VERIFY_BASE_URL`, and `VITE_API_BASE_URL` with the final live domains.

## Backup and Restore

Admin users can open **Admin > Settings > Backups** to download:

- **Database backup**: a consistent SQLite snapshot of `DATABASE_PATH`.
- **Full backup**: a ZIP archive containing `database/synmed.db` plus the contents of `SYNMED_STORAGE_ROOT` under `storage/`.

Recommended routine:

1. Download a full backup before any major deployment, database migration, or manual production data change.
2. Keep a copy outside Render, such as a secured cloud drive controlled by the business.
3. Confirm the backup file size is not zero and that the ZIP opens locally.

Manual restore on Render:

1. Pause or stop the backend service to avoid writes during restore.
2. Open the Render shell for the backend service.
3. Upload or place the full backup ZIP in the shell environment.
4. Run:

```bash
mkdir -p /var/data/restore
unzip synmed_full_backup_YYYYMMDD_HHMMSS.zip -d /var/data/restore
cp /var/data/restore/database/synmed.db /var/data/synmed.db
rm -rf /var/data/storage
mkdir -p /var/data/storage
cp -a /var/data/restore/storage/. /var/data/storage/
```

5. Restart the backend service.
6. Confirm `/health` responds and test admin login, patient documents, doctor licence previews, and chat attachments.

Database-only restore:

```bash
cp synmed_backup_YYYYMMDD_HHMMSS.db /var/data/synmed.db
```

Use database-only restore only when stored files are already intact or not needed.

## SQLite to PostgreSQL Migration

The app can run on SQLite by default or PostgreSQL when `DATABASE_URL` is set.
Do not set `DATABASE_URL` on production until the data import has been tested.

Before migrating:

1. Download a full backup from **Admin > Settings > Backups**.
2. Create a Render PostgreSQL database.
3. Copy the external PostgreSQL connection string.
4. Keep the backend on SQLite until the import has been tested.

Dry-run the local SQLite file:

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite-path .\synmed.db `
  --database-url "postgresql://USER:PASSWORD@HOST:PORT/DATABASE" `
  --dry-run
```

Import into an empty PostgreSQL database:

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite-path .\synmed.db `
  --database-url "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

If the target database already has test data and should be cleared first:

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite-path .\synmed.db `
  --database-url "postgresql://USER:PASSWORD@HOST:PORT/DATABASE" `
  --replace
```

After import:

1. Verify PostgreSQL row counts against SQLite:

```powershell
python scripts/verify_postgres_migration.py `
  --sqlite-path .\synmed.db `
  --database-url "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

2. Set `DATABASE_URL` on the backend service.
3. Redeploy the backend.
4. Confirm admin login, patient login, doctor login, payments, documents, support tickets, and consultations.
5. Keep the old SQLite backup until PostgreSQL has been verified in production.

Current limitation: Admin database backup downloads are SQLite-only. When PostgreSQL is active, the backup buttons are disabled until PostgreSQL dump backups are configured.
