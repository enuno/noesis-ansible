#!/bin/bash
set -e
SCHEMA_DIR="$(dirname "$0")/../schemas"
for schema in "$SCHEMA_DIR"/*.schema.json; do
  echo "Schema available: $(basename "$schema")"
done
echo "JSON validation stub complete"
