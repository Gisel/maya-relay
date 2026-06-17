# Maya Relay Production Slice Plan

Date: 2026-06-17

This plan turns the current 360 checklist into production-grade implementation slices. The goal is not to ship a disposable MVP. Each slice must have clear scope, contracts, tests, risks, and acceptance criteria before coding starts.

## Working Rule

Before implementation begins on any feature, define:

- Feature goal
- In scope
- Out of scope
- Data contract
- API contract
- UI contract
- Tests
- Risks
- Acceptance criteria
- Deploy and validation plan

No feature is called done until the acceptance criteria pass. If something is deferred, the reason must be explicit and today's work must not need to be thrown away later.

## Non-Negotiables

- Keep existing SMS, MMS, WhatsApp, calls, recording, transcription, recap, and native reply-code flows working.
- Keep `/admin` as a fallback operations page.
- Keep `ADMIN_PASSWORD` auth for the Saturday version unless a real auth migration is explicitly approved.
- Keep `.env`, Railway variables, and Supabase data as the source of truth.
- Do not expose Twilio, Supabase service role, OpenAI, or AssemblyAI secrets to the frontend.
- Do not mutate stored message bodies for display cleanup.
- Use additive migrations and backward-compatible API responses.
- Prefer focused commits with one concern per commit.
- Verify backend changes with `.venv/bin/python -m pytest`.
- Verify frontend changes with `npm run build` and Playwright when UI behavior changes.

## Operational Must-Haves

### Slice O1: Inbound Call Recording Automation Validation

Feature goal:

Validate that production inbound connected-call recording automation works end to end after deployment.

In scope:

- Place one answered inbound call through the live Twilio Studio flow.
- Confirm Maya Relay stores the longest/full completed recording.
- Confirm transcript and recap appear automatically when provider keys are configured.
- Confirm manual Transcribe recording and Generate recap buttons remain available as fallback.
- Record the result in the 360 doc.

Out of scope:

- New recording architecture.
- Outbound two-party recording.
- Call analytics.

Data/API/UI contract:

- No code contract change expected.
- Validate existing `calls` recording metadata, `transcription`, and `recap` fields.
- Validate existing Call Details UI.

Tests:

- Existing backend tests must remain green.
- Manual production call validation is required because this depends on Twilio Studio and live recording callbacks.

Risks:

- Twilio may produce multiple recordings for one call; Maya Relay should keep the longest completed one.
- AssemblyAI/OpenAI automation may fail independently of recording capture.
- Studio completion callbacks may not fire on every branch if Studio is misconfigured.

Acceptance criteria:

- Live answered inbound call appears in Calls workspace.
- Call has the full/longest recording attached.
- Audio playback works through Maya Relay.
- Transcript appears automatically, or a provider/configuration error is visible enough to diagnose.
- Recap appears automatically after transcript, or a provider/configuration error is visible enough to diagnose.
- Manual fallback buttons still work.

### Slice O2: Domain Validation And Root Redirect

Feature goal:

Make the custom domain open the operator dashboard cleanly.

Status:

- Root `/` to `/app` redirect has been implemented and deployed.
- `https://mayagraphics.co/` resolves to `https://mayagraphics.co/app`.
- `https://mayagraphics.co/app` returns `200`.

Remaining in scope:

- Keep Railway custom domain active.
- Confirm Cloudflare records remain DNS-only where required by Railway.
- Record final domain status in the 360 doc.

Out of scope:

- Public marketing website at root.
- Multi-page public website.

Acceptance criteria:

- `https://mayagraphics.co/` lands on the operator app.
- `https://mayagraphics.co/app` loads the operator app.
- Railway domain remains healthy.
- `/health` still returns `{"status":"ok"}`.

### Slice O3: Call Details Readability Polish

Feature goal:

Make call notes, transcription, and recap comfortable to read and edit during real operations.

In scope:

- Improve typography, spacing, and visual hierarchy in Call Details.
- Preserve editability for notes, transcription, recap, outcome, and follow-up status.
- Add clearer save success/error feedback if current feedback is too easy to miss.
- Confirm selected call changes update the form correctly.
- Keep mobile layout usable.

Out of scope:

- New call analytics.
- New data fields.
- AI recap prompt redesign.
- Timeline redesign beyond what is needed to keep the details panel coherent.

Data contract:

- No schema change expected.
- Existing `calls.notes`, `calls.transcription`, `calls.recap`, `calls.outcome`, and `calls.follow_up_status` remain authoritative.

API contract:

- Continue using `PATCH /api/calls/{call_id}`.
- Response should continue returning the updated call shape used by the UI.
- Errors should remain visible in the UI.

UI contract:

- Desktop: Call Details remains in the Calls workspace details area.
- Mobile: Details remain accessible without overflow or hidden save actions.
- Notes, transcription, and recap should read as content fields, not cramped admin textareas.
- Save state should be visible: saving, saved, error.

Tests:

- Frontend build.
- Existing e2e Call Details save test must pass.
- Add or update e2e coverage if save feedback or field behavior changes.

Risks:

- Pure styling changes can accidentally break mobile overflow.
- Controlled textareas can reset if selected-call state is mishandled.

Acceptance criteria:

- Existing call details can be edited and saved.
- Selecting a different call replaces the displayed details with that call's values.
- Long transcript/recap content is readable.
- Mobile viewport has no horizontal overflow.
- Build and relevant tests pass.

## Customer / Contact Production Slice

### Slice C1: Customer Profile Basics

Feature goal:

Give the operator a reliable customer profile inside the dashboard without turning Maya Relay into a full CRM yet.

In scope:

- Editable contact display name.
- Phone number visible and copyable/readable.
- Customer notes.
- Recent message and call history visible.
- Use contact display name before Twilio Lookup name.
- Keep the UI compact in the existing right panel or selected customer area.

Out of scope:

- Tags, VIP status, active/inactive client status.
- Multi-contact companies.
- Full CRM account model.
- Rich audit logs.
- Supabase Auth user attribution.

Data contract:

- `contacts.phone_number` remains the unique contact identity.
- `contacts.display_name` is the manual/operator name.
- Add `contacts.notes text` if not already present.
- Existing `contacts.lookup_name` remains read-only fallback from Twilio Lookup.
- Manual `display_name` must not be overwritten by Lookup.

API contract:

- Add or extend a contact endpoint:
  - `GET /api/contacts/{contact_id}` or include profile in conversation detail.
  - `PATCH /api/contacts/{contact_id}` with optional `displayName` and `notes`.
- Response should include:
  - `id`
  - `phone`
  - `displayName`
  - `lookupName`
  - `notes`
  - `recentMessages`
  - `recentCalls`
- Auth: same current admin session.

UI contract:

- Show customer name, phone, notes, and recent history in the dashboard.
- Edit name and notes without leaving the conversation/call workflow.
- Save state is clear.
- Empty notes/history states are quiet and professional.

Tests:

- Repository tests for contact update and notes persistence.
- API tests for authorized update, validation, and response shape.
- Frontend/e2e test for editing contact name/notes if UI changes.

Risks:

- Contact identity by phone needs careful normalization.
- Recent history must stay bounded; do not load every message/call.
- Manual names must not be erased by CSV import or Lookup later.

Acceptance criteria:

- Operator can edit and save a contact name.
- Operator can edit and save customer notes.
- Phone number remains visible.
- Recent messages/calls are visible without loading the entire database.
- Manual name is used in conversation/call display.

### Slice C2: Contact / Client Search

Feature goal:

Allow operators to find contacts/clients by name or phone without redesigning the whole dashboard.

In scope:

- Backend search endpoint.
- Basic dashboard UI entry point.
- Search by phone/name.
- Results show display name, lookup name, phone, and recent activity hint.
- Selecting a result opens the relevant conversation/contact context when available.

Out of scope:

- Full scalable client loading redesign.
- Advanced filters.
- Saved segments.
- Global command palette.

Data contract:

- Search `contacts.display_name`, `contacts.lookup_name`, and normalized `contacts.phone_number`.
- Return paginated/bounded results.
- Do not load all clients into the browser.

API contract:

- `GET /api/contacts?q=&limit=&offset=`
- Response:
  - `items`
  - `pagination.nextOffset`
- Each item:
  - `id`
  - `phone`
  - `displayName`
  - `lookupName`
  - `lastActivityAt`
  - `openConversationId`

UI contract:

- Add a small search surface to the existing dashboard.
- No massive layout redesign.
- Empty, loading, and error states are visible.

Tests:

- Repository search tests.
- API search tests for name, phone, pagination, and auth.
- Frontend/e2e smoke test if UI is added.

Risks:

- Search can become slow if implemented as unbounded scans.
- Phone normalization must match existing contact logic.

Acceptance criteria:

- Search finds by manual name.
- Search finds by lookup name.
- Search finds by phone fragments.
- Results are bounded/paginated.
- Selecting a result does something useful and predictable.

## CSV Import Production Slice

### Slice I1: CSV Contact Import

Feature goal:

Import customer names from CSV so Maya Relay can use known contacts before paid Twilio Lookup.

In scope:

- Upload CSV with `phone_number` and `display_name`.
- Normalize phone numbers.
- Upsert contacts by phone number.
- Blank names do not overwrite existing names.
- Existing manual names are preserved unless CSV has a real non-blank name and overwrite behavior is explicitly chosen.
- Imported contacts are used before Twilio Lookup.
- Return import summary.

Out of scope:

- Multi-column CRM import.
- Tag import.
- Company/account import.
- Background job queue.
- Import history dashboard.

Data contract:

- Contacts are upserted by normalized `phone_number`.
- `display_name` stores imported/manual name.
- Consider `contacts.name_source` later, but do not block on it unless overwrite rules become ambiguous.

API contract:

- `POST /api/contacts/import`
- Request: `multipart/form-data` with `file`.
- Response:
  - `created`
  - `updated`
  - `skipped`
  - `invalidRows`
  - row-level errors for invalid phone/missing required columns.
- Auth: same current admin session.

UI contract:

- Simple import surface in dashboard/admin area.
- Show required columns.
- Show summary after upload.
- Show row errors in a readable, bounded way.

Tests:

- CSV parser tests for valid rows, blank names, invalid phone, missing columns.
- Repository upsert tests.
- API upload tests.
- Optional e2e smoke if UI is added.

Risks:

- Bad CSVs can erase good names if overwrite rules are loose.
- Large files can cause slow requests; keep file size/row count bounded for this slice.
- Phone normalization must be consistent with existing relay behavior.

Acceptance criteria:

- Valid CSV creates new contacts.
- Existing contacts update only when allowed by the rules.
- Blank names never erase existing display names.
- Invalid rows are reported without crashing the whole import.
- Imported names display before Lookup names.

## WhatsApp Templates Production Slice

### Slice W1: Quick Template Drafts For Active Windows

Feature goal:

Give operators reusable WhatsApp/SMS reply drafts without pretending we have full WhatsApp business-initiated template management.

In scope:

- Add quick template drafts:
  - quote follow-up
  - proof ready
  - pickup reminder
  - payment reminder
- Insert selected draft into the composer.
- Use only inside active customer conversations.
- Make clear these are drafts, not Twilio-approved outbound templates.

Out of scope:

- Twilio template approval tooling.
- Business-initiated WhatsApp sends outside the 24-hour service window.
- Template usage tracking.
- Template editor/management UI.

Data contract:

- Static frontend/backend config is acceptable for this slice.
- No database table required until templates need editing, ownership, approval state, or tracking.

API contract:

- Existing `GET /api/quick-responses` may be extended.
- Response should distinguish quick replies/drafts from approved WhatsApp templates if needed:
  - `id`
  - `label`
  - `body`
  - `channels`
  - `kind`

UI contract:

- Drafts appear in the existing quick responses area.
- Selecting a draft fills the composer; it does not auto-send.
- Operator can edit before sending.

Tests:

- API test for quick response payload if backend changes.
- Frontend/e2e test that selecting a draft fills composer without sending.

Risks:

- Users may confuse drafts with approved WhatsApp templates.
- WhatsApp 24-hour window rules must not be bypassed.

Acceptance criteria:

- Drafts are visible.
- Selecting each draft fills composer text.
- Nothing sends automatically.
- Existing SMS and WhatsApp send flows remain unchanged.

## Observability Production Slice

### Slice S1: Operational Status View

Feature goal:

Give a simple operational view of recent failures without building a full logging pipeline.

In scope:

- Recent failed Twilio sends.
- Recent call recording/transcription/recap failures where available.
- Plain-English error hints where easy.
- Small dashboard/admin status view.

Out of scope:

- Full structured log pipeline.
- Alerting.
- Metrics warehouse.
- Long-term analytics.

Data contract:

- Use existing `messages.delivery_status`, `delivery_error_code`, and `delivery_error_message`.
- Use existing `calls` recording/transcription/recap fields and status metadata where available.
- If provider failure details are not persisted yet, add only narrowly scoped fields needed for operational diagnosis.

API contract:

- Add `GET /api/operations/status` or extend existing metrics endpoint.
- Response:
  - `failedMessages`
  - `recordingIssues`
  - `transcriptionIssues`
  - `generatedAt`
- Keep response bounded.

UI contract:

- Simple operational panel or admin view.
- Show recent issue, affected customer/phone when available, timestamp, and hint.
- Do not interrupt normal inbox use.

Tests:

- API tests for failed sends and empty state.
- Repository tests if new query helpers are added.
- Frontend build and optional e2e if UI is added.

Risks:

- Failure detection may be incomplete if older errors were not persisted.
- Too much noise can reduce trust.

Acceptance criteria:

- Operator can see recent failed sends.
- Empty state is clear when no issues exist.
- Error hints are plain English when known.
- View is bounded and does not load unbounded logs.

## Auth Production Slice

### Slice A1: Saturday Auth Position

Feature goal:

Avoid rushing a risky auth migration before Saturday, June 20, 2026.

In scope:

- Keep current admin password login.
- Improve session handling only if a specific issue is found.
- Document real users/roles as production hardening.

Out of scope:

- Full Supabase Auth.
- Roles/admin/operator split.
- Multi-user audit trails.

Risks:

- Real auth is easy to botch under time pressure.
- Changing auth can lock out the client or break the demo.

Acceptance criteria:

- Current login still works.
- Logout still works.
- Protected API routes remain protected.
- Real users/roles remain documented as Phase 2 production hardening.

## Explicitly Not Done By Saturday

These remain pending or Phase 2. Foundations are allowed, but they should not be represented as complete:

- Full Supabase Auth with roles/admin/operator.
- Full scalable client loading redesign.
- Full WhatsApp template approval/management/tracking.
- AI auto-response.
- Call analytics.
- Advanced customer tags/VIP/status.
- Business pricing refinement.

## Agent Usage

Agents can help, but only inside clear contracts. They should not own architecture decisions or make broad product changes.

Recommended split after contracts are approved:

- Lead path: architecture, DB/API contracts, integration, reviews, commits, deploys.
- Agent 1: Customer Profile and Contact Search implementation slice.
- Agent 2: CSV import backend and tests.
- Agent 3: Observability/status endpoint and minimal UI.
- Lead path: WhatsApp template UX and final integration, because this touches product behavior and messaging rules.

Other AI should be used for copy, prompt, or content drafting only, not code ownership.

## Schedule

### Tonight, Wednesday June 17, 2026

- Finalize this production-slice plan.
- Update the 360 doc truthfully.
- Confirm domain/root redirect remains healthy.
- Define and start one approved production slice.
- Preferred first coding slice: Call Details readability polish, because it is low schema risk and improves daily operations.

### Thursday June 18, 2026

- Finish Call Details polish if not complete.
- Start Customer Profile basics.
- Start Contact Search backend.
- Validate deployed recording automation with one real call.

### Friday June 19, 2026

- Finish Customer Profile basics.
- Finish Contact Search UI.
- Build CSV import backend and tests.
- Add CSV import UI if time allows.
- Add quick template drafts.
- Add observability/status MVP.

### Saturday June 20, 2026

- Regression testing.
- Real Twilio tests:
  - SMS
  - WhatsApp
  - inbound call
  - voicemail
  - connected call recording
  - transcript/recap
- Domain final check.
- Update 360 list truthfully.
- Commit/push final stable version.
