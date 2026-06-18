import csv
import io
import re
from dataclasses import dataclass
from typing import Literal

from app.config import normalize_phone_number
from app.db import RelayRepository


ImportErrorCode = Literal[
    "missing_columns",
    "missing_phone",
    "missing_display_name",
    "invalid_phone",
    "duplicate_phone",
    "decode_error",
    "too_many_rows",
]


@dataclass(frozen=True)
class ContactImportError:
    row: int
    code: ImportErrorCode
    message: str


@dataclass(frozen=True)
class ContactImportCandidate:
    row: int
    phone_number: str
    display_name: str


@dataclass(frozen=True)
class ContactImportResult:
    created: int
    updated: int
    skipped: int
    invalid_rows: tuple[ContactImportError, ...]


class ContactImportValidationError(ValueError):
    def __init__(self, errors: tuple[ContactImportError, ...]):
        self.errors = errors
        super().__init__("Contact import CSV is invalid.")


def import_contacts_csv(
    *,
    content: bytes,
    repository: RelayRepository,
    overwrite: bool = False,
    max_rows: int = 5000,
) -> ContactImportResult:
    candidates, errors = parse_contact_csv(content=content, max_rows=max_rows)
    created = 0
    updated = 0
    skipped = 0

    for candidate in candidates:
        _, action = repository.import_contact_display_name(
            phone_number=candidate.phone_number,
            display_name=candidate.display_name,
            overwrite=overwrite,
        )
        if action == "created":
            created += 1
        elif action == "updated":
            updated += 1
        else:
            skipped += 1

    return ContactImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        invalid_rows=tuple(errors),
    )


def parse_contact_csv(
    *,
    content: bytes,
    max_rows: int = 5000,
) -> tuple[tuple[ContactImportCandidate, ...], tuple[ContactImportError, ...]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContactImportValidationError(
            (
                ContactImportError(
                    row=0,
                    code="decode_error",
                    message="CSV must be UTF-8 encoded.",
                ),
            )
        )

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = set(reader.fieldnames or [])
    required_columns = {"phone_number", "display_name"}
    if not required_columns.issubset(fieldnames):
        missing = ", ".join(sorted(required_columns - fieldnames))
        raise ContactImportValidationError(
            (
                ContactImportError(
                    row=1,
                    code="missing_columns",
                    message=f"CSV is missing required column(s): {missing}.",
                ),
            )
        )

    errors: list[ContactImportError] = []
    by_phone: dict[str, ContactImportCandidate] = {}
    row_count = 0
    duplicate_rows: set[int] = set()

    for row_number, row in enumerate(reader, start=2):
        row_count += 1
        if row_count > max_rows:
            raise ContactImportValidationError(
                (
                    ContactImportError(
                        row=row_number,
                        code="too_many_rows",
                        message=f"CSV has more than {max_rows} data rows.",
                    ),
                )
            )

        raw_phone = (row.get("phone_number") or "").strip()
        raw_name = (row.get("display_name") or "").strip()
        if not raw_phone:
            errors.append(ContactImportError(row=row_number, code="missing_phone", message="Phone number is required."))
            continue
        if not raw_name:
            errors.append(
                ContactImportError(row=row_number, code="missing_display_name", message="Display name is required.")
            )
            continue

        phone_number = normalize_phone_number(raw_phone)
        if not _is_strict_e164(phone_number):
            errors.append(
                ContactImportError(
                    row=row_number,
                    code="invalid_phone",
                    message="Phone number must normalize to E.164 format, such as +15551234567.",
                )
            )
            continue

        previous = by_phone.get(phone_number)
        if previous is not None:
            duplicate_rows.add(previous.row)
            duplicate_rows.add(row_number)

        by_phone[phone_number] = ContactImportCandidate(
            row=row_number,
            phone_number=phone_number,
            display_name=raw_name,
        )

    for row_number in sorted(duplicate_rows):
        errors.append(
            ContactImportError(
                row=row_number,
                code="duplicate_phone",
                message="Duplicate phone number in CSV; the last nonblank name was used.",
            )
        )

    return tuple(by_phone.values()), tuple(errors)


def _is_strict_e164(phone_number: str) -> bool:
    return bool(re.fullmatch(r"\+[1-9]\d{7,14}", phone_number))
