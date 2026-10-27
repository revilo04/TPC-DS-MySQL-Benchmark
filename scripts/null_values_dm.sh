#!/bin/bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <scale factor> <query stream>" >&2
    exit 1
fi
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${TPCDS_PYTHON:-$repo_root/.venv/bin/python}"
exec "$python_bin" "$repo_root/scripts/preprocess_data.py" "$repo_root/../data-maintenance/$1/$2"
