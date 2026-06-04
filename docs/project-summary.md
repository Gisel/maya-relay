# Maya Relay - Project Summary

## Objective

Build a communication relay platform for Maya Graphics and Signs that lets customers communicate through the Maya business number while employees continue using native cellphone messaging.

For the current MVP, there is no employee dashboard and no CRM requirement. The backend acts as a routing layer between customers, Twilio, Supabase, and Francisco.

## Current Production State

### SMS / MMS

- Maya business number: `+1 (385) 220-8404`
- SMS enabled and tested.
- MMS enabled and tested.
- A2P campaign approved as Low Volume Mixed.
- Twilio Messaging Service and sender pool configured.
- Railway deployment is live.
- Supabase stores contacts, conversations, messages, delivery status, and attachments.
- Incoming media is copied from Twilio to the Supabase `attachments` bucket.

### Routing

Customer SMS flow:

```text
Customer
  -> Maya Twilio number
  -> FastAPI webhook
  -> Supabase conversation/message records
  -> Francisco native SMS app
```

Francisco reply flow:

```text
Francisco replies with #conversation_code
  -> Maya Twilio number
  -> FastAPI webhook
  -> Supabase conversation lookup
  -> Original customer
```

The conversation code is required while Francisco stays in a native SMS app, because multiple customers arrive in the same Maya SMS thread. The app validates the code and refuses to guess when the code is missing or invalid.

### Contact Names

- `FRANCISCO_PHONE` is the primary employee phone and comes from Railway/.env.
- `EMPLOYEE_PHONE_NUMBERS` optionally allows additional reply phones.
- Twilio Lookup can be enabled with `ENABLE_TWILIO_LOOKUP=true`.
- Lookup results are cached in `contacts.lookup_name`.
- Manual `contacts.display_name` takes precedence over Lookup.

### AI Triage

- Optional AI triage is available behind `ENABLE_AI_TRIAGE=true`.
- It adds a short internal note to Francisco's forwarded SMS.
- AI does not auto-reply to customers.
- The relay fails open if the AI call fails.

### Voice System

Production IVR is already completed and remains separate from this SMS relay.

Features:

- English routing
- Spanish routing
- Business hours routing
- Saturday routing
- Closed-hours voicemail
- English voicemail
- Spanish voicemail

## Current Technology Stack

- Backend: Python 3.12, FastAPI
- Database: Supabase
- Hosting: Railway
- Messaging: Twilio SMS/MMS now, WhatsApp future phase
- AI: OpenAI Responses API for optional internal triage
- Repository: GitHub

## Database Tables

`contacts`

- `id`
- `phone_number`
- `display_name`
- `lookup_name`
- `lookup_checked_at`
- `created_at`

`conversations`

- `id`
- `customer_phone`
- `assigned_employee`
- `conversation_code`
- `status`
- `created_at`
- `updated_at`

`messages`

- `id`
- `conversation_id`
- `direction`
- `from_phone`
- `to_phone`
- `body`
- `twilio_message_sid`
- `num_media`
- `media_urls`
- `media_content_types`
- `delivery_status`
- `delivery_error_code`
- `delivery_error_message`
- `created_at`

`message_attachments`

- `id`
- `message_id`
- `bucket`
- `object_path`
- `public_url`
- `source_url`
- `content_type`
- `size_bytes`
- `created_at`

## Pending Work

### WhatsApp Relay

Blocked until Meta/Twilio sender setup is ready:

- Get Meta admin access.
- Remove or release the incorrect test sender.
- Register `+1 (385) 220-8404` as the production WhatsApp sender.
- Wait for sender status to become `ONLINE`.
- Configure inbound and status webhooks.

Implementation after setup:

- Add channel-aware message handling for SMS and WhatsApp.
- Preserve WhatsApp addresses as `whatsapp:+E.164`.
- Route WhatsApp customer messages through the same conversation model.
- Respect WhatsApp's 24-hour free-form service window.
- Use approved templates for outbound messages outside the service window.

### Contact Upload

CSV upload is deferred. Expected first version:

- CSV columns: `phone_number`, `display_name`
- Upsert by `phone_number`
- Uploaded `display_name` overrides Twilio Lookup display
- Blank CSV names should not erase existing names by default

### Future AI

Potential later additions:

- Lead qualification
- Missing-information prompts
- Draft replies for Francisco
- Escalation detection
- Auto-response only after explicit approval and guardrails

## Success Criteria

- Customer texts Maya number.
- Francisco receives the message on his cellphone.
- Francisco replies from native SMS using the conversation code.
- Customer receives the response from Maya's business number.
- Customer attachments are preserved and forwarded.
- Francisco can identify the correct customer even when multiple conversations are active.
- Optional AI helps Francisco triage but never sends customer-facing text automatically.
