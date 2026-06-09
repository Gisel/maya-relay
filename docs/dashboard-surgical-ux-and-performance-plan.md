# Maya Relay Dashboard Surgical UX and Performance Plan

Date: 2026-06-08

This document is the working 360 functionality list for Maya Relay. It captures what is done, what is next, and what remains pending so we do not lose track while testing, shipping, and adding functionality surgically.

## Non-Negotiables

- Do not delete or disable existing functionality.
- Do not mutate stored message bodies for display cleanup.
- Keep the SMS phone-based reply code flow available for on-the-go replies.
- Keep `.env` and Railway variables as the source of truth for configuration.
- Prefer small, isolated commits with one concern per change.
- Verify frontend changes with `npm run build` and e2e tests when UI behavior can be affected.
- Verify backend changes with `.venv/bin/python -m pytest`.

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

## Next

- Validate Incoming Call Logging:
  - wait for Railway deploy after `fb6e5ba Log inbound Studio voice calls`
  - call the Maya number
  - confirm Twilio Studio `log_incoming_call` widget returns Success
  - confirm Maya Relay Calls tab -> Incoming shows the caller
  - if not visible, inspect Railway logs and Studio execution logs
- Add Studio completion logging:
  - add a second Studio HTTP Request near the end of the router flow
  - URL: `/webhooks/twilio/voice/studio/complete`
  - pass the same `access_key`
  - pass `CallSid`
  - pass final status if the flow exposes it, otherwise send `completed`
- Improve Call Details UX after functionality test:
  - make saved notes/transcription/recap easier to review
  - add clearer save success/error feedback if needed
  - confirm details change correctly when selecting different timeline calls
- Improve Manual Outbound Call:
  - create/update contact after calling a new number
  - add name
  - add notes
  - add call outcome
- Add Customer Profile basics:
  - notes
  - visible customer history
  - contact information foundation
- Add WhatsApp Templates:
  - quote follow-up
  - proof ready
  - pickup reminder
  - payment reminder
- Add Contact / Client Search foundation:
  - backend endpoint
  - tests
  - no major UI disruption yet
- Add CSV Contact Import:
  - `phone_number`
  - `display_name`
  - preserve manual names
  - blank values do not erase existing names
  - use uploaded contacts before paid Twilio Lookup
- Continue small operational polish:
  - attachment preview polish only if needed
  - mobile/header/customer action polish only if needed

## Pending

- Scalable client/conversation loading model:
  - conversations remain paginated and activity-ordered
  - contact/client search remains separate from conversation browsing
  - conversation details load only when selected
  - avoid loading all clients and all conversations at once
- Production Auth / Users:
  - real user accounts
  - roles
  - admin vs operator access
  - Supabase Auth later
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
- Customer Profile advanced:
  - tags
  - active/inactive client status
  - VIP/repeat customer marker
  - deeper customer history
- Call workflow advanced:
  - call notes in timeline
  - follow-up reminders
  - call analytics later
  - call recording after consent text and Twilio pricing are approved
  - automatic transcription after recording is working
  - AI recap generation from transcript/conversation context after transcription is stable
- Business / Pricing:
  - refine monthly fee after real usage
  - include infrastructure, AI, support, improvements, and monitoring

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

### Notes, Transcription, And Recap

Current state:

- `notes` exists in the `calls` table and is editable in the Calls workspace.
- `transcription` exists in the `calls` table and is editable manually.
- `recap` exists in the `calls` table and is editable manually.

Recommended meaning:

- Notes: human operator notes.
- Transcription: raw transcript of what was said.
- Recap: short summary of what matters from the call.

Automation path, not started yet:

1. Add call recording after consent language and pricing are approved.
2. Receive Twilio recording callbacks.
3. Send recording to AssemblyAI or another transcription provider.
4. Save transcript into `calls.transcription`.
5. Generate and save recap into `calls.recap`.
