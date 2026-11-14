#!/bin/bash
# Green gate for still-rest — run before every commit. Exit 0 = green.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1/5 kit"; python3 scripts/kit_lock.py check
echo "== 2/5 unit tests"; python3 -m unittest discover -s tests
echo "== 3/5 journal build check"; python3 scripts/build_journal.py --check --strict-safety
echo "== 4/5 legal pages build check"; python3 scripts/build_legal.py --check
echo "== 5/5 legacy-language redirect pages"; python3 scripts/build_redirects.py --check
echo "GREEN"
