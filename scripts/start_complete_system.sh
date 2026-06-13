#!/bin/bash
################################################################################
# Start Complete BroneRoda System (Local + Remote)
################################################################################

# Load nvm if available
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

# Source ROS2 (CRITICAL for Webots controller)
source /opt/ros/jazzy/setup.bash

# Set ROS environment
export ROS_DOMAIN_ID=10
export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# Disable type hash check for Humble/Jazzy compatibility
export ROS_DISABLE_TYPE_HASH_CHECK=1

print_header "Starting Complete BroneRoda System"

# 1. Start remote services
print_status "Starting remote services (Jetson + Orange Pi)..."
python3 /home/codename-hydra/start_all_remote.py

sleep 3

# 2. Start WebSocket Relay Server
print_status "Starting WebSocket Relay Server..."
python3 ~/Documents/Digital_Twin_Interface/ws_server.py > /dev/null 2>&1 &
sleep 2

# 3. Start Digital Twin UI in background
print_status "Starting Digital Twin Web Interface..."
cd ~/Documents/Digital_Twin_Interface
gnome-terminal -- bash -c "source ~/.nvm/nvm.sh; npm run dev; exec bash" &
sleep 2

# 4. Start Webots
print_status "Starting Webots Tahap 6 Monitoring..."
cd ~/Documents/BroneRoda

# Find Webots command
WEBOTS_CMD=""
if command -v webots &> /dev/null; then
    WEBOTS_CMD="webots"
elif [ -f "$HOME/webots/webots" ]; then
    WEBOTS_CMD="$HOME/webots/webots"
elif [ -f "$HOME/.ros/webotsR2025a/webots/webots" ]; then
    WEBOTS_CMD="$HOME/.ros/webotsR2025a/webots/webots"
fi

# Launch Webots with correct world file
WORLD_FILE="worlds/BroneRodaEstimationClosedBeta.wbt"

if [ -n "$WEBOTS_CMD" ] && [ -f "$WORLD_FILE" ]; then
    print_status "Launching Webots with $WORLD_FILE"
    "$WEBOTS_CMD" "$WORLD_FILE" &
    sleep 2
else
    echo "⚠️  Webots or world file not found"
    echo "  Webots: $WEBOTS_CMD"
    echo "  World: $WORLD_FILE"
fi

print_header "System Started Successfully"
echo ""
echo "Running services:"
echo "  • Orange Pi (10.30.117.200): TCP Bridge"
echo "  • Jetson (10.30.117.199): YOLO Detection"
echo "  • Digital Twin UI: http://localhost:5173"
echo "  • Webots: Opening..."
echo ""
echo "Check ROS topics:"
echo "  ros2 topic echo /robot_velocity"
echo ""
