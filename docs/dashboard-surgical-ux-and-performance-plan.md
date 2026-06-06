# Maya Relay Dashboard Surgical UX and Performance Plan

Date: 2026-06-06

This document captures the next dashboard work after the mobile Safari and New Call testing session. The goal is to keep the work precise, protect existing production behavior, and avoid broad rewrites while improving daily operator usability.

## Non-Negotiables

- Do not delete or disable existing functionality.
- Do not mutate stored message bodies for display cleanup.
- Keep the SMS phone-based reply code flow available for on-the-go replies.
- Keep `.env` and Railway variables as the source of truth for configuration.
- Prefer small, isolated commits with one concern per change.
- Verify changes on desktop and mobile Safari after UI fixes.

## Priority 0: New Call Drawer - UNSOLVED

Status: unresolved.

The New Call interface still overflows horizontally on mobile Safari. The screenshot from 2026-06-06 at 3:15 AM shows the bottom panel extending past the right edge: the customer phone input and Start call button are clipped, and the page can still pan sideways.

What is going wrong:

- New Call still behaves like a separate modal/bottom sheet implementation.
- It is visually close to a drawer, but it is not using the same proven drawer primitive as the working AI/customer details drawer.
- Prior width clamps and viewport math did not solve the underlying issue.
- The working drawer already behaves correctly, so continuing to tune a separate modal is wasted effort.

Required fix:

- Stop tuning New Call modal width.
- Reuse the exact working drawer pattern used by the AI/customer details drawer.
- Ideally extract a shared drawer primitive/component, then render New Call inside it.
- Keep all existing call behavior exactly the same.
- Do not change Twilio call endpoints, call flow, or call payloads while fixing the drawer.

Acceptance criteria:

- Opening New Call does not create horizontal page overflow.
- The app cannot pan left/right after New Call opens.
- Inputs and buttons remain fully visible on mobile Safari.
- Keyboard open/close does not deform the drawer width.
- Drawer width matches the working details drawer behavior.

## Priority 1: Performance Pass / Duplicate DB Calls

Current frontend issue:

- The app appears to make duplicate initial conversation requests.
- Likely causes include initial boot loading, search/debounce firing with an empty query, quick responses loading more often than needed, and detail fetches repeating after selected conversation changes or mutations.

Frontend plan:

- Split initial boot fetch from debounced search fetch.
- Prevent the search effect from firing on first render for an empty query.
- Load quick responses once unless explicitly refreshed.
- Fetch conversation detail only when `selectedId` changes or after an intentional mutation.
- Prefer local state updates after sends/close/reopen when possible instead of full list and detail refetches.

Backend plan:

- Audit `/api/conversations` for N+1 Supabase calls.
- Avoid per-conversation message/contact queries in list endpoints.
- Batch contacts by phone number.
- Batch latest messages by conversation ID, or use a SQL view/RPC for conversation list rows.
- Keep the goal for initial list loading near 2-4 DB queries instead of many per row.

Acceptance criteria:

- Initial page load does not double-fetch `/api/conversations`.
- Conversation list load has predictable low query count.
- Selecting one conversation only fetches the selected conversation detail.

## Priority 2: Display-Only Message Formatter

Add one frontend formatter that cleans relay-only text for dashboard display.

Clean from dashboard display only:

- `Reply with #CODE your message`
- `[#CODE]` routing markers
- internal routing hints
- attachment URL text when an attachment preview already exists

Rules:

- Do not mutate database message bodies.
- Keep raw message body available for debugging and audit.
- Preserve the phone SMS routing flow because Francisco may still reply from the native SMS thread.

Acceptance criteria:

- The dashboard reads like a normal chat.
- The code-based SMS fallback still works from the phone.
- Attachments show as previews/cards rather than long raw URLs when metadata is available.

## Priority 3: Desktop Density Pass

The desktop dashboard currently feels too padded and visually heavy. Make it feel like a real daily-use operator tool without changing behavior.

Target only:

- conversation list rows
- message bubbles
- right-side cards
- conversation header
- composer

Guidelines:

- Reduce padding and vertical whitespace.
- Keep panels readable and scannable.
- Preserve the current three-column architecture.
- Avoid broad layout rewrites.
- Avoid touching mobile styles unless required by shared selectors.

Acceptance criteria:

- More useful information fits above the fold.
- Conversations are visually separated without huge cards.
- Message bubbles feel tighter and more chat-like.

## Priority 4: Attachment Preview Polish

Make attachment previews feel production-ready.

Plan:

- Render image attachments with constrained dimensions.
- Render file attachments as clean file cards.
- Show filename, type, and open/download affordance when available.
- Hide raw attachment URLs from message display when a preview exists.

Acceptance criteria:

- Images do not break layout.
- Files are easy to identify and open.
- Long Supabase storage URLs do not dominate the conversation view.

## Priority 5: Composer Polish

Improve the reply composer without making mobile bulky.

Plan:

- Allow the composer to grow vertically for multi-line replies.
- Cap the height so it does not consume the screen.
- Keep compact icon buttons for attach and send.
- Prevent horizontal deformation when the mobile keyboard opens/closes.

Acceptance criteria:

- Operators can comfortably edit multi-line replies.
- Mobile remains compact.
- The composer does not create horizontal overflow.

## Deferred / Backlog

- Close conversation UX: confirmation and closed filtering.
- Call logging: save attempts/statuses in Supabase and show call history.
- Manual outbound call improvements: create-contact flow, notes, and call outcome.
- CSV contact upload: `phone_number`, `display_name`, preserve manual names.
- Better customer profile: notes, tags, history, active/inactive status.
- WhatsApp templates for business-initiated messages outside the 24-hour window.
- Production auth/users: real accounts, roles, and possibly Supabase Auth.
- Observability: structured logs, failed delivery view, Twilio error explanations.
- AI next phase: richer intent detection, missing-info checklist, safe auto-response.
- Pricing/business packaging: refine monthly support, AI, and infrastructure fee after usage.

## Recommended Next Session Order

1. Replace New Call modal with the same working drawer primitive used by details/AI.
2. Verify New Call on mobile Safari before touching anything else.
3. Fix duplicate frontend fetches.
4. Add display-only message formatting.
5. Run the desktop density pass.
6. Polish attachment previews.
7. Polish the composer.
8. Optimize `/api/conversations` query shape.
