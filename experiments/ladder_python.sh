#!/bin/bash
set -u
HERE=$(cd "$(dirname "$0")" && pwd)

if [ -n "${LADDER_PYTHON:-}" ]; then
  candidates=$LADDER_PYTHON
else
  candidates="$HERE/.venv/bin/python $HERE/../.venv/bin/python"
fi

for candidate in $candidates; do
  if [ -x "$candidate" ] && "$candidate" -c 'import sermon.pipeline.classify' 2>/dev/null; then
    echo "$candidate"
    exit 0
  fi
done

echo "none of these can import sermon.pipeline: $candidates" >&2
echo "install the project into one (uv pip install -e '.[dev]') or set LADDER_PYTHON" >&2
exit 1
