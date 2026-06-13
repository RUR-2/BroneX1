#!/bin/bash
################################################################################
# BroneRoda Remote Startup Orchestrator
# =====================================
# Starts YOLO tracking system on both Jetson and Orange Pi from laptop
################################################################################

set -e

# Configuration
JETSON_IP="10.30.117.199"
JETSON_USER="humanoid"
JETSON_PASS="111111"

ORANGE_IP="10.30.117.200"
ORANGE_USER="orange"
ORANGE_PASS="111111"


# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if sshpass is available
check_sshpass() {
    if command -v sshpass &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# SSH with password (using sshpass if available)
ssh_with_pass() {
    local user=$1
    local ip=$2
    local pass=$3
    local cmd=$4
    
    if check_sshpass; then
        sshpass -p "$pass" ssh -o StrictHostKeyChecking=no "$user@$ip" "$cmd"
    else
        ssh -o StrictHostKeyChecking=no "$user@$ip" "$cmd"
    fi
}

################################################################################
# Main Script
################################################################################

print_header "BroneRoda Remote Startup"

# Check connectivity
print_status "Checking device connectivity..."

if ! ping -c 1 -W 1 $ORANGE_IP &> /dev/null; then
    print_error "Orange Pi ($ORANGE_IP) not reachable!"
    exit 1
fi
print_status "Orange Pi reachable"

if ! ping -c 1 -W 1 $JETSON_IP &> /dev/null; then
    print_error "Jetson ($JETSON_IP) not reachable!"
    exit 1
fi
print_status "Jetson reachable"

# Check for sshpass
if ! check_sshpass; then
    print_warning "sshpass not found. Attempting SSH with keys..."
    print_warning "If prompted for password, enter: 111111"
fi

################################################################################
# Cleanup Existing Processes
################################################################################

print_header "Cleaning Up Existing Processes"

echo "Stopping processes on Orange Pi..."
ssh_with_pass "$ORANGE_USER" "$ORANGE_IP" "$ORANGE_PASS" "pkill -f orange_tcp_bridge || true" &> /dev/null
ssh_with_pass "$ORANGE_USER" "$ORANGE_IP" "$ORANGE_PASS" "pkill -f start_orange_pi || true" &> /dev/null
print_status "Orange Pi processes cleared"

echo "Stopping processes on Jetson..."
ssh_with_pass "$JETSON_USER" "$JETSON_IP" "$JETSON_PASS" "pkill -f jetson_yolo_tcp || true" &> /dev/null
ssh_with_pass "$JETSON_USER" "$JETSON_IP" "$JETSON_PASS" "pkill -f python3 || true" &> /dev/null
print_status "Jetson processes cleared"

sleep 1

################################################################################
# Start Orange Pi Bridge
################################################################################

print_header "Starting Orange Pi TCP Bridge"

echo "Deploying start script to Orange Pi..."
if check_sshpass; then
    sshpass -p "$ORANGE_PASS" scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/start_orange_pi.sh "$ORANGE_USER@$ORANGE_IP:~/" &> /dev/null
    sshpass -p "$ORANGE_PASS" scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/Downloads/orange_tcp_bridge.py "$ORANGE_USER@$ORANGE_IP:~/" &> /dev/null
else
    scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/start_orange_pi.sh "$ORANGE_USER@$ORANGE_IP:~/" &> /dev/null
    scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/Downloads/orange_tcp_bridge.py "$ORANGE_USER@$ORANGE_IP:~/" &> /dev/null
fi

print_status "Files deployed to Orange Pi"

echo "Starting bridge service..."
if check_sshpass; then
    sshpass -p "$ORANGE_PASS" ssh -o StrictHostKeyChecking=no "$ORANGE_USER@$ORANGE_IP" \
        "nohup ./start_orange_pi.sh > orange_bridge.log 2>&1 &" &
else
    ssh -o StrictHostKeyChecking=no "$ORANGE_USER@$ORANGE_IP" \
        "nohup ./start_orange_pi.sh > orange_bridge.log 2>&1 &" &
fi

sleep 2
print_status "Orange Pi bridge started"

################################################################################
# Start Jetson YOLO
################################################################################

print_header "Starting Jetson YOLO"

echo "Deploying YOLO script to Jetson..."
if check_sshpass; then
    sshpass -p "$JETSON_PASS" scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/Downloads/jetson_yolo_tcp.py "$JETSON_USER@$JETSON_IP:~/" &> /dev/null
else
    scp -o StrictHostKeyChecking=no \
        /home/codename-hydra/Downloads/jetson_yolo_tcp.py "$JETSON_USER@$JETSON_IP:~/" &> /dev/null
fi

print_status "YOLO script deployed to Jetson"

echo "Starting YOLO service..."
if check_sshpass; then
    sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON_USER@$JETSON_IP" \
        "nohup python3 jetson_yolo_tcp.py > yolo.log 2>&1 &" &
else
    ssh -o StrictHostKeyChecking=no "$JETSON_USER@$JETSON_IP" \
        "nohup python3 jetson_yolo_tcp.py > yolo.log 2>&1 &" &
fi

sleep 2
print_status "Jetson YOLO started"

################################################################################
# Summary
################################################################################

print_header "System Status"

echo ""
echo "All remote services started successfully!"
echo ""
echo "Running services:"
echo "  • Orange Pi ($ORANGE_IP): TCP Bridge (Port 5555)"
echo "  • Jetson ($JETSON_IP): YOLO Detection → TCP Client"
echo ""
echo "Next steps:"
echo "  1. Start Webots monitoring: ./start_webots_tahap6.sh"
echo "  2. Start Digital Twin UI: cd Documents/Digital_Twin_Interface && npm run dev"
echo ""
echo "To check logs:"
echo "  • Orange Pi: ssh orange@$ORANGE_IP 'tail -f orange_bridge.log'"
echo "  • Jetson: ssh humanoid@$JETSON_IP 'tail -f yolo.log'"
echo ""
echo "To stop services:"
echo "  • Orange Pi: ssh orange@$ORANGE_IP 'pkill -f orange_tcp_bridge'"
echo "  • Jetson: ssh humanoid@$JETSON_IP 'pkill -f jetson_yolo_tcp'"
echo ""
