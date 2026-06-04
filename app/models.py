from dataclasses import dataclass
from typing import Literal


Direction = Literal["customer_to_employee", "employee_to_customer", "system"]


@dataclass(frozen=True)
class Conversation:
    id: str
    customer_phone: str
    assigned_employee: str
    status: str


@dataclass(frozen=True)
class IncomingMessage:
    message_sid: str
    from_phone: str
    to_phone: str
    body: str
    num_media: int = 0
    media_urls: tuple[str, ...] = ()
    media_content_types: tuple[str, ...] = ()
