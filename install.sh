#!/usr/bin/env bash
# Install Memoria launcher on Linux: .desktop for rofi/wofi/etc. and script wrapper.
# Run from repo root. Vault path is read from .env (single config for both platforms).

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
LAUNCHER_DIR="$REPO_ROOT/launcher"
DESKTOP_SRC="$LAUNCHER_DIR/memoria.desktop"
DESKTOP_DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications/memoria.desktop"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

echo "Memoria launcher install (Linux)"
echo "Repo: $REPO_ROOT"
echo ""

# Ensure .env exists
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
        echo "No .env found. Copying .env.example to .env — please set OBSIDIAN_PATH."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        echo "Error: No .env or .env.example in repo."
        exit 1
    fi
fi

# First-run check: vault path
OBSIDIAN_PATH=""
if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line; do
        if [[ "$line" =~ ^OBSIDIAN_PATH=(.*) ]]; then
            OBSIDIAN_PATH="${BASH_REMATCH[1]}"
            OBSIDIAN_PATH="${OBSIDIAN_PATH%\"}"
            OBSIDIAN_PATH="${OBSIDIAN_PATH#\"}"
            break
        fi
    done < "$ENV_FILE"
fi

if [[ -z "$OBSIDIAN_PATH" || "$OBSIDIAN_PATH" == "/path/to/your/obsidian/vault" ]]; then
    echo "Warning: OBSIDIAN_PATH is not set or still the placeholder in .env."
    echo "  Edit $ENV_FILE and set OBSIDIAN_PATH to your Obsidian vault path."
fi
if [[ -n "$OBSIDIAN_PATH" && "$OBSIDIAN_PATH" != "/path/to/your/obsidian/vault" ]]; then
    if [[ ! -d "$OBSIDIAN_PATH" ]]; then
        echo "Warning: Vault path does not exist: $OBSIDIAN_PATH"
    elif [[ ! -d "$OBSIDIAN_PATH/.obsidian" ]]; then
        echo "Warning: Obsidian vault folder not detected (no .obsidian in vault)."
    fi
fi

# Make launcher script executable
chmod +x "$LAUNCHER_DIR/memoria.sh"

# Install .desktop: substitute @REPO_PATH@ with actual path
mkdir -p "$(dirname "$DESKTOP_DEST")"
sed "s|@REPO_PATH@|$REPO_ROOT|g" "$DESKTOP_SRC" > "$DESKTOP_DEST"
echo "Installed: $DESKTOP_DEST"

# Optional: ensure venv exists
if [[ ! -x "$REPO_ROOT/venv/bin/python" ]]; then
    echo "Note: venv not found. Create with: python -m venv venv && pip install -r requirements.txt"
fi

echo ""
echo "Done. Launch Memoria from rofi/wofi (search 'Memoria') or bind a key to:"
echo "  $LAUNCHER_DIR/memoria.sh"
