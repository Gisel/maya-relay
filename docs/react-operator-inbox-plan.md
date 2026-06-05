# Maya Relay React Operator Inbox Plan

## Purpose

Build Maya Relay into a production operator inbox for Maya Graphics and Signs. The current FastAPI admin page proved the workflow, but it should become a fallback operations page. The primary product should be a React app that lets Francisco manage SMS and WhatsApp conversations, send files, use AI assistance, and understand delivery state without copying codes or reading raw relay text.

## Senior Architecture Review

The proposed direction is right:

1. Verify and stabilize the backend.
2. Define the frontend in detail before coding.
3. Use production-oriented architecture, not a throwaway demo.
4. Split the work into parallel tracks when the contracts are clear.
5. Then implement.

The adjustment I would make is to put an API contract and data model checkpoint between steps 1 and 2. If we start React before the backend shape is stable, the UI will create accidental backend requirements. The backend should first expose clean JSON resources that reflect the product domain: conversations, messages, contacts, attachments, delivery status, AI suggestions, and quick replies.

## Product Principles

- The operator inbox is the source of truth for daily work.
- Native SMS reply by `#code` remains as a mobile fallback, not the premium workflow.
- WhatsApp and SMS should feel like channels inside one conversation system.
- AI should assist the human first; automatic customer replies come later behind explicit guardrails.
- Attachments are first-class objects, not pasted links.
- Failed delivery must be obvious and actionable.
- Every send action must be idempotent enough to prevent accidental double sends.
- The app must be usable on desktop and phone browsers.

## Target User Experience

### Layout

The first production screen should be the inbox itself:

- Top bar with Maya Relay brand and logout.
- Left inbox column with metrics, filters, search, and conversation list.
- Center conversation panel with chat timeline and composer.
- Right intelligence panel with customer profile, AI checklist, quick responses, and later history.

### Inbox Column

Required:

- Counts for open, failed, recent, and with attachments.
- Search by name, phone, message text, code, and delivery status.
- Filters:
  - Open
  - Failed
  - Recent
  - SMS
  - WhatsApp
  - Attachments
- Conversation preview with:
  - customer name or phone
  - last message snippet
  - channel badge
  - failed/pending/delivered state
  - relative update time

Later:

- Assigned employee filter.
- Unread count.
- SLA/response-time indicator.

### Conversation Panel

Required:

- Customer header with name, channel, phone, and status.
- Message bubbles grouped by direction:
  - customer inbound
  - operator/customer outbound
  - system/internal relay events
- Inline image previews.
- File chips for PDFs and non-image attachments.
- Delivery state per outbound message.
- Timestamp per message.
- Composer with:
  - textarea
  - drag/drop files
  - file preview list
  - Send button
  - sending/sent/failed state
  - clear composer after success
  - prevent double submit

Later:

- Retry failed send.
- Edit drafted message before send.
- Internal notes.
- Mark conversation resolved.
- Click-to-call.

### Right Intelligence Panel

Required:

- Customer profile:
  - display name
  - phone
  - channel
  - account/client status placeholder
- AI intent card:
  - detected intent
  - missing information checklist
  - suggested reply
- Quick responses:
  - request dimensions/specs
  - proof approval request
  - shop hours and pickup info
  - ask for artwork

Later:

- Customer history.
- Contact edit form.
- Uploaded contact source.
- AI-generated quote intake summary.
- Auto-response eligibility status.

## Backend Readiness Plan

### Current Backend Strengths

Already implemented:

- Twilio SMS/MMS inbound webhook.
- Twilio WhatsApp inbound webhook.
- Delivery status webhook.
- Supabase contacts, conversations, messages, and attachments.
- Public attachment storage.
- Channel-aware replies.
- AI triage and copy-ready suggestions.
- Native SMS fallback with conversation codes.
- Readiness checks.
- Tests for the relay, repository, webhooks, admin, AI, and Twilio sender.

### Backend Gaps Before React

Add a versioned JSON API under `/api`:

- `GET /api/me`
- `GET /api/readiness`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}`
- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/reply`
- `PATCH /api/conversations/{conversation_id}`
- `GET /api/quick-responses`
- `GET /api/metrics`

Future:

- `PATCH /api/contacts/{contact_id}`
- `POST /api/contacts/import`
- `POST /api/conversations/{conversation_id}/call`
- `POST /api/ai/suggest-reply`
- `POST /api/ai/classify`

### API Contract Direction

Conversation list item:

```json
{
  "id": "uuid",
  "code": "1B976390",
  "status": "open",
  "channel": "whatsapp",
  "customer": {
    "phone": "+18012009467",
    "displayName": "Gisel Gomez",
    "lookupName": "GOMEZ, GISEL"
  },
  "lastMessage": {
    "body": "Need a quote for presentation cards",
    "direction": "customer_to_employee",
    "deliveryStatus": "delivered",
    "createdAt": "2026-06-05T16:27:00Z",
    "hasAttachments": true
  },
  "updatedAt": "2026-06-05T16:28:00Z"
}
```

Message item:

```json
{
  "id": "uuid",
  "conversationId": "uuid",
  "direction": "employee_to_customer",
  "body": "Thanks. Can you confirm quantity and size?",
  "fromPhone": "+13852208404",
  "toPhone": "+18012009467",
  "deliveryStatus": "delivered",
  "deliveryErrorCode": null,
  "deliveryErrorMessage": null,
  "createdAt": "2026-06-05T16:28:00Z",
  "attachments": [
    {
      "url": "https://...",
      "contentType": "image/jpeg",
      "kind": "image"
    }
  ]
}
```

Reply request:

```json
{
  "body": "Thanks. Can you confirm quantity and size?",
  "clientRequestId": "browser-generated-uuid"
}
```

File replies should use `multipart/form-data` with:

- `body`
- `client_request_id`
- `reply_files[]`

### Backend Data Improvements

Recommended before or during React:

- Add `messages.client_request_id` to prevent double sends from browser retries.
- Add `messages.sent_by` or `operator_id` placeholder for future multi-user support.
- Add `conversations.last_read_at` later for unread state.
- Add `conversations.closed_at` later for resolved conversations.
- Add `ai_triage` structured storage instead of only embedding AI notes in message text.
- Consider a `quick_responses` table only after templates stabilize; static config is enough for v1.

## Frontend Architecture

Recommended stack:

- Vite + React + TypeScript.
- React Router for app routes.
- TanStack Query for server state.
- Plain CSS modules or a small design system layer first; avoid a large UI framework until interaction patterns settle.
- No global state library initially unless needed; conversation selection can live in URL state.

Why Vite over Next.js for this repo:

- Existing backend is FastAPI on Railway.
- We do not need SSR.
- Vite builds a static app that FastAPI can serve or Railway can deploy separately later.
- Faster to implement with less framework overhead.

Proposed structure:

```text
frontend/
  package.json
  index.html
  src/
    app/
      App.tsx
      routes.tsx
    api/
      client.ts
      conversations.ts
      types.ts
    components/
      Badge.tsx
      Button.tsx
      EmptyState.tsx
      FileDropzone.tsx
      MessageBubble.tsx
    features/
      inbox/
      conversation/
      intelligence/
      composer/
    styles/
      tokens.css
      global.css
```

## Frontend Routes

- `/app` inbox shell.
- `/app/conversations/:conversationId` selected conversation.
- `/login` if we replace the current cookie login with a frontend login screen.

For v1, the current `ADMIN_PASSWORD` cookie model can continue if the API enforces the same session cookie. Longer term, use real auth.

## Authentication Plan

V1:

- Keep `ADMIN_PASSWORD`.
- Add API auth dependency that checks the same session cookie.
- React login posts to existing `/admin/login` or a new `/api/auth/login`.
- Logout clears the cookie.

Production later:

- User table or managed auth.
- Role-based access:
  - owner
  - operator
  - viewer
- Audit logs for sends.

## Real-Time Strategy

V1:

- Poll conversation list every 10-15 seconds.
- Poll active conversation every 5-10 seconds.
- Refetch immediately after send.

Later:

- Supabase realtime or WebSocket/SSE from FastAPI.
- Push only conversation/message changes.

The polling approach is simpler and acceptable for a single-operator production v1.

## Attachment Strategy

Required:

- Incoming Twilio media is copied to Supabase Storage.
- Image attachments render inline.
- Non-image attachments render as file cards/links.
- Uploaded images send through Twilio media URLs.
- Uploaded non-images retain links in message body where media support is less predictable.

Need to validate:

- Twilio MMS size/type constraints.
- WhatsApp supported file types.
- User-friendly error if Twilio rejects a file.

## AI Strategy

V1:

- Keep AI as internal assistance.
- Show AI intent and missing info in the right panel.
- Show suggested reply as a one-click “Use reply” action.
- Never auto-send.

V1.5:

- Store AI output as structured JSON.
- Allow “regenerate suggestion.”
- Add quick response templates.

Later:

- Auto-response only for approved low-risk intents:
  - hours
  - address
  - basic intake questions
  - proof received confirmation
- Never auto-send pricing, timelines, complaints, or commitments without approval.

## Parallel Build Plan

Parallel work is useful only after the API contracts are written. Good split:

### Agent A: Backend API

- Add `/api` router.
- Add JSON serializers.
- Add auth dependency.
- Add idempotent reply endpoint.
- Add tests.

### Agent B: Frontend Shell

- Create Vite React app.
- Build layout, navigation, design tokens, and mock data screens.
- Build responsive desktop/mobile structure.

### Agent C: Conversation Experience

- Message bubbles.
- Attachment previews.
- Composer.
- Send states.
- File dropzone.

### Agent D: Intelligence Panel

- AI intent card.
- Missing info checklist.
- Quick response list.
- Customer profile panel.

### Agent E: QA/Integration

- API contract tests.
- Playwright smoke tests.
- Mobile viewport checks.
- Deployment build verification.

Do not split until backend JSON response shapes are frozen enough for frontend mock data.

## Implementation Phases

### Phase 0: Stabilize Current Backend

Goal: Make sure current production relay is healthy.

- Confirm SMS inbound/outbound.
- Confirm WhatsApp inbound/outbound.
- Confirm image media delivery.
- Confirm dashboard reply sends and clears fallback form.
- Confirm readiness endpoint.
- Confirm Railway deployment logs are clean.

### Phase 1: API Foundation

Goal: React-ready backend.

- Add `/api` router.
- Add API auth dependency.
- Add conversation list/detail/message endpoints.
- Add reply endpoint with multipart file support.
- Add metrics endpoint.
- Add tests.

### Phase 2: React Static Shell

Goal: Build product UI with mock data.

- Add frontend app.
- Build layout from the screenshot direction.
- Implement inbox list.
- Implement conversation panel.
- Implement right AI/customer panel.
- Implement responsive behavior.

### Phase 3: Connect Frontend To API

Goal: Operational inbox.

- Wire TanStack Query.
- Connect search/filter.
- Connect conversation route.
- Connect reply send.
- Connect file uploads.
- Add send states and error banners.
- Refetch after successful sends.

### Phase 4: Production Hardening

Goal: Make it safe for daily use.

- Add client request id for idempotent sends.
- Add delivery error UI.
- Add retry path if safe.
- Add structured logs around sends.
- Add basic Playwright smoke tests.
- Add mobile browser checks.

### Phase 5: Product Expansion

Goal: Convert from inbox to operational platform.

- Contact CSV import.
- Contact editing.
- Quick response management.
- Structured AI triage storage.
- Conversation close/reopen.
- Click-to-call bridge.
- Proof approval flow.
- Billing/pricing tier decisions.

## Production Quality Bar

Before replacing `/admin` as the primary tool:

- All backend tests pass.
- Frontend build passes.
- Core API routes have tests.
- Send flow prevents double sends.
- File upload errors are visible.
- Failed Twilio delivery is visible.
- Mobile layout is usable.
- No secrets are exposed to frontend.
- Service role key stays backend-only.
- `/admin` remains as fallback.

## Risks And Decisions

### Risk: Overbuilding too early

Mitigation: Build the operator inbox first. Defer CRM, campaigns, and automation until the core daily workflow is solid.

### Risk: Auth is too light

Mitigation: Use the existing password cookie only for v1. Plan real user auth before adding multiple customers or sensitive multi-operator workflows.

### Risk: WhatsApp expectations

Mitigation: Keep explaining that Twilio-controlled WhatsApp means customers use WhatsApp, operators use Maya Relay.

### Risk: AI confidence

Mitigation: Human approval remains required. Store and observe AI suggestions before enabling automation.

### Risk: Attachment delivery differences

Mitigation: Send images as Twilio media, keep non-image links, and show channel-specific failures clearly.

## Recommended Immediate Next Step

Start Phase 1:

1. Add `/api` routes and JSON serializers.
2. Keep current `/admin` untouched except for critical fixes.
3. Add backend tests for every frontend-needed route.
4. Then scaffold the React app against mock data that matches those JSON contracts.

This keeps momentum high while avoiding rework.
