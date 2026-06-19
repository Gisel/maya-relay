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
- AI knows Maya has one location.
- Office hours: Monday-Friday 9:00 AM-6:00 PM.
- Saturday is by appointment only.
- Suggested replies include the conversation code for easier copy/paste.

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
- Messaging: Twilio SMS/MMS and WhatsApp
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

### Demo Day Checklist

- Change Railway `FRANCISCO_PHONE` to Francisco's real cellphone.
- Clear `EMPLOYEE_PHONE_NUMBERS`, unless an extra testing/helper phone should also be allowed to reply.
- Wait for Railway to redeploy/restart.
- Confirm `https://maya-relay-production.up.railway.app/readiness` returns `"status": "ready"`.
- Confirm `francisco_phone_is_not_maya_number` is `true`.
- Send a fresh customer SMS to Maya's number.
- Confirm Francisco receives:
  - customer name/phone
  - conversation code
  - original message
  - reply instruction
  - short AI note and suggested reply when AI is enabled
- Reply from Francisco's phone using the new `#code`.
- Confirm the customer receives the reply from Maya's number.

### Pricing / Commercial

- One-time setup fee already discussed: `$1,500`.
- Suggested monthly fee: `$299/month` for AI-assisted SMS relay, hosting, maintenance, monitoring, and improvements.
- Client pays Twilio usage directly.
- Current vendor costs paid by us: Railway, Supabase, OpenAI.
- Future auto-response mode can be a higher tier after Francisco approves the AI behavior.

### WhatsApp Relay

- Production WhatsApp sender is configured through Twilio.
- Inbound WhatsApp messages use `/webhooks/twilio/whatsapp`.
- Status callbacks use `/webhooks/twilio/status`.
- WhatsApp customer messages use the same conversation model as SMS.
- Replies route through the original customer channel.
- The app must respect WhatsApp's 24-hour free-form service window.
- Approved templates will be needed later for outbound messages outside the service window.

### Customer Action Workflows

Proof approval and Assets upload are the first customer-action workflows.

Current Proof status:

- Operator `Proof` button exists in the conversation header.
- Operator can upload a proof file and send a tokenized review link.
- Supported proof upload types: PDF, PNG, JPG/JPEG.
- Proof upload limit: 32 MB.
- Public `/proof/{token}` page lets the customer approve or request changes.
- Public approval/change-request actions are stored as durable customer-action events.
- Maya Relay shows proof approval/change-request outcomes in the conversation timeline as internal system events.
- Token security stores hashes only; raw public tokens are only sent in the customer URL.
- SMS proof request flow has been live-smoke tested.

Current Assets status:

- Operator `Assets` button exists in the conversation header.
- Operator can send a tokenized customer upload link.
- Public `/assets/{token}` page supports drag/drop and multi-file choose-file upload.
- Asset upload limits: 8 files, 32 MB per file, 100 MB total.
- Supported asset types: PDF, image, design, document, and ZIP files.
- Uploaded files are stored as customer-action files.
- Maya Relay shows `Assets uploaded by customer` in the conversation timeline with the uploaded files attached.
- SMS and WhatsApp asset request flows have been live-smoke tested.

UI action color language:

- `Open`: status green.
- `Proof`: approval green.
- `Assets`: amber/gold file-request action.
- `Call`: blue.
- `Close`: red.

Pending:

- Live WhatsApp proof smoke test inside a fresh 24-hour WhatsApp service window.
- Approved WhatsApp template send path for proof links outside the 24-hour service window.
- Pending request visibility/cancel UI is implemented locally and awaits verification/deployment.
- Retry UI for failed customer-action sends remains pending.
- Formal frontend/e2e automation for proof and assets flows.

### React Operator Inbox

Phase 1 API foundation is implemented:

- Add authenticated `/api` JSON routes for the React frontend.
- Keep `/admin` as a fallback operations page.
- Add `client_request_id` to prevent accidental duplicate sends from browser retries or double-clicks.
- Keep backend configuration driven by `.env` locally and Railway variables in production.

### Contact Upload

CSV upload is deferred. Expected first version:

- CSV columns: `phone_number`, `display_name`
- Upsert by `phone_number`
- Uploaded `display_name` overrides Twilio Lookup display
- Blank CSV names should not erase existing names by default

### Future AI

Potential later additions:

- Refine AI prompt based on Francisco's feedback after demo.
- Decide whether to keep `Intent` and `Missing` lines, or switch to suggested-reply-only.
- Add lead qualification and structured extraction.
- Add escalation detection for urgent/angry/complex messages.
- Add auto-response mode only for low-risk messages after explicit approval.
- Keep human approval required for pricing, timelines, complaints, and complex jobs.

## Success Criteria

- Customer texts Maya number.
- Francisco receives the message on his cellphone.
- Francisco replies from native SMS using the conversation code.
- Customer receives the response from Maya's business number.
- Customer attachments are preserved and forwarded.
- Francisco can identify the correct customer even when multiple conversations are active.
- Optional AI helps Francisco triage but never sends customer-facing text automatically.
