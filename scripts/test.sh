#!/usr/bin/env bash
# Run all plugin checks.
#
# Usage: scripts/test.sh [<jobworkerp-rs-root>]
#   With an upstream path, also verifies the bundled schemas are in sync.
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
plugin_root=$(dirname "$script_dir")

python3 -I "$plugin_root/tests/test_validate_examples.py"
python3 -I "$script_dir/validate_examples.py"

if [[ $# -ge 1 ]]; then
  "$script_dir/sync-schema.sh" "$1" --check
fi
