# Maya Relay Dashboard Surgical UX and Performance Plan

Date: 2026-06-08

This document is the working dashboard roadmap for Maya Relay. It captures what has already been completed, what should remain pinned, and what should happen in the next development session. The guiding rule is still surgical progress: protect working SMS, WhatsApp, Twilio, Supabase, and call behavior while improving the operator inbox step by step.

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

## Completed In Recent Sessions

### Mobile Shell And Drawer Fixes

Status: done.

- Fixed New Call mobile drawer overflow.
- Added Playwright regression coverage for the New Call mobile drawer.
- Prevented mobile input focus zoom overflow.
- Constrained mobile login panel width.

Acceptance met:

- New Call no longer spills horizontally on iPhone Safari.
- Numeric keyboard open/close no longer deforms drawer width.
- Login panel no longer creates the same wide-card overflow.

### Frontend Fetch And Search Performance

Status: done.

- Reduced duplicate frontend conversation fetches.
- Batched conversation list metadata queries on the backend.
- Added `/api/conversations` pagination and frontend Load More.
- Added local cache-first conversation search.
- Kept debounced server search for older/unloaded matches.

Acceptance met:

- Initial boot no longer double-hits the conversation list the same way.
- Loaded conversations filter locally first.
- Server search still finds unloaded/older matches.
- Browsing history can page forward with Load More.

### Refresh And Message Ordering

Status: done.

- Added automatic inbox refresh for new messages.
- Added manual Refresh button.
- Moved active conversations to the top when new customer activity arrives.
- Scrolled selected conversation to the newest message.

Acceptance met:

- New messages can appear in the dashboard without manual page reload.
- Conversations with fresh activity move up instead of staying buried by old conversation creation date.
- Opening a conversation scrolls to the latest visible message.

### Needs Reply And Display Cleanup

Status: done.

- Added visual state for conversations that need a reply.
- Kept internal relay/system/AI suggestion messages out of the chat timeline.
- Preserved raw Supabase message data for audit/debugging.

Acceptance met:

- Customer messages can mark conversations as needing reply.
- AI suggestions are not displayed as if Francisco sent them.
- Dashboard display cleanup does not mutate stored message bodies.

### Presentation UX Polish

Status: partially done.

- Desktop density improved.
- Message bubble presentation improved.
- Composer can grow for multi-line replies.
- Header/topbar and button styling softened across multiple small commits.
- Attachment previews are improved enough to avoid raw URL noise in common cases.

Remaining caveat:

- Visual styling is better, but the frontend still does not have a full design-token system. Future styling should use CSS tokens rather than adding more hardcoded colors.

## Still Pending / Pinned

### 1. Contact / Client Search Endpoint

Status: pending.

Why it matters:

- Conversation search can find loaded conversations locally and older/unloaded conversations through server search.
- But the app still does not have a dedicated client/contact search model.
- As the business grows, the operator may need to find a client even when that client is not represented in the current loaded conversation page.

Surgical plan:

- Add a backend endpoint for contact/client search.
- Query contacts by phone number, display name, and lookup name.
- Keep the first version read-only.
- Do not change conversation routing or message sending.
- Add tests for search behavior.

Likely endpoint:

- `GET /api/contacts?query=...&limit=...`

### 2. Scalable Client / Conversation Loading Model

Status: pending.

Why it matters:

- Loading 50 conversations is fine now.
- The app should not eventually load 100 clients times many conversations each.
- Clients and conversations should not be treated as the same loading unit forever.

Recommended model:

- Conversation list remains paginated and activity-ordered.
- Loaded conversations remain locally filterable.
- Server conversation search covers older/unloaded conversation matches.
- Contact/client search is separate from conversation browsing.
- Conversation details load only when selected.
- Future client profile can show recent conversations lazily after choosing a client.

Decision needed later:

- Whether the left column remains conversation-first only, or whether we add a separate client search mode/view.

### 3. Attachment Preview Production Polish

Status: partially done, still worth improving.

Remaining work:

- Make image previews more consistent.
- Make non-image attachment cards feel intentional.
- Show filename/type/open affordance when metadata is available.
- Continue hiding raw attachment URL text when preview metadata exists.

Constraints:

- Do not mutate stored messages.
- Do not change Twilio/Supabase attachment persistence.

### 4. Client-Ready Visual Token Pass

Status: pending, but not urgent before functionality.

Goal:

- Add a small set of reusable CSS tokens for surfaces, borders, muted text, warning/attention states, control radius, panel radius, and common spacing.
- Migrate only the highest-churn hardcoded colors first.
- Avoid a broad React refactor.

Reason:

- The current CSS is workable but still has many one-off hardcoded values.
- Tokenizing gradually will make future visual changes cheaper.

### 5. Close Conversation UX

Status: pending.

Ideas:

- Add confirmation before closing if needed.
- Decide how closed conversations appear in the list.
- Add closed/open filtering only after the operator workflow is clearer.

### 6. Call Logging / Manual Outbound Improvements

Status: pending.

Ideas:

- Save call attempts/statuses in Supabase.
- Show call history in customer profile.
- Add create-contact flow, notes, and call outcome later.

## Next Development Session Plan

Recommended order:

1. Add the contact/client search endpoint.
2. Add backend tests for contact search.
3. Decide the smallest frontend surface for using contact search without disrupting the current conversation list.
4. If time allows, wire contact search into the existing search experience as a clearly separated fallback or result group.
5. Document the scalable client/conversation loading model after implementation decisions are confirmed.

Keep this session functionality-focused. Avoid more visual cleanup unless it blocks usability.

## Backlog

- CSV contact upload: `phone_number`, `display_name`, preserve manual names.
- Better customer profile: notes, tags, history, active/inactive status.
- WhatsApp templates for business-initiated messages outside the 24-hour window.
- Production auth/users: real accounts, roles, and possibly Supabase Auth.
- Observability: structured logs, failed delivery view, Twilio error explanations.
- AI next phase: richer intent detection, missing-info checklist, safe auto-response.
- Pricing/business packaging: refine monthly support, AI, and infrastructure fee after usage.
