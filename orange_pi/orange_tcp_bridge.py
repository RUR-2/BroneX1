#!/usr/bin/env python3
"""
Orange Pi TCP Server + Serial Bridge
====================================
Receives YOLO commands via TCP from Jetson and forwards to ESP32 via serial.
Also publishes telemetry to ROS2 for laptop monitoring.
"""

import socket
import threading
import serial
import time
import os

# Disable incompatible type hash checks (Jazzy -> Humble compatibility)
os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState, BatteryState
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy

class TCPToSerial(Node):
    def __init__(self):
        super().__init__('tcp_serial_bridge')
        
        # Serial connection
        try:
            self.ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
            self.get_logger().info("✓ Serial connected to ESP32")
        except Exception as e:
            self.get_logger().error(f"Serial connection failed: {e}")
            self.ser = None
        
        # Telemetry publishers
        self.battery_pub = self.create_publisher(BatteryState, '/battery_status', 10)
        self.motor_pub = self.create_publisher(JointState, '/motor_status', 10)
        self.velocity_pub = self.create_publisher(Twist, '/robot_velocity', 10)
        
        # State
        self.last_vx = 0.0
        self.last_vy = 0.0
        self.last_w = 0.0
        
        # Logging state
        self.telemetry_count = 0
        
        # Telemetry timer (5Hz to reduce network load)
        self.telemetry_timer = self.create_timer(0.2, self.publish_telemetry)

        # System Enabled State (Start/Stop Program)
        self.system_enabled = True
        self.enable_sub = self.create_subscription(
            Bool,
            '/system/enable',
            self.enable_callback,
            10
        )
        
        # TCP Server
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', 5555))
            self.server_socket.listen(1)
            
            # Start TCP thread
            self.tcp_thread = threading.Thread(target=self.tcp_server_loop, daemon=True)
            self.tcp_thread.start()
            self.get_logger().info("✓ TCP Server Started (Port 5555)")
        except Exception as e:
            self.get_logger().error(f"TCP Server Failed to Start: {e}")
            
        self.get_logger().info("Orange Pi Bridge Ready (TCP Only Mode)")

    def tcp_server_loop(self):
        """TCP server accepting connections from Jetson"""
        while True:
            try:
                self.get_logger().info("Waiting for Jetson connection...")
                client_socket, addr = self.server_socket.accept()
                self.get_logger().info(f"✓ Jetson connected from {addr}")
                
                # Create a file-like object for line buffering
                client_file = client_socket.makefile('r')
                
                while True:
                    # Read line-by-line (properly handles message framing)
                    line = client_file.readline()
                    if not line:
                        break
                    
                    # Parse command (format: "x,y,z\n")
                    try:
                        parts = line.strip().split(',')
                        if len(parts) == 3:
                            x, y, z = map(float, parts)
                            self.process_yolo_command(x, y, z)
                        else:
                            self.get_logger().warn(f"Invalid format: {line.strip()}")
                    except Exception as e:
                        self.get_logger().error(f"Parse error: {e} | Data: {line.strip()}")
                
                client_file.close()
                client_socket.close()
                self.get_logger().warn("Jetson disconnected")
                
            except Exception as e:
                self.get_logger().error(f"TCP error: {e}")
                time.sleep(1)

    def enable_callback(self, msg):
        """Handle enabling/disabling of robot"""
        self.system_enabled = msg.data
        status = "ENABLED" if self.system_enabled else "DISABLED"
        self.get_logger().warn(f"System State Changed: {status}")
        
        if not self.system_enabled:
            # Emergency Stop
            self.send_robot_command(0, 0, 0)

    def send_robot_command(self, vx, vy, w):
        """Send command to ESP32 (vx, vy, w are centered at 0)"""
        # Boolean rotation buttons logic
        b6 = 0
        b7 = 0
        if w > 0.1:
            b6 = 0
            b7 = 1
        elif w < -0.1:
            b6 = 1
            b7 = 0
        
        # Convert to PWM (0-255, 127 is stop)
        x_val = int(max(0, min(255, vy + 127)))
        y_val = int(max(0, min(255, vx + 127)))
        
        packet = f"<{x_val},{y_val},{b6},{b7}>\n"
        
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(packet.encode('utf-8'))
                
                # Update state for telemetry (Speed 63 Normalization)
                self.last_vx = vx / 63.0
                self.last_vy = vy / 63.0
                self.last_w = w / 5.0
                
            except Exception as e:
                self.get_logger().error(f"Serial write error: {e}")

    def process_yolo_command(self, x, y, z):
        """Process YOLO command (TCP)"""
        # Check if system is enabled
        if not self.system_enabled:
            return

        # Half speed requested: 127 -> 63
        Vx = y * 63   # Was 28
        Vy = x * 63   # Was 28
        W = z * 5.0   # Rotation unchanged
        
        if abs(Vx) < 5: Vx = 0
        if abs(Vy) < 5: Vy = 0
        
        self.send_robot_command(Vx, Vy, W)
    
    def publish_telemetry(self):
        """Publish telemetry for laptop monitoring"""
        
        # Heartbeat
        self.telemetry_count += 1
        if self.telemetry_count % 25 == 0:
            self.get_logger().info(f"System Active (TCP Mode) | Vx={self.last_vx:.2f}, Vy={self.last_vy:.2f}")
            
        # Battery
        battery_msg = BatteryState()
        battery_msg.header.stamp = self.get_clock().now().to_msg()
        battery_msg.header.frame_id = "base_link"
        battery_msg.location = "slot1"
        battery_msg.serial_number = "1234"
        battery_msg.voltage = 24.0
        battery_msg.current = abs(self.last_vx + self.last_vy) * 10.0
        battery_msg.percentage = 100.0
        battery_msg.present = True
        self.battery_pub.publish(battery_msg)
        
        # Motors
        motor_msg = JointState()
        motor_msg.header.stamp = self.get_clock().now().to_msg()
        motor_msg.header.frame_id = "base_link"
        motor_msg.name = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        motor_msg.position = []
        
        # Calculate individual wheel speeds (Mecanum Kinematics)
        # Mapping:
        # 1: FL (Front Left)  = Vx + Vy + W
        # 2: FR (Front Right) = Vx - Vy - W
        # 3: RL (Rear Left)   = Vx - Vy + W
        # 4: RR (Rear Right)  = Vx + Vy - W
        
        # Telemetry: Invert VX/VY for ROS/Webots (Physical Robot is correct, Webots is inverted)
        vx = -self.last_vx * 10.0  # INVERTED
        vy = -self.last_vy * 10.0  # INVERTED
        w  = self.last_w  * 10.0

        v1 = vx + vy + w  # FL
        v2 = vx - vy - w  # FR
        v3 = vx - vy + w  # RL
        v4 = vx + vy - w  # RR
        
        motor_msg.velocity = [float(v1), float(v2), float(v3), float(v4)]
        
        # Simulated Torque (Effort) based on velocity
        # Ideally this would come from motor drivers, but we estimate it
        motor_msg.effort = [
            abs(float(v1)) * 2.0,
            abs(float(v2)) * 2.0,
            abs(float(v3)) * 2.0,
            abs(float(v4)) * 2.0
        ]
        
        self.motor_pub.publish(motor_msg)
        
        # Velocity
        velocity_msg = Twist()
        velocity_msg.linear.x = -self.last_vx  # INVERTED
        velocity_msg.linear.y = -self.last_vy  # INVERTED
        velocity_msg.linear.z = 0.0
        velocity_msg.angular.x = 0.0
        velocity_msg.angular.y = 0.0
        velocity_msg.angular.z = self.last_w
        self.velocity_pub.publish(velocity_msg)


def main(args=None):
    rclpy.init(args=args)
    node = TCPToSerial()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
