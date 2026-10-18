#!/bin/bash
# Fetch the markdown-resume editor's own default stylesheet as ohmycv-base.css (git-ignored here).
# Upstream: junian/markdown-resume (master), a descendant of Renovamen/oh-my-cv. Both are copyleft-licensed
# (AGPL-3.0 / GPL-3.0), so the file is fetched on demand rather than redistributed inside this MIT-licensed kit.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
URL=${1:-https://raw.githubusercontent.com/junian/markdown-resume/master/site/src/assets/default-resume.css.txt}
curl -fsSL "$URL" -o "$HERE/ohmycv-base.css"
echo "wrote $HERE/ohmycv-base.css ($(wc -c < "$HERE/ohmycv-base.css") bytes) from $URL"
