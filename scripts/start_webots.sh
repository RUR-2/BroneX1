#!/bin/bash
################################################################################
# Start Webots for BroneRoda Monitoring
################################################################################

# Source ROS2 first (CRITICAL for controller to work)
source /opt/ros/jazzy/setup.bash

# Set ROS environment
export ROS_DOMAIN_ID=10
export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# Disable type hash check for Humble/Jazzy compatibility
export ROS_DISABLE_TYPE_HASH_CHECK=1

echo "=========================================="
echo "Starting Webots Tahap 6 Monitoring"
echo "=========================================="
echo ""
echo "ROS Environment:"
echo "  ROS_DISTRO: $ROS_DISTRO"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "  CYCLONEDDS_URI: $CYCLONEDDS_URI"
echo ""

cd ~/Documents/BroneRoda

# Try to find Webots
WEBOTS_CMD=""

if command -v webots &> /dev/null; then
    WEBOTS_CMD="webots"
elif [ -f "$HOME/webots/webots" ]; then
    WEBOTS_CMD="$HOME/webots/webots"
elif [ -f "$HOME/.ros/webotsR2025a/webots/webots" ]; then
    WEBOTS_CMD="$HOME/.ros/webotsR2025a/webots/webots"
fi

if [ -n "$WEBOTS_CMD" ]; then
    echo "✓ Webots found: $WEBOTS_CMD"
    
    # Use specific world file
    WORLD_FILE="worlds/BroneRodaEstimationClosedBeta.wbt"
    
    if [ -f "$WORLD_FILE" ]; then
        echo "✓ Loading $WORLD_FILE"
        echo "✓ Starting Webots (GUI will open)..."
        "$WEBOTS_CMD" "$WORLD_FILE"
    else
        echo "⚠️  World file not found: $WORLD_FILE"
        echo "Available worlds:"
        ls -1 worlds/*.wbt 2>/dev/null || echo "  No .wbt files found"
    fi
else
    echo "⚠️  Webots command not found in PATH"
    echo ""
    echo "Please install Webots:"
    echo "  sudo snap install webots"
    echo ""
    echo "Or open Webots manually:"
    echo "  1. Open Webots from application menu"
    echo "  2. File → Open World"
    echo "  3. Open: ~/Documents/BroneRoda/worlds/BroneRodaEstimationClosedBeta.wbt"
    echo "  4. Load controller: Diter_Roda_Tahap6_YOLO_WS_Bridge"
    echo ""
fi
