#!/bin/bash

# =============================================================================
# BRONE DIGITAL TWIN - TAHAP 6 MONITORING SYSTEM (EXTERN MODE)
# =============================================================================
# Starts complete monitoring system with extern controller:
# - WebSocket Relay Server
# - Digital Twin Web Interface  
# - Webots Simulator
# - Tahap 6 Monitoring Controller (Extern)
# =============================================================================

# === CONFIGURATION ===
WS_SERVER_DIR="/home/codename-hydra/Documents/Digital_Twin_Interface"
WS_SERVER_FILE="ws_server.py"
WS_SERVER_PORT="8765"

CONTROLLER_DIR="/home/codename-hydra/Documents/BroneRoda/controllers/Diter_Roda_Tahap6_YOLO_WS_Bridge"
CONTROLLER_FILE="Diter_Roda_Tahap6_YOLO_WS_Bridge.py"

DDS_CONFIG="file:///home/codename-hydra/Documents/cyclonedds.xml"

export WEBOTS_HOME="/home/codename-hydra/webots"
WEBOTS_WORLD="/home/codename-hydra/Documents/BroneRoda/worlds/BroneRodaEstimationClosedBeta.wbt"

export PYTHONPATH=${WEBOTS_HOME}/lib/controller/python:$PYTHONPATH
export LD_LIBRARY_PATH=${WEBOTS_HOME}/lib/controller:$LD_LIBRARY_PATH

echo "🚀 MELUNCURKAN SISTEM TAHAP 6 MONITORING (EXTERN MODE)..."
echo "📡 Urutan Startup:"
echo "   1️⃣  WebSocket Server (Port $WS_SERVER_PORT)"
echo "   2️⃣  Web Interface (http://localhost:5173)"
echo "   3️⃣  Webots Simulator"
echo "   4️⃣  Tahap 6 Monitoring Controller (Extern)"
echo ""

# TAB 1: WEBSOCKET SERVER
gnome-terminal --tab --title="WEBSOCKET SERVER" -- bash -c "
    echo '🌐 Starting WebSocket Server...';
    cd '$WS_SERVER_DIR';
    python3 '$WS_SERVER_FILE';
    exec bash"

echo "⏳ Menunggu WebSocket Server (2 detik)..."
sleep 2

# TAB 2: WEB INTERFACE
gnome-terminal --tab --title="WEB INTERFACE" -- bash -c "
    echo '🌐 Starting Web Interface...';
    export NVM_DIR=\"\$HOME/.nvm\";
    [ -s \"\$NVM_DIR/nvm.sh\" ] && \\. \"\$NVM_DIR/nvm.sh\";
    cd '/home/codename-hydra/Documents/Digital_Twin_Interface';
    npm run dev -- --host;
    exec bash"

echo "⏳ Menunggu Web Interface (2 detik)..."
sleep 2

# TAB 3: TAHAP 6 MONITORING CONTROLLER (EXTERN MODE) - START FIRST!
gnome-terminal --tab --title="TAHAP 6 MONITOR" -- bash -c "
    echo 'Mengaktifkan Tahap 6 Monitoring Controller (Extern Mode)...';
    echo 'Controller will wait for Webots connection...';
    source /opt/ros/jazzy/setup.bash;
    
    # --- SETUP JARINGAN ROS ---
    export ROS_DOMAIN_ID=10;
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp;
    export CYCLONEDDS_URI='$DDS_CONFIG';
    
    cd '$CONTROLLER_DIR';
    export WEBOTS_HOME='$WEBOTS_HOME';
    export PYTHONPATH=\${WEBOTS_HOME}/lib/controller/python:\$PYTHONPATH;
    export LD_LIBRARY_PATH=\${WEBOTS_HOME}/lib/controller:\$LD_LIBRARY_PATH;
    
    # Extern mode: Connect to BroneRobot via IPC
    export WEBOTS_CONTROLLER_URL=ipc://1234/BroneRobot;
    
    # --- AUTO-RESPAWN LOOP ---
    while true; do
        echo '>> Memulai Tahap 6 Monitoring Controller...';
        echo '>> Waiting for Webots to start...';
        python3 '$CONTROLLER_FILE'
        
        echo '>> Webots Reset terdeteksi. Respawn dalam 2 detik...';
        sleep 2;
    done
    exec bash"

echo "⏳ Menunggu Controller ready (3 detik)..."
sleep 3

# TAB 4: WEBOTS SIMULATOR - START AFTER CONTROLLER
gnome-terminal --tab --title="WEBOTS SIM" -- bash -c "
    echo 'Starting Webots - will auto-connect to waiting controller...';
    source /opt/ros/jazzy/setup.bash;
    export ROS_DOMAIN_ID=10;
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp;
    export CYCLONEDDS_URI='$DDS_CONFIG';
    $WEBOTS_HOME/webots '$WEBOTS_WORLD';
    exec bash"

echo "✅ SISTEM TAHAP 6 SIAP! (EXTERN MODE)"
echo ""
echo "Components:"
echo "  • WebSocket Server: localhost:8765"
echo "  • Web Interface: Check terminal"
echo "  • Webots: Running with <extern> controller"
echo "  • Controller: Auto-respawn extern mode"
echo ""
echo "📊 Monitoring:"
echo "  - Subscribe telemetry from Orange Pi"
echo "  - Visualize in Webots"
echo "  - Broadcast to Digital Twin Interface"
echo ""
