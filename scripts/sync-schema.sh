#!/usr/bin/env bash
# Mirror the workflow schemas from a jobworkerp-rs checkout into the skill references.
#
# Usage: scripts/sync-schema.sh <jobworkerp-rs-root> [--check]
#   --check  Do not copy; exit 1 if the bundled copies differ from upstream.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <jobworkerp-rs-root> [--check]" >&2
  exit 2
fi

upstream_root=$1
mode=${2:-sync}
plugin_root=$(cd "$(dirname "$0")/.." && pwd)
refs="$plugin_root/skills/jobworkerp-workflow/references"

# upstream path -> bundled path.
# workflow.yaml is the code-generation schema (human reference);
# workflow_minimal_fix.json is the schema the runtime validator actually uses.
pairs=(
  "runner/schema/workflow.yaml:$refs/workflow-schema.yaml"
  "runner/schema/workflow_minimal_fix.json:$refs/workflow-validation-schema.json"
)

status=0
for pair in "${pairs[@]}"; do
  src="$upstream_root/${pair%%:*}"
  dst="${pair#*:}"
  if [[ ! -f "$src" ]]; then
    echo "missing upstream file: $src" >&2
    exit 2
  fi
  if [[ "$mode" == "--check" ]]; then
    if cmp -s "$src" "$dst"; then
      echo "up to date: ${dst#"$plugin_root"/}"
    else
      echo "OUT OF DATE: ${dst#"$plugin_root"/} (run scripts/sync-schema.sh $upstream_root)" >&2
      status=1
    fi
  else
    cp "$src" "$dst"
    echo "synced: ${dst#"$plugin_root"/}"
  fi
done
exit $status
