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
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --target=*)   TARGET_OVERRIDE="${arg#*=}" ;;
    --list)       LIST_ONLY=1 ;;
    -y|--yes|--all) ASSUME_YES=1 ;;
    --help|-h)    SHOW_HELP=1 ;;
    -*)           echo "Unknown flag: $arg" >&2; exit 2 ;;
    *)            REQUESTED="$arg" ;;
  esac
done

if [ "$SHOW_HELP" = "1" ]; then
  cat <<'EOF'
Install UTM Grabber skills into your AI coding agents.

Usage:
  install.sh <skill-name>                 Install one skill (prompts which agent)
  install.sh all                          Install every skill
  install.sh --list                       Show available skills
  install.sh <skill-name> --target=NAME   Install only to NAME, no prompt
  install.sh <skill-name> -y              Install to all detected, no prompt

Targets: claude | cursor | codex | agents
When run interactively you are asked which agent(s) to install into.
Piped/non-interactive runs (no terminal) install to all detected agents.
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

# Candidate agent targets: any agent whose config dir exists, plus the
# shared ~/.agents/skills that Cursor and Codex also read.
CAND_LABELS=()
CAND_DIRS=()
[ -d "$HOME/.claude" ] && { CAND_LABELS+=("Claude Code  (~/.claude/skills)"); CAND_DIRS+=("$HOME/.claude/skills"); }
[ -d "$HOME/.cursor" ] && { CAND_LABELS+=("Cursor       (~/.cursor/skills)"); CAND_DIRS+=("$HOME/.cursor/skills"); }
[ -d "$HOME/.codex" ]  && { CAND_LABELS+=("Codex        (~/.codex/skills)");  CAND_DIRS+=("$HOME/.codex/skills"); }
CAND_LABELS+=("Shared       (~/.agents/skills)")
CAND_DIRS+=("$HOME/.agents/skills")

# Detect a usable controlling terminal. Opening /dev/tty fails when there is
# none (e.g. CI), unlike `[ -r /dev/tty ]` which only checks permission bits.
if (exec 3</dev/tty) 2>/dev/null; then HAS_TTY=1; else HAS_TTY=0; fi

TARGETS=()
if [ -n "$TARGET_OVERRIDE" ]; then
  case "$TARGET_OVERRIDE" in
    claude) TARGETS+=("$HOME/.claude/skills") ;;
    cursor) TARGETS+=("$HOME/.cursor/skills") ;;
    codex)  TARGETS+=("$HOME/.codex/skills") ;;
    agents) TARGETS+=("$HOME/.agents/skills") ;;
    all)    TARGETS=("${CAND_DIRS[@]}") ;;
    *) echo "Unknown target: $TARGET_OVERRIDE" >&2; exit 2 ;;
  esac
elif [ "$ASSUME_YES" = "1" ] || [ "$HAS_TTY" = "0" ]; then
  # Non-interactive (piped, no terminal) or -y/--all: install everywhere.
  TARGETS=("${CAND_DIRS[@]}")
else
  # Interactive single-choice menu. Read from /dev/tty so the prompt works
  # even when the script itself is piped in via `curl ... | bash`.
  MENU=("All detected (recommended)")
  for l in "${CAND_LABELS[@]}"; do MENU+=("$l"); done

  echo "Where should '$REQUESTED' be installed?" > /dev/tty
  PS3="Choose a number [1]: "
  select opt in "${MENU[@]}"; do
    # Empty input (just Enter) -> default to option 1 (All).
    [ -z "${REPLY:-}" ] && REPLY=1
    case "$REPLY" in
      1) TARGETS=("${CAND_DIRS[@]}"); break ;;
      ''|*[!0-9]*) echo "Enter a number from the list." > /dev/tty ;;
      *)
        idx=$((REPLY - 2))   # MENU[0] is "All"; candidates start at MENU[1]
        if [ "$idx" -ge 0 ] && [ -n "${CAND_DIRS[$idx]:-}" ]; then
          TARGETS=("${CAND_DIRS[$idx]}"); break
        else
          echo "Invalid choice: $REPLY" > /dev/tty
        fi
        ;;
    esac
  done < /dev/tty
fi

# Safety net: never proceed with an empty target list (e.g. the menu received
# EOF). Empty "${TARGETS[@]}" is also an unbound-variable error under `set -u`
# in bash 3.2, so this guard doubles as protection against that.
if [ "${#TARGETS[@]}" -eq 0 ]; then
  TARGETS=("${CAND_DIRS[@]}")
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
