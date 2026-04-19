## SynMed OTP Setup

This project now supports:

- Telegram OTP for doctors
- Telegram OTP for admins
- Email OTP for patients

### Required Environment Variables

Add these to the root `.env` file:

```env
AUTH_SECRET_KEY=change_this_synmed_auth_secret
AUTH_DEV_OTP_VISIBLE=1
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=1
```

### Delivery Behavior

- Doctors/admins receive OTP through the Telegram bot.
- Patients receive OTP through email.
- In development, `AUTH_DEV_OTP_VISIBLE=1` exposes the OTP in API responses for easier testing.
- In production, set `AUTH_DEV_OTP_VISIBLE=0`.

### Telegram OTP Requirement

Doctors and admins must have already started or interacted with the bot before Telegram can deliver OTP successfully.

### Email OTP Requirement

Patients must have an email saved on their SynMed patient record.

### Recommended Next Test

1. Start the bot and web backend.
2. Fill in SMTP settings.
3. Request OTP as a doctor/admin and confirm delivery in Telegram.
4. Request OTP as a patient and confirm delivery by email.
