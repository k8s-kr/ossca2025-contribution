#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/run_periods_and_append.sh [-n]
# -n : dry-run (print actions instead of executing)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/site/data"
SCRIPT="$ROOT_DIR/ossca-k8s-contributions.sh"
DRY_RUN=0

while getopts "n" opt; do
  case $opt in
    n) DRY_RUN=1 ;;
    *) echo "Usage: $0 [-n]" ; exit 1 ;;
  esac
done

if [ ! -f "$SCRIPT" ]; then
  echo "Error: script not found: $SCRIPT"
  exit 1
fi

shopt -s nullglob
for f in "$DATA_DIR"/*.txt; do
  base=$(basename "$f")
  # skip contributions.json if present
  if [ "$base" = "contributions.json" ]; then
    continue
  fi

  if [[ $base =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})\.\.([0-9]{4}-[0-9]{2}-[0-9]{2})\.txt$ ]]; then
    start=${BASH_REMATCH[1]}
    end=${BASH_REMATCH[2]}

    # header to separate runs
    header="=== $start..$end - $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="

    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[DRY] $SCRIPT \"$start\" \"$end\" >> \"$f\""
    else
      echo "Running for $base: $start .. $end"
      echo "$header" >> "$f"
      # append stdout+stderr so failures are visible in the file
      if ! "$SCRIPT" "$start" "$end" > "$f" 2>&1; then
        echo "Warning: script failed for $base; see above for details"
      fi
      echo "" >> "$f"
    fi
  else
    echo "Skipping $base: filename doesn't match YYYY-MM-DD..YYYY-MM-DD.txt"
  fi
done

echo "Done."
