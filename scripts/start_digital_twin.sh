#!/bin/bash
################################################################################
# Start Digital Twin Interface with proper Node/npm PATH
################################################################################

# Load nvm if available
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    source "$NVM_DIR/nvm.sh"
fi

echo "=========================================="
echo "Starting Digital Twin Interface"
echo "=========================================="
echo ""

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "❌ npm not found in PATH"
    echo ""
    echo "Please ensure Node.js/npm is installed:"
    echo "  Via nvm: source ~/.nvm/nvm.sh"
    echo "  Or: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
    exit 1
fi

echo "✓ npm found: $(which npm)"
echo "✓ node version: $(node -v)"
echo ""

cd ~/Documents/Digital_Twin_Interface

# Kill existing instance
pkill -f "vite.*Digital_Twin" 2>/dev/null
pkill -f "npm.*Digital_Twin" 2>/dev/null

echo "Starting Digital Twin UI..."
npm run dev &

sleep 3

echo ""
echo "✓ Digital Twin UI started"
echo ""
echo "Access at: http://localhost:5173"
echo ""
