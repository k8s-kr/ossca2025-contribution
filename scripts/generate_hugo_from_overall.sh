#!/usr/bin/env bash
set -euo pipefail

# generate_hugo_from_overall.sh
# Reads data/overall.txt (or given file) and generates a Hugo-compatible
# markdown page under content/periods/<START..END>/index.md

INFILE="${1:-data/overall.txt}"
if [ ! -f "$INFILE" ]; then
  echo "Input file not found: $INFILE" >&2
  exit 1
fi

# Extract period
read_line=$(grep -m1 "^Checking GitHub activity from" "$INFILE" || true)
if [[ $read_line =~ Checking[[:space:]]GitHub[[:space:]]activity[[:space:]]from[[:space:]]([0-9]{4}-[0-9]{2}-[0-9]{2})[[:space:]]to[[:space:]]([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
  START=${BASH_REMATCH[1]}
  END=${BASH_REMATCH[2]}
else
  echo "Cannot determine period from $INFILE" >&2
  exit 1
fi

OUTDIR="site/content/periods/${START}..${END}"
mkdir -p "$OUTDIR"
# Use _index.md so Hugo treats it as a section index and generates a directory page
OUTFILE="$OUTDIR/_index.md"

echo "Generating $OUTFILE from $INFILE"
# Delegate complex parsing to Python script for reliability
python3 ./scripts/generate_hugo_from_overall.py "$INFILE"
