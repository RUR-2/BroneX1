"""
DSC Wanderer Webots Controller
==============================
Subscribe /cmd_vel_dsc dari dsc_wanderer_node dan gerakkan
robot BRONE di Webots simulator.

Setup:
  1. Jalankan dsc_wanderer_node.py di WSL
  2. Set controller robot di Webots ke: dsc_wanderer_webots
  3. Jalankan simulasi Webots

Topics yang digunakan:
  /cmd_vel_dsc  (geometry_msgs/Twist)  — input velocity dari DSC node
  /dsc/state    (std_msgs/String)      — state display di console
"""

import os
import sys
import threading
from controller import Robot

# ROS2
try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from std_msgs.msg import String
except ImportError:
    print("ERROR: ROS2 tidak tersedia. Source dulu: source /opt/ros/jazzy/setup.bash")
    sys.exit(1)


class DSCSubscriber(Node):
    """ROS2 node untuk subscribe cmd_vel dari DSC Wanderer"""

    def __init__(self):
        super().__init__('dsc_webots_bridge')

        self.vx = 0.0
        self.vy = 0.0
        self.w  = 0.0
        self.state = "IDLE"

        self.create_subscription(
            Twist, '/cmd_vel_dsc', self._cmd_cb, 10
        )
        self.create_subscription(
            String, '/dsc/state', self._state_cb, 10
        )

        self.get_logger().info("DSC Webots Bridge — menunggu /cmd_vel_dsc ...")

    def _cmd_cb(self, msg: Twist):
        self.vx = msg.linear.x
        self.vy = msg.linear.y
        self.w  = msg.angular.z

    def _state_cb(self, msg: String):
        self.state = msg.data


class DSCWebotsController:
    """Webots controller yang gerakkan robot dari DSC Wanderer output"""

    # Kinematik mecanum (sama dengan tracker_controller)
    L       = 0.208   # half-width + half-length (m)
    R_WHEEL = 0.06    # wheel radius (m)
    SIN_A   = 0.7071
    COS_A   = 0.7071
    MAX_SPD = 46.0    # rad/s max wheel speed
    INV     = -1.0    # invert semua roda (kalibrasi BRONE)

    def __init__(self):
        # Webots init
        self.robot    = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # Motor setup
        self.wheels = []
        for name in ['wheel1', 'wheel2', 'wheel3', 'wheel4']:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            self.wheels.append(m)

        # ROS2 init
        if not rclpy.ok():
            rclpy.init()

        self.ros_node = DSCSubscriber()
        self.ros_thread = threading.Thread(
            target=lambda: rclpy.spin(self.ros_node), daemon=True
        )
        self.ros_thread.start()

        print("\n" + "="*50)
        print("DSC Wanderer Webots Controller — READY")
        print("="*50)
        print("Menunggu perintah dari dsc_wanderer_node ...")
        print("Pastikan node sudah aktif dengan mode WANDERER\n")

    def _inverse_kinematics(self, vx, vy, w):
        """Hitung kecepatan roda dari velocity robot (mecanum)"""
        r = self.R_WHEEL
        w1 = (-self.COS_A * vx + self.SIN_A * vy + self.L * w) / r
        w2 = (-self.COS_A * vx - self.SIN_A * vy + self.L * w) / r
        w3 = ( self.COS_A * vx - self.SIN_A * vy + self.L * w) / r
        w4 = ( self.COS_A * vx + self.SIN_A * vy + self.L * w) / r
        return [w1, w2, w3, w4]

    def _clamp(self, val):
        return max(-self.MAX_SPD, min(self.MAX_SPD, val))

    def run(self):
        last_print = 0.0

        while self.robot.step(self.timestep) != -1:
            vx = self.ros_node.vx
            vy = self.ros_node.vy
            w  = self.ros_node.w

            # Hitung wheel velocities
            wheel_vels = self._inverse_kinematics(vx, vy, w)

            # Set ke motor dengan inversi kalibrasi
            for i, wheel in enumerate(self.wheels):
                wheel.setVelocity(self._clamp(wheel_vels[i] * self.INV))

            # Print state tiap 1 detik
            t = self.robot.getTime()
            if t - last_print >= 1.0:
                state = self.ros_node.state.split('|')[0].strip() if '|' in self.ros_node.state else self.ros_node.state
                print(f"[t={t:6.1f}s] {state} | vx={vx:+.2f} vy={vy:+.2f} w={w:+.2f}")
                last_print = t

    def __del__(self):
        try:
            self.ros_node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except:
            pass


if __name__ == "__main__":
    controller = DSCWebotsController()
    controller.run()
