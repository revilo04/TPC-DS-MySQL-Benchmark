"""Stream TPC-DS pipe-delimited data into CSV files accepted by the loader."""
import argparse
from functools import lru_cache
import os
import re
import tempfile
from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tools" / "tpcds.sql"


@lru_cache(maxsize=1)
def schema_columns(schema_path=SCHEMA_PATH):
    schema = Path(schema_path).read_text(encoding="utf-8")
    tables = {}
    table_pattern = re.compile(
        r"\bcreate\s+table\s+`?([A-Za-z0-9_]+)`?\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    column_pattern = re.compile(r"^\s*([A-Za-z_]\w*)\s+")
    for table_match in table_pattern.finditer(schema):
        columns = []
        for line in table_match.group(2).splitlines():
            column_match = column_pattern.match(line)
            if column_match and not column_match.group(1).casefold() in {
                "primary", "unique", "constraint", "key", "foreign"
            }:
                columns.append((column_match.group(1), "not null" in line.casefold()))
        if not columns:
            raise ValueError(f"No columns found for table {table_match.group(1)}")
        tables[table_match.group(1).casefold()] = columns
    if not tables:
        raise ValueError(f"No table definitions found in {schema_path}")
    return tables


def normalize_line(
    line,
    trailing_delimiter=False,
    expected_fields=None,
    final_field_nullable=True,
):
    row = line.rstrip(b"\r\n")
    fields = row.split(b"|")
    if expected_fields is not None:
        if trailing_delimiter and len(fields) == expected_fields + 1 and fields[-1] == b"":
            fields.pop()
        if len(fields) == expected_fields - 1 and final_field_nullable:
            fields.append(b"")
        if len(fields) != expected_fields:
            raise ValueError(
                f"Expected {expected_fields} fields, found {len(fields)}"
            )
    elif trailing_delimiter and row.endswith(b"|"):
        row = row[:-1]  # dsdgen's record terminator is not an extra column.
        fields = row.split(b"|")
    return b"|".join(field if field else b"\\N" for field in fields) + b"\n"


def preprocess_file(source):
    source = Path(source)
    target = source.with_suffix(".csv")
    columns = schema_columns().get(source.stem.casefold())
    expected_fields = len(columns) if columns else None
    final_field_nullable = columns is None or not columns[-1][1]
    temporary = None
    try:
        with source.open("rb") as src, tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=target.name + ".", delete=False
        ) as dst:
            temporary = Path(dst.name)
            for line_number, line in enumerate(src, 1):
                try:
                    normalized = normalize_line(
                        line,
                        source.suffix == ".dat",
                        expected_fields,
                        final_field_nullable,
                    )
                except ValueError as error:
                    raise ValueError(
                        f"{source}:{line_number}: {error}; file was not changed"
                    ) from error
                dst.write(normalized)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    sources = sorted(args.directory.glob("*.dat"))
    dat_stems = {path.stem for path in sources}
    sources += sorted(path for path in args.directory.glob("*.csv") if path.stem not in dat_stems)
    if not sources:
        parser.error(f"No .dat or .csv files in {args.directory}")
    for source in sources:
        print(f"Prepared {preprocess_file(source)}")


if __name__ == "__main__":
    main()
