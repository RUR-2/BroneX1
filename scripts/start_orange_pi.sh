#!/bin/bash

# =============================================================================
# ORANGE PI - TCP BRIDGE STARTUP SCRIPT
# =============================================================================
# Starts Orange Pi TCP server + Serial bridge + ROS2 telemetry publisher
# =============================================================================

echo "========================================"
echo "ORANGE PI - Starting TCP Bridge"
echo "========================================"
echo ""

# ROS2 Environment
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/orange/NVME/Brone/Code/cyclonedds.xml

echo "Environment:"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "  RMW: $RMW_IMPLEMENTATION"
echo ""

# Setup serial port
echo "Setting up serial port..."
echo "orange" | sudo -S chmod 666 /dev/ttyUSB0

if [ $? -eq 0 ]; then
    echo "✓ Serial port ready"
else
    echo "✗ Failed to setup serial port"
    exit 1
fi

echo ""
echo "========================================"
echo "Starting TCP Bridge..."
echo "========================================"
echo "Components:"
echo "  • TCP Server: Port 5555"
echo "  • Serial: /dev/ttyUSB0 → ESP32"
echo "  • ROS2 Telemetry Publisher"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Run bridge
python3 ~/orange_tcp_bridge.py
