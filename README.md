# csvguard: a CSV data-quality checker

## Description:

csvguard is a command-line tool that checks a CSV file against a set of rules, separates the good rows from the bad ones, tidies the good rows, and explains exactly what is wrong with the bad ones.

Messy CSV files are one of the most common problems in data work. A single export can contain emails without a domain, ages typed as words, impossible dates such as 30 February, status values nobody agreed on, and the same customer twice. If that data flows straight into a database or a report, the mistakes travel with it. csvguard sits at the very start of a data pipeline and acts as a gatekeeper: nothing reaches the next step until it has passed the rules.

The rules live in a JSON **schema** file rather than in the code, so the same program can check any CSV. A schema lists each column with its type (`string`, `integer`, `float`, `date` or `email`), whether a value is required, and optional constraints: a list of `allowed` values, a `min` and `max` for numbers, or a regular-expression `pattern`. An optional `key` names the column that should be unique, such as a customer ID.

#### Video Demo: <URL HERE>

## Usage

```
pip install -r requirements.txt
python project.py samples/customers.csv --schema samples/schema.json
```

An optional `--out-dir` flag chooses where the output files go. By default they are written next to the input file.

The program produces three results:

1. `customers_clean.csv`: every row that passed, with values normalized. Extra spaces are removed, emails are lowercased, numbers are standardized and every date is converted to ISO format (`YYYY-MM-DD`).
2. `customers_rejected.csv`: every row that failed, unchanged, plus an `errors` column such as `age: below minimum 18` so a person can fix the source.
3. A summary table in the terminal showing total, clean and rejected rows, the percentage of valid rows, and which columns caused the most issues.

## Files

**project.py** contains the whole program, written as plain functions with no classes. `main` is the conductor: it reads the command-line arguments, calls each step in order and is the only function that prints or exits. `load_schema` reads the JSON rules and checks that the rules themselves are sensible, for example rejecting an unknown type or a `min` on a text column, so mistakes are caught before any data is touched. `read_csv` and `write_csv` handle the files. `check_columns` confirms the CSV contains every column the schema expects. `validate_value` is the heart of the program: it checks one value against one rule and returns either `None` or a short error message. `parse_date` tries several date formats in turn. `validate_row` applies `validate_value` to every column of a row, and `find_duplicates` flags repeated key values. `process_rows` brings these together to split the data into clean and rejected rows, using `clean_value` and `clean_row` to tidy the clean ones. Finally `summarize` counts the results and `format_report` turns them into tables with the `tabulate` library.

**test_project.py** contains pytest tests for every function except `main` and the small file helpers: valid and invalid values of each type, required and optional fields, every constraint, broken schemas, duplicate detection and the report numbers, including the edge case of a CSV with no data rows.

**samples/** holds a deliberately messy `customers.csv` and a matching `schema.json`, with at least one example of every kind of problem the tool detects.

**requirements.txt** lists the two libraries the project needs: `tabulate` and `pytest`.

### Design choices

**Plain functions instead of classes.** Each step is a small function that takes data in and returns data out. Only `main` and the file helpers read files or print, which means everything else can be tested with ordinary Python values instead of real files.

**The `csv` module instead of pandas.** pandas would have hidden most of the validation logic behind a few library calls. Writing the checks by hand with the standard `csv` module made the rules explicit and kept the project light.

**Report the first problem per value, but every problem per row.** A value like `abc` in an age column is "not an integer"; also saying it is "below minimum" would be noise. Across a row, though, every broken column is listed, so one pass is enough to fix it.

**Check the type before the constraints.** Converting a value to its type first means constraints such as `min` are only ever compared with real numbers.

**Keep rejected rows instead of deleting them.** Silently dropping bad data hides problems. Saving rejected rows with a reason makes the tool's decisions transparent and lets someone correct the source.

**Keep the first duplicate.** When a key repeats, the first row is treated as the original and later copies are rejected, which is predictable and easy to explain.

**Day-first dates.** A date like `05/01/2024` is read as 5 January, the European convention. This is documented here because the format is ambiguous.

### Possible improvements

Future versions could stream very large files row by row instead of reading them into memory, support more types such as booleans, and export the report as Markdown or JSON for use in automated pipelines.

python project.py data/customers.csv --schema data/schema.json