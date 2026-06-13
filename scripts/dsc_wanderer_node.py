#!/usr/bin/env python3
"""
DSC Wanderer Node — Autonomous Dynamical System Navigation
===========================================================
Implements a Modulated Dynamical System for smooth, autonomous
random wandering on the omnidirectional BRONE platform.

Architecture:
  - Resample a random attractor goal (ξ*) in a bounded arena
  - Nominal DS: ξ̇_nom = -κ(ξ - ξ*)
  - No obstacle modulation yet (no sensor input) — pure wandering
  - EMA smoothing to prevent jittery velocity commands
  - Publishes geometry_msgs/Twist to /cmd_vel_dsc (consumed by Orange Pi bridge)
  - Listens to /dsc/mode (std_msgs/String) to activate/deactivate

Usage:
  source /opt/ros/jazzy/setup.bash
  export ROS_DOMAIN_ID=10
  export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  python3 dsc_wanderer_node.py

Topics published:
  /cmd_vel_dsc   (geometry_msgs/Twist)  — velocity commands for Orange Pi bridge
  /dsc/state     (std_msgs/String)      — current DSC state for dashboard

Topics subscribed:
  /dsc/mode      (std_msgs/String)      — "WANDERER" | "STOP"
  /robot_velocity (geometry_msgs/Twist) — current robot velocity (odometry est.)

Author: BroneX1 Social Nav Team
Version: 1.0 — Pure DS Wanderer (no obstacle layer)
"""

import os
import math
import time
import random
import threading

os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String

# ─────────────────────────────────────────────
# Tunable Parameters
# ─────────────────────────────────────────────
class DSCConfig:
    # ── Arena bounds (metres, robot-relative coordinate system)
    # The robot treats its starting pose as origin (0,0).
    # These bounds define how far a random goal can be sampled.
    ARENA_X_MIN = -1.5      # metres
    ARENA_X_MAX =  1.5
    ARENA_Y_MIN = -1.5
    ARENA_Y_MAX =  1.5

    # ── DS gain κ: how aggressively robot accelerates toward goal
    # Higher κ → faster response, but can overshoot at low loop rates
    KAPPA = 0.8             # [1/s]

    # ── Goal tolerance: distance below which we resample a new goal
    GOAL_TOLERANCE = 0.12   # metres

    # ── Maximum output velocities (will be clipped to these)
    MAX_VX = 0.35           # m/s
    MAX_VY = 0.35           # m/s
    MAX_W  = 0.6            # rad/s

    # ── EMA smoothing factor α (0 = no update, 1 = no smoothing)
    # Lower → smoother but more lag; recommended 0.15–0.35
    EMA_ALPHA = 0.25

    # ── Goal resample timeout: even if goal not reached, resample after N seconds
    GOAL_TIMEOUT_SEC = 8.0

    # ── Heading behaviour
    # "GOAL"     — robot always faces toward the current DS goal
    # "FREE"     — robot heading drifts slowly (good for mascot wandering feel)
    # "FIXED"    — heading stays at 0 (robot always faces forward)
    HEADING_MODE = "GOAL"

    # ── Slow heading gain (used in FREE mode)
    HEADING_GAIN = 0.3      # [rad/s per rad error]

    # ── Control loop rate
    LOOP_HZ = 20.0          # Hz


class DSCWandererNode(Node):
    """
    Autonomous DS Wanderer for BRONE omnidirectional platform.

    State machine:
        IDLE   → waiting for /dsc/mode = "WANDERER"
        MOVING → DS active, heading toward current attractor
        PAUSED → /dsc/mode = "STOP" received, publishes zero velocity
    """

    def __init__(self):
        super().__init__('dsc_wanderer_node')
        self.cfg = DSCConfig()

        # ── Internal state ──────────────────────────────────────
        self.mode = "IDLE"              # IDLE | MOVING | PAUSED
        self.pos_x = 0.0               # Estimated position X (from velocity integration)
        self.pos_y = 0.0               # Estimated position Y
        self.heading = 0.0             # Estimated heading (rad)

        self.goal_x = 0.0              # Current DS attractor X
        self.goal_y = 0.0              # Current DS attractor Y
        self.goal_sampled_at = 0.0     # time.time() when goal was last sampled

        # Smoothed velocity outputs (EMA state)
        self.smooth_vx = 0.0
        self.smooth_vy = 0.0
        self.smooth_w  = 0.0

        # Last odometry update time (for integration)
        self.last_odom_time = time.time()
        self.odom_vx = 0.0
        self.odom_vy = 0.0
        self.odom_w  = 0.0

        self._lock = threading.Lock()

        # ── ROS2 publishers ─────────────────────────────────────
        self.cmd_pub = self.create_publisher(
            Twist, '/cmd_vel_dsc', 10
        )
        self.state_pub = self.create_publisher(
            String, '/dsc/state', 10
        )

        # ── ROS2 subscribers ────────────────────────────────────
        self.mode_sub = self.create_subscription(
            String, '/dsc/mode',
            self._mode_callback, 10
        )
        self.odom_sub = self.create_subscription(
            Twist, '/robot_velocity',
            self._odom_callback, 10
        )

        # ── Control loop timer ──────────────────────────────────
        period = 1.0 / self.cfg.LOOP_HZ
        self.timer = self.create_timer(period, self._control_loop)

        # Sample initial goal (won't be used until mode = WANDERER)
        self._resample_goal()

        self.get_logger().info("=" * 50)
        self.get_logger().info("DSC Wanderer Node — READY")
        self.get_logger().info(f"  Arena : [{self.cfg.ARENA_X_MIN},{self.cfg.ARENA_X_MAX}] x "
                               f"[{self.cfg.ARENA_Y_MIN},{self.cfg.ARENA_Y_MAX}] m")
        self.get_logger().info(f"  κ     : {self.cfg.KAPPA}")
        self.get_logger().info(f"  EMA α : {self.cfg.EMA_ALPHA}")
        self.get_logger().info(f"  Loop  : {self.cfg.LOOP_HZ} Hz")
        self.get_logger().info("Send to /dsc/mode → 'WANDERER' to start")
        self.get_logger().info("=" * 50)

    # ────────────────────────────────────────────────────────────
    # Callbacks
    # ────────────────────────────────────────────────────────────

    def _mode_callback(self, msg: String):
        """Handle mode change from /dsc/mode topic."""
        new_mode = msg.data.strip().upper()

        with self._lock:
            if new_mode == "WANDERER" and self.mode != "MOVING":
                self.mode = "MOVING"
                self._resample_goal()
                self.get_logger().info("▶ DSC WANDERER MODE ACTIVATED")

            elif new_mode == "STOP" and self.mode != "PAUSED":
                self.mode = "PAUSED"
                # Immediately publish stop
                self._publish_zero()
                self.get_logger().info("■ DSC WANDERER PAUSED")

            elif new_mode == "IDLE":
                self.mode = "IDLE"
                self._publish_zero()
                self.get_logger().info("◉ DSC WANDERER IDLE")

    def _odom_callback(self, msg: Twist):
        """
        Receive robot velocity from Orange Pi telemetry and integrate
        to estimate robot position (dead-reckoning).

        Note: /robot_velocity publishes INVERTED vx/vy (see orange_tcp_bridge.py),
        so we re-invert here to get actual robot-frame velocity.
        """
        now = time.time()
        dt = now - self.last_odom_time
        self.last_odom_time = now

        # Orange Pi publishes inverted values for Webots display — undo that
        actual_vx = -msg.linear.x
        actual_vy = -msg.linear.y
        actual_w  =  msg.angular.z

        with self._lock:
            self.odom_vx = actual_vx
            self.odom_vy = actual_vy
            self.odom_w  = actual_w

            # Dead-reckoning: integrate velocity in world frame
            # Robot heading rotates the body-frame velocity to world frame
            cos_h = math.cos(self.heading)
            sin_h = math.sin(self.heading)

            world_vx = actual_vx * cos_h - actual_vy * sin_h
            world_vy = actual_vx * sin_h + actual_vy * cos_h

            self.pos_x   += world_vx * dt
            self.pos_y   += world_vy * dt
            self.heading += actual_w  * dt

            # Wrap heading to [-π, π]
            self.heading = math.atan2(math.sin(self.heading), math.cos(self.heading))

    # ────────────────────────────────────────────────────────────
    # Core DS Control Loop
    # ────────────────────────────────────────────────────────────

    def _control_loop(self):
        """Main 20 Hz DS control loop."""
        with self._lock:
            mode = self.mode

        if mode == "IDLE":
            return

        if mode == "PAUSED":
            self._publish_zero()
            self._publish_state("PAUSED | goal=({:.2f},{:.2f})".format(
                self.goal_x, self.goal_y))
            return

        # ── mode == "MOVING" ────────────────────────────────────

        with self._lock:
            pos_x   = self.pos_x
            pos_y   = self.pos_y
            heading = self.heading
            goal_x  = self.goal_x
            goal_y  = self.goal_y
            t_since_goal = time.time() - self.goal_sampled_at

        # ── 1. Check goal reached or timed out ──────────────────
        dx = goal_x - pos_x
        dy = goal_y - pos_y
        dist = math.hypot(dx, dy)

        if dist < self.cfg.GOAL_TOLERANCE or t_since_goal > self.cfg.GOAL_TIMEOUT_SEC:
            self.get_logger().info(
                f"↻ Goal reached (dist={dist:.3f}m, t={t_since_goal:.1f}s) — resampling"
            )
            with self._lock:
                self._resample_goal()
                goal_x = self.goal_x
                goal_y = self.goal_y
                dx = goal_x - pos_x
                dy = goal_y - pos_y
                dist = math.hypot(dx, dy)

        # ── 2. Nominal DS velocity (body frame) ─────────────────
        #   ξ̇_nom = -κ(ξ - ξ*)  in world frame,
        #   then rotated to robot body frame for omnidirectional command

        # World-frame nominal velocity
        world_vx_nom = self.cfg.KAPPA * dx
        world_vy_nom = self.cfg.KAPPA * dy

        # Rotate to robot body frame
        cos_h =  math.cos(heading)
        sin_h =  math.sin(heading)
        body_vx =  world_vx_nom * cos_h + world_vy_nom * sin_h
        body_vy = -world_vx_nom * sin_h + world_vy_nom * cos_h

        # ── 3. Heading command ───────────────────────────────────
        if self.cfg.HEADING_MODE == "GOAL":
            # Desired heading = direction to goal
            desired_heading = math.atan2(dy, dx)
            heading_error = math.atan2(
                math.sin(desired_heading - heading),
                math.cos(desired_heading - heading)
            )
            w_cmd = self.cfg.HEADING_GAIN * heading_error

        elif self.cfg.HEADING_MODE == "FREE":
            # Slow drift proportional to lateral velocity
            w_cmd = self.cfg.HEADING_GAIN * body_vy * 0.4

        else:  # FIXED
            w_cmd = 0.0

        # ── 4. Clip velocities ───────────────────────────────────
        body_vx = max(-self.cfg.MAX_VX, min(self.cfg.MAX_VX, body_vx))
        body_vy = max(-self.cfg.MAX_VY, min(self.cfg.MAX_VY, body_vy))
        w_cmd   = max(-self.cfg.MAX_W,  min(self.cfg.MAX_W,  w_cmd))

        # ── 5. EMA smoothing ─────────────────────────────────────
        α = self.cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = α * body_vx + (1.0 - α) * self.smooth_vx
            self.smooth_vy = α * body_vy + (1.0 - α) * self.smooth_vy
            self.smooth_w  = α * w_cmd   + (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        # ── 6. Publish ───────────────────────────────────────────
        twist = Twist()
        twist.linear.x  = sv
        twist.linear.y  = svv
        twist.angular.z = sw
        self.cmd_pub.publish(twist)

        # ── 7. State string for dashboard ────────────────────────
        self._publish_state(
            f"WANDERING | goal=({goal_x:.2f},{goal_y:.2f}) "
            f"dist={dist:.2f}m | vx={sv:.2f} vy={svv:.2f} w={sw:.2f}"
        )

    # ────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────

    def _resample_goal(self):
        """
        Sample a new random attractor goal within arena bounds.
        Ensures the new goal is at least 0.4m away from current position
        to avoid micro-movements.
        """
        cfg = self.cfg
        min_dist = 0.40  # metres

        for _ in range(20):  # max attempts
            gx = random.uniform(cfg.ARENA_X_MIN, cfg.ARENA_X_MAX)
            gy = random.uniform(cfg.ARENA_Y_MIN, cfg.ARENA_Y_MAX)
            if math.hypot(gx - self.pos_x, gy - self.pos_y) >= min_dist:
                break

        self.goal_x = gx
        self.goal_y = gy
        self.goal_sampled_at = time.time()
        self.get_logger().info(f"  ★ New goal → ({gx:.2f}, {gy:.2f})")

    def _publish_zero(self):
        """Publish a zero-velocity Twist (graceful stop)."""
        # EMA toward zero
        α = self.cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = (1.0 - α) * self.smooth_vx
            self.smooth_vy = (1.0 - α) * self.smooth_vy
            self.smooth_w  = (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        # Only publish actual zero when velocity is negligible
        if abs(sv) < 0.005 and abs(svv) < 0.005 and abs(sw) < 0.005:
            sv = svv = sw = 0.0

        twist = Twist()
        twist.linear.x  = sv
        twist.linear.y  = svv
        twist.angular.z = sw
        self.cmd_pub.publish(twist)

    def _publish_state(self, state_str: str):
        """Publish DSC state string to /dsc/state for dashboard."""
        msg = String()
        msg.data = state_str
        self.state_pub.publish(msg)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
def main(args=None):
    rclpy.init(args=args)
    node = DSCWandererNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("DSC Wanderer stopped.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
