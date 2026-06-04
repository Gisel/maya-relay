# Maya SMS Relay

FastAPI backend for routing customer SMS messages through the Maya Graphics business number while employees keep using their native SMS app.

## Project Summary

See [docs/project-summary.md](docs/project-summary.md) for the working requirements.

## Local Setup

1. Create a virtual environment.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create `.env` in this folder:

```text
/Users/giselgomez/Documents/Maya-SMS Relay/.env
```

Use `.env.example` as the template.

3. Run the app.

```bash
uvicorn app.main:app --reload
```

4. Check health.

```bash
curl http://127.0.0.1:8000/health
```

## Environment Variables

```env
APP_ENV=development
VERIFY_TWILIO_SIGNATURE=false
ENABLE_TWILIO_LOOKUP=false
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_MESSAGING_SERVICE_SID=
MAYA_BUSINESS_NUMBER=+13852208404
FRANCISCO_PHONE=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ATTACHMENTS_BUCKET=attachments
```

Keep `.env` private. It is ignored by git.

## Supabase

Run `supabase_schema.sql` in the Supabase SQL editor.

The schema enables RLS and grants access only to `service_role`, because this backend is server-only. The `anon` and `authenticated` roles are intentionally not granted table access for the MVP.

## Twilio Webhooks

For local testing, use a tunnel such as ngrok and point Twilio to:

```text
POST https://your-public-url/webhooks/twilio/sms
POST https://your-public-url/webhooks/twilio/status
```

For Railway, use:

```text
POST https://your-railway-app.up.railway.app/webhooks/twilio/sms
POST https://your-railway-app.up.railway.app/webhooks/twilio/status
```

## Railway

This repo includes `railway.toml`. Railway should run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set the same environment variables from `.env.example` in Railway's Variables tab.

## MVP Routing

- Customer texts Maya number.
- App creates or reuses an open conversation.
- App forwards the message to Francisco with a conversation code, such as `#A1B2C3D4`.
- Francisco replies to Maya number with the code, such as `#A1B2C3D4 Yes, send measurements`.
- App strips the code and routes the reply to that specific customer conversation.
- If the code is missing or invalid, app texts Francisco back with a correction instead of guessing.

## MMS Attachments

Incoming media is downloaded from Twilio with the configured Twilio credentials, uploaded to the public Supabase Storage bucket named `attachments`, recorded in `message_attachments`, and forwarded as a Supabase public URL.

## Contact Names

When `ENABLE_TWILIO_LOOKUP=true`, unknown customer phone numbers are checked once with Twilio Lookup Caller Name, then cached in `contacts.lookup_name`. If `contacts.display_name` exists, it takes precedence over Lookup.
