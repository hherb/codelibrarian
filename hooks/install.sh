#!/bin/sh
# Install codelibrarian git hooks into the current repo's .git/hooks/

set -e

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

for hook in post-commit post-merge; do
    src="$SCRIPT_DIR/$hook"
    dst="$HOOKS_DIR/$hook"
    cp "$src" "$dst"
    chmod 755 "$dst"
    echo "Installed: $dst"
done

echo "Done."
