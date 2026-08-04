# WhatsApp Window & Conversation Integrity — Assessment and Solution Paths

Date: 2026-08-01 (Saturday)
Status: **Assessment only. No code changes made.** Implementation targeted for Sunday 2026-08-02 while the shop is closed.
Author context: Investigation triggered by client report that customer **Martin Alcocer** was not receiving WhatsApp messages.

> This document captures the full diagnosis, root causes, evidence, impact, and the candidate fix paths (with trade-offs) for each problem. It is a planning artifact. Nothing here has been implemented. All investigation was **read-only** (code reading + SELECT-only SQL).

---

## 1. Executive Summary

The reported "Martin isn't getting WhatsApps" is the visible tip of a **systemic, ~2-month-old WhatsApp regression**, not a one-customer issue.

Three independent defects compound:

1. **Ingestion misrouting (root cause).** Inbound WhatsApp messages are being received on the **SMS webhook** (`/webhooks/twilio/sms`), which does **not** strip the `whatsapp:` address prefix and hard-codes the channel to `sms`. As a result, WhatsApp customers are stored as `channel = "sms"` conversations whose `customer_phone` literally contains `whatsapp:+1...`.

2. **Silent delivery failure (visible symptom).** The normal **composer reply** path does not check the WhatsApp 24-hour service window and never falls back to an approved template. When an operator replies to a WhatsApp customer **more than 24h after their last inbound**, Twilio rejects it with error **`63016`** ("freeform outside allowed window"). The dashboard still shows the message as sent — so the operator believes the customer was reached.

3. **Conversation/contact fragmentation.** The conversation identity key is `(customer_phone exact string, assigned_employee, customer_channel, status='open')`. Any variation in phone format, channel, **or assigned operator** creates a *new* open thread for the same person. This produced duplicate open conversations and duplicate contact rows.

**Blast radius:** 9 corrupted conversations spanning **6 distinct WhatsApp customers**, created between **2026-06-05 and 2026-07-29**. At least one duplicate contact row confirmed (Martin). Every affected customer has the same failure mode for proactive ("your order is ready / come pick it up") messages sent outside the 24h window.

**Nothing customer-facing is safe to change while the shop is open**, so today is assessment; Sunday is implementation.

---

## 2. How We Investigated (read-only)

- Read the send/receive code paths: `app/routes/twilio_sms.py`, `app/services/relay.py`, `app/twilio_client.py`, `app/routes/api.py`, `app/db.py`, `app/config.py`.
- Ran SELECT-only diagnostic queries against production Supabase (see Appendix A). No writes, no schema changes.

---

## 3. Root-Cause Analysis

### 3.1 Ingestion misrouting (the source)

- `app/routes/twilio_sms.py`
  - `inbound_sms` handler sets `channel="sms"` and passes `From` through **without** stripping a `whatsapp:` prefix.
  - `inbound_whatsapp` handler **does** strip the prefix (`_strip_whatsapp_prefix`) and sets `channel="whatsapp"`.
- `app/services/relay.py` (`_handle_customer_message`) passes `message.from_phone` **verbatim** into `get_or_create_customer_conversation` — no normalization at the relay layer.
- `app/db.py` (`get_or_create_customer_conversation`) uses `customer_phone` as an **exact string** match/insert. So an inbound with `from_phone = "whatsapp:+18013827687"` creates/matches a conversation whose `customer_phone` is literally `whatsapp:+18013827687`, `channel = "sms"`.

**Why replies still sometimes worked:** `app/twilio_client.py` `_recipient_for_channel` only adds/normalizes the `whatsapp:` prefix when the channel is `whatsapp`. For these `sms`-labeled threads it passes `to = "whatsapp:+18013827687"` **unchanged**. Twilio sees the `whatsapp:` prefix and routes the message over WhatsApp anyway — so it succeeds **inside** the 24h window and fails with `63016` **outside** it. The app, believing the thread is SMS, never applies the window/template logic that would have prevented the failure.

**Important nuance:** `app/config.py` `normalize_phone_number()` *does* correctly strip a `whatsapp:` prefix (it extracts digits). The corruption exists because the **inbound relay/webhook path never calls it** — not because normalization is broken.

**Likely external trigger:** a Twilio configuration state in which WhatsApp inbound is delivered to the SMS webhook URL (e.g., the WhatsApp sender living inside a Messaging Service whose inbound request URL points at `/webhooks/twilio/sms`). Earliest corrupted row is **2026-06-05**, so this has been in effect for roughly two months. **To confirm on Sunday:** inspect the Messaging Service / WhatsApp sender inbound webhook configuration in the Twilio Console.

### 3.2 Silent 24-hour-window failure (the symptom operators saw)

- WhatsApp enforces a **24-hour customer care window**: free-form messages are allowed only within 24h of the customer's last inbound message. Outside it, **only pre-approved templates** may be sent. This is Meta policy; code cannot bypass it.
- `app/routes/api.py`:
  - The **Quick Responses** send path resolves the effective channel via `_effective_customer_channel(...)` and checks `_has_active_whatsapp_window(...)`, switching to an approved Content template when the window is closed. **Correct.**
  - The **composer reply** path (`POST /api/conversations/{id}/reply`) sends with `conversation.customer_channel` **raw**, with **no window check and no template fallback**. **This is the gap.**
- Consequence: proactive outreach after the window closes is accepted by Twilio (returns a SID → looks "sent"), then flips to `undelivered` with `delivery_error_code = 63016`. No operator-facing signal.

### 3.3 Conversation & contact fragmentation (the multiplier)

- Identity key in `get_or_create_customer_conversation` = `(customer_phone, assigned_employee, customer_channel, status='open')`.
- Splits a single person into multiple open threads when **any** of these vary:
  - **Phone format** (`whatsapp:+1801…` vs `+1801…`) — the prefix bug.
  - **Channel** (`sms` vs `whatsapp`) — by design today.
  - **`assigned_employee`** — changes with operator routing / `FRANCISCO_PHONE` changes. **Confirmed** by data: three numbers have two open `sms`-prefixed threads each, which is only possible if `assigned_employee` differed.
- `get_or_create_contact` similarly keys on the raw phone string, so the prefix produced **duplicate contact rows** (confirmed for Martin: `whatsapp:+18013827687` and `+18013827687`).

---

## 4. Evidence

### 4.1 Martin Alcocer — end-to-end confirmation

- All recent inbound in his active thread `2ba9fb7f` have `from_phone = whatsapp:+18013827687` (prefix preserved → arrived on the SMS webhook). Conversation is `channel = sms`, `customer_phone = whatsapp:+18013827687`.
- Delivery outcomes align perfectly with the 24h window:

| Sent (UTC) | Result | Prior inbound | Gap | Interpretation |
|---|---|---|---|---|
| Jul 20 18:43 | undelivered `63016` | Jul 16 20:46 | ~4d | window closed |
| Jul 20 20:50 | (sent) `63016` | Jul 16 | ~4d | window closed |
| Jul 20 21:13 | undelivered `63016` | Jul 16 | ~4d | window closed |
| Jul 24 22:01 | undelivered `63016` | Jul 22 16:26 | ~2d | window closed |
| Jul 27 21:16 | read | Jul 27 21:06 | 10m | window open |
| Jul 29 15:07 | read | Jul 29 15:03 | 4m | window open |

- The "proper" WhatsApp thread `597f8c40` (clean phone, `channel=whatsapp`) went silent after **Jul 3**; all traffic since flows through the corrupted `sms` thread.
- Martin's last inbound is **Jul 29 15:03**, so as of this writing his window is **closed** — any free-form WhatsApp to him now would fail `63016`.

### 4.2 Shop-wide corruption inventory (9 threads, 6 customers)

| Number | Corrupted thread(s) | Name | Notes |
|---|---|---|---|
| `+18013827687` | `2ba9fb7f` | Martin Alcocer | + clean `sms` `9b28087e` + clean `whatsapp` `597f8c40` → 4 threads total; duplicate contact row |
| `+18012009467` | `27e6b6d2` (Jul 18), `47dec472` (Jun 18) | — | 2 open (assigned_employee split) |
| `+14358508575` | `e538f6bc` (Jun 20), `f789f598` (Jun 19) | — | 2 open |
| `+5218443261219` | `26732e08`, `80bf5462` (Jun 19) | — | 2 open, Mexico |
| `+18018979721` | `b79bd6f4` (Jul 6) | — | 1 |
| `+8618237151778` | `9b79d8bc` (Jul 3) | — | 1, China |

All 9 have `customer_channel = sms` with a `whatsapp:`-prefixed `customer_phone`. There are **zero** prefixed rows with `channel = whatsapp` (the real WhatsApp handler strips the prefix), which is itself proof the corruption comes exclusively from the SMS-path ingestion.

> Outstanding metric (optional, non-blocking): Appendix A query **G** quantifies total `63016`/undelivered messages and affected customers shop-wide — useful for the client conversation.

---

## 5. Impact Assessment

- **Customer experience:** proactive "your order is ready / come pick it up / your quote" messages — the shop's most important outbound WhatsApp — silently fail whenever the customer hasn't written in the last 24h. Customers appear ignored.
- **Operator trust:** the dashboard reports these as sent. Operators cannot tell a message was lost.
- **Data integrity:** conversation history for affected customers is split across 2–4 threads; contacts are duplicated; customer profile / search / future CSV & Lookup work will misbehave for these records.
- **Deliverability risk:** repeated out-of-window free-form attempts can degrade the WhatsApp sender quality rating with Meta.
- **Scope:** at least 6 WhatsApp customers today; the ingestion defect affects **all** future WhatsApp customers until fixed.

---

## 6. Problem → Solution Paths (for joint analysis)

For each problem, candidate approaches with trade-offs and a recommendation. **Decisions to be made together before Sunday are flagged.**

### Problem A — WhatsApp inbound misrouted & misclassified

- **A1. Twilio config only** — repoint WhatsApp inbound to `/webhooks/twilio/whatsapp`.
  - Pros: no deploy; stops new corruption immediately.
  - Cons: relies on config staying correct; the exact misconfiguration that caused this could recur; doesn't help if a Messaging Service must post all channels to one URL.
- **A2. Code-only defensive detection** — make ingestion self-correcting: if `From` starts with `whatsapp:`, strip it and force `channel="whatsapp"`, regardless of which webhook received it; always run `normalize_phone_number()`. Add the same backstop in the relay layer before `get_or_create`.
  - Pros: robust to any Twilio routing; single source of truth for channel/phone parsing.
  - Cons: requires deploy + tests.
- **A3. Both (recommended).** Fix the Twilio config *and* add the code defense. Defense-in-depth: config gives instant relief, code guarantees it can never recur.

**Decision A:** Confirm we do A3, and identify the exact Twilio Console setting to change (Messaging Service inbound URL vs. WhatsApp sender webhook).

### Problem B — Silent 63016 on closed-window composer sends

- **B1. Hard block + guide (recommended for Sunday).** In the composer reply endpoint, resolve the true channel via `_effective_customer_channel` and, if WhatsApp + window closed, refuse the send with a clear structured error and steer the operator to an approved template (Pickup Reminder, Payment Reminder, etc.).
  - Pros: honest, minimal, mirrors existing Quick Response logic; ends the silent-failure class entirely.
  - Cons: operators can no longer free-text a closed window (this is *correct* per Meta, but is a behavior change to communicate).
- **B2. Auto-open the matching template** — when the operator tries to free-text a closed window, pop the closest template modal with variables pre-filled.
  - Pros: smoothest operator experience.
  - Cons: more frontend work; needs mapping from intent → template.
- **B3. AI-drafted template** — offer an AI-suggested template selection/body for the closed-window case.
  - Pros: flexible.
  - Cons: most work; template bodies are fixed/approved anyway, limiting AI value.

- **B4. Closed-window composer auto-sends via the existing `maya_owner_message` template (recommended — best of both worlds).**
  - We already have an approved WhatsApp template that carries an operator's free text: Quick Response **"Custom WhatsApp message"** (`id: maya_owner_message`, `api.py:352-367`), body `"Maya Graphics:\n{message}"` with a free-text `message` variable, sent via `WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID`. It works **outside** the 24h window because it's a template.
  - Path: when the composer detects WhatsApp + window closed, instead of blocking, wrap Francisco's typed text into `maya_owner_message` and send it as a template. Francisco keeps typing freely; the system chooses free-form vs. owner-message template based on window state — mirroring what Quick Responses already do.
  - Pros: no new template to build; operator types naturally; no silent failure; reuses proven infrastructure.
  - Cons / caveats to verify Sunday:
    1. `WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID` must be set in Railway and the template Meta-approved (else this path 503s — fall back to B1 block+guide until configured).
    2. WhatsApp template variables **cannot contain line breaks, tabs, or long runs of spaces** — Francisco's message must be a single paragraph; validate/normalize before send.
    3. The `Maya Graphics:` prefix is fixed and always shown; **media cannot ride along** in this template (a photo outside the window needs a separate media-header template).

**Recommendation:** ship **B4** as the primary closed-window behavior, with **B1 (block + guide)** as the automatic fallback whenever the owner-message SID is missing/unapproved or the text can't be template-safely sent (e.g. it has attachments). B2 (auto-open a specific canned template like Pickup Reminder) remains a nice fast-follow for structured reminders. **Decision B:** confirm B4-primary + B1-fallback for Sunday; B2 in-scope or later?

Companion (strongly recommended, display-only): **make `undelivered` / `63016` visible** on the message bubble so a failed send can never look delivered again. Data already exists in `messages.delivery_error_code`.

### Problem C — Conversation & contact identity (fragmentation)

- **C1. Normalize + dedup within channel, drop `assigned_employee` from the key (recommended core).**
  - Force clean E.164 everywhere; match/insert on `(normalized_phone, channel, status='open')` only.
  - Pros: eliminates format splits and operator-routing splits; keeps reply-routing trivially correct (one channel per thread); smallest safe change.
  - Cons: SMS and WhatsApp for the same person remain separate threads (usually fine; and per the data, these customers are WhatsApp-only — their `sms` threads are corruption artifacts).
- **C2. One thread per phone across channels (matches the literal "single thread" goal; larger).**
  - Identity = normalized phone only; store channel per message; reply on the last-inbound channel (or operator-selected).
  - Pros: true single-client view.
  - Cons: real complexity — reply transport selection, mixed-window logic, UI changes; higher risk; should be its own tested slice, not a Sunday change.
- **Enforcement (either):** a **partial unique index** (`status='open'`) makes duplicates impossible at the DB level; pair with upsert-on-conflict to close the create race. **Must run cleanup (Problem D) first**, or the index creation fails on existing duplicates.

**Companion decision — keep the forward target current (required if we drop `assigned_employee` from the key).** Today the relay forwards each inbound customer message to `conversation.assigned_employee`, the phone stored *on the thread* (`relay.py`). If we stop keying on it, a returning customer stays glued to whatever employee was stored when the thread was first created — so if routing / `FRANCISCO_PHONE` later changes, new inbound could forward to a **stale** phone. Pair the change with one of:
- **(a) Refresh on inbound (recommended):** update `conversation.assigned_employee` to the current routing each time a customer message arrives. Simple, keeps history on one thread, always forwards to the live number.
- **(b) Resolve at send time:** ignore the stored value and compute the forward target from current settings when forwarding. Also fine, but leaves the stored field potentially misleading.

**Recommendation:** C1 for Sunday, with companion **(a) refresh-on-inbound**; consider C2 later only if a fused SMS+WhatsApp thread is genuinely wanted. **Decision C:** C1 vs. C2, the exact dedup key (`(phone, channel)` vs `(phone)`), and confirm companion (a).

### Problem D — Clean up existing corrupted data

Per-number strategy (some numbers have a clean twin, some are duplicated):

- **D1. Fix-in-place** (for a single corrupted thread with no twin): `UPDATE` the row to clean phone + `channel='whatsapp'`.
  - Pros: simplest; preserves the thread and its history.
  - Cons: only valid when it won't collide with an existing clean/duplicate thread for the same key.
- **D2. Merge into canonical** (for numbers with duplicates or a clean twin, e.g. Martin, `+18012009467`, `+14358508575`, `+5218443261219`): pick one canonical thread, repoint child rows (`messages`, `customer_action_requests/files/events`, `message_attachments`) to it, then close/delete the emptied duplicates. Merge/delete the duplicate **contact** rows too.
  - Pros: preserves full history under one thread; required where duplicates exist.
  - Cons: multi-table migration; **highest risk** step.
- **D3. Close-and-let-reform** (conservative): close the corrupted threads; after Problem A is fixed, the next inbound creates a clean thread naturally.
  - Pros: no destructive edits to historical rows.
  - Cons: loses visible continuity; past history sits in closed threads.

**Recommendation:** hybrid — D1 where safe, D2 where duplicates/twins exist. **Mandatory:** full backup + a dry-run that prints intended row moves and post-merge counts before executing. **Decision D:** confirm hybrid, canonical-thread selection rule (prefer the thread with the most recent activity / most messages), and whether to backfill historical `messages.from_phone` (cosmetic).

### Problem E — Prevent recurrence (guardrails)

- **E1. DB CHECK constraints:** `conversations.customer_phone` and `contacts.phone_number` must match `^\+[0-9]+$` (rejects any `whatsapp:` prefix or garbage at write time).
- **E2. Partial unique index** on the chosen open-thread key (after cleanup).
- **E3. Monitoring:** a lightweight recurring check/alert for any new `customer_phone LIKE 'whatsapp:%'` or new `63016`, so regressions surface immediately.

**Decision E:** confirm constraints + index, and whether to add the monitoring query to the observability surface.

---

## 7. Proposed Sequence (Sunday, shop closed)

| Phase | Change | Type | Risk | Reversible |
|---|---|---|---|---|
| 0 | Backup DB; capture pre-state counts | ops | none | — |
| 1 | Fix Twilio inbound routing (A1) + code defense (A2) | config + code | low | yes |
| 2 | Composer window-guard (B1) + surface failures | code | low–med | yes |
| 3 | Normalize + dedup identity (C1) | code | low–med | yes |
| 4 | CHECK constraints + partial unique index (E1/E2) | schema | med | mostly |
| 5 | Data cleanup/merge of 9 threads + contacts (D1/D2) | data migration | **high** | with backup |
| 6 | Live validation (test WhatsApp in/out, in & out of window) | manual | — | — |
| 7 | (optional/later) C2 one-thread-per-phone; B2 auto-template; E3 monitoring | code | med | yes |

Ordering note: constraints/index (Phase 4) can be created **before or after** cleanup, but the unique index will **reject** until duplicates are gone — so run the unique index step *after* Phase 5, or add it disabled/validated afterward.

### Validation checklist (Phase 6)
- Send a live inbound WhatsApp from a test phone → lands in exactly **one** `channel='whatsapp'`, clean-E.164 thread; no duplicate contact.
- Reply inside the window → delivered.
- Reply (free-text) outside the window → **blocked with guidance**, not silently sent.
- Send the Pickup Reminder template outside the window → delivered.
- Confirm existing SMS relay, `#code` replies, calls, Proof/Assets, Quick Responses unaffected.
- `.venv/bin/python -m pytest`, `npm run build`, Playwright green.

### Rollback posture
- Phases 1–3 are code — revert commit + redeploy.
- Phase 4 schema — constraints/index are droppable.
- Phase 5 data — restore from the Phase 0 backup; keep the dry-run output as the authoritative change record.

---

## 8. Open Decisions (to settle before coding)

1. **A:** Which exact Twilio setting routes WhatsApp inbound to `/sms`? Do A3 (config + code).
2. **B:** Confirm B4 (closed-window composer auto-sends via `maya_owner_message`) as primary + B1 (block+guide) fallback. B2 Sunday or later? Include the failure-visibility UI? First verify the owner-message SID is set in Railway and Meta-approved.
3. **C:** C1 (per-channel, drop `assigned_employee`) vs. C2 (one-thread-per-phone)? Exact dedup key? Confirm companion **(a) refresh `assigned_employee` on inbound** so forwards never go to a stale phone.
4. **D:** Confirm hybrid cleanup + canonical-selection rule; backfill `from_phone`? Investigate whether `+18016943079` is really Martin's 2nd number or a mis-save.
5. **E:** Constraints + unique index scope; add monitoring to observability?
6. **Scope for Sunday:** minimum viable = Phases 0–3 + 5 (stops loss + cleans data). Phase 4 index and Phase 7 items can follow.

---

## Appendix A — Diagnostic queries used (read-only)

```sql
-- A) Martin's conversations + channel
select c.id, c.customer_phone, c.customer_channel, c.status, c.created_at, c.updated_at,
       ct.display_name, ct.lookup_name
from conversations c
left join contacts ct on ct.phone_number = c.customer_phone
where ct.display_name ilike '%alcocer%' or ct.lookup_name ilike '%alcocer%'
order by c.updated_at desc;

-- B) Recent messages + delivery status for Martin
select m.created_at, m.direction, m.delivery_status, m.delivery_error_code,
       m.delivery_error_message, left(m.body,60) as body_preview
from messages m
join conversations c on c.id = m.conversation_id
left join contacts ct on ct.phone_number = c.customer_phone
where ct.display_name ilike '%alcocer%' or ct.lookup_name ilike '%alcocer%'
order by m.created_at desc limit 25;

-- C) Last inbound (window state)
select max(m.created_at) as last_inbound
from messages m join conversations c on c.id = m.conversation_id
left join contacts ct on ct.phone_number = c.customer_phone
where (ct.display_name ilike '%alcocer%' or ct.lookup_name ilike '%alcocer%')
  and m.direction = 'customer_to_employee';

-- D) Confirm prefix preserved + channel per message
select m.conversation_id, c.customer_channel, c.customer_phone, m.direction,
       m.from_phone, m.delivery_error_code, m.created_at
from messages m join conversations c on c.id = m.conversation_id
where c.id in ('2ba9fb7f-dac4-4874-bb61-fe0075a5df06','597f8c40-a6d8-48e2-9514-e0a6457bcdda')
order by m.created_at desc limit 20;

-- E) Blast radius
select customer_channel, count(*) as threads, min(created_at) as earliest, max(updated_at) as latest
from conversations where customer_phone like 'whatsapp:%' group by customer_channel;

-- F) Duplicate contact rows
select id, phone_number, display_name, lookup_name
from contacts where phone_number ilike '%18013827687%';

-- G) Shop-wide silent-failure impact (OUTSTANDING — run for the client metric)
select delivery_error_code, count(*) as messages, count(distinct conversation_id) as conversations,
       min(created_at) as first_seen, max(created_at) as last_seen
from messages where delivery_error_code is not null
group by delivery_error_code order by messages desc;

-- H) The corrupted threads, named
select c.id, c.customer_phone, c.customer_channel, c.status, ct.display_name, c.updated_at
from conversations c left join contacts ct on ct.phone_number = c.customer_phone
where c.customer_phone like 'whatsapp:%' order by c.updated_at desc;
```

## Appendix B — Key code references

- `app/routes/twilio_sms.py` — `inbound_sms` (channel hard-coded `sms`, no prefix strip) vs. `inbound_whatsapp` (`_strip_whatsapp_prefix`, channel `whatsapp`); `_strip_whatsapp_prefix`.
- `app/services/relay.py` — `_handle_customer_message` passes `from_phone` verbatim to `get_or_create_customer_conversation`; customer reply send path.
- `app/twilio_client.py` — `_recipient_for_channel` / `_sender_for_channel` only apply the `whatsapp:` prefix when channel is `whatsapp`.
- `app/routes/api.py` — composer reply `POST /conversations/{id}/reply` (raw channel, **no window guard**); Quick Response send (window-aware); `_has_active_whatsapp_window`; `_effective_customer_channel`; new-conversation path normalizes + strips prefix.
- `app/db.py` — `get_or_create_customer_conversation` (identity key incl. `assigned_employee` + exact-string phone); `get_or_create_contact`; `create_message` (bumps `conversations.updated_at`).
- `app/config.py` — `normalize_phone_number` (already strips `whatsapp:` correctly; simply not called on the inbound path).
