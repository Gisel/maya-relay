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
ENABLE_AI_TRIAGE=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini
ADMIN_PASSWORD=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_MESSAGING_SERVICE_SID=
MAYA_BUSINESS_NUMBER=+13852208404
FRANCISCO_PHONE=
EMPLOYEE_PHONE_NUMBERS=
BUSINESS_HOURS_TEXT=Monday-Friday 9:00 AM-6:00 PM. Saturday is by appointment.
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

Railway builds the React operator inbox from `frontend/` during the same service build, then FastAPI serves the compiled app at `/app`. The backend remains the only running service.

For local frontend work:

```bash
npm install
npm --workspace frontend run dev
```

For production build verification:

```bash
npm run build
```

## Demo Operations

Before demoing with Francisco's real phone:

1. Set `FRANCISCO_PHONE` in Railway to Francisco's cellphone.
2. Clear `EMPLOYEE_PHONE_NUMBERS` unless an extra helper/test phone should also be allowed to reply.
3. Wait for Railway to redeploy/restart.
4. Open `/readiness` and confirm `"status": "ready"`.
5. Confirm `"francisco_phone_is_not_maya_number": true`.
6. Send a fresh customer SMS and reply using the new `#code`.

## Admin Dashboard

Set `ADMIN_PASSWORD` to enable the read-only operations dashboard at `/admin`. Leave it blank to hide the dashboard.

## React App API Foundation

The React operator inbox will use authenticated JSON routes under `/api`. These routes use the same `ADMIN_PASSWORD` session cookie as `/admin`, keep all secrets server-side, and are additive to the existing Twilio webhooks.

Current Phase 1 routes:

- `GET /api/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/readiness`
- `GET /api/metrics`
- `GET /api/quick-responses`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}`
- `GET /api/conversations/{conversation_id}/messages`
- `PATCH /api/conversations/{conversation_id}`
- `POST /api/conversations/{conversation_id}/reply`

The reply endpoint accepts `multipart/form-data` with `body`, `client_request_id`, and optional `reply_files`. `client_request_id` is stored on the message to prevent accidental duplicate sends from browser retries or double-clicks.

## MVP Routing

- Customer texts Maya number.
- App creates or reuses an open conversation.
- App forwards the message to Francisco with a conversation code, such as `#A1B2C3D4`.
- Francisco replies to Maya number with the code, such as `#A1B2C3D4 Yes, send measurements`.
- App strips the code and routes the reply to that specific customer conversation.
- If the code is missing or invalid, app texts Francisco back with a correction instead of guessing.

`FRANCISCO_PHONE` is the primary phone that receives forwarded customer texts. It must be an employee phone, not the Maya business number. `EMPLOYEE_PHONE_NUMBERS` is an optional comma-separated allowlist of additional phones that may reply with conversation codes. Phone values are normalized, so `8018334544` and `+18018334544` are treated as the same US number.

## MMS Attachments

Incoming media is downloaded from Twilio with the configured Twilio credentials, uploaded to the public Supabase Storage bucket named `attachments`, recorded in `message_attachments`, and forwarded as a Supabase public URL.

## Contact Names

When `ENABLE_TWILIO_LOOKUP=true`, unknown customer phone numbers are checked once with Twilio Lookup Caller Name, then cached in `contacts.lookup_name`. If `contacts.display_name` exists, it takes precedence over Lookup.

## AI Triage

When `ENABLE_AI_TRIAGE=true`, inbound customer messages are summarized for Francisco with a short internal AI note. The note is included only in the employee-facing forwarded SMS. The app never sends AI-generated text directly to customers.
