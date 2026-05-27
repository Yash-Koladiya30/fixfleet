#!/usr/bin/env bash
# FixFleet installer — auto-picks the best method available.
# Run: curl -sSL https://raw.githubusercontent.com/Yash-Koladiya30/fixfleet/main/install.sh | bash

set -e

PKG="fixfleet"
GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'; CYAN='\033[96m'; BOLD='\033[1m'; RESET='\033[0m'

echo -e "${BOLD}${CYAN}── FixFleet installer ──${RESET}"
echo ""

# ── Step 1: check Python ───────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}✗ python3 not found.${RESET}"
    echo "  Install: brew install python3   (macOS)"
    echo "           apt install python3    (Debian/Ubuntu)"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

echo -e "${GREEN}✓${RESET} Python ${PY_VER} detected"

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    echo -e "${RED}✗ Python 3.9+ required. You have ${PY_VER}.${RESET}"
    exit 1
fi

# ── Step 2: try uv (fastest, most reliable on bleeding-edge Python) ──
if command -v uv >/dev/null 2>&1; then
    echo -e "${CYAN}→ uv detected — using 'uv tool install' (recommended path)${RESET}"
    if uv tool install "$PKG"; then
        echo -e "${GREEN}✓ Installed via uv${RESET}"
        echo ""
        echo -e "${BOLD}Run it:${RESET}  fixfleet"
        exit 0
    fi
    echo -e "${YELLOW}! uv tool install failed, falling back to pipx${RESET}"
fi

# ── Step 3: try pipx ───────────────────────────────────────────
if command -v pipx >/dev/null 2>&1; then
    echo -e "${CYAN}→ pipx detected — using 'pipx install'${RESET}"
    if pipx install "$PKG" 2>&1; then
        pipx ensurepath >/dev/null 2>&1 || true
        echo -e "${GREEN}✓ Installed via pipx${RESET}"
        echo ""
        echo -e "${BOLD}Run it:${RESET}  fixfleet"
        echo -e "${YELLOW}  (restart terminal if 'command not found')${RESET}"
        exit 0
    fi
    echo -e "${YELLOW}! pipx install failed (often Python 3.14 ensurepip bug), falling back${RESET}"

    # Retry with python 3.12 if available
    if command -v python3.12 >/dev/null 2>&1; then
        echo -e "${CYAN}→ Retrying pipx with python3.12${RESET}"
        if pipx install --python "$(command -v python3.12)" "$PKG"; then
            echo -e "${GREEN}✓ Installed via pipx + python3.12${RESET}"
            echo ""
            echo -e "${BOLD}Run it:${RESET}  fixfleet"
            exit 0
        fi
    fi
fi

# ── Step 4: fall back to pip --user ────────────────────────────
echo -e "${CYAN}→ Falling back to 'pip install --user'${RESET}"
if ! python3 -m pip install --user --upgrade "$PKG"; then
    echo -e "${RED}✗ pip install failed${RESET}"
    exit 1
fi

USER_BIN=$(python3 -m site --user-base)/bin
echo -e "${GREEN}✓ Installed to ${USER_BIN}${RESET}"

# ── Step 5: PATH check ─────────────────────────────────────────
case ":$PATH:" in
    *":${USER_BIN}:"*)
        echo -e "${GREEN}✓ ${USER_BIN} already on PATH${RESET}"
        ;;
    *)
        echo -e "${YELLOW}! ${USER_BIN} not on PATH${RESET}"
        SHELL_RC=""
        case "${SHELL##*/}" in
            zsh)  SHELL_RC="$HOME/.zshrc" ;;
            bash) SHELL_RC="$HOME/.bashrc" ;;
            fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
        esac
        if [ -n "$SHELL_RC" ]; then
            echo "  Add to PATH (one time):"
            echo -e "    ${CYAN}echo 'export PATH=\"${USER_BIN}:\$PATH\"' >> ${SHELL_RC}${RESET}"
            echo -e "    ${CYAN}source ${SHELL_RC}${RESET}"
        fi
        ;;
esac

echo ""
echo -e "${BOLD}${GREEN}🚀 FixFleet ready!${RESET}"
echo -e "${BOLD}Run it:${RESET}  fixfleet"
echo -e "${BOLD}Repo:${RESET}    https://github.com/Yash-Koladiya30/fixfleet"
