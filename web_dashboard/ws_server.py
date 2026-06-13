#!/usr/bin/env python3
"""
Digital Twin WebSocket Server
Broadcasts real-time robot telemetry data to web interface
"""

import asyncio
import json
import time
import websockets
from datetime import datetime

class DigitalTwinServer:
    """WebSocket server for broadcasting robot data"""
    
    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.controller_client = None  # Track the controller connection
        self.latest_data = None
        
        # Simulated data for testing (will be replaced with real controller data)
        self.mock_data = {
            "timestamp": 0,
            "electrical": {
                "voltage": 22.2,
                "current": 1.2,
                "power": 26.6,
                "cell_voltage": 3.7
            },
            "battery": {
                "soc": 100.0,
                "runtime_hours": 24.0
            },
            "motors": {
                "torques": {
                    "FL": 0.0,
                    "FR": 0.0,
                    "RL": 0.0,
                    "RR": 0.0
                },
                "rpm": {
                    "FL": 0,
                    "FR": 0,
                    "RL": 0,
                    "RR": 0
                },
                "avg_rpm": 0
            },
            "motion": {
                "vx": 0.0,
                "vy": 0.0,
                "w": 0.0
            },
            "system": {
                "uptime": 0.0,
                "ping_ms": 0
            }
        }
    
    async def register(self, websocket):
        """Register new client"""
        self.clients.add(websocket)
        print(f"[+] Client connected: {websocket.remote_address}")
        print(f"    Total clients: {len(self.clients)}")
        
        # Send initial data
        if self.latest_data:
            await websocket.send(json.dumps(self.latest_data))
    
    async def unregister(self, websocket):
        """Unregister client"""
        self.clients.remove(websocket)
        print(f"[-] Client disconnected: {websocket.remote_address}")
        print(f"    Total clients: {len(self.clients)}")
    
    async def broadcast(self, data):
        """Broadcast data to all connected clients"""
        if self.clients:
            message = json.dumps(data)
            # Create tasks for all sends
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )
    
    async def handle_client(self, websocket, path):
        """Handle individual client connection"""
        await self.register(websocket)
        try:
            # Keep connection alive and handle incoming messages
            async for message in websocket:
                try:
                    # Try to parse as JSON
                    data = json.loads(message)
                    
                    # Check if this is telemetry data from controller
                    if "electrical" in data and "motors" in data:
                        # This is controller telemetry, store and broadcast
                        self.latest_data = data
                        # Mark this connection as the controller
                        if self.controller_client != websocket:
                            self.controller_client = websocket
                            print(f"[CTRL] Controller identified: {websocket.remote_address}")
                        print(f"[DATA] Received from controller: Battery {data['battery']['soc']:.1f}%, "
                              f"Power {data['electrical']['power']:.1f}W")
                    
                    # Check if this is a command from web client
                    elif "command" in data:
                        command = data.get("command")
                        print(f"[CMD] Command received from web client: {command}")
                        print(f"[CMD] Current controller_client: {self.controller_client}")
                        print(f"[CMD] Current websocket: {websocket}")
                        print(f"[CMD] Are they different? {self.controller_client != websocket}")
                        
                        # Relay command to controller if connected
                        if self.controller_client and self.controller_client != websocket:
                            try:
                                message_to_send = json.dumps(data)
                                print(f"[CMD] Sending to controller: {message_to_send}")
                                await self.controller_client.send(message_to_send)
                                print(f"[CMD] ✅ Successfully relayed command to controller: {command}")
                            except Exception as e:
                                print(f"[ERR] ❌ Failed to relay command to controller: {e}")
                        else:
                            print(f"[WARN] ⚠️ No controller connected to receive command")
                            print(f"[WARN]    controller_client is None: {self.controller_client is None}")
                            if self.controller_client:
                                print(f"[WARN]    controller_client == websocket: {self.controller_client == websocket}")
                    
                    else:
                        # Regular message (ping/echo)
                        await websocket.send(message)
                        
                except json.JSONDecodeError:
                    # Not JSON, just echo back for ping/pong
                    await websocket.send(message)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            # Clear controller reference if this was the controller
            if websocket == self.controller_client:
                self.controller_client = None
                print("[CTRL] Controller disconnected")
            await self.unregister(websocket)
    
    async def data_generator(self):
        """Generate/update robot data (hybrid mode: real + fallback to mock)"""
        start_time = time.time()
        last_real_data_time = 0
        data_timeout = 2.0  # If no real data for 2s, show "waiting" status
        
        while True:
            current_time = time.time()
            
            # Update mock data timestamp and uptime
            self.mock_data["timestamp"] = current_time
            self.mock_data["system"]["uptime"] = current_time - start_time
            
            # Determine which data to broadcast
            if self.latest_data and "electrical" in self.latest_data:
                # We have real controller data
                data_age = current_time - last_real_data_time
                
                # Update timestamp for real data
                self.latest_data["timestamp"] = current_time
                
                await self.broadcast(self.latest_data)
            else:
                # No real data yet, use mock data
                await self.broadcast(self.mock_data)
            
            # Update at 5Hz (200ms)
            await asyncio.sleep(0.2)

    
    async def start(self):
        """Start WebSocket server"""
        print("=" * 50)
        print("Digital Twin WebSocket Server")
        print("=" * 50)
        print(f"Host: {self.host}")
        print(f"Port: {self.port}")
        print(f"URL:  ws://{self.host}:{self.port}")
        print("=" * 50)
        print("\nWaiting for connections...")
        
        # Start server and data generator concurrently
        async with websockets.serve(self.handle_client, self.host, self.port):
            await self.data_generator()

def main():
    """Main entry point"""
    server = DigitalTwinServer(host='localhost', port=8765)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\n[!] Server stopped by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")

if __name__ == "__main__":
    main()
