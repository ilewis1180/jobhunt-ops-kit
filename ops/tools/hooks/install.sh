#!/bin/bash
# Install the repo's versioned git hooks (pre-commit PII gate). Other hooks are left untouched.
set -eu
REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
HOOKS_REL="ops/tools/hooks"
HOOK="$REPO/.git/hooks/pre-commit"
cat > "$HOOK" <<'H'
#!/bin/bash
# thin wrapper; the real hook is versioned in tools/hooks/pre-commit
exec "$(git rev-parse --show-toplevel)/ops/tools/hooks/pre-commit" "$@"
H
chmod +x "$HOOK" "$REPO/$HOOKS_REL/pre-commit"
echo "installed $HOOK -> $HOOKS_REL/pre-commit"
