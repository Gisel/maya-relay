import html
import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import Settings, get_settings
from app.db import RelayRepository
from app.dependencies import get_repository


router = APIRouter(prefix="/admin", tags=["admin"])
SESSION_COOKIE = "maya_admin"


def _admin_enabled(settings: Settings) -> None:
    if not settings.admin_password:
        raise HTTPException(status_code=404)


def _session_value(settings: Settings) -> str:
    return hmac.new(
        settings.admin_password.encode("utf-8"),
        b"maya-admin-session",
        "sha256",
    ).hexdigest()


def _is_authenticated(request: Request, settings: Settings) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return hmac.compare_digest(cookie, _session_value(settings))


def _require_admin(request: Request, settings: Settings) -> None:
    _admin_enabled(settings)
    if not _is_authenticated(request, settings):
        raise HTTPException(status_code=401)


@router.get("", response_class=HTMLResponse)
def admin_index(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> HTMLResponse:
    _admin_enabled(settings)
    if not _is_authenticated(request, settings):
        return HTMLResponse(_layout("Maya Admin", _login_form()))

    query = (request.query_params.get("q") or "").strip()
    conversations = repository.list_conversations()
    metrics = _conversation_metrics(conversations)
    visible_conversations = _filter_conversations(conversations, query)
    rows = []
    for conversation in visible_conversations:
        last_message = conversation.get("last_message") or {}
        customer = conversation.get("customer_name") or conversation["customer_phone"]
        body = str(last_message.get("body") or "")
        delivery_status = str(last_message.get("delivery_status") or "pending")
        rows.append(
            "<tr>"
            f"<td><a href='/admin/conversations/{_e(conversation['id'])}'>#{_e(conversation['conversation_code'])}</a></td>"
            f"<td>{_e(customer)}<br><span>{_e(conversation['customer_phone'])}</span></td>"
            f"<td>{_badge(conversation['status'])}</td>"
            f"<td>{_e(last_message.get('direction') or '')}</td>"
            f"<td>{_e(body[:140])}</td>"
            f"<td>{_badge(delivery_status)}</td>"
            f"<td>{_format_time(conversation.get('updated_at'))}</td>"
            "</tr>"
        )

    content = (
        "<section class='toolbar'>"
        "<h1>Maya Relay</h1>"
        "<a class='button' href='/admin/logout'>Logout</a>"
        "</section>"
        f"{_metrics_bar(metrics)}"
        f"{_search_bar(query, len(visible_conversations), len(conversations))}"
        "<table>"
        "<thead><tr><th>Code</th><th>Customer</th><th>Status</th><th>Last direction</th>"
        "<th>Last message</th><th>Delivery</th><th>Updated</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=\"7\">No matching conversations.</td></tr>'}</tbody>"
        "</table>"
    )
    return HTMLResponse(_layout("Maya Admin", content))


@router.post("/login")
def admin_login(
    password: str = Form(...),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    _admin_enabled(settings)
    if not hmac.compare_digest(password, settings.admin_password):
        return RedirectResponse("/admin", status_code=303)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(SESSION_COOKIE, _session_value(settings), httponly=True, secure=True, samesite="lax")
    return response


@router.get("/logout")
def admin_logout(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    _admin_enabled(settings)
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
def conversation_detail(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> HTMLResponse:
    _require_admin(request, settings)
    messages = repository.list_messages_for_conversation(conversation_id)
    items = []
    for message in messages:
        media_urls = message.get("media_urls") or []
        media_links = "".join(
            f"<a class='media' href='{_e(url)}' target='_blank' rel='noreferrer'>Attachment {index + 1}</a>"
            for index, url in enumerate(media_urls)
        )
        items.append(
            "<article class='message'>"
            f"<div>{_badge(message['direction'])} <span>{_format_time(message.get('created_at'))}</span></div>"
            f"<pre>{_e(message.get('body') or '')}</pre>"
            f"<p>From {_e(message.get('from_phone') or '')} to {_e(message.get('to_phone') or '')}</p>"
            f"<p>Delivery: {_e(message.get('delivery_status') or 'pending')}"
            f" {_e(message.get('delivery_error_code') or '')} {_e(message.get('delivery_error_message') or '')}</p>"
            f"{media_links}"
            "</article>"
        )
    content = (
        "<section class='toolbar'>"
        "<h1>Conversation</h1>"
        "<a class='button' href='/admin'>Back</a>"
        "</section>"
        f"{''.join(items) or '<p>No messages yet.</p>'}"
    )
    return HTMLResponse(_layout("Conversation", content))


def _login_form() -> str:
    return (
        "<main class='login'>"
        "<h1>Maya Relay</h1>"
        "<form method='post' action='/admin/login'>"
        "<input type='password' name='password' placeholder='Admin password' autofocus>"
        "<button type='submit'>Open dashboard</button>"
        "</form>"
        "</main>"
    )


def _layout(title: str, content: str) -> str:
    return (
        "<!doctype html><html><head>"
        f"<title>{_e(title)}</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<style>{_CSS}</style>"
        "</head><body>"
        f"{content}"
        "</body></html>"
    )


def _badge(value: str) -> str:
    clean = str(value or "unknown").lower().replace("_", "-")
    return f"<span class='badge badge-{_e(clean)}'>{_e(value)}</span>"


def _conversation_metrics(conversations: list[dict]) -> dict[str, int]:
    total = len(conversations)
    open_count = sum(1 for conversation in conversations if conversation.get("status") == "open")
    failed_count = sum(
        1
        for conversation in conversations
        if (conversation.get("last_message") or {}).get("delivery_status") in {"failed", "undelivered"}
    )
    attachments = sum(
        1 for conversation in conversations if ((conversation.get("last_message") or {}).get("num_media") or 0) > 0
    )
    return {"total": total, "open": open_count, "failed": failed_count, "attachments": attachments}


def _metrics_bar(metrics: dict[str, int]) -> str:
    labels = [
        ("Open conversations", metrics["open"]),
        ("Recent conversations", metrics["total"]),
        ("Failed deliveries", metrics["failed"]),
        ("With attachments", metrics["attachments"]),
    ]
    cards = "".join(f"<article class='metric'><strong>{value}</strong><span>{_e(label)}</span></article>" for label, value in labels)
    return f"<section class='metrics'>{cards}</section>"


def _search_bar(query: str, visible_count: int, total_count: int) -> str:
    result_text = f"{visible_count} of {total_count} conversations"
    clear_link = "<a class='clear' href='/admin'>Clear</a>" if query else ""
    return (
        "<form class='search' method='get' action='/admin'>"
        f"<input type='search' name='q' value='{_e(query)}' "
        "placeholder='Search name, phone, code, delivery, or message text'>"
        "<button type='submit'>Search</button>"
        f"<span>{_e(result_text)}</span>{clear_link}"
        "</form>"
    )


def _filter_conversations(conversations: list[dict], query: str) -> list[dict]:
    if not query:
        return conversations
    needle = query.casefold()
    return [conversation for conversation in conversations if needle in _conversation_search_text(conversation)]


def _conversation_search_text(conversation: dict) -> str:
    last_message = conversation.get("last_message") or {}
    parts = [
        conversation.get("conversation_code"),
        conversation.get("customer_phone"),
        conversation.get("customer_name"),
        conversation.get("status"),
        last_message.get("body"),
        last_message.get("direction"),
        last_message.get("delivery_status"),
        last_message.get("delivery_error_code"),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _format_time(value: object) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _e(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return _e(parsed.astimezone(UTC).strftime("%b %-d, %I:%M %p UTC"))


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


_CSS = """
:root{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{margin:0;background:#f6f7f9;color:#16181d}
a{color:#164ea6;text-decoration:none}
.toolbar{display:flex;align-items:center;justify-content:space-between;padding:24px 28px;background:white;border-bottom:1px solid #dde1e7}
h1{font-size:22px;margin:0}
.button,button{background:#16181d;color:white;border:0;border-radius:6px;padding:10px 14px;font-weight:650}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px}
.metric{background:white;border:1px solid #dde1e7;border-radius:8px;padding:16px}
.metric strong{display:block;font-size:28px;line-height:1}
.metric span{display:block;color:#667085;font-size:12px;text-transform:uppercase;margin-top:8px;font-weight:700}
.search{display:grid;grid-template-columns:minmax(220px,1fr) auto auto auto;gap:10px;align-items:center;margin:16px;background:white;border:1px solid #dde1e7;border-radius:8px;padding:12px}
.search input{width:100%}
.search span,.search .clear{font-size:13px;color:#667085}
table{width:calc(100% - 32px);margin:16px;border-collapse:collapse;background:white;border:1px solid #dde1e7}
th,td{padding:12px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top;font-size:14px}
th{font-size:12px;text-transform:uppercase;color:#667085;background:#fbfcfd}
td span,.message p{color:#667085;font-size:12px}
.badge{display:inline-block;background:#eef2f7;color:#2f3643;border-radius:999px;padding:3px 8px;font-size:12px}
.badge-open,.badge-delivered{background:#dcfce7;color:#166534}
.badge-failed,.badge-undelivered{background:#fee2e2;color:#991b1b}
.badge-queued,.badge-pending{background:#fef3c7;color:#92400e}
.badge-system{background:#e0e7ff;color:#3730a3}
.badge-customer-to-employee{background:#dbeafe;color:#1d4ed8}
.badge-employee-to-customer{background:#f3e8ff;color:#6b21a8}
.message{margin:16px;padding:16px;background:white;border:1px solid #dde1e7;border-radius:8px}
pre{white-space:pre-wrap;font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}
.media{display:inline-block;margin-right:8px}
.login{min-height:100vh;display:grid;place-content:center;gap:16px}
.login form{display:flex;gap:8px}
input{padding:10px 12px;border:1px solid #cbd2dc;border-radius:6px;font-size:14px}
@media(max-width:900px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.search{grid-template-columns:1fr}table{display:block;overflow-x:auto}}
"""
