#!/usr/bin/env python3
"""
BroneRoda Remote Startup - Python Version
Uses PTY for SSH automation (no sshpass required)
"""

import pty
import os
import time
import sys

# Configuration
JETSON_IP = "10.30.117.199"
JETSON_USER = "humanoid"
JETSON_PASS = "111111"

ORANGE_IP = "10.30.117.200"
ORANGE_USER = "orange"
ORANGE_PASS = "111111"

# Local paths
ORANGE_SCRIPT = "/home/codename-hydra/Downloads/orange_tcp_bridge.py"
JETSON_SCRIPT = "/home/codename-hydra/Downloads/jetson_yolo_tcp.py"

# Colors
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'

def print_header(text):
    print(f"\n{'='*50}")
    print(text)
    print('='*50)

def print_status(text):
    print(f"{GREEN}✓{NC} {text}")

def print_error(text):
    print(f"{RED}✗{NC} {text}")

def read_output(fd, duration=2):
    time.sleep(duration)
    try:
        return os.read(fd, 10240).decode('utf-8', errors='ignore')
    except OSError:
        return ""

def ssh_exec(user, ip, password, commands):
    """Execute commands via SSH using pty"""
    pid, fd = pty.fork()
    
    if pid == 0:
        # Child process
        os.execlp("ssh", "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{ip}")
        sys.exit(0)
    
    # Parent process
    try:
        # Login
        out = read_output(fd, 3)
        if "password" in out.lower():
            os.write(fd, (password + "\n").encode())
            out = read_output(fd, 2)
        
        if "denied" in out.lower():
            return False
        
        # Execute commands
        for cmd in commands:
            os.write(fd, (cmd + "\n").encode())
            time.sleep(0.5)
        
        time.sleep(2)
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        try:
            os.close(fd)
        except:
            pass

def deploy_file(user, ip, password, local_path, remote_filename):
    """Deploy file using cat via SSH"""
    if not os.path.exists(local_path):
        print_error(f"Local file not found: {local_path}")
        return False
    
    with open(local_path, 'r') as f:
        content = f.read()
    
    pid, fd = pty.fork()
    
    if pid == 0:
        os.execlp("ssh", "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{ip}")
        sys.exit(0)
    
    try:
        # Login
        out = read_output(fd, 3)
        if "password" in out.lower():
            os.write(fd, (password + "\n").encode())
            out = read_output(fd, 2)
        
        # Upload using cat
        EOF = "EOF_DEPLOY"
        os.write(fd, f"cat > {remote_filename} << '{EOF}'\n".encode())
        
        # Write content in chunks
        chunk_size = 1024
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i+chunk_size]
            os.write(fd, chunk.encode())
            time.sleep(0.01)
        
        os.write(fd, b"\n")
        os.write(fd, (EOF + "\n").encode())
        time.sleep(2)
        
        return True
        
    except Exception as e:
        print_error(f"Deploy failed: {e}")
        return False
    finally:
        try:
            os.close(fd)
        except:
            pass

def main():
    print_header("BroneRoda Remote Startup (Python)")
    
    # Orange Pi
    print_header("Setting up Orange Pi")
    
    print("Cleaning old processes...")
    ssh_exec(ORANGE_USER, ORANGE_IP, ORANGE_PASS, [
        "pkill -f orange_tcp_bridge || true",
        "pkill -f start_orange_pi || true"
    ])
    print_status("Processes cleared")
    
    print("Deploying script...")
    if deploy_file(ORANGE_USER, ORANGE_IP, ORANGE_PASS, ORANGE_SCRIPT, "orange_tcp_bridge.py"):
        print_status("Script deployed")
    else:
        print_error("Deploy failed")
        return
    
    print("Starting bridge service...")
    ssh_exec(ORANGE_USER, ORANGE_IP, ORANGE_PASS, [
        "nohup python3 orange_tcp_bridge.py > orange_bridge.log 2>&1 &",
        "sleep 1",
        "echo 'Service started'"
    ])
    print_status("Orange Pi bridge started")
    
    # Jetson
    print_header("Setting up Jetson")
    
    print("Cleaning old processes...")
    ssh_exec(JETSON_USER, JETSON_IP, JETSON_PASS, [
        "pkill -f jetson_yolo_tcp || true",
        "pkill -f python3 || true"
    ])
    print_status("Processes cleared")
    
    print("Deploying YOLO script...")
    if deploy_file(JETSON_USER, JETSON_IP, JETSON_PASS, JETSON_SCRIPT, "jetson_yolo_tcp.py"):
        print_status("Script deployed")
    else:
        print_error("Deploy failed")
        return
    
    print("Starting YOLO service...")
    ssh_exec(JETSON_USER, JETSON_IP, JETSON_PASS, [
        "nohup python3 jetson_yolo_tcp.py > yolo.log 2>&1 &",
        "sleep 1",
        "echo 'Service started'"
    ])
    print_status("Jetson YOLO started")
    
    # Summary
    print_header("System Status")
    print("\n✓ All remote services started!")
    print(f"\nRunning services:")
    print(f"  • Orange Pi ({ORANGE_IP}): TCP Bridge (Port 5555)")
    print(f"  • Jetson ({JETSON_IP}): YOLO Detection")
    print(f"\nNext steps:")
    print(f"  1. Start Webots: ./start_webots_tahap6.sh")
    print(f"  2. Start Digital Twin: cd Documents/Digital_Twin_Interface && npm run dev")
    print()

if __name__ == "__main__":
    main()
