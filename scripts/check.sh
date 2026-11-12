#!/bin/bash
# Green gate for still-rest — run before every commit. Exit 0 = green.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1/4 kit"; python3 scripts/kit_lock.py check
echo "== 2/4 unit tests"; python3 -m unittest discover -s tests
echo "== 3/4 journal build check"; python3 scripts/build_journal.py --check --strict-safety
echo "== 4/4 legal pages build check"; python3 scripts/build_legal.py --check
echo "GREEN"
