#!/usr/bin/env zsh
# ──────────────────────────────────────────────────────────────────────────────
# Setup script for AI Finance Advisor — creates venv, installs deps, registers
# Jupyter kernel. Run once from the project root:
#   chmod +x setup.sh && ./setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
KERNEL_NAME="finance_advisor"

echo "──────────────────────────────────────────"
echo " Finance Advisor — Environment Setup"
echo "──────────────────────────────────────────"
echo "Project : $PROJECT_DIR"
echo "Venv    : $VENV_DIR"
echo ""

# ── 1. Create virtual environment ─────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    echo "✓ Virtual environment already exists — skipping creation"
else
    echo "→ Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
fi

# ── 2. Activate venv ──────────────────────────────────────────────────────────
source "$VENV_DIR/bin/activate"
echo "✓ Virtual environment activated"

# ── 3. Install libomp (required by XGBoost on macOS) ─────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    if ! brew list libomp &>/dev/null; then
        echo "→ Installing libomp (needed by XGBoost on macOS)..."
        brew install libomp
        echo "✓ libomp installed"
    else
        echo "✓ libomp already installed"
    fi
fi

# ── 4. Upgrade pip ────────────────────────────────────────────────────────────
echo ""
echo "→ Upgrading pip..."
pip install --upgrade pip --quiet

# ── 5. Install all dependencies ───────────────────────────────────────────────
echo ""
echo "→ Installing packages from requirements.txt..."
pip install -r "$PROJECT_DIR/requirements.txt"
echo "✓ All packages installed"

# ── 6. Register the Jupyter kernel ────────────────────────────────────────────
echo ""
echo "→ Registering Jupyter kernel as '$KERNEL_NAME'..."
python -m ipykernel install --sys-prefix --name "$KERNEL_NAME" --display-name "Finance Advisor (Python)"
echo "✓ Kernel registered"

# ── 7. Create models output directory ─────────────────────────────────────────
mkdir -p "$PROJECT_DIR/models"
echo "✓ models/ directory ready"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────"
echo " Setup complete!"
echo ""
echo " To run the notebooks:"
echo "   source .venv/bin/activate"
echo "   jupyter notebook"
echo ""
echo " Then open:"
echo "   transaction_categorization.ipynb"
echo "   expense_forecasting.ipynb"
echo ""
echo " Select kernel: 'Finance Advisor (Python)'"
echo "──────────────────────────────────────────"
