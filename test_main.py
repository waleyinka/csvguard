"""
Tests for main.py. Run with:  pytest test_main.py

Each test function is named test_<function> to match the function it checks,
as CS50 requires. Only the pure functions are tested here; main() is checked
by running the program on the sample files.
"""

import json
from datetime import date

import pytest

from main import (
    check_columns,
    clean_row,
    clean_value,
    find_duplicates,
    format_report,
    load_schema,
    parse_date,
    process_rows,
    summarize,
    validate_row,
    validate_value,
)


# A small schema reused by several tests, so they all agree on the rules.
SCHEMA = {
    "columns": {
        "id": {"type": "integer", "required": True, "min": 1},
        "email": {"type": "email", "required": True},
        "status": {"type": "string", "required": False, "allowed": ["active", "inactive"]},
    },
    "key": "id",
}


def write_schema(tmp_path, content):
    """Helper: save a schema dict as JSON in pytest's temporary folder."""
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(content))
    return path


def test_load_schema(tmp_path):
    # A valid schema loads, and "required" defaults to False when missing.
    schema = load_schema(write_schema(tmp_path, {"columns": {"name": {"type": "string"}}}))
    assert schema["columns"]["name"]["required"] is False

    # Each of these broken schemas must raise ValueError.
    bad_schemas = [
        {},                                                        # no columns
        {"columns": {}},                                           # empty columns
        {"columns": {"a": {"type": "number"}}},                    # unknown type
        {"columns": {"a": {"type": "string", "min": 1}}},          # min on string
        {"columns": {"a": {"type": "string", "allowed": "x"}}},    # allowed not a list
        {"columns": {"a": {"type": "string", "pattern": "("}}},    # broken regex
        {"columns": {"a": {"type": "string"}}, "key": "b"},        # key not a column
    ]
    for bad in bad_schemas:
        with pytest.raises(ValueError):
            load_schema(write_schema(tmp_path, bad))


def test_load_schema_invalid_json(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        load_schema(path)


def test_check_columns():
    assert check_columns(["id", "email", "status"], SCHEMA) == []
    assert check_columns(["id"], SCHEMA) == ["email", "status"]
    assert check_columns([], SCHEMA) == ["email", "id", "status"]


def test_parse_date():
    assert parse_date("2024-01-05") == date(2024, 1, 5)
    assert parse_date("2024/01/05") == date(2024, 1, 5)
    assert parse_date("05.01.2024") == date(2024, 1, 5)
    assert parse_date("05/01/2024") == date(2024, 1, 5)  # day first
    assert parse_date("2024-02-30") is None               # impossible date
    assert parse_date("yesterday") is None


def test_validate_value():
    integer = {"type": "integer", "required": True, "min": 1, "max": 120}
    assert validate_value("42", integer) is None
    assert validate_value(" 42 ", integer) is None
    assert validate_value("12a", integer) == "not an integer"
    assert validate_value("", integer) == "required value missing"
    assert validate_value(None, integer) == "required value missing"
    assert validate_value("0", integer) == "below minimum 1"
    assert validate_value("121", integer) == "above maximum 120"

    # Optional empty values are fine.
    assert validate_value("", {"type": "integer", "required": False}) is None

    floats = {"type": "float"}
    assert validate_value("3.5", floats) is None
    assert validate_value("abc", floats) == "not a number"
    assert validate_value("nan", floats) == "not a number"

    assert validate_value("2024-02-30", {"type": "date"}) == "invalid date"
    assert validate_value("ada@example.com", {"type": "email"}) is None
    assert validate_value("ada@example", {"type": "email"}) == "invalid email"

    status = {"type": "string", "allowed": ["active", "inactive"]}
    assert validate_value("active", status) is None
    assert validate_value("paused", status) == "not one of: active, inactive"

    phone = {"type": "string", "pattern": r"\+?[0-9 ]{7,15}"}
    assert validate_value("+372 5555 1234", phone) is None
    assert validate_value("call me", phone) == "does not match pattern"


def test_clean_value():
    assert clean_value(" 007 ", {"type": "integer"}) == "7"
    assert clean_value("3", {"type": "float"}) == "3.0"
    assert clean_value("05.01.2024", {"type": "date"}) == "2024-01-05"
    assert clean_value("Ada@Mail.COM", {"type": "email"}) == "ada@mail.com"
    assert clean_value("  Ada   Lovelace ", {"type": "string"}) == "Ada Lovelace"
    assert clean_value("", {"type": "date"}) == ""


def test_validate_row():
    good = {"id": "1", "email": "a@b.com", "status": "active"}
    assert validate_row(good, SCHEMA) == []

    bad = {"id": "x", "email": "nope", "status": "active"}
    assert validate_row(bad, SCHEMA) == ["id: not an integer", "email: invalid email"]

    # A row with an extra cell (stored by DictReader under the key None).
    extra = {"id": "1", "email": "a@b.com", "status": "", None: ["surprise"]}
    assert validate_row(extra, SCHEMA) == ["row: too many fields"]


def test_clean_row():
    row = {"id": " 01 ", "email": "A@B.COM", "status": "active", "notes": " keep me "}
    cleaned = clean_row(row, SCHEMA)
    assert cleaned == {"id": "1", "email": "a@b.com", "status": "active", "notes": " keep me "}
    assert row["id"] == " 01 "  # the original row is not modified


def test_find_duplicates():
    rows = [{"id": "1"}, {"id": "2"}, {"id": "1"}, {"id": " 2 "}, {"id": ""}, {"id": ""}]
    assert find_duplicates(rows, "id") == {2, 3}
    assert find_duplicates([{"id": "1"}, {"id": "2"}], "id") == set()
    assert find_duplicates(rows, None) == set()


def test_process_rows():
    rows = [
        {"id": "1", "email": "ADA@example.com", "status": "active"},
        {"id": "2", "email": "bad-email", "status": "active"},
        {"id": "1", "email": "copy@example.com", "status": "inactive"},
    ]
    clean, rejected = process_rows(rows, SCHEMA)

    assert clean == [{"id": "1", "email": "ada@example.com", "status": "active"}]
    assert [row["errors"] for row in rejected] == [
        "email: invalid email",
        "id: duplicate value",
    ]


def test_summarize():
    rejected = [
        {"errors": "email: invalid email; id: not an integer"},
        {"errors": "email: required value missing"},
    ]
    report = summarize(10, 8, rejected)
    assert report["total"] == 10
    assert report["clean"] == 8
    assert report["rejected"] == 2
    assert report["valid_pct"] == 80.0
    assert report["issues_by_column"] == {"email": 2, "id": 1}

    # A CSV with a header but no data rows must not crash.
    assert summarize(0, 0, [])["valid_pct"] == 0.0


def test_format_report():
    report = summarize(2, 1, [{"errors": "email: invalid email"}])
    text = format_report(report)
    assert "Total rows" in text
    assert "50.0%" in text
    assert "email" in text

    assert "No issues found." in format_report(summarize(1, 1, []))