#!/bin/bash

# === KONFIGURASI WEBSOCKET SERVER (LAPTOP) ===
WS_SERVER_DIR="/home/codename-hydra/Documents/Digital_Twin_Interface"
WS_SERVER_FILE="ws_server.py"
WS_SERVER_PORT="8765"

# === KONFIGURASI ROBOT (ORANGE PI) ===
ROBOT_USER="orange"
ROBOT_IP="10.30.117.200"
ROBOT_SCRIPT="/home/orange/nyalakan_robot.sh"

# === KONFIGURASI CONTROLLER (LAPTOP) ===
CONTROLLER_DIR="/home/codename-hydra/Documents/BroneRoda/controllers/Diter_Roda_Tahap5_WS_Bridge"
CONTROLLER_FILE="DITER_Roda_ROS_WS_Bridge.py"

# === KONFIGURASI XML DDS (PENTING!) ===
# Pastikan path ini menunjuk ke file XML yang baru diedit
DDS_CONFIG="file:///home/codename-hydra/Documents/cyclonedds.xml"

# === KONFIGURASI WEBOTS (LAPTOP) ===
export WEBOTS_HOME="/home/codename-hydra/webots"
WEBOTS_WORLD="/home/codename-hydra/Documents/BroneRoda/worlds/BroneRodaEstimationClosedBeta.wbt"

# === SETUP ENVIRONMENT ===
export PYTHONPATH=${WEBOTS_HOME}/lib/controller/python:$PYTHONPATH
export LD_LIBRARY_PATH=${WEBOTS_HOME}/lib/controller:$LD_LIBRARY_PATH

echo "🚀 MELUNCURKAN SISTEM BRONE (AUTO-RESPAWN MODE)..."
echo "📡 Urutan Startup:"
echo "   1️⃣  WebSocket Server (Port $WS_SERVER_PORT)"
echo "   2️⃣  Web Interface (http://localhost:5173)"
echo "   3️⃣  Robot Fisik (SSH)"
echo "   4️⃣  Webots Simulator"
echo "   5️⃣  DITER Controller Bridge"
echo ""

# TAB 1: WEBSOCKET SERVER (INDEPENDENT)
# Server harus jalan dulu sebelum controller connect
gnome-terminal --tab --title="WEBSOCKET SERVER" -- bash -c "
    echo '🌐 Starting WebSocket Server...';
    cd '$WS_SERVER_DIR';
    python3 '$WS_SERVER_FILE';
    exec bash"

echo "⏳ Menunggu WebSocket Server (2 detik)..."
sleep 2

# TAB 2: WEB INTERFACE
# Menjalankan frontend Vite
gnome-terminal --tab --title="WEB INTERFACE" -- bash -c "
    echo '🌐 Starting Web Interface...';
    # Load NVM untuk mendapatkan akses ke npm
    export NVM_DIR=\"\$HOME/.nvm\";
    [ -s \"\$NVM_DIR/nvm.sh\" ] && \\. \"\$NVM_DIR/nvm.sh\";
    cd '/home/codename-hydra/Documents/Digital_Twin_Interface';
    npm run dev -- --host;
    exec bash"

echo "⏳ Menunggu Web Interface (2 detik)..."
sleep 2

# TAB 3: ROBOT ASLI (SSH)
# Robot akan menyala otomatis via SSH
gnome-terminal --tab --title="REAL ROBOT" -- bash -c "ssh -t $ROBOT_USER@$ROBOT_IP '$ROBOT_SCRIPT'; exec bash"

echo "⏳ Menunggu Robot (2 detik)..."
sleep 2

# TAB 4: WEBOTS
# Memuat ROS Jazzy agar Clock Sinkron + Load DDS XML
gnome-terminal --tab --title="WEBOTS SIM" -- bash -c "
    source /opt/ros/jazzy/setup.bash; 
    export ROS_DOMAIN_ID=10;
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp;
    export CYCLONEDDS_URI='$DDS_CONFIG';
    $WEBOTS_HOME/webots '$WEBOTS_WORLD'; 
    exec bash"

echo "⏳ Menunggu Webots loading (5 detik)..."
sleep 5

# TAB 5: CONTROLLER OTAK (AUTO-RESPAWN LOOP)
# Bagian ini akan menghidupkan Python lagi setiap kali dia mati/reset
gnome-terminal --tab --title="DITER DASHBOARD" -- bash -c "
    echo 'Mengaktifkan Controller dengan ROS_DOMAIN_ID=10...';
    source /opt/ros/jazzy/setup.bash;  
    
    # --- SETUP JARINGAN ROS (FIXED) ---
    export ROS_DOMAIN_ID=10;
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp;
    export CYCLONEDDS_URI='$DDS_CONFIG';
    
    cd '$CONTROLLER_DIR';
    export WEBOTS_HOME='$WEBOTS_HOME';
    export PYTHONPATH=\${WEBOTS_HOME}/lib/controller/python:\$PYTHONPATH;
    export LD_LIBRARY_PATH=\${WEBOTS_HOME}/lib/controller:\$LD_LIBRARY_PATH;
    
    # Tembak ke Robot bernama 'BroneRobot'
    export WEBOTS_CONTROLLER_URL=ipc://1234/BroneRobot;
    
    # --- LOOP INFINITE ---
    while true; do
        echo '>> Memulai DITER Controller...'
        python3 '$CONTROLLER_FILE'
        
        echo '>> Webots Reset terdeteksi. Respawn dalam 2 detik...'
        sleep 2
    done
    exec bash"

echo "✅ SISTEM SIAP! SILAKAN RESET SEPUASNYA."