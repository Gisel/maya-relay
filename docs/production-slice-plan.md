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

## Production-Ready Language Standard

Use the phrase `production-ready` only when every required item for the declared scope is complete and verified. Local tests alone are not enough.

For a slice to be called production-ready, all applicable checks must be true:

- Code is implemented.
- Local backend tests pass.
- Frontend build passes when frontend code is touched.
- Playwright/e2e tests pass when UI or operator workflow is touched.
- Required Supabase schema changes are applied in production, not only present in `supabase_schema.sql`.
- Required Railway deployment is successful.
- Live production smoke test passes against the deployed app.
- Required Twilio, Supabase, OpenAI, AssemblyAI, domain/DNS, or other third-party configuration is verified in the live environment.
- The 360 doc and production slice plan reflect the true current status.
- No known blocker remains for the declared scope.

If any item is missing, do not call the work production-ready. Use precise status language instead:

- `Implemented locally`
- `Tests pass locally`
- `Committed and pushed`
- `Deployed, pending live verification`
- `Backend code ready, production schema pending`
- `Production schema applied, live smoke pending`
- `Blocked on Supabase migration`
- `Validated in production`

Example:

`Backend code ready, tests pass locally, production Supabase schema pending` is acceptable.

`Backend is production-ready` is not acceptable until production schema, deployment, and live smoke checks have all passed.

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

Current status:

- Backend/API foundation is implemented.
- The first dashboard placement was reverted because it crowded the active details panel and risked existing operator workflows.
- Frontend integration must be treated as a new scoped UX slice, not as a quick right-panel insertion.

In scope:

- Editable contact display name.
- Phone number visible and copyable/readable.
- Customer notes.
- Recent message and call history visible.
- Use contact display name before Twilio Lookup name.
- Keep the UI compact and subordinate to the existing conversation/call workflow.

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

- Implemented endpoints:
  - `GET /api/contacts?q=&limit=&offset=`
  - `PATCH /api/contacts/{contact_id}` with optional `displayName` and `notes`.
- Response should include:
  - `id`
  - `phone`
  - `displayName`
  - `lookupName`
  - `notes`
- Auth: same current admin session.

UI contract:

- Existing dashboard details panel must continue showing customer name, phone, AI Suggested Reply, and Quick Responses.
- Edit name and notes through an explicit edit action, drawer, or modal.
- Do not place large forms above AI Suggested Reply or Quick Responses in the default right panel.
- Recent history may be shown only if bounded and visually secondary.
- Save state is clear.
- Empty notes/history states are quiet and professional.

Tests:

- Repository tests for contact update and notes persistence.
- API tests for authorized update, validation, and response shape.
- Frontend/e2e test for editing contact name/notes when UI is reintroduced.
- Regression test that existing center-column messages still render.

Risks:

- Contact identity by phone needs careful normalization.
- Recent history must stay bounded; do not load every message/call.
- Manual names must not be erased by CSV import or Lookup later.

Acceptance criteria:

- Operator can edit and save a contact name.
- Operator can edit and save customer notes.
- Phone number remains visible.
- Recent messages/calls are visible only if included in the accepted UI slice; otherwise they remain pending.
- Manual name is used in conversation/call display.

### Slice C2: Contact / Client Search

Feature goal:

Allow operators to find contacts/clients by name or phone without redesigning the whole dashboard.

Current status:

- Backend/API foundation is implemented.
- Dashboard UI is pending after reverting the first placement.

In scope:

- Backend search endpoint.
- Basic dashboard UI entry point that does not disrupt conversation search.
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

- Add a focused search surface to the existing dashboard.
- Do not replace or crowd the existing conversation search.
- Do not place global contact search inside the default active conversation details stack.
- Empty, loading, and error states are visible.

Tests:

- Repository search tests.
- API search tests for name, phone, pagination, and auth.
- Frontend/e2e smoke test when UI is added.
- Regression test that existing conversation search still works.

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

Current status:

- Backend/API foundation is implemented and tested.
- The first dashboard upload placement was reverted because it had poor feedback and belonged in an admin/import surface, not the active conversation details panel.

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

- Simple import surface in dashboard/admin area, settings area, or dedicated drawer/modal.
- Do not place CSV import controls in the active conversation details panel.
- Show required columns.
- Show summary after upload.
- Show row errors in a readable, bounded way.
- Show progress/loading, success, skipped/invalid row counts, and error feedback.

Tests:

- CSV parser tests for valid rows, blank names, invalid phone, missing columns.
- Repository upsert tests.
- API upload tests.
- Frontend/e2e smoke when UI is added.
- Regression test that the Text/Calls rail, center message timeline, composer, and details toggle are unchanged.

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

## Customer Action Workflow Production Slice

### Slice A1: Proof Approval Close-Out

Feature goal:

Finish the Proof approval workflow with truthful production status, then use it as the foundation for Assets.

Current status:

- Database tables, indexes, RLS, and grants exist for customer-action requests, files, and events.
- Operator `Proof` action, proof upload modal, public proof page, and conversation timeline events are implemented.
- SMS proof flow has been live-smoke tested through approval and request-changes outcomes.
- Backend tests and frontend build pass.

Still in scope before calling the full Proof workflow production-ready:

- Live WhatsApp proof smoke test inside a fresh 24-hour service window.
- Confirm production `PUBLIC_BASE_URL` keeps proof links on `https://mayagraphics.co`.
- Confirm invalid/oversize proof upload messages are understandable in the deployed app.
- Add formal frontend/e2e coverage or document why it remains deferred for the next test-hardening slice.

Out of scope:

- WhatsApp template send path outside the 24-hour window.
- Assets upload workflow.
- Job/order management.
- AI-generated proof requests.

Acceptance criteria:

- SMS proof request, approval, and request-changes remain working in production.
- WhatsApp proof request works inside a fresh 24-hour WhatsApp conversation.
- Maya Relay timeline shows proof decisions clearly.
- No existing SMS, WhatsApp, profile, CSV import, observability, calls, or composer workflow regresses.
- Status docs match the live result.

### Slice A2: Assets Request And Upload

Feature goal:

Reuse the customer-action foundation to let the operator request missing customer assets and let the customer upload them through a tokenized public link.

Current status:

- Implemented and deployed.
- Backend tests pass.
- Frontend build passes.
- Live SMS and WhatsApp smoke passed.
- Live acceptance criteria passed for the declared Assets scope.
- Mobile operator-app Playwright coverage exists and passes; formal public `/assets/{token}` e2e coverage remains pending.

In scope:

- Add `Assets` action near `Proof`.
- Operator modal asks for instructions and sends an upload link.
- Public `/assets/{token}` page supports drag/drop and choose-file upload.
- Customer can add a note and submit.
- Maya Relay conversation timeline shows assets submitted with customer note and file count.

Out of scope:

- Asset library management.
- File virus scanning beyond current storage safeguards.
- Job/order assignment.
- AI classification of uploaded files.

Acceptance criteria:

- Assets request can be sent by SMS.
- Public customer upload works on mobile.
- Submitted assets are stored and linked to the request.
- Maya Relay shows the submission event.
- Proof workflow remains unchanged.

Validation plan:

- Completed: deploy from GitHub/Railway.
- Completed: send an Assets request from an SMS conversation.
- Completed: open the public asset link on phone.
- Completed: upload multiple files with a note.
- Completed: confirm Maya Relay shows `Assets uploaded by customer` in the conversation timeline.
- Completed: repeat inside a fresh 24-hour WhatsApp conversation.
- Pending hardening: add formal frontend/e2e automation when a frontend e2e runner exists.

## WhatsApp Templates Production Slice

### Slice W1: Template-Aware Quick Responses

Feature goal:

Give operators reusable quick responses that choose free-form or Twilio Content template sends according to channel and WhatsApp 24-hour window state.

Current status as of 2026-06-19:

- Implemented, tested locally, committed, and pushed.
- Quick response list has been cleaned to:
  - request missing job specs
  - shop hours
  - new customer intro
  - quote follow-up
  - pickup reminder
  - payment reminder
- Proof-related quick responses were removed because Proof and Assets are now dedicated customer-action workflows.
- Template-aware quick responses open a focused confirmation modal and prefill known customer variables.
- SMS and active-window WhatsApp sends use free-form text.
- Stale WhatsApp conversations use configured Twilio Content templates when a mapped template exists.
- Backend tests passed with 151 tests at implementation time.
- Frontend build passed.
- Mobile Playwright coverage was added and passed with 42 tests.
- Pending live verification: production smoke for template-aware quick responses inside and outside the WhatsApp 24-hour window after template approval/configuration is stable.

In scope:

- Clean quick response list:
  - request missing job specs
  - shop hours
  - new customer intro
  - quote follow-up
  - pickup reminder
  - payment reminder
- Remove proof-related quick responses because Proof is a dedicated customer-action workflow.
- Add template mappings:
  - `maya_new_customer_intro`
  - `maya_quote_follow_up`
  - `maya_pickup_reminder`
  - `maya_payment_reminder`
- SMS sends use free-form text.
- WhatsApp inside an active 24-hour window uses free-form text.
- WhatsApp outside the active 24-hour window uses the mapped Twilio Content template.
- Add a focused confirmation modal for template-aware responses and required variables.

Out of scope:

- Twilio template approval tooling.
- Template editor/management UI.
- General composer template conversion.
- Retry UI for failed sends.

Data contract:

- Static frontend/backend config is acceptable for this slice.
- No database table required until templates need editing, ownership, approval state, or tracking.

API contract:

- Existing `GET /api/quick-responses` may be extended.
- Add `POST /api/conversations/{conversation_id}/quick-responses/{quick_response_id}/send`.
- Response should distinguish plain quick replies from template-aware responses:
  - `id`
  - `label`
  - `body`
  - `channels`
  - `group`
  - `templateKey`
  - `variables`

UI contract:

- Plain quick responses continue to fill the composer.
- Template-aware quick responses open a small confirmation modal.
- Variable fields prefill from selected customer context when possible.
- Mobile layout must keep the modal within the viewport and make the send action reachable.

Tests:

- API tests for quick response payload, SMS free-form send, WhatsApp active-window free-form send, WhatsApp stale-window template send, and missing template config.
- Frontend build must pass.
- Formal frontend/e2e tests remain a future hardening item.

Risks:

- Twilio templates must have variable shapes that match the app mapping.
- WhatsApp 24-hour window rules must not be bypassed.

Acceptance criteria:

- Cleaned quick response list appears in the right panel.
- Plain responses still fill the composer.
- Template-aware responses can be sent from the confirmation modal.
- Older-than-24-hour WhatsApp mapped responses use `ContentSid`.
- Existing composer, Proof, Assets, Calls, Requests, and AI Suggested Reply behavior remain intact.

### Slice W2: Proof And Assets WhatsApp Action Templates

Feature goal:

Allow Proof and Assets customer-action links to send through approved WhatsApp templates outside the 24-hour service window.

Current status as of 2026-06-19:

- Backend send path is implemented for Proof and Assets action-link templates.
- Production Railway variables have been added for the core action templates:
  - `WHATSAPP_TEMPLATE_PROOF_READY_CONTENT_SID`
  - `WHATSAPP_TEMPLATE_ASSETS_NEEDED_CONTENT_SID`
- Current Twilio template SIDs:
  - `maya_proof_ready`: `HX7f7896c1911956f2817e11158289dc5d`
  - `maya_assets_needed`: `HX63099b79862bbb7dd9d608e0652aa026`
- The Assets template was recreated after a Twilio variable-placement issue and Railway was updated to the new SID.
- Railway deployment succeeded after the sender/template-send fix.
- Pending: Twilio/Meta approval and true older-than-24-hours WhatsApp smoke test.

Acceptance criteria:

- Proof request sent to an older-than-24-hours WhatsApp conversation uses the approved `maya_proof_ready` template and is delivered.
- Assets request sent to an older-than-24-hours WhatsApp conversation uses the approved `maya_assets_needed` template and is delivered.
- Timeline remains operator-readable with the public action URL visible.
- If a required Content SID is missing, the app blocks send with a clear configuration error.
- SMS and active-window WhatsApp action links remain unchanged.

## AI Suggested Reply Slice

### Slice AI1: Live Suggested Reply Refresh

Feature goal:

Keep the right-panel AI Suggested Reply current as customers respond, without auto-replying or using stale relay notes.

Current status as of 2026-06-19:

- Implemented, tested locally, committed, and pushed.
- Added `POST /api/conversations/{conversation_id}/suggested-reply`.
- The dashboard auto-refreshes suggestions when the latest visible message is from the customer.
- The dashboard clears suggestions when the latest visible message is from Maya/operator.
- A manual `Refresh` button was added to the AI Suggested Reply panel.
- AI receives the last 6 visible customer/operator messages as context and ignores internal system messages.
- Stale response protection prevents an in-flight suggestion from updating the wrong selected conversation.
- Backend tests passed with 154 tests.
- Frontend build passed.
- Mobile Playwright tests passed with 42 tests.

Out of scope:

- AI auto-response.
- Full conversation memory.
- Job/order-aware context.
- Automatic pricing, timeline, or policy commitments.

Production watch items:

- Monitor whether AI asks for details the customer already provided.
- Keep the current 6-message context unless real production behavior shows repeated misses.
- If needed, tune to 8-10 recent visible messages or add focused context from pending Proof/Assets requests.

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

## Current Next Steps As Of 2026-06-19

Immediate validation queue:

- Wait for Twilio/Meta approval state to settle for `maya_proof_ready` and `maya_assets_needed`.
- Smoke test older-than-24-hours WhatsApp Proof and Assets sends after approval.
- Smoke test template-aware quick responses inside and outside the WhatsApp 24-hour window.
- Monitor live AI Suggested Reply behavior with the current last-6-visible-message context.

Recommended next production slices:

- Asset/proof retention and deletion controls so storage only keeps live project files.
- Retry UI for failed customer-action sends.
- Public Proof/Assets frontend/e2e automation.
- Auth hardening: move beyond shared `ADMIN_PASSWORD` when ready.
- AI suggested reply refinement after enough real production examples are observed.

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

## Auth And User-Routed Calls Addendum - June 20, 2026

This addendum defines the next production direction after the New Message and New Call saved-customer selector slices. It is additive. Do not remove the current shared-password path until the replacement is implemented, tested, deployed, and validated.

### Slice A1: Production Auth Foundation

Feature goal:

Give Maya Relay a real operator identity model so future actions can safely depend on who is logged in.

Current status:

- The app uses a shared `ADMIN_PASSWORD` cookie.
- All operator APIs are protected by the same shared admin session.
- There is no trusted per-user identity yet.
- Two operators need access to the whole app for the first production release.
- Both operators can share one role for now.

In scope:

- Add two real operator users.
- Use one role: `operator`.
- Store operator routing config with the user identity:
  - display name
  - login identifier
  - role
  - active flag
  - call routing line, such as `signs` or `general_orders`
  - click-to-call phone number
- Replace the shared login behavior with user login while preserving the current secure cookie pattern.
- Passwords must be hashed; no plaintext password storage.
- `/api/me` returns authenticated user identity, role, and call-routing readiness.
- Existing operator API access remains all-or-nothing: authenticated operators can access the full app.
- Keep the current shared-password behavior available only as a transition fallback if needed during rollout.

Out of scope:

- Fine-grained permissions.
- Admin user-management UI.
- Multi-company tenancy.
- Customer login/auth.
- Role-based feature hiding.
- Call routing changes; those belong to Slice A2.

Data contract:

- Add an operator identity record with stable ID, login identifier, display name, role, active flag, password hash, and timestamps.
- Add or associate call-routing settings for each operator.
- Keep existing conversations, messages, contacts, calls, proof requests, and asset requests compatible.
- Do not rewrite historical call records.

API contract:

- `POST /api/auth/login`
  - Request includes login identifier and password.
  - Response confirms authentication and returns safe user summary.
- `POST /api/auth/logout`
  - Clears the auth cookie/session.
- `GET /api/me`
  - Returns authenticated user, role, app metadata, features, and call-routing readiness.
- Existing protected endpoints continue returning `401` when unauthenticated.

UI contract:

- Login screen adds a user identifier field and password field.
- Logout remains in the top bar.
- The app should display only small, useful identity context if needed; do not crowd the operator workspace.
- Show clear login errors without leaking which account exists.
- Mobile login must remain clean and usable.

Tests:

- Backend tests for valid login, invalid login, logout, `/api/me`, inactive user rejection, and protected endpoint rejection.
- Password hash verification tests.
- Session/cookie tests.
- Frontend/e2e login smoke for one operator.
- Regression tests that SMS, WhatsApp, calls, proof/assets, contacts, and CSV endpoints still require auth.

Risks:

- Locking both operators out if credentials or env/seeding are wrong.
- Accidentally exposing password hashes or service-role data.
- Session migration confusion while Railway deploys.
- Tests relying on old shared-password-only login.

Acceptance criteria:

- Two configured operators can log in.
- Both can access the full app.
- `/api/me` identifies the logged-in operator.
- Invalid and inactive users cannot log in.
- Existing app workflows remain protected and functional.
- No call routing behavior changes yet.

Deploy/validation plan:

- Commit the auth foundation as its own slice.
- Deploy through Railway.
- Confirm both operators can log in and out.
- Confirm old unauthenticated access is rejected.
- Confirm existing SMS/WhatsApp/call screens load after login.

### Slice A2: User-Routed Outbound Calls

Feature goal:

Route outbound click-to-call actions to the phone configured for the logged-in operator, so Signs and General Orders can receive their own calls.

Current status:

- `POST /api/calls` starts a new manual outbound call.
- `POST /api/conversations/{conversation_id}/call` starts a call from an existing conversation.
- Both paths currently resolve the employee phone from `FRANCISCO_PHONE`.
- Calls already store `employee_phone`, so the historical call log can remain compatible.

In scope:

- Resolve outbound call employee phone from the authenticated operator.
- Support two configured operator destinations for the first release.
- Preserve the existing New Call and conversation Call buttons.
- Preserve manual phone/name fallback in New Call.
- Store the selected employee phone on the call record.
- Add operator attribution to outbound call records if a new nullable field is approved.
- Show a clear error if the logged-in operator has no call phone configured.

Out of scope:

- Complex queue routing.
- Call transfer.
- Inbound Studio Flow replacement.
- Department-switching UI unless explicitly approved.
- Recording behavior changes.

Data contract:

- Existing `calls.employee_phone` remains authoritative for the phone Twilio called first.
- Add nullable operator attribution only if needed:
  - `operator_user_id`
  - `operator_display_name`
  - `operator_routing_line`
- Existing call rows remain valid with null operator attribution.

API contract:

- `POST /api/calls`
  - Uses authenticated operator routing phone instead of global `FRANCISCO_PHONE`.
- `POST /api/conversations/{conversation_id}/call`
  - Uses the same routing resolver.
- Error states:
  - `401` unauthenticated.
  - `503` authenticated operator has no call phone configured.
  - Existing customer-phone validation errors remain unchanged.

UI contract:

- The Call buttons stay simple and elegant.
- No new routing dropdown for the first implementation.
- Optional small confirmation/error copy may mention which operator phone will ring only if it helps prevent confusion.
- Mobile layout must not gain extra crowded controls.

Tests:

- Backend tests that each operator routes calls to the correct configured phone.
- Backend tests for missing operator call phone.
- Backend tests for both New Call and conversation Call paths.
- Repository tests for optional call attribution if added.
- E2E smoke that the New Call drawer still works after auth.

Risks:

- Misconfigured operator phone routes calls to the wrong person.
- Existing `FRANCISCO_PHONE` assumptions in tests need careful update.
- Twilio click-to-call behavior must remain unchanged except the first leg destination.

Acceptance criteria:

- Operator A clicks Call and Operator A's configured phone rings first.
- Operator B clicks Call and Operator B's configured phone rings first.
- The customer is still bridged only after the operator answers.
- Call records show the correct `employee_phone`.
- Existing calls, conversations, messages, proof/assets, contacts, and CSV import continue working.

Deploy/validation plan:

- Commit as a separate slice after auth foundation is live.
- Deploy through Railway.
- Smoke test with both operators:
  - log in as Operator A
  - start a call
  - confirm Operator A phone rings
  - log in as Operator B
  - start a call
  - confirm Operator B phone rings
- Confirm no inbound Studio behavior changed.
