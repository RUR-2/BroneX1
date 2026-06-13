#!/bin/bash
################################################################################
# Start DSC Wanderer Node
# Launches the Dynamical System autonomous wandering node on the laptop.
#
# Usage:
#   bash start_dsc_wanderer.sh              # starts node, then activate manually
#   bash start_dsc_wanderer.sh --auto       # starts AND immediately activates wandering
################################################################################

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── ROS2 environment ─────────────────────────────────────────────────────────
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=10
export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DISABLE_TYPE_HASH_CHECK=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DSC_NODE="$SCRIPT_DIR/dsc_wanderer_node.py"

echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  DSC Wanderer Node — BroneX1           ${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

if [ ! -f "$DSC_NODE" ]; then
    echo "ERROR: $DSC_NODE not found"
    exit 1
fi

echo -e "${GREEN}✓${NC} Starting DSC Wanderer node..."
echo ""
echo "  To ACTIVATE wandering:"
echo "    ros2 topic pub --once /drive_mode std_msgs/msg/String \"data: 'DSC'\""
echo "    ros2 topic pub --once /dsc/mode   std_msgs/msg/String \"data: 'WANDERER'\""
echo ""
echo "  To STOP:"
echo "    ros2 topic pub --once /dsc/mode std_msgs/msg/String \"data: 'STOP'\""
echo "    ros2 topic pub --once /drive_mode std_msgs/msg/String \"data: 'YOLO'\""
echo ""
echo "  Monitor state:"
echo "    ros2 topic echo /dsc/state"
echo "    ros2 topic echo /cmd_vel_dsc"
echo ""
echo -e "${YELLOW}------------------------------------------${NC}"
echo ""

# If --auto flag given, activate wandering after a short delay
if [[ "$1" == "--auto" ]]; then
    echo -e "${YELLOW}[--auto] Will activate wandering in 3s after node starts${NC}"
    (
        sleep 4
        source /opt/ros/jazzy/setup.bash
        export ROS_DOMAIN_ID=10
        export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
        export ROS_DISABLE_TYPE_HASH_CHECK=1
        ros2 topic pub --once /drive_mode std_msgs/msg/String "data: 'DSC'" > /dev/null 2>&1
        ros2 topic pub --once /dsc/mode   std_msgs/msg/String "data: 'WANDERER'" > /dev/null 2>&1
        echo -e "${GREEN}✓ Wandering ACTIVATED${NC}"
    ) &
fi

# Run the DSC node (blocking)
python3 "$DSC_NODE"
