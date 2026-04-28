#!/usr/bin/env bash
# setup.sh
# This script creates a Python 3.13.x virtual environment in the directory
# where the script resides and installs the packages listed in requirements.txt.
# It is compatible with both Bash and Zsh.

# Determine the directory of this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Function to find a suitable Python 3.13 executable
find_python() {
    # Prefer python3.13 if available
    if command -v python3.13 >/dev/null 2>&1; then
        echo "python3.13"
    elif command -v python3 >/dev/null 2>&1; then
        # Check if python3 is 3.13.x
        PYVER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
        if [[ $PYVER == 3.13.* ]]; then
            echo "python3"
        else
            echo "python3.13"
        fi
    else
        echo ""  # No suitable Python found
    fi
}

PYTHON=$(find_python)
if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3.13.x not found. Please install it before running this script." >&2
    exit 1
fi

# Create virtual environment
VENV_DIR="$SCRIPT_DIR/.venv"
if [[ -d "$VENV_DIR" ]]; then
    echo "Virtual environment already exists at $VENV_DIR"
else
    echo "Creating virtual environment using $PYTHON"
    "$PYTHON" -m venv "$VENV_DIR"
    if [[ $? -ne 0 ]]; then
        echo "Failed to create virtual environment." >&2
        exit 1
    fi
fi

# Activate the virtual environment
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install requirements
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [[ -f "$REQUIREMENTS_FILE" ]]; then
    echo "Installing packages from $REQUIREMENTS_FILE"
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "Warning: $REQUIREMENTS_FILE not found. Skipping package installation." >&2
fi

# Deactivate the virtual environment
 deactivate

echo "Setup complete. Activate the environment with: source $VENV_DIR/bin/activate"
