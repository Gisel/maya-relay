# Maya Relay Dashboard Surgical UX and Performance Plan

Date: 2026-06-11

This document is the working 360 functionality list for Maya Relay. It captures what is done, what is next, and what remains pending so we do not lose track while testing, shipping, and adding functionality surgically.

Detailed production-slice contracts now live in [production-slice-plan.md](production-slice-plan.md). Use that plan before coding new feature work: every slice needs scope, out-of-scope, data/API/UI contracts, tests, risks, and acceptance criteria.

## Non-Negotiables

- Do not delete or disable existing functionality.
- Do not mutate stored message bodies for display cleanup.
- Keep the SMS phone-based reply code flow available for on-the-go replies.
- Keep `.env` and Railway variables as the source of truth for configuration.
- Prefer small, isolated commits with one concern per change.
- Verify frontend changes with `npm run build` and e2e tests when UI behavior can be affected.
- Verify backend changes with `.venv/bin/python -m pytest`.
- Do not label broad MVP work as done unless production acceptance criteria are met.
- Do not use `production-ready` unless code, tests, production schema/configuration, Railway deployment, live smoke test, and docs are all complete for the declared scope.
- If production verification is incomplete, use precise labels such as `implemented locally`, `tests pass locally`, `deployed pending live verification`, `production schema pending`, or `validated in production`.

## Styling And CSS Token Rule

The dashboard now has some CSS variables in `frontend/src/styles.css`, including brand blue/green tokens and the topbar height. Any new frontend code should prefer existing CSS classes and CSS variables instead of hardcoded inline styles or one-off color values.

Current rule for future work:

- Use existing CSS classes before adding new ones.
- Use CSS custom properties for shared colors, surfaces, borders, typography, spacing, and radius when a style will be reused.
- Avoid inline `style={{ ... }}` unless the value is truly dynamic runtime data.
- Do not add hardcoded colors in JSX.
- If a new color is needed in more than one place, add it as a token at the top of `frontend/src/styles.css`.
- Keep styling changes frontend-only unless the user explicitly asks for behavior changes.

Recommended future token additions when we do a broader visual pass:

- `--color-surface`
- `--color-surface-muted`
- `--color-border`
- `--color-text-muted`
- `--color-warning`
- `--color-attention`
- `--radius-control`
- `--radius-panel`
- `--space-*` spacing tokens for repeated layout values

This is not urgent for functionality work, but it will reduce future style cleanup cost.

## UX Vision Note

The dashboard should feel soft, modern, calm, and client-ready. It should not feel loud, blocky, overly bold, or like an older admin dashboard. The product is an operator inbox, so the visual design should support quick scanning and confident replies without drawing attention to the interface itself.

Visual direction to preserve:

- Use lighter typography weights, generally 500-600 for UI labels and CTAs.
- Avoid heavy all-bold button text.
- Avoid pure cyan or electric blue.
- Use restrained, composed colors.
- Keep WhatsApp/outbound green clean and professional, not harsh.
- Prefer subtle borders, quiet backgrounds, and compact spacing over heavy badges or oversized emphasis.
- Keep the mobile polish that is already working.

## Done

- SMS relay with conversation code routing.
- WhatsApp inbound/outbound through Twilio.
- AI suggested reply generation.
- Copy-paste friendly AI suggestion SMS for on-the-go use.
- React operator dashboard at `/app`.
- Conversation search.
- Local cache-first search for loaded conversations.
- Server search for older/unloaded conversations.
- Conversation pagination and Load More.
- Send message from dashboard.
- Attach/upload media foundation.
- Drag-and-drop attachments in composer.
- Manual top Refresh reliability.
- Public Supabase attachments bucket integration.
- Twilio Lookup fallback and contact caching.
- Click-to-call bridge: Francisco receives call first, then Twilio bridges to customer.
- Manual outbound call to a new number.
- Calls workspace foundation:
  - Text / Calls tab switcher in the left rail.
  - Calls search.
  - Outgoing / Incoming / All call filters.
  - Calls list grouped by customer/conversation activity.
  - Calls tab defaults to All so recent inbound and outbound calls are visible together.
  - Calls tab refreshes automatically every 15 seconds while open.
  - Calls center workspace with selected customer header.
  - Call timeline/history.
  - Editable call details for outcome, follow-up status, notes, recap, and transcription.
  - Call details save through `PATCH /api/calls/{call_id}`.
  - Mobile Calls layout uses horizontal compact call pills like Text conversations.
  - Mobile hides Latest Call Summary to preserve room for timeline/details.
  - Right panel stays focused on Customer Profile, AI Suggested Reply, and Quick Responses.
- Outgoing call logging:
  - click-to-call creates a call record
  - manual outbound call creates a call record
  - Twilio voice status callback updates call status
  - duplicate active call guard prevents rapid double-starts
- Incoming call logging foundation for Twilio Studio:
  - `POST /webhooks/twilio/voice/studio/incoming` logs inbound Studio calls without changing Maya Router routing.
  - `POST /webhooks/twilio/voice/studio/complete` can mark Studio-routed inbound calls complete/busy/no-answer later.
  - Optional `TWILIO_STUDIO_WEBHOOK_SECRET` protects Studio HTTP Request widgets.
  - Studio completion widgets are configured per live-call path so connected inbound calls can be marked completed.
- Recording capture foundation:
  - `POST /webhooks/twilio/voice/recording` stores Twilio recording metadata on the matching call by `CallSid`.
  - Studio live-call recordings can also be fetched from Twilio after `/webhooks/twilio/voice/studio/complete` when Studio does not expose a recording callback URL.
  - Completed recordings auto-mark untouched calls as `Voicemail` with `Pending follow-up`.
  - Completed connected-call recordings do not auto-mark the call as voicemail.
  - Call Details shows recording status, a Maya Relay audio player, and an Open Recording link when Twilio provides `RecordingUrl`.
  - Call Details can send a captured recording to AssemblyAI and save the result into `transcription`.
  - Completed recordings can automatically transcribe through AssemblyAI and generate an OpenAI recap when keys are configured.
  - Live inbound recording automation chooses the longest completed Twilio recording when multiple recordings exist for the same call.
  - AssemblyAI requests now explicitly use `universal-3-pro` with fallback to `universal-2`.
  - AssemblyAI polling now waits up to 10 minutes by default for longer call recordings.
  - `ENABLE_CALL_RECORDING_AUTOMATION=false` can disable automatic transcription/recap if needed.
- Inbound call recording consent blurb added in Twilio Studio before recording connected calls.
- Inbound connected-call recording enabled in Twilio Studio for the selected live-call paths.
- Custom root domain setup started:
  - GoDaddy nameservers moved to Cloudflare for `mayagraphics.co`.
  - Cloudflare root CNAME points to Railway.
  - Railway ownership TXT record added.
- Custom root domain is live:
  - `https://mayagraphics.co/app` loads the operator dashboard.
  - App root `/` redirects to `/app` so the custom domain opens the operator dashboard.
- Basic close/reopen conversation functionality.
- Close Conversation UX:
  - confirmation before closing
  - undo after close
  - closed conversations hidden by default
  - Open / Closed / All filtering
  - explicit red Close action styling and accessible Close/Reopen labels
- Session ID exposed in UI.
- Needs-reply visual state for customer messages.
- Internal AI/system relay messages hidden from dashboard chat display.
- Remaining relay/display cleanup done enough for current operations.
- New Call mobile drawer overflow fixed.
- Login mobile overflow fixed.
- Mobile dashboard improvements: compact composer, safer drawer behavior, improved mobile layout.
- Reply composer grows vertically for multi-line replies.
- Dashboard visual softening started.
- CSS token rule documented for future frontend styling.
- `.env` / Railway variables remain source of truth.
- Customer / Contact production slice:
  - backend contact profile/search contract
  - editable contact name and notes via API
  - phone number visible in existing dashboard summary
  - contact search by name/phone via API
  - bounded contact search results via API
- CSV Contact Import production slice:
  - backend endpoint and tests
  - accepts CSV with `phone_number`, `display_name`
  - upserts contacts conservatively
  - blank names do not overwrite
  - imported names used before paid Twilio Lookup
  - initial dashboard upload UI was reverted because it crowded the operator details panel and did not meet UX acceptance criteria

## Next

- Rebuild Customer/Profile/Search/Import frontend as a scoped UX slice:
  - preserve the existing Text/Calls rail, center message timeline, composer, details toggle, AI Suggested Reply, and Quick Responses
  - keep the right panel lightweight by default; do not place CSV import or broad search inside the active conversation details stack
  - add profile editing through an explicit Edit action, drawer, or modal
  - add contact search as a separate focused operator action, not a replacement for conversation search
  - add CSV import under an admin/settings/import surface with clear progress, success, skipped, and invalid-row feedback
  - verify with Playwright that existing messages still render in the center column before calling the slice done
- Validate deployed inbound call recording automation:
  - place one answered inbound call after deploy
  - confirm Maya Relay stores the longest/full Twilio recording, not the short ring/early segment
  - confirm transcript and recap appear without clicking manual buttons
  - confirm manual Transcribe recording and Generate recap buttons still work as fallback
- Improve Call Details UX after live use:
  - soften notes/transcription/recap typography
  - make saved notes/transcription/recap easier to review
  - add clearer save success/error feedback if needed
  - confirm details change correctly when selecting different timeline calls
- Decide outbound two-party recording:
  - confirm consent language and Twilio pricing before enabling `<Dial record>` for bridged outbound calls
  - once approved, send outbound recordings to the same recording callback so automation covers them too
- Improve Manual Outbound Call:
  - create/update contact after calling a new number
  - add name
  - add notes
  - add call outcome
- Improve Customer / Contact history display:
  - make recent message/call history more visible inside the profile area
  - keep history bounded and avoid full CRM redesign
- Build WhatsApp quick template drafts:
  - quote follow-up
  - proof ready
  - pickup reminder
  - payment reminder
  - active conversation drafts only; no business-initiated template tooling yet
- Build Observability MVP:
  - recent failed Twilio sends
  - recent recording/transcription/recap failures where available
  - plain-English error hints where easy
- Continue small operational polish:
  - attachment preview polish only if needed
  - mobile/header/customer action polish only if needed

## Pending

- Customer Profile frontend integration:
  - editable name and notes through a focused edit surface
  - visible customer history without crowding the active conversation panel
  - clear save/loading/error feedback
- Add WhatsApp Templates:
  - quote follow-up
  - proof ready
  - pickup reminder
  - payment reminder
- Contact / Client Search frontend:
  - use the existing backend endpoint
  - search by phone/name
  - open the related active/recent conversation when available
  - do not disrupt the existing conversation search
- CSV Contact Import frontend:
  - use the existing backend endpoint
  - accept `phone_number` and `display_name`
  - show created/updated/skipped counts and row-level errors
  - do not place import controls in the active conversation details panel
- Scalable client/conversation loading model:
  - conversations remain paginated and activity-ordered
  - contact/client search remains separate from conversation browsing
  - conversation details load only when selected
  - avoid loading all clients and all conversations at once
- Production Auth / Users:
  - keep current admin password for Saturday scope
  - improve current session handling only if a specific issue is found
  - real user accounts, roles, admin/operator split, and Supabase Auth later
- Observability:
  - structured logs
  - failed delivery view
  - plain-English Twilio error explanations
  - possible health/status dashboard
- AI Next Phase:
  - richer intent detection
  - missing-info checklist
  - suggested quick actions
  - human approval mode first
  - auto-response only for approved safe cases
- WhatsApp advanced workflow:
  - template approval/management
  - business-initiated conversations outside the 24-hour window
  - template usage tracking
- Asset storage retention:
  - delete or archive old proof/customer asset files after projects are no longer live
  - remove related database rows safely without breaking active conversation history
  - keep live project assets available until the operator explicitly closes or archives them
- Customer Profile advanced:
  - tags
  - active/inactive client status
  - VIP/repeat customer marker
  - deeper customer history
- Call workflow advanced:
  - call notes in timeline
  - follow-up reminders
  - call analytics later
  - optional outbound two-party recording only after consent workflow is approved
  - richer recap generation from transcript plus conversation context
- Business / Pricing:
  - refine monthly fee after real usage
  - include infrastructure, AI, support, improvements, and monitoring

## Current Status Snapshot

- SMS/MMS relay is working and tested.
- WhatsApp inbound/outbound relay works inside the 24-hour window.
- React operator inbox is live at `/app`.
- Customer profile panel, contact edit, and CSV import are implemented.
- Calls workspace is implemented.
- Call recording/transcription/recap code path exists with manual fallback buttons.
- Proof request workflow is implemented:
  - operator sends proof
  - customer opens `/proof/{token}`
  - customer can approve or request changes
  - result appears in conversation timeline
- Assets request workflow is implemented:
  - operator sends upload link
  - customer opens `/assets/{token}`
  - customer can upload multiple files
  - uploaded files appear in conversation timeline
- Pending Requests tab is implemented:
  - shows Proof/Assets requests
  - highlights pending requests
  - can cancel pending requests
  - blocks duplicate pending same-type requests
- Quick Responses have been cleaned up:
  - Request missing job specs
  - Shop hours
  - New customer intro
  - Quote follow-up
  - Pickup reminder
  - Payment reminder
- Template-aware quick responses are implemented:
  - SMS uses free-form sends
  - WhatsApp active-window sends use free-form sends
  - WhatsApp stale-window sends use Twilio Content templates
- WhatsApp Proof/Assets template send path is implemented.
- AI Suggested Reply live refresh is implemented:
  - auto-refreshes when the latest visible message is from the customer
  - uses the last 6 visible customer/operator messages
  - includes a manual Refresh button
  - clears the suggestion when Maya/operator replied last
- Mobile Playwright coverage exists for the operator app.
- Latest verification:
  - backend tests passed: 154
  - frontend build passed
  - mobile e2e passed: 42
- Docs have been updated; this 360 status refresh is pending commit/push.

## Current Pending Snapshot

- Confirm Twilio/Meta approval for:
  - `maya_proof_ready`
  - `maya_assets_needed`
- Smoke test older-than-24-hour WhatsApp sends:
  - Proof request
  - Assets request
- Smoke test template-aware quick responses:
  - inside the 24-hour WhatsApp window
  - outside the 24-hour WhatsApp window
- Fresh live validation of call recording/transcription/recap:
  - place one real answered inbound call
  - confirm recording appears
  - confirm transcript appears
  - confirm recap appears
  - confirm manual buttons still work
- Add Railway/readiness visibility for AssemblyAI and call automation config.
- Add persisted provider error visibility for transcription/recap failures.
- Add public Proof/Assets e2e automation.
- Add e2e coverage for Transcribe recording and Generate recap buttons.
- Add asset/proof retention and deletion controls.
- Add retry UI for failed customer-action sends.
- Harden auth beyond shared `ADMIN_PASSWORD`.
- Monitor AI suggestions in production; tune beyond the last 6 messages only if needed.

## Production Release Priority Snapshot - 2026-06-20

This dated snapshot is the current planning source for the first production release. It is additive to the historical `Done`, `Next`, and `Pending` sections above. Do not delete older notes without explicit approval; add newer dated snapshots as the truth changes.

### Done For First Production Release

- Live-call recording automation validation: done.
- Customer Profile basics: done.
- Contact/client search foundation: done.
- CSV import: done.
- Observability/error explanations: done for first release; remaining improvements are low priority.
- New outbound SMS/WhatsApp conversation start: done.
  - Operators can start SMS or WhatsApp conversations from the top-bar Message action.
  - Saved-customer search, manual phone/name fallback, SMS free-form sends, and WhatsApp owner-message template sends are implemented.
  - WhatsApp owner-written first messages use the approved `maya_owner_message` Twilio template and require `WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID` in local `.env` and Railway.
- Reusable saved-customer selector for New Call: done.
  - New Call reuses the same saved-customer selector pattern as New Message.
  - Operators can search/select a saved customer or manually enter phone/name.
  - Existing `POST /api/calls` behavior is preserved.

### Partially Done / Needs Focused Follow-Up

- WhatsApp templates: partially done, medium priority.
  - Template-aware quick responses are implemented.
  - Proof/Assets WhatsApp template send path is implemented.
  - Remaining work is approval confirmation and older-than-24-hour smoke validation.

### Low Priority

- Call Details UX polish.
- Manual outbound call contact/details workflow.
- Observability/error explanation improvements beyond the first-release baseline.

### Pending

- Production auth/users: pending.
- Mobile phone-number keypad/picker inside phone fields: pending.
  - This is distinct from saved-customer search.
  - Desired behavior is a mobile-friendly number picker/keypad experience when entering a phone number.
  - Deferred intentionally; current manual phone entry remains available.

### High Priority New Production Slices

Planning note, June 20, 2026:

- Execution order is auth foundation first, then user-routed outbound calls.
- Both operators can share one app role for the first production release.
- The key production need is trusted user identity so the Call action can route to the logged-in operator's configured phone line.

1. Role/user-routed outbound calls.
   - New phone calls need to route through the correct line/team context, such as Signs versus General Orders.
   - The call button should be linked to the logged-in user or role so the call rings/routes to that user's configured phone line.
2. Authentication foundation for role/user routing.
   - Auth is required for role-aware call routing and future production user separation.
   - This should be planned as a production auth slice, not a quick login patch.

## Current Call Workflow Notes

### Outgoing Calls

Outgoing calls are logged by the backend when Maya Relay starts the call. Existing click-to-call routing is preserved:

1. Maya Relay asks Twilio to call Francisco/the office first.
2. Twilio requests `/webhooks/twilio/voice/bridge/{conversation_id}`.
3. The bridge dials the customer.
4. Maya Relay creates a `calls` row with `direction = outbound`.
5. Twilio status callbacks hit `/webhooks/twilio/voice/status` and update the call record.

### Incoming Calls

Incoming calls are routed by the existing Twilio Studio Flow, Maya Router. Maya Relay should not replace that flow.

Current integration pattern:

1. Studio receives `Incoming Call`.
2. Studio runs `log_incoming_call` as a Make HTTP Request widget near the beginning of the flow.
3. The widget posts to:
   - `https://maya-relay-production.up.railway.app/webhooks/twilio/voice/studio/incoming`
4. Maya Relay logs the inbound call and returns JSON.
5. Studio continues normal routing whether logging succeeds or fails.

Required Studio HTTP parameters:

- `access_key` = same value as Railway `TWILIO_STUDIO_WEBHOOK_SECRET`
- `CallSid` = Studio call SID variable
- `CallStatus` = `ringing`
- `From` = caller phone variable
- `To` = Maya/Twilio number variable

Widget transitions:

- Success -> continue normal router flow
- Fail -> continue normal router flow

Do not check "Authenticate with Twilio" for this widget. The request goes to Maya Relay, not Twilio's API.

### Recording Capture

Current state:

- Maya Relay accepts recording callbacks at:
  - `https://maya-relay-production.up.railway.app/webhooks/twilio/voice/recording`
- The callback stores:
  - `RecordingSid`
  - `RecordingUrl`
  - `RecordingStatus`
  - `RecordingDuration`
  - `RecordingChannels`
- The callback matches recordings to calls by `CallSid`.
- Call Details displays recording status, a Maya Relay audio player, and an Open Recording link when recording metadata exists.
- Completed recordings auto-mark calls as Voicemail/Pending follow-up only when no manual outcome was already saved.
- Completed connected-call recordings do not auto-mark as voicemail.
- For Studio connected calls, Maya Relay can fetch recordings from Twilio after `/webhooks/twilio/voice/studio/complete`.
- If Twilio returns multiple completed recordings for one call, Maya Relay uses the longest completed recording.

Twilio Studio setup for voicemail:

- In the Record Voicemail widget, set Recording Status Callback to:
  - `https://maya-relay-production.up.railway.app/webhooks/twilio/voice/recording`
- Leave "Transcribe Audio To Text" off for now.
- Add a Transcription Callback URL later only if using Twilio's built-in transcription.

Important:

- The Record Voicemail widget captures voicemail-style caller audio.
- Full two-party call recording is a separate setting on the widgets that connect/dial the call.
- Connected inbound call recording is enabled only after the consent blurb.
- Twilio recording URLs require Twilio authentication for reliable playback, so Maya Relay proxies recording audio through `GET /api/calls/{call_id}/recording`.

### Notes, Transcription, And Recap

Current state:

- `notes` exists in the `calls` table and is editable in the Calls workspace.
- `transcription` exists in the `calls` table and is editable manually.
- If `ASSEMBLYAI_API_KEY` is configured, Call Details can transcribe a captured recording through `POST /api/calls/{call_id}/transcribe`.
- `recap` exists in the `calls` table, is editable manually, and can be generated from a saved transcript through `POST /api/calls/{call_id}/recap`.
- recording metadata exists in the `calls` table and is displayed when Twilio sends it.
- Automatic recording processing can transcribe completed recordings and generate recaps without pressing the manual buttons.
- AssemblyAI transcription uses `universal-3-pro` with fallback to `universal-2`.
- AssemblyAI polling waits up to 10 minutes by default for longer recordings.

Production validation:

- Incoming voicemail call logging works through the Twilio Studio incoming-call HTTP hook.
- Twilio voicemail recording metadata reaches Maya Relay through the Recording Status Callback.
- Call Details shows recording status, duration, Open Recording, and an authenticated audio player.
- AssemblyAI transcription successfully fills `calls.transcription` from the captured recording.
- OpenAI recap generation successfully fills `calls.recap` from the saved transcription.
- Inbound connected-call recording and automatic processing are implemented and deployed; final live validation is next.

Recommended meaning:

- Notes: human operator notes.
- Transcription: raw transcript of what was said.
- Recap: short summary of what matters from the call.

Automation path:

1. Twilio records voicemail or consented connected inbound call audio.
2. Twilio recording callback or Studio completion sync stores the recording metadata.
3. Maya Relay chooses the longest completed recording for the call.
4. AssemblyAI transcribes the recording automatically when configured.
5. OpenAI generates a short internal recap automatically when configured.
6. Manual Transcribe recording and Generate recap buttons remain available as fallback.
