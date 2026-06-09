from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass
class Response:
    data: list[dict[str, Any]]


class InMemorySupabaseClient:
    def __init__(self):
        self.tables: dict[str, InMemoryTable] = {
            name: InMemoryTable(name)
            for name in ("contacts", "conversations", "messages", "message_attachments", "calls", "call_events")
        }
        self._clock = 0
        self.query_count = 0

    def table(self, name: str) -> "InMemoryQuery":
        if name not in self.tables:
            self.tables[name] = InMemoryTable(name)
        return InMemoryQuery(self, self.tables[name])

    def seed(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        table = self.tables[table_name]
        for row in rows:
            table.rows.append(self._with_defaults(table.name, row))

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        return deepcopy(self.tables[table_name].rows)

    def _insert(self, table: "InMemoryTable", payload: dict[str, Any]) -> dict[str, Any]:
        row = self._with_defaults(table.name, payload)
        self._enforce_uniques(table, row)
        table.rows.append(row)
        return deepcopy(row)

    def _upsert(self, table: "InMemoryTable", payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
        conflict_columns = [column.strip() for column in on_conflict.split(",") if column.strip()]
        if not conflict_columns:
            return self._insert(table, payload)

        for index, row in enumerate(table.rows):
            if all(row.get(column) == payload.get(column) for column in conflict_columns):
                updated = {**row, **payload, "updated_at": self._timestamp()}
                table.rows[index] = updated
                return deepcopy(updated)

        return self._insert(table, payload)

    def _with_defaults(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._timestamp()
        row = deepcopy(payload)
        row.setdefault("id", f"{table_name[:-1]}-{self._next_index(table_name)}")
        row.setdefault("created_at", now)

        if table_name == "contacts":
            row.setdefault("display_name", None)
            row.setdefault("lookup_name", None)
            row.setdefault("lookup_checked_at", None)

        if table_name == "conversations":
            row.setdefault("status", "open")
            row.setdefault("customer_channel", "sms")
            row.setdefault("conversation_code", f"C{self._next_index(table_name):04d}")
            row.setdefault("updated_at", now)

        if table_name == "messages":
            row.setdefault("delivery_status", None)
            row.setdefault("delivery_error_code", None)
            row.setdefault("delivery_error_message", None)
            row.setdefault("media_urls", [])
            row.setdefault("media_content_types", [])
            row.setdefault("client_request_id", None)

        if table_name == "calls":
            row.setdefault("outcome", None)
            row.setdefault("notes", None)
            row.setdefault("follow_up_status", "none")
            row.setdefault("recap", None)
            row.setdefault("transcription", None)
            row.setdefault("recording_sid", None)
            row.setdefault("recording_url", None)
            row.setdefault("recording_status", None)
            row.setdefault("recording_duration_seconds", None)
            row.setdefault("recording_channels", None)
            row.setdefault("started_at", now)
            row.setdefault("answered_at", None)
            row.setdefault("completed_at", None)
            row.setdefault("updated_at", now)

        if table_name == "call_events":
            row.setdefault("payload", {})
            row.setdefault("received_at", now)

        return row

    def _enforce_uniques(self, table: "InMemoryTable", row: dict[str, Any]) -> None:
        for existing in table.rows:
            if table.name == "contacts" and existing.get("phone_number") == row.get("phone_number"):
                raise AssertionError(f"duplicate contacts.phone_number: {row.get('phone_number')}")
            if table.name == "conversations" and existing.get("conversation_code") == row.get("conversation_code"):
                raise AssertionError(f"duplicate conversations.conversation_code: {row.get('conversation_code')}")
            if (
                table.name == "messages"
                and row.get("client_request_id") is not None
                and existing.get("conversation_id") == row.get("conversation_id")
                and existing.get("client_request_id") == row.get("client_request_id")
            ):
                raise AssertionError(f"duplicate messages.client_request_id: {row.get('client_request_id')}")

    def _timestamp(self) -> str:
        self._clock += 1
        return f"2026-06-04T00:00:{self._clock:02d}+00:00"

    def _next_index(self, table_name: str) -> int:
        return len(self.tables[table_name].rows) + 1


class InMemoryTable:
    def __init__(self, name: str):
        self.name = name
        self.rows: list[dict[str, Any]] = []


class InMemoryQuery:
    def __init__(self, client: InMemorySupabaseClient, table: InMemoryTable):
        self.client = client
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.order_by: tuple[str, bool] | None = None
        self.limit_count: int | None = None
        self.range_bounds: tuple[int, int] | None = None
        self.selected_columns: list[str] | None = None
        self.operation: str = "select"
        self.payload: dict[str, Any] | None = None
        self.conflict_columns = ""

    def select(self, columns: str = "*") -> "InMemoryQuery":
        self.selected_columns = None if columns == "*" else [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "InMemoryQuery":
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "InMemoryQuery":
        self.filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> "InMemoryQuery":
        self.filters.append(("gte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> "InMemoryQuery":
        self.order_by = (column, desc)
        return self

    def limit(self, count: int) -> "InMemoryQuery":
        self.limit_count = count
        return self

    def range(self, start: int, end: int) -> "InMemoryQuery":
        self.range_bounds = (start, end)
        return self

    def insert(self, payload: dict[str, Any]) -> "InMemoryQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def upsert(self, payload: dict[str, Any], *, on_conflict: str = "", **_kwargs: Any) -> "InMemoryQuery":
        self.operation = "upsert"
        self.payload = payload
        self.conflict_columns = on_conflict
        return self

    def update(self, payload: dict[str, Any]) -> "InMemoryQuery":
        self.operation = "update"
        self.payload = payload
        return self

    def execute(self) -> Response:
        self.client.query_count += 1
        if self.operation == "insert":
            assert self.payload is not None
            return Response([self.client._insert(self.table, self.payload)])

        if self.operation == "upsert":
            assert self.payload is not None
            return Response([self.client._upsert(self.table, self.payload, self.conflict_columns)])

        if self.operation == "update":
            assert self.payload is not None
            return Response(self._update_rows())

        return Response(self._select_rows())

    def _select_rows(self) -> list[dict[str, Any]]:
        rows = self._matching_rows()
        if self.order_by is not None:
            column, desc = self.order_by
            rows.sort(key=lambda row: row.get(column), reverse=desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        if self.range_bounds is not None:
            start, end = self.range_bounds
            rows = rows[start: end + 1]
        return [self._project(row) for row in rows]

    def _update_rows(self) -> list[dict[str, Any]]:
        updated_rows = []
        for index, row in enumerate(self.table.rows):
            if not self._matches(row):
                continue
            updated = {**row, **self.payload, "updated_at": self.client._timestamp()}
            self.table.rows[index] = updated
            updated_rows.append(self._project(updated))
        return updated_rows

    def _matching_rows(self) -> list[dict[str, Any]]:
        return [deepcopy(row) for row in self.table.rows if self._matches(row)]

    def _matches(self, row: dict[str, Any]) -> bool:
        for operator, column, value in self.filters:
            if operator == "eq" and row.get(column) != value:
                return False
            if operator == "in" and row.get(column) not in value:
                return False
            if operator == "gte" and (row.get(column) is None or str(row.get(column)) < str(value)):
                return False
        return True

    def _project(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None:
            return deepcopy(row)
        return {column: deepcopy(row.get(column)) for column in self.selected_columns}
