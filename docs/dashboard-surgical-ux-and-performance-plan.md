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
- Public Supabase attachments bucket integration.
- Twilio Lookup fallback and contact caching.
- Click-to-call bridge: Francisco receives call first, then Twilio bridges to customer.
- Manual outbound call to a new number.
- Basic close/reopen conversation functionality.
- Close Conversation UX:
  - confirmation before closing
  - undo after close
  - closed conversations hidden by default
  - Open / Closed / All filtering
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

- Fix manual top Refresh button reliability.
- Add Call Logging:
  - save call attempts/statuses
  - show call history
  - add call outcomes: connected, voicemail, no answer, follow-up needed
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
- Business / Pricing:
  - refine monthly fee after real usage
  - include infrastructure, AI, support, improvements, and monitoring
