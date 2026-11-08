#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
scale_factor="${1:-1}"

case "$scale_factor" in
    1|2|4|8) ;;
    *)
        printf 'Usage: %s [1|2|4|8] [--setup-only | --benchmark-only] [--force]\n' "$0" >&2
        exit 2
        ;;
esac
shift || true

cd "$repo_root"
if command -v python >/dev/null 2>&1; then
    python_cmd=python
elif command -v python3 >/dev/null 2>&1; then
    python_cmd=python3
else
    echo "Python 3 is required but was not found on PATH." >&2
    exit 127
fi

exec "$python_cmd" -m scripts.run_benchmark "$scale_factor" "$@"
