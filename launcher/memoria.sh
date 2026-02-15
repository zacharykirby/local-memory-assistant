#!/usr/bin/env bash
# Memoria launcher: activates venv and runs chat. Run from repo root or via .desktop.
# WM-agnostic; use with rofi, wofi, or any keybind that runs the .desktop file.

set -e

# Repo root = parent of directory containing this script
LAUNCHER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$LAUNCHER_DIR/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/.env"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"

# ---- First-run check: vault path from .env ----
check_vault() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "Warning: No .env found. Copy .env.example to .env and set OBSIDIAN_PATH."
        return 1
    fi
    OBSIDIAN_PATH=""
    while IFS= read -r line; do
        if [[ "$line" =~ ^OBSIDIAN_PATH=(.*) ]]; then
            OBSIDIAN_PATH="${BASH_REMATCH[1]}"
            OBSIDIAN_PATH="${OBSIDIAN_PATH%\"}"
            OBSIDIAN_PATH="${OBSIDIAN_PATH#\"}"
            break
        fi
    done < "$ENV_FILE"
    if [[ -z "$OBSIDIAN_PATH" ]]; then
        echo "Warning: OBSIDIAN_PATH not set in .env."
        return 1
    fi
    if [[ ! -d "$OBSIDIAN_PATH" ]]; then
        echo "Warning: Vault path does not exist: $OBSIDIAN_PATH"
        return 1
    fi
    if [[ ! -d "$OBSIDIAN_PATH/.obsidian" ]]; then
        echo "Warning: Obsidian vault folder not detected (no .obsidian in $OBSIDIAN_PATH)."
    fi
    return 0
}

if ! check_vault; then
    echo "Fix .env and OBSIDIAN_PATH, then run Memoria again."
    read -r -p "Continue anyway? [y/N] " ans
    if [[ "${ans,,}" != "y" && "${ans,,}" != "yes" ]]; then
        exit 1
    fi
fi

# ---- Run Memoria ----
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Error: venv not found. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

exec "$VENV_PYTHON" src/chat.py "$@"
