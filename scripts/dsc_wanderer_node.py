#!/usr/bin/env python3
"""
DSC Wanderer Node — Autonomous DS Navigation + Proxemic Zone Layer
===================================================================
Implements a Modulated Dynamical System for smooth, autonomous
random wandering on the omnidirectional BRONE campus mascot platform,
with a Proxemic Zone layer that modifies robot behavior based on
the detected distance of the nearest human.

═══════════════════════════════════════════════════════════════════
PROXEMIC ZONES (Edward T. Hall, adapted for BRONE)
═══════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────┐
  │  Zone          │ Distance    │ BRONE Behavior           │
  ├─────────────────────────────────────────────────────────┤
  │  INTIMATE      │ 0–0.45 m   │ Emergency soft stop       │
  │  PERSONAL      │ 0.45–1.2 m │ Slow + pivot face-to-face │
  │  SOCIAL        │ 1.2–3.6 m  │ DS modulation + polite    │
  │                │             │ detour (body orientation) │
  │  PUBLIC        │ > 3.6 m    │ Free wandering (full DS)  │
  └─────────────────────────────────────────────────────────┘

DS Modulation (Social Zone):
  ξ̇_mod = M(ξ) · ξ̇_nom
  where M encodes an asymmetric ellipse around the human,
  stretched forward along human facing direction.

Speed Scaling (Personal Zone):
  v_scale = (d - R_intimate) / (R_personal - R_intimate)
  clamped to [0, 1] — robot decelerates linearly as human approaches.

═══════════════════════════════════════════════════════════════════
TOPICS
═══════════════════════════════════════════════════════════════════

Published:
  /cmd_vel_dsc        (geometry_msgs/Twist)   — velocity to Orange Pi bridge
  /dsc/state          (std_msgs/String)        — human-readable state string
  /dsc/proxemic_zone  (std_msgs/String)        — active zone name (for dashboard)

Subscribed:
  /dsc/mode           (std_msgs/String)        — "WANDERER" | "STOP" | "IDLE"
  /robot_velocity     (geometry_msgs/Twist)    — telemetry from Orange Pi (odom)
  /social/humans      (std_msgs/String)        — JSON array of detected humans
                                                  (from future perception node)
                                                  Format: see _parse_humans()

═══════════════════════════════════════════════════════════════════
USAGE
═══════════════════════════════════════════════════════════════════

  source /opt/ros/jazzy/setup.bash
  export ROS_DOMAIN_ID=10
  export CYCLONEDDS_URI=file:///home/codename-hydra/Documents/cyclonedds.xml
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  python3 dsc_wanderer_node.py

  # Activate wandering
  ros2 topic pub --once /dsc/mode std_msgs/msg/String "data: 'WANDERER'"

  # Inject a simulated human 1.0 m ahead (Personal zone) for testing:
  ros2 topic pub --once /social/humans std_msgs/msg/String \
    'data: "[{\"x\": 1.0, \"y\": 0.0, \"facing_deg\": 180}]"'

Author: BroneX1 Social Nav Team
Version: 2.0 — DS Wanderer + Proxemic Zone Layer
"""

import os
import math
import time
import random
import json
import threading
from dataclasses import dataclass, field
from typing import List, Optional

os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String


# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════

class DSCConfig:
    """All tunable parameters in one place."""

    # ── Arena bounds (metres from start position) ────────────────
    ARENA_X_MIN = -2.0
    ARENA_X_MAX =  2.0
    ARENA_Y_MIN = -2.0
    ARENA_Y_MAX =  2.0

    # ── DS gain κ ────────────────────────────────────────────────
    KAPPA = 0.8             # [1/s]

    # ── Goal tolerance & timeout ─────────────────────────────────
    GOAL_TOLERANCE   = 0.12  # metres — resample when closer than this
    GOAL_TIMEOUT_SEC = 8.0   # seconds — resample even if not reached

    # ── Velocity caps (full-speed, no proxemic scaling) ──────────
    MAX_VX = 0.35            # m/s
    MAX_VY = 0.35            # m/s
    MAX_W  = 0.6             # rad/s

    # ── EMA smoothing (lower = smoother, more lag) ───────────────
    EMA_ALPHA = 0.25

    # ── Heading mode: "GOAL" | "FREE" | "FIXED" ─────────────────
    HEADING_MODE = "GOAL"
    HEADING_GAIN = 0.35      # [rad/s per rad error]

    # ── Control loop rate ────────────────────────────────────────
    LOOP_HZ = 20.0

    # ── Proxemic zone radii (metres) ─────────────────────────────
    R_INTIMATE  = 0.45       # inner boundary of Personal zone
    R_PERSONAL  = 1.2        # inner boundary of Social zone
    R_SOCIAL    = 3.6        # inner boundary of Public zone
    # Public zone: > R_SOCIAL

    # ── Personal zone: pivot toward human ────────────────────────
    # Angular gain used to rotate robot to face human
    PIVOT_GAIN  = 1.2        # [rad/s per rad error]

    # ── Social zone: DS modulation ellipse shape ─────────────────
    # a_front: ellipse half-axis in human's forward direction (larger = more space)
    # a_rear : ellipse half-axis behind human (smaller = can pass closer from behind)
    ELLIPSE_A_FRONT = 1.8    # metres (frontal safety margin)
    ELLIPSE_A_REAR  = 0.7    # metres (rear safety margin)
    ELLIPSE_B       = 0.9    # metres (lateral half-axis, symmetric)

    # DS modulation strength in Social zone (0=no modulation, 1=full)
    MODULATION_GAIN = 0.85

    # ── Human detection timeout ───────────────────────────────────
    # If no /social/humans message received for this long, treat as no humans
    HUMAN_TIMEOUT_SEC = 1.0


# ══════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════

@dataclass
class HumanAgent:
    """
    Detected human in robot-centric frame.

    x, y       : position relative to robot (metres, robot-frame)
    facing_deg : direction the human is facing (degrees, 0 = same as robot forward,
                 180 = human facing the robot head-on)
    distance   : Euclidean distance from robot (computed automatically)
    """
    x: float = 0.0
    y: float = 0.0
    facing_deg: float = 0.0   # 0–360
    distance: float = field(init=False)

    def __post_init__(self):
        self.distance = math.hypot(self.x, self.y)

    @property
    def facing_rad(self) -> float:
        return math.radians(self.facing_deg)


class ProxemicZone:
    """Zone identifiers and display names."""
    INTIMATE = "INTIMATE"
    PERSONAL = "PERSONAL"
    SOCIAL   = "SOCIAL"
    PUBLIC   = "PUBLIC"

    EMOJI = {
        INTIMATE: "🛑",
        PERSONAL: "🤝",
        SOCIAL:   "🚶",
        PUBLIC:   "🌐",
    }

    @staticmethod
    def classify(distance: float, cfg: DSCConfig) -> str:
        if distance < cfg.R_INTIMATE:
            return ProxemicZone.INTIMATE
        elif distance < cfg.R_PERSONAL:
            return ProxemicZone.PERSONAL
        elif distance < cfg.R_SOCIAL:
            return ProxemicZone.SOCIAL
        else:
            return ProxemicZone.PUBLIC


# ══════════════════════════════════════════════════════════════════
# Main node
# ══════════════════════════════════════════════════════════════════

class DSCWandererNode(Node):
    """
    Autonomous DS Wanderer + Proxemic Zone Layer for BRONE.

    Internal state machine:
        IDLE      → waiting for /dsc/mode = "WANDERER"
        WANDERING → DS active, full-speed free roam (PUBLIC zone)
        SOCIAL    → DS modulation active, human in Social zone
        GREETING  → slow approach + pivot to face human (Personal zone)
        FROZEN    → soft stop, human in Intimate zone
        PAUSED    → externally paused via /dsc/mode = "STOP"
    """

    def __init__(self):
        super().__init__('dsc_wanderer_node')
        self.cfg = DSCConfig()

        # ── DS / odometry state ──────────────────────────────────
        self.mode   = "IDLE"
        self.pos_x  = 0.0
        self.pos_y  = 0.0
        self.heading = 0.0

        self.goal_x = 0.0
        self.goal_y = 0.0
        self.goal_sampled_at = 0.0

        self.smooth_vx = 0.0
        self.smooth_vy = 0.0
        self.smooth_w  = 0.0

        self.last_odom_time = time.time()

        # ── Proxemic state ───────────────────────────────────────
        self.humans: List[HumanAgent] = []
        self.humans_last_stamp = 0.0        # time.time() of last /social/humans msg
        self.nearest_human: Optional[HumanAgent] = None
        self.active_zone = ProxemicZone.PUBLIC

        # Freeze ramp state (used when entering FROZEN from SOCIAL)
        self._freeze_alpha = self.cfg.EMA_ALPHA  # will be temporarily reduced

        self._lock = threading.Lock()

        # ── ROS2 publishers ──────────────────────────────────────
        self.cmd_pub   = self.create_publisher(Twist,  '/cmd_vel_dsc',       10)
        self.state_pub = self.create_publisher(String, '/dsc/state',         10)
        self.zone_pub  = self.create_publisher(String, '/dsc/proxemic_zone', 10)

        # ── ROS2 subscribers ─────────────────────────────────────
        self.create_subscription(String, '/dsc/mode',      self._mode_callback,   10)
        self.create_subscription(Twist,  '/robot_velocity', self._odom_callback,   10)
        self.create_subscription(String, '/social/humans',  self._humans_callback, 10)

        # ── Control loop ─────────────────────────────────────────
        period = 1.0 / self.cfg.LOOP_HZ
        self.create_timer(period, self._control_loop)

        # Seed initial goal
        self._resample_goal()

        self._log_banner()

    # ══════════════════════════════════════════════════════════════
    # ROS2 Callbacks
    # ══════════════════════════════════════════════════════════════

    def _mode_callback(self, msg: String):
        """Switch operating mode from /dsc/mode topic."""
        new_mode = msg.data.strip().upper()
        with self._lock:
            if new_mode == "WANDERER" and self.mode not in ("WANDERING", "SOCIAL",
                                                             "GREETING", "FROZEN"):
                self.mode = "WANDERING"
                self._resample_goal()
                self.get_logger().info("▶ DSC WANDERER ACTIVATED")

            elif new_mode == "STOP":
                self.mode = "PAUSED"
                self.get_logger().info("■ DSC PAUSED (external)")

            elif new_mode == "IDLE":
                self.mode = "IDLE"
                self.get_logger().info("◉ DSC IDLE")

    def _odom_callback(self, msg: Twist):
        """
        Dead-reckoning from /robot_velocity telemetry.
        Orange Pi publishes INVERTED vx/vy for Webots display — undo here.
        """
        now = time.time()
        dt  = min(now - self.last_odom_time, 0.2)  # cap dt to 200ms
        self.last_odom_time = now

        vx = -msg.linear.x   # undo Orange Pi inversion
        vy = -msg.linear.y
        w  =  msg.angular.z

        with self._lock:
            cos_h = math.cos(self.heading)
            sin_h = math.sin(self.heading)
            self.pos_x   += (vx * cos_h - vy * sin_h) * dt
            self.pos_y   += (vx * sin_h + vy * cos_h) * dt
            self.heading += w * dt
            self.heading  = math.atan2(math.sin(self.heading),
                                       math.cos(self.heading))

    def _humans_callback(self, msg: String):
        """
        Receive detected humans from perception layer.

        Expected JSON format (robot-centric frame):
          [
            {"x": 1.2, "y": -0.3, "facing_deg": 170.0},
            ...
          ]

        Fields:
          x, y        — position relative to robot centre (metres)
          facing_deg  — direction human is FACING:
                          0   = human faces same direction as robot
                          180 = human faces toward the robot (head-on)
        """
        try:
            raw = json.loads(msg.data)
            agents = []
            for item in raw:
                h = HumanAgent(
                    x=float(item.get("x", 0.0)),
                    y=float(item.get("y", 0.0)),
                    facing_deg=float(item.get("facing_deg", 0.0)),
                )
                agents.append(h)
            with self._lock:
                self.humans = agents
                self.humans_last_stamp = time.time()
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.get_logger().warn(f"[humans] parse error: {e}")

    # ══════════════════════════════════════════════════════════════
    # Core Control Loop — 20 Hz
    # ══════════════════════════════════════════════════════════════

    def _control_loop(self):
        with self._lock:
            mode    = self.mode
            pos_x   = self.pos_x
            pos_y   = self.pos_y
            heading = self.heading
            goal_x  = self.goal_x
            goal_y  = self.goal_y
            t_goal  = time.time() - self.goal_sampled_at
            humans  = list(self.humans)
            h_age   = time.time() - self.humans_last_stamp

        # ── 0. Hard exits ────────────────────────────────────────
        if mode in ("IDLE", "PAUSED"):
            self._publish_zero()
            self._publish_state(f"{mode}")
            return

        # ── 1. Refresh human list (timeout → treat as empty) ─────
        if h_age > self.cfg.HUMAN_TIMEOUT_SEC:
            humans = []

        # ── 2. Find nearest human ────────────────────────────────
        nearest: Optional[HumanAgent] = None
        if humans:
            nearest = min(humans, key=lambda h: h.distance)

        # ── 3. Classify proxemic zone ────────────────────────────
        if nearest is None:
            zone = ProxemicZone.PUBLIC
        else:
            zone = ProxemicZone.classify(nearest.distance, self.cfg)

        # ── 4. Update internal mode based on zone ────────────────
        with self._lock:
            self.nearest_human = nearest
            self.active_zone   = zone
            if mode not in ("IDLE", "PAUSED"):
                if zone == ProxemicZone.INTIMATE:
                    self.mode = "FROZEN"
                elif zone == ProxemicZone.PERSONAL:
                    self.mode = "GREETING"
                elif zone == ProxemicZone.SOCIAL:
                    self.mode = "SOCIAL"
                else:
                    # PUBLIC — go back to free wandering
                    if self.mode != "WANDERING":
                        self.mode = "WANDERING"
                        self.get_logger().info(
                            "↩ Human left Social zone — resuming WANDERING"
                        )
                mode = self.mode  # refresh local

        # Publish zone for dashboard
        self._publish_zone(zone)

        # ── 5. Dispatch to zone handler ──────────────────────────
        if mode == "FROZEN":
            self._handle_intimate(nearest)

        elif mode == "GREETING":
            self._handle_personal(nearest, heading)

        elif mode == "SOCIAL":
            self._handle_social(nearest, pos_x, pos_y, heading,
                                goal_x, goal_y, t_goal)
        else:
            # WANDERING — pure DS, no humans nearby
            self._handle_public(pos_x, pos_y, heading,
                                 goal_x, goal_y, t_goal)

    # ══════════════════════════════════════════════════════════════
    # Zone Handlers
    # ══════════════════════════════════════════════════════════════

    def _handle_intimate(self, human: HumanAgent):
        """
        INTIMATE ZONE (0 – 0.45 m)
        Emergency soft stop. EMA ramps velocity to zero quickly.
        Robot holds position until human moves away.
        """
        # Aggressive EMA decay to stop fast
        α_stop = 0.08
        with self._lock:
            self.smooth_vx = (1.0 - α_stop) * self.smooth_vx
            self.smooth_vy = (1.0 - α_stop) * self.smooth_vy
            self.smooth_w  = (1.0 - α_stop) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        if abs(sv) < 0.005 and abs(svv) < 0.005 and abs(sw) < 0.005:
            sv = svv = sw = 0.0

        self._publish_cmd(sv, svv, sw)
        dist_str = f"{human.distance:.2f}m" if human else "?"
        self._publish_state(
            f"🛑 INTIMATE | d={dist_str} | EMERGENCY STOP"
        )

    def _handle_personal(self, human: HumanAgent, heading: float):
        """
        PERSONAL ZONE (0.45 – 1.2 m)
        Decelerate + pivot to face the human (mascot greeting behaviour).

        Speed scales linearly from 0 (at R_INTIMATE) to MAX_VX (at R_PERSONAL).
        Heading command turns robot to face human while translating slowly.
        """
        cfg = self.cfg

        # ── Speed scale: 0 near intimate boundary → 1 at personal boundary
        d = human.distance
        speed_scale = (d - cfg.R_INTIMATE) / (cfg.R_PERSONAL - cfg.R_INTIMATE)
        speed_scale = max(0.0, min(1.0, speed_scale))

        # ── Pivot: compute angle from robot forward to human position
        angle_to_human = math.atan2(human.y, human.x)  # robot-frame
        # heading_error in world frame: how much robot must rotate
        heading_error = math.atan2(
            math.sin(angle_to_human - heading),
            math.cos(angle_to_human - heading)
        )
        w_pivot = cfg.PIVOT_GAIN * heading_error
        w_pivot = max(-cfg.MAX_W, min(cfg.MAX_W, w_pivot))

        # ── Translation: slow glide toward human (social approach)
        # Move at reduced speed along current heading
        vx_approach = speed_scale * cfg.MAX_VX * 0.4   # gentle approach
        vy_approach = 0.0

        # ── EMA smoothing
        α = cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = α * vx_approach + (1.0 - α) * self.smooth_vx
            self.smooth_vy = α * vy_approach + (1.0 - α) * self.smooth_vy
            self.smooth_w  = α * w_pivot     + (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        self._publish_cmd(sv, svv, sw)
        self._publish_state(
            f"🤝 PERSONAL | d={d:.2f}m | speed_scale={speed_scale:.2f} "
            f"| pivot_err={math.degrees(heading_error):.1f}°"
        )

    def _handle_social(self, human: HumanAgent, pos_x: float, pos_y: float,
                       heading: float, goal_x: float, goal_y: float,
                       t_goal: float):
        """
        SOCIAL ZONE (1.2 – 3.6 m)
        Full DS modulation: nominal attractor flow is deflected around an
        asymmetric ellipse centred on the human.

        Ellipse orientation: aligned with human's facing direction.
        Front semi-axis (a_front) is larger than rear (a_rear) because
        humans are more sensitive to approach from the front.

        The modulation matrix M is constructed from:
          n(ξ) — normal vector pointing away from human
          t(ξ) — tangent vector sliding along ellipse perimeter
        """
        cfg = self.cfg

        # ── Resample goal if needed ──────────────────────────────
        if (math.hypot(goal_x - pos_x, goal_y - pos_y) < cfg.GOAL_TOLERANCE
                or t_goal > cfg.GOAL_TIMEOUT_SEC):
            with self._lock:
                self._resample_goal()
                goal_x, goal_y = self.goal_x, self.goal_y

        # ── Nominal DS velocity (world frame) ────────────────────
        dx_goal = goal_x - pos_x
        dy_goal = goal_y - pos_y
        wvx_nom = cfg.KAPPA * dx_goal
        wvy_nom = cfg.KAPPA * dy_goal

        # ── DS Modulation around human (world frame) ─────────────
        # Robot position relative to human centre
        rx = pos_x - human.x   # NOTE: human.x,y are robot-relative;
        ry = pos_y - human.y   # we need robot-to-human vector in world frame.
        # But since human coords are robot-frame, convert:
        # human_world = robot_world + R(heading) * human_robot
        # For modulation we only need the relative vector, which IS (rx, ry)
        # in robot frame → rotate to world frame:
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        # robot-to-human in world frame:
        hx_w =  human.x * cos_h - human.y * sin_h   # human world-x relative
        hy_w =  human.x * sin_h + human.y * cos_h   # human world-y relative

        # Ellipse alignment: human facing direction in world frame
        # human.facing_rad is in robot-frame → rotate to world
        h_face_world = human.facing_rad + heading
        cos_f = math.cos(h_face_world)
        sin_f = math.sin(h_face_world)

        # Vector from human to robot in world frame
        dxr =  -hx_w   # robot is at 0,0 in its own frame; human offset = hx_w,hy_w
        dyr =  -hy_w

        # Project onto ellipse axes (rotated by human facing)
        proj_front = dxr * cos_f + dyr * sin_f   # along human forward
        proj_lat   =-dxr * sin_f + dyr * cos_f   # lateral

        # Asymmetric semi-axis: use a_front when robot is ahead of human,
        # a_rear when robot is behind
        a_axis = cfg.ELLIPSE_A_FRONT if proj_front > 0 else cfg.ELLIPSE_A_REAR
        b_axis = cfg.ELLIPSE_B

        # Normalised ellipse distance Γ(ξ) = (proj_front/a)² + (proj_lat/b)²
        # Γ > 1 → outside ellipse (safe), Γ < 1 → inside (collision zone)
        a_sq = a_axis ** 2
        b_sq = b_axis ** 2
        denom_a = a_sq if a_sq > 1e-6 else 1e-6
        denom_b = b_sq if b_sq > 1e-6 else 1e-6
        gamma = (proj_front ** 2) / denom_a + (proj_lat ** 2) / denom_b

        # Modulation eigenvalue λ_r: radial (push away)
        # λ_r approaches 0 as robot approaches surface (Γ → 1)
        # λ_r = 1 - 1/Γ  (standard Khansari-Zadeh formulation)
        gamma_safe = max(gamma, 1e-3)
        lambda_r = 1.0 - (1.0 / gamma_safe)
        lambda_r = max(0.0, lambda_r)

        # Tangential eigenvalue λ_t: slide along boundary
        # λ_t = 1 + 1/Γ
        lambda_t = 1.0 + (1.0 / gamma_safe)

        # Normal direction (pointing away from human, world frame)
        dist_h = math.hypot(hx_w, hy_w)
        if dist_h > 1e-4:
            n_x = -hx_w / dist_h   # pointing away from human (robot outward)
            n_y = -hy_w / dist_h
        else:
            n_x, n_y = 1.0, 0.0

        # Tangent direction (perpendicular to normal, choose side toward goal)
        t_x = -n_y
        t_y =  n_x
        # Flip tangent if it opposes the nominal direction
        if t_x * wvx_nom + t_y * wvy_nom < 0:
            t_x, t_y = -t_x, -t_y

        # Decompose nominal velocity into normal + tangential components
        v_dot_n = wvx_nom * n_x + wvy_nom * n_y
        v_dot_t = wvx_nom * t_x + wvy_nom * t_y

        # Apply modulation: scale normal by λ_r, tangential by λ_t
        mod_strength = cfg.MODULATION_GAIN * max(0.0, (1.0 - (gamma - 1.0)))
        mod_strength = max(0.0, min(1.0, mod_strength))

        wvx_mod = wvx_nom + mod_strength * (
            (lambda_r - 1.0) * v_dot_n * n_x +
            (lambda_t - 1.0) * v_dot_t * t_x
        )
        wvy_mod = wvy_nom + mod_strength * (
            (lambda_r - 1.0) * v_dot_n * n_y +
            (lambda_t - 1.0) * v_dot_t * t_y
        )

        # ── Rotate modulated world velocity to body frame ─────────
        body_vx =  wvx_mod * cos_h + wvy_mod * sin_h
        body_vy = -wvx_mod * sin_h + wvy_mod * cos_h

        # ── Heading ───────────────────────────────────────────────
        w_cmd = self._compute_heading_cmd(heading, dx_goal, dy_goal)

        # ── Clip ──────────────────────────────────────────────────
        body_vx = max(-cfg.MAX_VX, min(cfg.MAX_VX, body_vx))
        body_vy = max(-cfg.MAX_VY, min(cfg.MAX_VY, body_vy))
        w_cmd   = max(-cfg.MAX_W,  min(cfg.MAX_W,  w_cmd))

        # ── EMA ───────────────────────────────────────────────────
        α = cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = α * body_vx + (1.0 - α) * self.smooth_vx
            self.smooth_vy = α * body_vy + (1.0 - α) * self.smooth_vy
            self.smooth_w  = α * w_cmd   + (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        self._publish_cmd(sv, svv, sw)
        self._publish_state(
            f"🚶 SOCIAL | d={human.distance:.2f}m Γ={gamma:.2f} "
            f"λr={lambda_r:.2f} | vx={sv:.2f} vy={svv:.2f}"
        )

    def _handle_public(self, pos_x: float, pos_y: float, heading: float,
                       goal_x: float, goal_y: float, t_goal: float):
        """
        PUBLIC ZONE (> 3.6 m) — pure DS free wandering.
        No humans nearby, robot moves freely toward random attractor.
        """
        cfg = self.cfg

        dx = goal_x - pos_x
        dy = goal_y - pos_y
        dist = math.hypot(dx, dy)

        # ── Resample if needed ───────────────────────────────────
        if dist < cfg.GOAL_TOLERANCE or t_goal > cfg.GOAL_TIMEOUT_SEC:
            self.get_logger().info(
                f"↻ Goal reached/timeout (d={dist:.2f}m, t={t_goal:.1f}s)"
            )
            with self._lock:
                self._resample_goal()
                goal_x, goal_y = self.goal_x, self.goal_y
                dx = goal_x - pos_x
                dy = goal_y - pos_y
                dist = math.hypot(dx, dy)

        # ── Nominal DS velocity ──────────────────────────────────
        wvx_nom = cfg.KAPPA * dx
        wvy_nom = cfg.KAPPA * dy

        # Rotate to body frame
        cos_h =  math.cos(heading)
        sin_h =  math.sin(heading)
        body_vx =  wvx_nom * cos_h + wvy_nom * sin_h
        body_vy = -wvx_nom * sin_h + wvy_nom * cos_h

        # ── Heading ──────────────────────────────────────────────
        w_cmd = self._compute_heading_cmd(heading, dx, dy)

        # ── Clip ─────────────────────────────────────────────────
        body_vx = max(-cfg.MAX_VX, min(cfg.MAX_VX, body_vx))
        body_vy = max(-cfg.MAX_VY, min(cfg.MAX_VY, body_vy))
        w_cmd   = max(-cfg.MAX_W,  min(cfg.MAX_W,  w_cmd))

        # ── EMA ──────────────────────────────────────────────────
        α = cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = α * body_vx + (1.0 - α) * self.smooth_vx
            self.smooth_vy = α * body_vy + (1.0 - α) * self.smooth_vy
            self.smooth_w  = α * w_cmd   + (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w

        self._publish_cmd(sv, svv, sw)
        self._publish_state(
            f"🌐 WANDERING | goal=({goal_x:.2f},{goal_y:.2f}) "
            f"d={dist:.2f}m | vx={sv:.2f} vy={svv:.2f} w={sw:.2f}"
        )

    # ══════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════

    def _compute_heading_cmd(self, heading: float, dx: float, dy: float) -> float:
        """Compute angular velocity command based on HEADING_MODE config."""
        cfg = self.cfg
        if cfg.HEADING_MODE == "GOAL":
            desired = math.atan2(dy, dx)
            err = math.atan2(math.sin(desired - heading),
                             math.cos(desired - heading))
            return cfg.HEADING_GAIN * err
        elif cfg.HEADING_MODE == "FREE":
            return cfg.HEADING_GAIN * 0.15 * math.sin(time.time() * 0.3)
        else:  # FIXED
            return 0.0

    def _resample_goal(self):
        """Sample a new random attractor at least 0.4 m from current position."""
        cfg = self.cfg
        for _ in range(20):
            gx = random.uniform(cfg.ARENA_X_MIN, cfg.ARENA_X_MAX)
            gy = random.uniform(cfg.ARENA_Y_MIN, cfg.ARENA_Y_MAX)
            if math.hypot(gx - self.pos_x, gy - self.pos_y) >= 0.4:
                break
        self.goal_x = gx
        self.goal_y = gy
        self.goal_sampled_at = time.time()
        self.get_logger().info(f"  ★ New attractor → ({gx:.2f}, {gy:.2f})")

    def _publish_cmd(self, vx: float, vy: float, w: float):
        """Publish a Twist command on /cmd_vel_dsc."""
        t = Twist()
        t.linear.x  = float(vx)
        t.linear.y  = float(vy)
        t.angular.z = float(w)
        self.cmd_pub.publish(t)

    def _publish_zero(self):
        """Graceful stop via EMA decay toward zero."""
        α = self.cfg.EMA_ALPHA
        with self._lock:
            self.smooth_vx = (1.0 - α) * self.smooth_vx
            self.smooth_vy = (1.0 - α) * self.smooth_vy
            self.smooth_w  = (1.0 - α) * self.smooth_w
            sv, svv, sw = self.smooth_vx, self.smooth_vy, self.smooth_w
        if abs(sv) < 0.005 and abs(svv) < 0.005 and abs(sw) < 0.005:
            sv = svv = sw = 0.0
        self._publish_cmd(sv, svv, sw)

    def _publish_state(self, s: str):
        msg = String()
        msg.data = s
        self.state_pub.publish(msg)

    def _publish_zone(self, zone: str):
        msg = String()
        msg.data = zone
        self.zone_pub.publish(msg)

    def _log_banner(self):
        cfg = self.cfg
        self.get_logger().info("=" * 60)
        self.get_logger().info("DSC Wanderer + Proxemic Zone Layer — READY")
        self.get_logger().info(f"  Zones  : Intimate<{cfg.R_INTIMATE}m "
                               f"Personal<{cfg.R_PERSONAL}m "
                               f"Social<{cfg.R_SOCIAL}m Public")
        self.get_logger().info(f"  Arena  : [{cfg.ARENA_X_MIN},{cfg.ARENA_X_MAX}] × "
                               f"[{cfg.ARENA_Y_MIN},{cfg.ARENA_Y_MAX}] m")
        self.get_logger().info(f"  κ={cfg.KAPPA}  α={cfg.EMA_ALPHA}  "
                               f"Loop={cfg.LOOP_HZ}Hz")
        self.get_logger().info("")
        self.get_logger().info("Activate  : ros2 topic pub --once /dsc/mode "
                               "std_msgs/msg/String \"data: 'WANDERER'\"")
        self.get_logger().info("Test human: ros2 topic pub --once /social/humans "
                               "std_msgs/msg/String "
                               "'data: \"[{\\\"x\\\": 1.0, \\\"y\\\": 0.0, "
                               "\\\"facing_deg\\\": 180}]\"'")
        self.get_logger().info("=" * 60)


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

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
