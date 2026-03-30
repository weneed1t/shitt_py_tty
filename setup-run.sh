#!/usr/bin/env bash
#
# setup-and-run.sh - Setup virtual environment and launch web terminal server
# 
# Usage: ./setup-and-run.sh [--reinstall] [--no-sudo]
#
# Options:
#   --reinstall   Force reinstall of dependencies
#   --no-sudo     Run without sudo (for testing as regular user)
#

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/.venv"
readonly REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
readonly MAIN_FILE="${SCRIPT_DIR}/main.py"
readonly HOST="0.0.0.0"
readonly PORT="8200"
readonly PYTHON_CMD="${VENV_DIR}/bin/python3"
readonly PIP_CMD="${VENV_DIR}/bin/pip"
readonly UVICORN_CMD="${VENV_DIR}/bin/uvicorn"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Flags
REINSTALL=false
USE_SUDO=true

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
log_error()   { echo -e "${RED}[✗]${NC} $*" >&2; }

check_root() {
    if [[ "$USE_SUDO" == "true" ]] && [[ $EUID -ne 0 ]]; then
        log_warn "Running with sudo - you may be prompted for password"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reinstall)
                REINSTALL=true
                shift
                ;;
            --no-sudo)
                USE_SUDO=false
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [--reinstall] [--no-sudo]"
                echo "  --reinstall   Force reinstall of Python dependencies"
                echo "  --no-sudo     Skip sudo (run as current user)"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

create_requirements() {
    if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
        log_info "Creating requirements.txt..."
        cat > "$REQUIREMENTS_FILE" << 'EOF'
# Web Terminal Dependencies
# Install with: pip install -r requirements.txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
# Note: websockets is included via uvicorn[standard]
EOF
        log_success "Created requirements.txt"
    fi
}

setup_venv() {
    if [[ ! -d "$VENV_DIR" ]] || [[ "$REINSTALL" == "true" ]]; then
        log_info "Setting up Python virtual environment..."
        
        # Remove existing venv if reinstalling
        if [[ "$REINSTALL" == "true" ]] && [[ -d "$VENV_DIR" ]]; then
            log_warn "Removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        fi
        
        # Create virtual environment
        if ! python3 -m venv "$VENV_DIR"; then
            log_error "Failed to create virtual environment"
            log_info "Try: sudo apt install python3-venv (Debian/Ubuntu)"
            exit 1
        fi
        log_success "Virtual environment created at: $VENV_DIR"
    else
        log_info "Virtual environment already exists (use --reinstall to rebuild)"
    fi
}

install_dependencies() {
    log_info "Checking Python dependencies..."
    
    # Upgrade pip first (suppress output unless error)
    "$PIP_CMD" install --upgrade pip -q 2>/dev/null || true
    
    # Check if key packages are already installed
    if "$PIP_CMD" list -q | grep -qE "^fastapi " && \
       "$PIP_CMD" list -q | grep -qE "^uvicorn " && \
       [[ "$REINSTALL" == "false" ]]; then
        log_success "Dependencies already installed"
        return 0
    fi
    
    log_info "Installing dependencies from requirements.txt..."
    if ! "$PIP_CMD" install -r "$REQUIREMENTS_FILE" -q; then
        log_error "Failed to install dependencies"
        exit 1
    fi
    log_success "Dependencies installed successfully"
}

verify_setup() {
    log_info "Verifying installation..."
    
    # Check main.py exists
    if [[ ! -f "$MAIN_FILE" ]]; then
        log_error "main.py not found at: $MAIN_FILE"
        exit 1
    fi
    
    # Check uvicorn is callable
    if ! "$PYTHON_CMD" -c "import uvicorn" 2>/dev/null; then
        log_error "uvicorn not properly installed in virtual environment"
        exit 1
    fi
    
    # Check fastapi is available
    if ! "$PYTHON_CMD" -c "import fastapi" 2>/dev/null; then
        log_error "fastapi not properly installed in virtual environment"
        exit 1
    fi
    
    log_success "Setup verified successfully"
}

run_server() {
    log_info "Starting web terminal server..."
    log_info "Listening on http://${HOST}:${PORT}"
    log_warn "⚠️  This server provides shell access - ensure proper authentication!"
    
    if [[ "$USE_SUDO" == "true" ]]; then
        # Run with sudo - use full path to uvicorn in venv
        log_info "Running with elevated privileges (sudo)..."
        exec sudo "$UVICORN_CMD" main:app \
            --host "$HOST" \
            --port "$PORT" \
            --app-dir "$SCRIPT_DIR" \
            --log-level info
    else
        # Run without sudo
        log_info "Running as current user (no sudo)..."
        exec "$UVICORN_CMD" main:app \
            --host "$HOST" \
            --port "$PORT" \
            --app-dir "$SCRIPT_DIR" \
            --log-level info
    fi
}

# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------

main() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Web Terminal Server Setup & Run     ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo
    
    parse_args "$@"
    check_root
    
    # Ensure we're in the script directory for relative paths
    cd "$SCRIPT_DIR"
    
    create_requirements
    setup_venv
    install_dependencies
    verify_setup
    
    echo
    log_success "Ready to launch!"
    echo
    
    # This exec replaces the current process - script won't continue after this
    run_server
}

# Run main function with all arguments
main "$@"