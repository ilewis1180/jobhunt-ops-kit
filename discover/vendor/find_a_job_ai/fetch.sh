#!/bin/bash
# Fetch the pinned upstream find-a-job-ai grader and apply the sales-grading patch (see SOURCE.md).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
COMMIT=d50233e
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone -q https://github.com/michaelshirley1/find-a-job-ai.git "$TMP/src"
git -C "$TMP/src" checkout -q "$COMMIT"
cp "$TMP/src/scripts/daily_job_search.py" "$HERE/daily_job_search.py"
patch -s "$HERE/daily_job_search.py" "$HERE/sales-grading.patch"
echo "vendored $HERE/daily_job_search.py @ $COMMIT with sales-grading.patch (git-ignored)"
