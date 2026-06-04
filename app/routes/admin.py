import html
import hmac

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

    conversations = repository.list_conversations()
    rows = []
    for conversation in conversations:
        last_message = conversation.get("last_message") or {}
        customer = conversation.get("customer_name") or conversation["customer_phone"]
        body = str(last_message.get("body") or "")
        rows.append(
            "<tr>"
            f"<td><a href='/admin/conversations/{_e(conversation['id'])}'>#{_e(conversation['conversation_code'])}</a></td>"
            f"<td>{_e(customer)}<br><span>{_e(conversation['customer_phone'])}</span></td>"
            f"<td>{_badge(conversation['status'])}</td>"
            f"<td>{_e(last_message.get('direction') or '')}</td>"
            f"<td>{_e(body[:140])}</td>"
            f"<td>{_e(last_message.get('delivery_status') or '')}</td>"
            f"<td>{_e(conversation.get('updated_at') or '')}</td>"
            "</tr>"
        )

    content = (
        "<section class='toolbar'>"
        "<h1>Maya Relay</h1>"
        "<a class='button' href='/readiness'>Readiness</a>"
        "</section>"
        "<table>"
        "<thead><tr><th>Code</th><th>Customer</th><th>Status</th><th>Last direction</th>"
        "<th>Last message</th><th>Delivery</th><th>Updated</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=\"7\">No conversations yet.</td></tr>'}</tbody>"
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
            f"<div>{_badge(message['direction'])} <span>{_e(message.get('created_at') or '')}</span></div>"
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
    return f"<span class='badge'>{_e(value)}</span>"


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


_CSS = """
:root{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{margin:0;background:#f6f7f9;color:#16181d}
a{color:#164ea6;text-decoration:none}
.toolbar{display:flex;align-items:center;justify-content:space-between;padding:24px 28px;background:white;border-bottom:1px solid #dde1e7}
h1{font-size:22px;margin:0}
.button,button{background:#16181d;color:white;border:0;border-radius:6px;padding:10px 14px;font-weight:650}
table{width:calc(100% - 32px);margin:16px;border-collapse:collapse;background:white;border:1px solid #dde1e7}
th,td{padding:12px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top;font-size:14px}
th{font-size:12px;text-transform:uppercase;color:#667085;background:#fbfcfd}
td span,.message p{color:#667085;font-size:12px}
.badge{display:inline-block;background:#eef2f7;color:#2f3643;border-radius:999px;padding:3px 8px;font-size:12px}
.message{margin:16px;padding:16px;background:white;border:1px solid #dde1e7;border-radius:8px}
pre{white-space:pre-wrap;font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}
.media{display:inline-block;margin-right:8px}
.login{min-height:100vh;display:grid;place-content:center;gap:16px}
.login form{display:flex;gap:8px}
input{padding:10px 12px;border:1px solid #cbd2dc;border-radius:6px;font-size:14px}
"""
