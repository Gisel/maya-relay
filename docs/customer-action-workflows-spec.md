# Customer Action Workflows Spec

Date: 2026-06-17

This spec defines a production-grade foundation for customer-facing action links in Maya Relay. The first two operator workflows are:

- Proof: customer can approve, reject/request changes, or leave feedback.
- Assets: operator asks the customer to upload files or missing job inputs.

The goal is to support SMS and WhatsApp with the same durable workflow, then add Twilio WhatsApp templates and richer buttons later without rebuilding the core system.

## Current Status As Of 2026-06-18

Proof approval is implemented, committed, pushed, and live-smoke tested for SMS.

Completed:

- Supabase schema foundation exists for `customer_action_requests`, `customer_action_files`, and `customer_action_events`.
- `Proof` action exists in the conversation header near `Open`, `Call`, and `Close`.
- Operator can create a proof request with an uploaded proof file.
- Backend validates proof uploads for supported file types and size.
- Backend generates tokenized public proof links and stores only token hashes.
- Public `/proof/{token}` page loads proof content and supports `Approve proof` and `Request changes`.
- Customer decisions are recorded as durable action events.
- Maya Relay conversation timeline shows customer proof decisions as internal system events.
- `PUBLIC_BASE_URL` / request-host handling prevents localhost links in production and uses the production domain when configured.
- Proof modal and public proof page typography have been softened after live UX testing.

Verified:

- Backend tests: `.venv/bin/python -m pytest` passed with 137 tests.
- Frontend build: `npm --workspace frontend run build` passed.
- Live SMS proof request delivered.
- Live public proof approval updated Maya Relay.
- Live public change request with comment updated Maya Relay.

Pending before calling the broader Proof workflow fully production-ready:

- Live WhatsApp proof request test inside an active 24-hour WhatsApp service window.
- Approved WhatsApp template support for proof links outside the 24-hour window.
- Formal frontend/e2e automation; the frontend package currently has no Playwright script.
- Optional pending-request visibility/cancel/retry UI for operators.
- Asset upload workflow.

## Working Rules

- Additive only: do not remove or disturb current SMS, WhatsApp, calls, customer profile, CSV import, observability, or reply-code behavior.
- Keep scope tight: build one production-grade slice at a time.
- Do not grow `frontend/src/App.tsx` with feature logic. Add focused components and call them from `App.tsx`.
- Do not call the work production-ready until code, tests, schema, deployment, and live smoke checks all pass.
- Public customer pages must not expose internal IDs, admin data, internal notes, or secrets.
- WhatsApp template support is not considered done until approved templates are configured, `ContentSid` values are stored, sends are tested, and failure states are visible.

## Product Model

### Operator Actions

The conversation header should eventually support two customer-action entry points:

- `Proof`: sends a proof approval request.
- `Assets`: asks the customer to upload missing files or job information.

The customer-facing pages expose two experiences:

- Proof: `Approve`, `Request changes`, and optional feedback/comment.
- Assets: `Upload assets` with optional notes.

The first implementation slice should start with `Proof` because it has the clearest status model and immediate client value. `Assets` should use the same tables, token security, public page structure, file handling, and event model.

### Workflow 1: Proof Approval

Operator goal:

Send a proof for customer review and receive a durable approval or change request.

Customer actions:

- Approve.
- Request changes with a comment.
- Leave feedback before final operator follow-up.

### Workflow 2: Assets

Operator goal:

Ask the customer for missing artwork, logo, photos, design files, sizes, quantities, or other production inputs.

Customer actions:

- Upload files.
- Add notes.
- Submit assets.

## In Scope For First Implementation Slice

- Add a `Proof` action near `Open`, `Call`, and `Close`.
- Add a modal for creating a proof approval request.
- Support uploaded proof files. External proof URLs are deferred so proof review has one controlled file path first.
- Add optional operator note.
- Create a durable approval request record.
- Generate a secure public token.
- Send the customer a review link through the current conversation channel.
- Add public `/proof/{token}` page.
- Allow `Approve` and `Request changes`.
- Write approval events back to the conversation timeline as system events.
- Add backend tests, frontend build, and Playwright coverage.

## Deferred From First Slice

- Full Twilio template approval management UI.
- Real WhatsApp quick-reply button templates.
- AI auto-changing approval status without operator confirmation.
- Job/order management beyond the approval request record.
- Full asset library UI.
- Expiration automation jobs unless they are trivial and safe.
- Customer authentication.

Deferred does not mean ignored. The schema and API must leave room for these without replacement work.

## Data Contract

### `customer_action_requests`

One table should support proof approvals and asset requests.

```sql
id uuid primary key
conversation_id text not null
contact_id uuid null
request_type text not null -- proof, assets
status text not null -- pending, approved, changes_requested, submitted, expired, canceled
title text null
operator_note text null
public_token_hash text not null unique
expires_at timestamptz null
completed_at timestamptz null
canceled_at timestamptz null
created_by text null
created_at timestamptz not null
updated_at timestamptz not null
```

Status rules:

- `proof`: `pending`, `approved`, `changes_requested`, `expired`, `canceled`
- `assets`: `pending`, `submitted`, `expired`, `canceled`

### `customer_action_files`

Stores proof files and customer-uploaded assets.

```sql
id uuid primary key
request_id uuid not null
role text not null -- proof, customer_asset
bucket text null
object_path text null
public_url text null
external_url text null
original_filename text null
content_type text null
size_bytes bigint null
created_at timestamptz not null
```

### `customer_action_events`

Audit trail and conversation timeline source.

```sql
id uuid primary key
request_id uuid not null
conversation_id text not null
event_type text not null -- created, sent, opened, approved, changes_requested, assets_submitted, canceled, expired
comment text null
metadata jsonb not null default '{}'
created_at timestamptz not null
```

## Public Token Security

- Generate at least 32 random bytes.
- Store only a hash of the token.
- Put the raw token only in the customer URL.
- Public endpoints look up by token hash.
- Tokens must be unguessable and unique.
- Public responses must reveal only customer-safe data.
- Public submit endpoints must be idempotent.
- Final states cannot be overwritten accidentally.
- Add basic rate limiting or abuse protection before public launch.
- Uploaded files must not be enumerable.

## API Contract

### Admin APIs

`POST /api/conversations/{conversation_id}/customer-actions`

Creates a customer action request and sends a customer message.

Request:

- multipart form
- `request_type`: `proof | assets`
- `title`: optional
- `operator_note`: optional
- `message_body`: optional override
- `proof_file`: required for proof approval in the current slice
- `proof_url`: deferred

Response:

```json
{
  "request": {
    "id": "uuid",
    "conversationId": "conversation-1",
    "requestType": "proof",
    "status": "pending",
    "publicUrl": "https://mayagraphics.co/proof/token-redacted",
    "createdAt": "..."
  },
  "message": {
    "twilioMessageSid": "SM...",
    "deliveryStatus": "queued"
  }
}
```

`GET /api/conversations/{conversation_id}/customer-actions`

Lists recent action requests for the selected conversation.

`POST /api/customer-actions/{request_id}/cancel`

Cancels a pending request and records an event.

### Public APIs

`GET /api/public/customer-actions/{token}`

Returns customer-safe request details.

`POST /api/public/customer-actions/{token}/approve`

Approves a pending proof request.

`POST /api/public/customer-actions/{token}/request-changes`

Marks a proof request as changes requested and stores a comment.

`POST /api/public/customer-actions/{token}/upload-assets`

Uploads customer files and optional notes for asset requests.

## UI Contract

### Operator Header

Add a `Proof` action near:

- Open status pill
- Call
- Close

This action opens a modal. It does not replace existing message composer workflows.

### Proof Modal

Fields:

- Customer name and phone, read-only.
- Proof file upload with choose-file and drag/drop.
- Optional note.
- Message preview.
- Send approval request.

States:

- Idle.
- Uploading/sending.
- Sent.
- Error with plain-English recovery.

### Customer Public Page

Proof approval page:

- Maya branding.
- Proof preview or link.
- Operator note.
- `Approve` button.
- `Request changes` button.
- Comment field for requested changes.
- Final confirmation state.

Asset upload page:

- Maya branding.
- Requested asset instructions.
- File upload control with drag/drop.
- Optional notes.
- Submit confirmation state.

## Twilio Contract

### SMS

Send normal body text with the public action link.

### WhatsApp Inside 24-Hour Window

Send normal free-form body text with the public action link.

### WhatsApp Outside 24-Hour Window

Do not blindly send free-form WhatsApp.

Allowed production options:

- Block the send and show that an approved WhatsApp template is required.
- Or send with an approved Twilio Content `ContentSid` and variables.

Recommended future templates:

- `proof_ready`: "Your proof for {{1}} is ready. Please review it using the secure Maya Graphics link below." with CTA URL `https://mayagraphics.co/proof/{{2}}`
- `assets_needed`: "We need your files for {{1}}. Please upload them using the secure Maya Graphics link below." with CTA URL `https://mayagraphics.co/assets/{{2}}`

For WhatsApp CTA templates, `{{1}}` is the job/request title and `{{2}}` is the public action token only.

Template management remains pending until:

- Template exists in Twilio Content Template Builder.
- Meta approval is confirmed.
- `ContentSid` is stored in config or DB.
- Send path supports `contentSid` and `contentVariables`.
- Production smoke test proves delivery.

## AI Agent Contract

AI can assist, but should not own the workflow in the first slice.

In scope:

- Draft suggested operator note.
- Draft customer-facing message body.
- Summarize customer change-request comments.
- Suggest status updates from inbound natural-language replies.

Out of scope initially:

- Auto-approving.
- Auto-requesting changes.
- Sending proof requests without operator confirmation.
- Creating Twilio templates automatically.

## Tests

Backend:

- Creating a proof approval requires authentication.
- Public token is hashed in storage.
- Raw token is not returned by admin list endpoints.
- Public token lookup works.
- Approve changes status once and is idempotent.
- Request changes requires a comment.
- Canceled/expired requests cannot be completed.
- Twilio send failure leaves request/event state diagnosable.

Frontend/e2e:

- `Proof` action opens modal.
- Modal can create a proof request.
- Existing conversation messages remain visible.
- Public proof page approve flow works.
- Public request-changes flow works.
- Mobile layout has no horizontal overflow.

Manual production smoke:

- Create proof request from deployed app.
- Confirm customer receives SMS link.
- Confirm customer receives WhatsApp link inside active window.
- Confirm public link loads.
- Approve from public page.
- Confirm Maya Relay conversation shows approval event.
- Request changes from another request.
- Confirm comment appears in Maya Relay.

## Risks

- Public links can expose customer files if token security or file storage is weak.
- WhatsApp outside-window free-form sends can silently fail.
- Large proof files can exceed provider limits or slow public pages.
- Uploading customer assets creates storage and malware/scanning considerations.
- Operators may send duplicate approval requests if pending state is not visible.
- AI-generated message copy may be wrong if not operator-confirmed.

## Acceptance Criteria For First Slice

- Existing Maya Relay messaging, calls, customer profile, CSV import, observability, and quick responses still work.
- `Proof` action exists in the conversation header.
- Operator can create and send a proof approval request.
- Customer can approve or request changes through a public token URL.
- Maya Relay records status and events durably.
- Conversation timeline shows proof approval events.
- Token security tests pass.
- Backend tests pass.
- Frontend build passes.
- Playwright tests pass for the operator and public flows.
- Supabase production schema is applied.
- Railway deployment succeeds.
- Live SMS smoke passes.
- Live WhatsApp smoke passes for the supported send mode.

Only after every applicable item passes can the first slice be called production-ready.
