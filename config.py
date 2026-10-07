# ---------------------------------------------------------------------------
# Constants: settings shared by several functions, defined once at the top.
# ---------------------------------------------------------------------------
 
# The column types a schema is allowed to use.
VALID_TYPES = {"string", "integer", "float", "date", "email"}
 
# Only these types can have "min" and "max" rules.
NUMERIC_TYPES = {"integer", "float"}
 
# Date formats we accept, tried in this order. Day-first is assumed for
# formats like 05/01/2024 (5 January), which is the European convention.
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"]
 
# A deliberately simple email check: text, "@", text, ".", 2+ letters.
EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}"
 
# Name of the extra column added to rejected rows to explain what was wrong.
ERRORS_COLUMN = "errors"