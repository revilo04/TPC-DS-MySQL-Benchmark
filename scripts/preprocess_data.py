"""Stream TPC-DS pipe-delimited data into CSV files accepted by the loader."""
import argparse
import os
import tempfile
from pathlib import Path


def normalize_line(line, trailing_delimiter=False):
    row = line.rstrip(b"\r\n")
    if trailing_delimiter and row.endswith(b"|"):
        row = row[:-1]  # dsdgen's record terminator is not an extra column.
    return b"|".join(field if field else b"\\N" for field in row.split(b"|")) + b"\n"


def preprocess_file(source):
    source = Path(source)
    target = source.with_suffix(".csv")
    temporary = None
    try:
        with source.open("rb") as src, tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=target.name + ".", delete=False
        ) as dst:
            temporary = Path(dst.name)
            for line in src:
                dst.write(normalize_line(line, source.suffix == ".dat"))
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
