/**
 * Configuration for WebSocket connection to robot controller
 */

export const WS_CONFIG = {
    /** WebSocket server URL */
    URL: 'ws://localhost:8765',

    /** Reconnection attempt interval (ms) */
    RECONNECT_INTERVAL: 3000,

    /** Ping interval for connection health check (ms) */
    PING_INTERVAL: 1000,

    /** Maximum reconnection attempts before giving up (0 = infinite) */
    MAX_RECONNECT_ATTEMPTS: 0
} as const;

/** Robot telemetry data structure */
export interface RobotData {
    timestamp: number;
    electrical: {
        voltage: number;
        current: number;
        power: number;
        cell_voltage: number;
    };
    battery: {
        soc: number;
        runtime_hours: number;
    };
    motors: {
        torques: {
            FL: number;
            FR: number;
            RL: number;
            RR: number;
        };
        rpm: {
            FL: number;
            FR: number;
            RL: number;
            RR: number;
        };
        avg_rpm: number;
    };
    motion: {
        vx: number;
        vy: number;
        w: number;
    };
    system: {
        uptime: number;
        ping_ms: number;
    };
}
