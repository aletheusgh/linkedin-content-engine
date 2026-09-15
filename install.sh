#!/usr/bin/env bash
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
SKILLS_DIR="$CODEX_HOME_DIR/skills"
DEST="$SKILLS_DIR/linkedin-content-engine"

mkdir -p "$SKILLS_DIR"

if [[ "$SOURCE" == "$DEST" ]]; then
  echo "LinkedIn Content Engine is already installed at $DEST"
  exit 0
fi

if [[ -e "$DEST" ]]; then
  BACKUP="$DEST.backup-$(date +%Y%m%d-%H%M%S)"
  mv "$DEST" "$BACKUP"
  echo "Previous version backed up to $BACKUP"
fi

cp -R "$SOURCE" "$DEST"
echo "Installed LinkedIn Content Engine to $DEST"
echo "Restart Codex before using the skill."
