#!/usr/bin/env bash
#
# UTM Grabber skills installer.
#
# Installs a skill from the public monorepo into every AI coding agent
# detected on this machine (Claude Code, Cursor, Codex) plus the shared
# ~/.agents/skills directory that Cursor and Codex both read.
#
# Usage:
#   curl -fsSL <url>/install.sh | bash -s -- <skill-name>
#   curl -fsSL <url>/install.sh | bash -s -- all
#   curl -fsSL <url>/install.sh | bash -s -- --list
#
# Inspect before running:
#   curl -fsSL <url>/install.sh | less
#
set -euo pipefail

REPO="${UTM_SKILLS_REPO:-https://github.com/handldigital/utm-grabber-skills}"
SKILLS_SUBDIR="skills"

TARGET_OVERRIDE=""
REQUESTED=""
LIST_ONLY=0
SHOW_HELP=0

for arg in "$@"; do
  case "$arg" in
    --target=*) TARGET_OVERRIDE="${arg#*=}" ;;
    --list)     LIST_ONLY=1 ;;
    --help|-h)  SHOW_HELP=1 ;;
    -*)         echo "Unknown flag: $arg" >&2; exit 2 ;;
    *)          REQUESTED="$arg" ;;
  esac
done

if [ "$SHOW_HELP" = "1" ]; then
  cat <<'EOF'
Install UTM Grabber skills into your AI coding agents.

Usage:
  install.sh <skill-name>                 Install one skill
  install.sh all                          Install every skill
  install.sh --list                       Show available skills
  install.sh <skill-name> --target=NAME   Restrict where it installs

Targets: claude | cursor | codex | agents | all (default: all detected)
EOF
  exit 0
fi

command -v git >/dev/null 2>&1 || { echo "git is required but not found." >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Fetching skills catalog..."
git clone --depth 1 "$REPO" "$TMP/repo" >/dev/null 2>&1 || {
  echo "Could not clone $REPO" >&2
  exit 1
}

# bash 3.2-safe array fill (macOS ships bash 3.2; no mapfile/readarray).
AVAILABLE=()
while IFS= read -r d; do
  [ -n "$d" ] && AVAILABLE+=("$d")
done < <(
  cd "$TMP/repo/$SKILLS_SUBDIR" 2>/dev/null && \
  for x in */; do [ -f "$x/SKILL.md" ] && echo "${x%/}"; done
)

if [ "${#AVAILABLE[@]}" -eq 0 ]; then
  echo "No skills found in $REPO/$SKILLS_SUBDIR." >&2
  exit 1
fi

if [ "$LIST_ONLY" = "1" ]; then
  echo "Available skills:"
  printf '  - %s\n' "${AVAILABLE[@]}"
  exit 0
fi

if [ -z "$REQUESTED" ]; then
  echo "Specify a skill to install. Available:"
  printf '  - %s\n' "${AVAILABLE[@]}"
  echo
  echo "Run:  curl -fsSL <url>/install.sh | bash -s -- <skill-name>"
  exit 1
fi

TO_INSTALL=()
if [ "$REQUESTED" = "all" ]; then
  TO_INSTALL=("${AVAILABLE[@]}")
else
  for s in "${AVAILABLE[@]}"; do
    [ "$s" = "$REQUESTED" ] && TO_INSTALL+=("$s")
  done
  if [ "${#TO_INSTALL[@]}" -eq 0 ]; then
    echo "Unknown skill: $REQUESTED" >&2
    echo "Available:" >&2
    printf '  - %s\n' "${AVAILABLE[@]}" >&2
    exit 1
  fi
fi

TARGETS=()
if [ -n "$TARGET_OVERRIDE" ] && [ "$TARGET_OVERRIDE" != "all" ]; then
  case "$TARGET_OVERRIDE" in
    claude) TARGETS+=("$HOME/.claude/skills") ;;
    cursor) TARGETS+=("$HOME/.cursor/skills") ;;
    codex)  TARGETS+=("$HOME/.codex/skills") ;;
    agents) TARGETS+=("$HOME/.agents/skills") ;;
    *) echo "Unknown target: $TARGET_OVERRIDE" >&2; exit 2 ;;
  esac
else
  [ -d "$HOME/.claude" ] && TARGETS+=("$HOME/.claude/skills")
  [ -d "$HOME/.cursor" ] && TARGETS+=("$HOME/.cursor/skills")
  [ -d "$HOME/.codex" ]  && TARGETS+=("$HOME/.codex/skills")
  # Universal fallback read by Cursor and Codex (and other open-standard tools).
  TARGETS+=("$HOME/.agents/skills")
fi

for name in "${TO_INSTALL[@]}"; do
  src="$TMP/repo/$SKILLS_SUBDIR/$name"
  for dir in "${TARGETS[@]}"; do
    mkdir -p "$dir"
    rm -rf "$dir/$name"
    cp -R "$src" "$dir/$name"
    echo "  installed $name -> $dir/$name"
  done
done

echo
echo "Done. Start a new chat or restart your agent to load the skill."
