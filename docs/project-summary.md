# Maya Relay - Project Summary

## Objective

Build a communication relay platform for Maya Graphics and Signs that allows customers to communicate through the Maya business number while employees continue using their native cellphone messaging applications.

No dashboards.

No CRM requirement for MVP.

No additional apps required for employees.

The system acts as a routing layer between customers and employees.

## Current State

### Twilio

Business number:

`+1 (385) 220-8404`

Status:

- SMS enabled
- MMS enabled
- A2P campaign approved
- Messaging Service configured
- Sender pool configured

Campaign:

- Low Volume Mixed
- Status: Verified

SMS testing:

- Incoming SMS: working
- Outgoing SMS: working
- Delivery confirmed

### Voice System

Production IVR completed.

Features:

- English routing
- Spanish routing
- Business hours routing
- Saturday routing
- Closed-hours voicemail
- English voicemail
- Spanish voicemail

Voice routing remains functional.

### WhatsApp

Current status:

- Existing WhatsApp Business Account exists
- Incorrect test sender registered previously
- Need Meta admin access to remove old sender
- Need to register `+1 (385) 220-8404` as production WhatsApp sender

Do not work on WhatsApp until Meta access is available.

## Maya Relay MVP

```text
Customer SMS
  -> Twilio
  -> FastAPI
  -> Supabase
  -> Forward SMS to Francisco

Francisco replies via native SMS app
  -> Twilio
  -> FastAPI
  -> Route response to original customer
```

Customer always sees Maya Graphics business number.

Employee always uses native phone messaging application.

## Technology Stack

Backend:

- Python 3.12
- FastAPI

Database:

- Supabase

Hosting:

- Railway

Messaging:

- Twilio SMS
- Twilio WhatsApp future phase

Repository:

- GitHub

AI:

- OpenAI future phase

## Database Tables

`contacts`

- `id`
- `phone_number`
- `created_at`

`conversations`

- `id`
- `customer_phone`
- `assigned_employee`
- `status`
- `created_at`
- `updated_at`

`messages`

- `id`
- `conversation_id`
- `direction`
- `body`
- `created_at`

## Development Order

### Phase 1: Infrastructure

- GitHub repo
- Railway project
- Supabase project
- Environment variables

### Phase 2: FastAPI

- `/health`
- `/webhooks/twilio/sms`
- `/webhooks/twilio/employee`

### Phase 3: SMS Relay

- Customer -> Francisco
- Francisco -> Customer

### Phase 4: Conversation Tracking

- Conversation IDs
- Multiple simultaneous customers

### Phase 5: WhatsApp Relay

- Same architecture
- Channel abstraction

### Phase 6: AI Assistant

- Lead qualification
- Auto responses
- Escalation to employee

## Success Criteria

- Customer texts Maya number.
- Francisco receives message on cellphone.
- Francisco replies from cellphone.
- Customer receives response from Maya number.
- No dashboard required.
- No app required.
- No manual routing required.

