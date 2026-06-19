# Customer Action Workflows Implementation Plan

Date: 2026-06-17

Source spec: `docs/customer-action-workflows-spec.md`

This plan turns the Proof and Assets customer-action workflow into implementation slices. The first build target is Proof. Assets must reuse the same foundation and should not require replacing the Proof work later.

## Slice Status As Of 2026-06-18

Proof approval is implemented and live-smoke tested for the SMS path.

Done:

- Database foundation: implemented in `supabase_schema.sql` and applied in Supabase.
- Backend domain/API: proof create, public lookup, approve, request changes, token hashing, status transitions, and event recording are implemented.
- File handling: operator proof upload is implemented with type and size validation. Current supported proof inputs are PDF, PNG, JPG, and JPEG up to 32 MB.
- Messaging: proof request sends through the existing conversation channel. SMS has been live-tested. WhatsApp is supported only inside an active 24-hour WhatsApp window until approved templates are added.
- Operator UI: `Proof` button and proof request modal are implemented in focused customer-action components.
- Public UI: `/proof/{token}` page is implemented for review, approval, and change requests.
- Conversation timeline: public proof decisions appear in Maya Relay as internal system events.
- UX polish: proof modal/public proof typography and proof decision status cards were refined after live testing.

Verified:

- `.venv/bin/python -m pytest`: 137 passed.
- `npm --workspace frontend run build`: passed.
- Live SMS proof link delivered.
- Live approval and change-request actions appeared in the Maya Relay conversation.

Not done yet:

- WhatsApp template send path for proof links outside the 24-hour service window.
- Live WhatsApp proof smoke test inside a fresh 24-hour conversation.
- Formal frontend/e2e automation; no frontend Playwright script exists yet.
- Admin list/cancel/retry UI for pending customer-action requests.
- Assets workflow.

## Assets Slice Status As Of 2026-06-18

Assets request/upload has been implemented locally and completed automated verification.

Implemented:

- Operator `Assets` action in the conversation header.
- Operator assets request modal with title, customer message, and internal note.
- Admin API to create `request_type = assets` requests and send the upload link through the current conversation channel.
- Public `/assets/{token}` page with drag/drop and multi-file choose-file upload.
- Public assets submit API with validation:
  - up to 8 files
  - 32 MB per file
  - 100 MB total per submission
  - PDF, image, design, document, and ZIP file types
- Uploaded files are stored as `customer_action_files.role = customer_asset`.
- Customer submission records an `assets_submitted` event.
- Maya Relay creates a conversation system message with the uploaded files attached, so the files arrive in the conversation timeline.

Verified locally:

- `.venv/bin/python -m pytest`: 140 passed.
- `npm --workspace frontend run build`: passed.

Verified in production:

- Live SMS asset request delivered.
- Customer upload page accepted multiple files.
- Uploaded assets appeared in the Maya Relay conversation.
- Live WhatsApp asset request worked inside an active 24-hour WhatsApp conversation.

Pending before calling the Assets slice production-ready:

- Formal frontend/e2e automation; no frontend Playwright script exists yet.

## Pending Request Visibility Slice Status As Of 2026-06-19

Implemented locally:

- Conversation detail responses already include recent `customerActions`; the React app now stores that list in state.
- The right details panel now has a compact `Quick Responses` / `Requests` tab set.
- The `Requests` tab shows recent Proof and Assets requests with type, title, status, created time, and operator note.
- Pending requests are highlighted.
- Operators can cancel pending requests from the `Requests` tab.
- Same-type duplicate Proof or Assets requests are blocked while a request is still pending.
- Backend cancel endpoint added: `POST /api/customer-actions/{request_id}/cancel`.
- Cancel transitions only allow `pending -> canceled` and record a `canceled` customer-action event.

Pending verification:

- Backend test suite.
- Frontend production build.
- Live production smoke after deployment.

## Scope Guardrails

- Additive only. Do not break existing SMS, WhatsApp, calls, AI suggested replies, quick responses, customer profile, CSV import, observability, or native reply-code flows.
- Keep `frontend/src/App.tsx` as orchestration only. Add feature logic in focused components/services.
- Do not call the slice production-ready until schema, code, tests, deployment, and live smoke checks all pass.
- Do not implement WhatsApp template management in the first Proof slice. Leave a clean seam for approved `ContentSid` sends later.
- Do not expose internal IDs, admin notes, service-role behavior, or secrets on public customer pages.

## Final Product Shape

Two operator buttons in the conversation header:

- `Proof`: sends a customer proof review link.
- `Assets`: sends a customer upload link.

Customer-side actions:

- Proof page: `Approve`, `Request changes`, optional feedback/comment.
- Assets page: upload files, optional notes, submit.

First implementation slice:

- Build only `Proof` end to end.
- Build the database/API foundation so `Assets` can reuse it later.

## Slice 1: Database Foundation

### Files

- `supabase_schema.sql`
- backend repository tests

### Tables

Add three tables.

```sql
create table if not exists public.customer_action_requests (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  contact_id uuid references public.contacts(id) on delete set null,
  request_type text not null check (request_type in ('proof', 'assets')),
  status text not null default 'pending' check (
    status in ('pending', 'approved', 'changes_requested', 'submitted', 'expired', 'canceled')
  ),
  title text,
  operator_note text,
  public_token_hash text not null unique,
  expires_at timestamptz,
  completed_at timestamptz,
  canceled_at timestamptz,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (request_type = 'proof' and status in ('pending', 'approved', 'changes_requested', 'expired', 'canceled'))
    or
    (request_type = 'assets' and status in ('pending', 'submitted', 'expired', 'canceled'))
  )
);
```

```sql
create table if not exists public.customer_action_files (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.customer_action_requests(id) on delete cascade,
  role text not null check (role in ('proof', 'customer_asset')),
  bucket text,
  object_path text,
  public_url text,
  external_url text,
  original_filename text,
  content_type text,
  size_bytes bigint,
  created_at timestamptz not null default now(),
  check (
    (object_path is not null and bucket is not null)
    or external_url is not null
  )
);
```

```sql
create table if not exists public.customer_action_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.customer_action_requests(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  event_type text not null check (
    event_type in ('created', 'sent', 'opened', 'approved', 'changes_requested', 'assets_submitted', 'canceled', 'expired')
  ),
  comment text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
```

### Indexes

```sql
create index if not exists customer_action_requests_conversation_created_idx
  on public.customer_action_requests (conversation_id, created_at desc);

create index if not exists customer_action_requests_status_created_idx
  on public.customer_action_requests (status, created_at desc);

create index if not exists customer_action_files_request_idx
  on public.customer_action_files (request_id, created_at);

create index if not exists customer_action_events_request_created_idx
  on public.customer_action_events (request_id, created_at);

create index if not exists customer_action_events_conversation_created_idx
  on public.customer_action_events (conversation_id, created_at desc);
```

### Updated-At Trigger

Reuse the existing `public.set_updated_at()` function.

```sql
drop trigger if exists customer_action_requests_set_updated_at on public.customer_action_requests;

create trigger customer_action_requests_set_updated_at
before update on public.customer_action_requests
for each row
execute function public.set_updated_at();
```

### RLS And Grants

```sql
alter table public.customer_action_requests enable row level security;
alter table public.customer_action_files enable row level security;
alter table public.customer_action_events enable row level security;

grant all on public.customer_action_requests to service_role;
grant all on public.customer_action_files to service_role;
grant all on public.customer_action_events to service_role;

notify pgrst, 'reload schema';
```

Public pages must use server endpoints, not direct Supabase anonymous access.

### DB Acceptance Criteria

- Schema can be applied repeatedly without errors.
- Existing tables and data are untouched.
- Service-role backend can create/read/update requests, files, and events.
- RLS is enabled for new tables.
- Backend tests verify inserts, token lookup, status transitions, and event ordering.

## Slice 2: Backend Domain Layer

### New Module Boundaries

Add focused modules:

- `app/customer_actions.py`: domain helpers, token generation/hash, serializers.
- `app/services/customer_actions.py`: create proof request, complete proof request, cancel request.
- Repository methods on `RelayRepository` instead of ad hoc route SQL.

### Token Rules

- Generate raw token with `secrets.token_urlsafe(32)` or stronger.
- Store `sha256(token + server_secret)` or HMAC-SHA256 with an app secret.
- Never store raw token.
- Only return full public URL immediately after creation.
- Admin list responses should not include raw token.

Suggested config:

- `PUBLIC_BASE_URL`, default derived from request origin when safe.
- `CUSTOMER_ACTION_TOKEN_SECRET`, required in production.

### Repository Methods

Add methods such as:

- `create_customer_action_request(...)`
- `add_customer_action_file(...)`
- `add_customer_action_event(...)`
- `get_customer_action_by_token_hash(...)`
- `get_customer_action_for_admin(...)`
- `list_customer_actions_for_conversation(...)`
- `mark_customer_action_approved(...)`
- `mark_customer_action_changes_requested(...)`
- `cancel_customer_action_request(...)`

State transitions must be explicit.

Allowed Proof transitions:

- `pending -> approved`
- `pending -> changes_requested`
- `pending -> canceled`
- `pending -> expired`

Final states are idempotent. A second approve on an already approved request returns the approved state. A change request after approval should be rejected.

### Timeline Events

When an action event occurs, create a system message or include events in conversation detail. First slice should choose the least disruptive path:

Preferred first slice:

- Write `customer_action_events`.
- Add public-facing event summaries to `GET /api/conversations/{id}` as timeline items or system messages.
- Do not mutate customer/employee message bodies.

If conversation UI only supports messages cleanly, create `messages.direction = 'system'` records with explicit action text. This is additive but should be kept easy to distinguish.

### Backend Acceptance Criteria

- Creating Proof request requires admin auth.
- Public token lookup works without admin auth.
- Approve/request-changes endpoints work without admin auth but only with valid token.
- Token hash is stored, raw token is not.
- Duplicate public submissions do not corrupt state.
- Twilio send failure is returned clearly and recorded as an event.
- Existing `/api/conversations`, reply sending, contacts, calls, and operations status tests still pass.

## Slice 3: File Handling

### Proof Input Options

Proof request modal currently supports:

- uploaded file

Deferred:

- external proof URL

Validation:

- Require one uploaded proof file in the current slice.
- Reject empty file.
- Restrict content types initially: PDF, PNG, JPG/JPEG.
- Enforce 32 MB proof upload limit.

Storage:

- Reuse existing Supabase attachment storage service if suitable.
- Store proof files under a distinct path prefix, for example `customer-actions/{request_id}/proof/{filename}`.
- Public proof page should use a controlled URL strategy. If bucket is public today, the token still protects discovery of the page, but file URL may be shareable. Document this clearly.

### File Acceptance Criteria

- Uploaded proof can be stored and rendered/linked from public proof page.
- Invalid file types and oversize files are rejected with clear errors.
- No existing MMS/attachment behavior regresses.

## Slice 4: Messaging And Twilio

### First Slice Message Behavior

Use current channel send path:

- SMS: body with public link.
- WhatsApp inside active window: body with public link.

Message body example:

```text
Your proof is ready. Review it here: https://mayagraphics.co/proof/{token}
```

### WhatsApp Outside 24-Hour Window

First Proof slice should not pretend this is solved.

Implementation options:

- If the app cannot prove an active WhatsApp window, show a safe warning and either block WhatsApp send or let operator send SMS fallback if available.
- Later slice: add approved Twilio template send with `contentSid` and `contentVariables`.

### Future Template Slice

Add after Proof workflow is stable:

- `message_templates` table or config mapping:
  - `template_key`
  - `channel`
  - `twilio_content_sid`
  - `status`
  - `variables_schema`
- Send with `contentSid` for WhatsApp outside-window.
- Store template send metadata in events.

### Messaging Acceptance Criteria

- Proof request creates exactly one outbound customer message attempt.
- Message record stores Twilio SID/status if send succeeds.
- Send failure does not lose the created request; operator sees the failure and can retry/cancel.
- Existing SMS/WhatsApp replies still work.

## Slice 5: Admin API

### Endpoints

`POST /api/conversations/{conversation_id}/customer-actions`

Request:

- multipart form
- `request_type = proof`
- `title`
- `operator_note`
- `message_body`
- `proof_file`

Response includes:

- request id
- status
- public URL only in create response
- message delivery seed status
- proof file summary

`GET /api/conversations/{conversation_id}/customer-actions`

Returns recent requests for that conversation. No raw tokens.

`POST /api/customer-actions/{request_id}/cancel`

Cancels pending request and records event.

### Public API

`GET /api/public/customer-actions/{token}`

Returns:

- request type
- status
- title
- operator note
- proof file/link summary
- safe business name/branding metadata

`POST /api/public/customer-actions/{token}/approve`

No body required. Returns final state.

`POST /api/public/customer-actions/{token}/request-changes`

Body:

```json
{ "comment": "Please make the logo bigger." }
```

Requires non-empty comment.

## Slice 6: Frontend UI

### Component Boundaries

Do not put feature implementation inside `App.tsx`.

Suggested files:

- `frontend/src/customerActions/ProofActionButton.tsx`
- `frontend/src/customerActions/ProofRequestModal.tsx`
- `frontend/src/customerActions/ProofPublicPage.tsx`
- `frontend/src/customerActions/customerActionsApi.ts`
- `frontend/src/customerActions/types.ts`

`App.tsx` should only:

- pass selected conversation/customer context
- open/close modal
- refresh conversation detail after action

### Operator UI

Header:

- Add `Proof` button near `Call` and `Close`.
- Button opens modal.

Modal:

- Customer name/phone read-only.
- File upload with choose-file and drag/drop.
- Optional note.
- Message preview.
- Send button.
- Success/error state.

Conversation timeline:

- Show proof events clearly:
  - Proof request sent.
  - Proof approved.
  - Changes requested: comment.

### Public UI

Route:

- `/proof/{token}`

Page:

- Maya branding.
- Proof preview/link.
- Operator note.
- Approve button.
- Request changes button and comment form.
- Final state after submission.
- Expired/canceled/already-completed states.

### UI Acceptance Criteria

- `Proof` button does not disturb existing header actions.
- Modal is usable on desktop and mobile.
- Public page is usable on mobile.
- Existing Playwright workflow remains green.
- New Playwright tests cover operator modal and public approve/request-changes flows.

## Slice 7: AI Assistance

AI should be assistive only in first implementation.

Add after base Proof flow works:

- Generate suggested proof message body from conversation context.
- Generate suggested operator note.
- Summarize change-request comments for operator.
- Detect inbound natural language approval/change intent and suggest a status update.

Do not:

- Auto-send proof requests.
- Auto-approve or auto-request changes.
- Auto-create Twilio templates.

## Test Plan

### Backend Unit/Integration Tests

- Schema-backed fake repository or Supabase repository coverage.
- Token hash create/lookup.
- Create proof request with uploaded file.
- Reject missing proof source.
- Approve pending proof.
- Approve already approved proof idempotently.
- Reject changes request without comment.
- Reject change request after approval.
- Cancel pending proof.
- Public lookup hides internal fields.
- Twilio send failure leaves request diagnosable.

### Frontend/E2E Tests

- Header shows `Proof`.
- Modal opens and closes.
- Proof request sends with URL.
- Existing messages remain visible.
- Public proof page loads from token.
- Approve flow updates state.
- Request changes flow requires comment and submits.
- Mobile viewport has no horizontal overflow.

### Manual Live Smoke

- Apply Supabase schema in production.
- Deploy Railway from GitHub.
- Create proof request from live app using SMS conversation.
- Confirm customer receives link.
- Open public link on phone.
- Approve.
- Confirm Maya Relay timeline shows approval.
- Create second proof request.
- Request changes with comment.
- Confirm comment appears in Maya Relay.
- Test WhatsApp conversation inside active window.
- Document WhatsApp outside-window behavior as pending unless template send is implemented and tested.

## Implementation Order

1. Add schema to `supabase_schema.sql`.
2. Add backend domain helpers and repository methods with tests.
3. Add admin create/list/cancel APIs.
4. Add public lookup/approve/request-changes APIs.
5. Add public proof page.
6. Add operator Proof button and modal components.
7. Add timeline event rendering.
8. Add e2e tests.
9. Run backend tests, frontend build, and e2e.
10. Commit and push.
11. Apply Supabase schema in production.
12. Wait for Railway deploy.
13. Run live smoke tests.
14. Update spec/status docs with exact result.

## Open Decisions Before Coding

- Proof file storage: reuse attachments bucket or create a separate bucket/prefix?
- Public base URL source: fixed `PUBLIC_BASE_URL` env var or derive from request?
- Token secret: new required env var or reuse existing server secret?
- Timeline rendering: system `messages` records or separate event items in conversation detail?
- WhatsApp outside-window first behavior: block, warn, or support template immediately?
- Initial file size/type limits for proof uploads.

## First Coding Slice Recommendation

Start with backend and DB only:

- Add schema.
- Add token helpers.
- Add repository/service methods.
- Add admin/public APIs.
- Add tests.

Do not build the operator UI until backend behavior is locked and tested. This keeps the frontend from shaping the data model accidentally.
