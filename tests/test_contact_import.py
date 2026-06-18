import pytest

from app.services.contact_import import ContactImportValidationError, import_contacts_csv, parse_contact_csv
from tests.fakes import FakeRepository


def test_parse_contact_csv_normalizes_valid_rows_and_reports_row_errors():
    candidates, errors = parse_contact_csv(
        content=(
            "phone_number,display_name\n"
            "(555) 000-0001,Maria Lopez\n"
            ",Missing Phone\n"
            "555-000-0002,\n"
            "not-a-phone,Bad Phone\n"
        ).encode("utf-8")
    )

    assert candidates[0].phone_number == "+15550000001"
    assert candidates[0].display_name == "Maria Lopez"
    assert [(error.row, error.code) for error in errors] == [
        (3, "missing_phone"),
        (4, "missing_display_name"),
        (5, "invalid_phone"),
    ]


def test_parse_contact_csv_rejects_missing_columns():
    with pytest.raises(ContactImportValidationError) as exc:
        parse_contact_csv(content=b"phone,name\n+15550000001,Maria\n")

    assert exc.value.errors[0].code == "missing_columns"


def test_parse_contact_csv_uses_last_duplicate_name_and_reports_duplicates():
    candidates, errors = parse_contact_csv(
        content=(
            "phone_number,display_name\n"
            "+15550000001,First Name\n"
            "(555) 000-0001,Second Name\n"
        ).encode("utf-8")
    )

    assert len(candidates) == 1
    assert candidates[0].display_name == "Second Name"
    assert [(error.row, error.code) for error in errors] == [
        (2, "duplicate_phone"),
        (3, "duplicate_phone"),
    ]


def test_import_contacts_csv_preserves_existing_names_without_overwrite():
    repository = FakeRepository()
    repository.upsert_contact_display_name("+15550000001", "Existing Name")

    result = import_contacts_csv(
        content=(
            "phone_number,display_name\n"
            "+15550000001,CSV Name\n"
            "+15550000002,New Name\n"
        ).encode("utf-8"),
        repository=repository,
        overwrite=False,
    )

    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 1
    assert repository.get_contact("+15550000001").display_name == "Existing Name"
    assert repository.get_contact("+15550000002").display_name == "New Name"


def test_import_contacts_csv_can_overwrite_existing_real_name_when_explicit():
    repository = FakeRepository()
    repository.upsert_contact_display_name("+15550000001", "Existing Name")

    result = import_contacts_csv(
        content=b"phone_number,display_name\n+15550000001,CSV Name\n",
        repository=repository,
        overwrite=True,
    )

    assert result.created == 0
    assert result.updated == 1
    assert result.skipped == 0
    assert repository.get_contact("+15550000001").display_name == "CSV Name"


def test_import_contacts_csv_blank_name_does_not_overwrite():
    repository = FakeRepository()
    repository.upsert_contact_display_name("+15550000001", "Existing Name")

    result = import_contacts_csv(
        content=b"phone_number,display_name\n+15550000001,\n",
        repository=repository,
        overwrite=True,
    )

    assert result.created == 0
    assert result.updated == 0
    assert result.skipped == 0
    assert result.invalid_rows[0].code == "missing_display_name"
    assert repository.get_contact("+15550000001").display_name == "Existing Name"
