"""
csvguard: a command-line data-quality checker for CSV files.
 
Usage:
    python project.py data/customers.csv --schema data/schema.json
 
How the pieces fit together
---------------------------
1.  main() is the conductor. It reads the command-line arguments, then calls
    the other functions in order. It is the only function that prints or
    exits the program.
2.  load_schema() reads the JSON schema (the "rules" for each column) and
    checks that the rules themselves make sense.
3.  read_csv() reads the CSV into a header (list of column names) and a list
    of rows (each row is a dict: {column name: value}).
4.  check_columns() confirms the CSV has every column the schema expects.
5.  process_rows() loops through the rows. For each one:
        - validate_row() asks validate_value() to check every column value.
          validate_value() uses parse_date() for date columns.
        - find_duplicates() has already flagged repeated key values.
        - Rows with no problems are tidied by clean_row(), which calls
          clean_value() for every column.
        - Rows with problems are kept as-is, plus an "errors" column.
6.  write_csv() saves the clean rows and rejected rows to two new files.
7.  summarize() turns the results into numbers, and format_report() turns
    those numbers into a readable table for main() to print.
 
Design rule: apart from main(), read_csv(), write_csv() and load_schema(),
every function takes plain data in and returns plain data out. They never
read files or print anything, which is what makes them easy to test.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from datetime import datetime
 
from tabulate import tabulate

import config


def main():
    """
    Run the whole pipeline: load rules, read data, check it, save results,
    print a summary. Any expected problem (missing file, bad schema) ends the
    program with a friendly message via sys.exit instead of a traceback.
    """
    
    args = parse_args()
    
    
    # Load and check the schema before touching any data.
    try:
        schema = load_schema(args.schema)
    except ValueError as error:
        sys.exit(f"Invalid schema: {error}")
        
        
    # Read the CSV.
    try:
        header, rows = read_csv(args.csv_path)
    except FileNotFoundError:
        sys.exit(f"CSV file not found: {args.csv_path}")

    if not header:
        sys.exit("CSV file is empty.")
        
    missing_columns = check_columns(header, schema)
    if missing_columns:
        sys.exit(f"CSV is missing columns: {', '.join(missing_columns)}")
        
    clean_rows, rejected_rows = process_rows(rows, schema)    
    clean_path, rejected_path = output_path(args.csv_path, args.out_dir)
    
    os.makedirs("output", exist_ok=True)
    
    write_csv(clean_path, header, clean_rows)
    write_csv(rejected_path, header + [config.ERRORS_COLUMN], rejected_rows)
    
    report = summarize(len(rows), len(clean_rows), rejected_rows)
    print(format_report(report))
    print(f"\nClean rows saved to:    {clean_path}")
    print(f"Rejected rows saved to: {rejected_path}")
    

def parse_args():
    """
    Define and read the command-line arguments.
 
    Returns an object whose attributes are the argument values:
    args.csv_path, args.schema and args.out_dir.
    """
    parser = argparse.ArgumentParser(
        description="Validate and clean a CSV file against a JSON schema."
    )
    parser.add_argument("csv_path", help="path to the CSV file to check")
    parser.add_argument("--schema", required=True, help="path to the JSON schema")
    parser.add_argument(
        "--out-dir",
        default="output",
        help="folder for output files (default: same folder as the CSV)",
    )
    return parser.parse_args()


def load_schema(schema_path):
    """
    Read a JSON schema file and check that its rules make sense.
 
    A schema looks like:
        {
          "columns": {
            "id":    {"type": "integer", "required": true, "min": 1},
            "email": {"type": "email"}
          },
          "key": "id"
        }
 
    Returns the schema as a dict, with "required" filled in (default False)
    for every column.
    
    Raises:
        ValueError with a helpful message if anything is wrong, and
        FileNotFoundError if the file does not exist.
    """
    with open(schema_path, "r", encoding="utf-8") as file:
        try:
            schema = json.load(file)
        except json.JSONDecodeError:
            raise ValueError("schema is not valid JSON")
        
    if not isinstance(schema, dict):
        raise ValueError("schema must be a JSON object")
    
    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise ValueError('schema needs a non-empty "columns" object')
    
    for name, rule in columns.items():
        if not isinstance(rule, dict):
            raise ValueError(f'rule for "{name}" must be an object')
 
        column_type = rule.get("type")
        if column_type not in config.VALID_TYPES:
            raise ValueError(f'"{name}" has unknown type "{column_type}"')
 
        rule["required"] = bool(rule.get("required", False))
 
        if ("min" in rule or "max" in rule) and column_type not in config.NUMERIC_TYPES:
            raise ValueError(f'"{name}": min/max only work on integer or float')
 
        if "allowed" in rule and not isinstance(rule["allowed"], list):
            raise ValueError(f'"{name}": "allowed" must be a list')
 
        if "pattern" in rule:
            try:
                re.compile(rule["pattern"])
            except re.error:
                raise ValueError(f'"{name}": pattern is not a valid regex')
            
    key = schema.get("key")
    if key is not None and key not in columns:
        raise ValueError(f'key "{key}" is not one of the columns')
 
    return schema


def read_csv(path):
    """
    Read a CSV file.
 
    Returns (header, rows):
        header: list of column names, e.g. ["id", "name"] ([] if file empty)
        rows:   list of dicts, e.g. [{"id": "1", "name": "Ada"}, ...]
 
    "utf-8-sig" quietly removes the invisible marker Excel sometimes puts at
    the start of a file, so the first column name stays clean.
    """
    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        header = reader.fieldnames or []
    return header, rows
 
 
def write_csv(path, header, rows):
    """Write a list of row dicts to a CSV file, header first."""
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
 
 
def output_path(csv_path, out_dir=None):
    """
    Work out where to save results.
 
    "data/customers.csv" -> ("data/customers_clean.csv",
                             "data/customers_rejected.csv")
    If out_dir is given, the files go there instead.
    """
    folder = out_dir if out_dir else os.path.dirname(csv_path)
    base = os.path.splitext(os.path.basename(csv_path))[0]  # "customers"
    clean = os.path.join(folder, f"{base}_clean.csv")
    rejected = os.path.join(folder, f"{base}_rejected.csv")
    return clean, rejected
 
 
# ---------------------------------------------------------------------------
# Core logic:
# ---------------------------------------------------------------------------
 
def check_columns(header, schema):
    """
    Return a sorted list of schema columns that are missing from the CSV header.
    An empty list means everything we need is there.
    """
    return sorted(column for column in schema["columns"] if column not in header)
 
 
def parse_date(value):
    """
    Try each format in DATE_FORMATS and return a datetime.date if one fits,
    otherwise None. Returning None (instead of raising) lets validate_value
    and clean_value use a simple "if" check.
    """
    for date_format in config.DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue  # this format didn't fit, try the next one
    return None
 
 
def validate_value(value, rule):
    """
    Check one value against one column rule.
 
    Returns None if the value is fine, or a short error message if not.
    Only the FIRST problem is reported, to keep messages readable.
 
    Order matters:
        1. empty values: is the field required?
        2. type:         can it be read as the right kind of value?
        3. constraints:  allowed values, min/max, regex pattern
    The type is checked first so we never compare, say, "abc" with a minimum.
    """
    # DictReader gives None for cells missing from a short row; treat as empty.
    value = (value or "").strip()
 
    # 1. Empty value
    if value == "":
        return "required value missing" if rule.get("required") else None
 
    column_type = rule["type"]
    number = None  # will hold the converted number for min/max checks
 
    # 2. Type check
    if column_type == "integer":
        try:
            number = int(value)
        except ValueError:
            return "not an integer"
    elif column_type == "float":
        try:
            number = float(value)
        except ValueError:
            return "not a number"
        if not math.isfinite(number):  # rejects "nan" and "inf"
            return "not a number"
    elif column_type == "date":
        if parse_date(value) is None:
            return "invalid date"
    elif column_type == "email":
        if not re.fullmatch(config.EMAIL_PATTERN, value):
            return "invalid email"
    # "string" needs no type check: any text is a valid string.
 
    # 3. Constraint checks
    if "allowed" in rule:
        # Compare as text, so the schema can list numbers or words.
        allowed = [str(item) for item in rule["allowed"]]
        if value not in allowed:
            return f"not one of: {', '.join(allowed)}"
 
    if "min" in rule and number < rule["min"]:
        return f"below minimum {rule['min']}"
 
    if "max" in rule and number > rule["max"]:
        return f"above maximum {rule['max']}"
 
    if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
        return "does not match pattern"
 
    return None
 
 
def clean_value(value, rule):
    """
    Return a tidied version of a value that has ALREADY passed validation.
 
    Examples:
        integer " 007 "          -> "7"
        float   "3"              -> "3.0"
        date    "05.01.2024"     -> "2024-01-05"   (ISO format)
        email   "Ada@Mail.COM"   -> "ada@mail.com"
        string  " Ada   Lovelace"-> "Ada Lovelace"
    """
    value = (value or "").strip()
    if value == "":
        return ""
 
    column_type = rule["type"]
    if column_type == "integer":
        return str(int(value))
    if column_type == "float":
        return str(float(value))
    if column_type == "date":
        return parse_date(value).isoformat()
    if column_type == "email":
        return value.lower()
    # string: split on any whitespace and rejoin with single spaces
    return " ".join(value.split())
 
 
def validate_row(row, schema):
    """
    Check every schema column in one row.
 
    Returns a list of messages like ["age: not an integer", "email: invalid
    email"]. An empty list means the row is valid.
    """
    errors = []
 
    # csv.DictReader stores extra cells (more cells than headers) under the
    # key None. That usually means a stray comma, so we flag it.
    if None in row:
        errors.append("row: too many fields")
 
    for column, rule in schema["columns"].items():
        message = validate_value(row.get(column), rule)
        if message:
            errors.append(f"{column}: {message}")
    return errors
 
 
def clean_row(row, schema):
    """
    Return a copy of a valid row with every schema column cleaned.
    Columns that are not in the schema are passed through unchanged.
    """
    cleaned = dict(row)  # copy, so the original row is never modified
    for column, rule in schema["columns"].items():
        cleaned[column] = clean_value(row.get(column), rule)
    return cleaned
 
 
def find_duplicates(rows, key):
    """
    Return the positions (0-based) of rows whose key value has already
    appeared earlier. The FIRST occurrence is kept; later copies are flagged.
 
    Empty key values are skipped here, because validate_value already reports
    a missing required key.
    """
    if key is None:
        return set()
 
    seen = set()        # key values we've already met
    duplicates = set()  # row positions to flag
    for position, row in enumerate(rows):
        value = (row.get(key) or "").strip()
        if value == "":
            continue
        if value in seen:
            duplicates.add(position)
        else:
            seen.add(value)
    return duplicates
 
 
def process_rows(rows, schema):
    """
    Split rows into (clean_rows, rejected_rows).
 
    This is where the other core functions come together:
        find_duplicates -> which rows repeat the key
        validate_row    -> what is wrong with each row
        clean_row       -> tidy the rows that passed
    Rejected rows keep their original values plus an "errors" column, so a
    person can see exactly what to fix.
    """
    key = schema.get("key")
    duplicate_positions = find_duplicates(rows, key)
 
    clean_rows = []
    rejected_rows = []
    for position, row in enumerate(rows):
        errors = validate_row(row, schema)
        if position in duplicate_positions:
            errors.append(f"{key}: duplicate value")
 
        # Drop the None key (extra cells) so the row can be written back out.
        row = {column: value for column, value in row.items() if column is not None}
 
        if errors:
            rejected = dict(row)
            rejected[config.ERRORS_COLUMN] = "; ".join(errors)
            rejected_rows.append(rejected)
        else:
            clean_rows.append(clean_row(row, schema))
 
    return clean_rows, rejected_rows
 
 
def summarize(total, clean_count, rejected_rows):
    """
    Turn the results into report numbers.
 
    Returns a dict:
        {
          "total": 15, "clean": 9, "rejected": 6, "valid_pct": 60.0,
          "issues_by_column": {"email": 2, "age": 1, ...}
        }
    Issues are counted by reading the "column: message" text in each rejected
    row's errors column.
    """
    issues_by_column = {}
    for row in rejected_rows:
        for error in row[config.ERRORS_COLUMN].split("; "):
            column = error.split(":")[0]  # text before the first ":"
            issues_by_column[column] = issues_by_column.get(column, 0) + 1
 
    # Avoid dividing by zero when the CSV has a header but no rows.
    valid_pct = round(clean_count / total * 100, 1) if total else 0.0
 
    return {
        "total": total,
        "clean": clean_count,
        "rejected": total - clean_count,
        "valid_pct": valid_pct,
        # Sort so the most common problems appear first.
        "issues_by_column": dict(
            sorted(issues_by_column.items(), key=lambda item: (-item[1], item[0]))
        ),
    }
 
 
def format_report(report):
    """Turn a summarize() dict into two text tables for printing."""
    overview = tabulate(
        [
            ["Total rows", report["total"]],
            ["Clean rows", report["clean"]],
            ["Rejected rows", report["rejected"]],
            ["Valid", f"{report['valid_pct']}%"],
        ],
        tablefmt="rounded_outline",
    )
 
    if not report["issues_by_column"]:
        return f"{overview}\n\nNo issues found."
 
    issues = tabulate(
        list(report["issues_by_column"].items()),
        headers=["Column", "Issues"],
        tablefmt="rounded_outline",
    )
    return f"{overview}\n\nIssues by column:\n{issues}"
 
 
if __name__ == "__main__":
    main()