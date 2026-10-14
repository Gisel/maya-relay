# MMS Delivery Failures & Mobile Composer Fixes

Date: 2026-10-14
Status: **✅ COMPLETE — all fixes implemented, deployed, and verified (MMS delivery + mobile composer) or pending final on-device confirmation (badge clipping).**
Author context: Investigation triggered by client report ("tengo estos textos que dicen los clientes que no les llega") that shirt-proof photos sent to Oliva Landscaping (Luis) and another customer (+18013010076) never arrived.

## Completion summary

- **MMS delivery root cause found and fixed.** Pulled the real Twilio error codes from Supabase for the failed messages: `12300` (Invalid Content-Type — raw iPhone `.HEIC` photos), `30019`/`11751` (carrier size limit exceeded, even after JPEG conversion). AT&T's real MMS cap is ~0.6–1.0MB; the app only enforced a 50MB sanity limit with no format/size handling.
- **Fix:** employee replies now auto-convert HEIC → JPEG and auto-compress oversized images to a carrier-safe size (~500KB target, 1600px max dimension) before sending to Twilio, while keeping the full-resolution original as a link in the message text. New `app/image_processing.py`; wired into `app/routes/admin.py` and `app/routes/api.py` via `app/reply_helpers.py`.
- **"New message" (starting a brand-new conversation) gained photo-attach support** on both mobile and desktop — previously text-only. The photo sends as an automatic follow-up message right after the typed first message, reusing the same HEIC/compression-safe reply endpoint.
- **Short links added.** The "full quality" link text was a raw ~140-char Supabase storage URL that wrapped across multiple lines and (it turned out) contributed to white-bar padding around the photo. Replaced with a short `mayagraphics.co/i/<token>` redirect (new standalone `short_links` table — no coupling to the existing proof-approval system) worded "See original photo:".
- **Short-link domain bug fixed.** First deploy produced a relative `/i/<token>` link with no domain — `settings.app_base_url` is unset in production. The existing proof-request flow avoids this via a request-derived fallback (`_public_base_url` in `api.py`); extracted that into a shared `app/public_base_url.py` and pointed the short-link code at it too.
- **White-bar letterboxing root-caused and fixed.** SMS/MMS clients size a message bubble to its widest text line, then center a narrower photo inside it — so any caption/link text sent in the same MMS as an image padded the photo with white space. Replies with both text and an image now send as two separate messages (text first, then a bare image) via a new `send_reply_messages()` helper in `app/reply_helpers.py`.
- **Mobile keyboard covering the composer — four iterations to the real fix:**
  1. `interactive-widget=resizes-content` viewport meta tag — insufficient alone.
  2. Switched `.app-shell`/`.workspace` from `100svh` to `100dvh` — still insufficient.
  3. Added `useVisualViewportHeight()` (tracks `window.visualViewport` directly via a `--app-height` CSS var) plus a `scrollIntoView` nudge on attach — improved but didn't fully fix it.
  4. **Real root cause** (found via side-by-side screenshots from the client): attaching a photo added a second row (filename chip) below the paperclip/field/send row, growing the composer's height while the keyboard was already open — no viewport-tracking fix can compensate for a box that changes size out from under a fixed keyboard. Fixed by not growing the composer at all: attached files now show as a small count badge on the attach button on mobile instead of a filename row. Desktop keeps the original filename-chip behavior (no keyboard to fight with there).
- **Badge clipping tweak.** The new attach-badge's top edge was clipped by the composer's `overflow: hidden`; nudged its `top` offset from `-4px` to `0`.

## Shipped commits (chronological)

1. `Fix MMS delivery failures from HEIC photos and oversized images` — `app/image_processing.py`, `app/reply_helpers.py`, `app/routes/admin.py`, `app/routes/api.py`.
2. `Add photo attachment to New message, short redirect links, clearer link text` — `app/short_links.py`, `app/routes/short_links.py`, `frontend/src/messaging/NewMessageDrawer.tsx`.
3. `Fix short link missing domain` — new `app/public_base_url.py` (extracted from `api.py`).
4. `Split caption+photo replies into two texts to stop white-bar letterboxing` — `send_reply_messages()` in `app/reply_helpers.py`; `ReplyResponse.additionalMessages` added to the API contract.
5. `Fix mobile keyboard covering the reply composer` (viewport meta) → `Use dvh instead of svh` → `Track real visible viewport via VisualViewport API` → `Show attached files as a badge on mobile instead of a growing row` → `Nudge attach badge down so its top edge isn't clipped`.

## New database table

```sql
create table if not exists public.short_links (
  token text primary key,
  target_url text not null,
  created_at timestamptz not null default now()
);
```

(Already applied by the user via the Supabase SQL editor; also recorded in `supabase_schema.sql`.)

## Follow-up / pending

- **Luis (Oliva Landscaping) and +18013010076 are still waiting on the photos that originally failed to deliver** (Oct 12). Those messages sit as `delivery_status = 'failed'` in Supabase with no automatic retry. Next step: resend them now that the pipeline is fixed.
- Recurring garbled-text reports during this session ("This is a tes**t**", "New i**m**age", "A new o**n**e") were traced to the user dictating via iOS voice-to-text (confirmed by a visible "🎤 EN" dictation indicator in one screenshot), not an app bug — no code changes made for this.
- `MMS_TARGET_BYTES` (500,000) / `MMS_MAX_DIMENSION_PX` (1600) are env-configurable in Railway if compressed image quality ever needs tuning.
- Final on-device confirmation of the attach-badge clipping fix (commit 5 above) was pending at the time of writing.
