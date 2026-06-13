/**
 * Digital Twin Interface - Main Application
 *
 * Real-time digital twin interface integrated with robot controller via WebSocket
 */

import Chart from 'chart.js/auto';
import { WS_CONFIG, type RobotData } from './config';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface TimeRangeData {
    labels: string[];
    data: number[];
}

interface MultiLineDataset {
    label: string;
    data: number[];
    color: string;
}

interface MultiTimeRangeData {
    labels: string[];
    datasets: MultiLineDataset[];
}

interface SingleModeData {
    type?: string;
    label: string;
    color: string;
    bgColor: string;
    unit: string;
    min: number;
    max: number;
    ranges: {
        seconds: TimeRangeData;
        minutes: TimeRangeData;
        hours: TimeRangeData;
    };
}

interface MultiModeData {
    type: 'multi';
    unit: string;
    min: number;
    max: number;
    ranges: {
        seconds: MultiTimeRangeData;
        minutes: MultiTimeRangeData;
        hours: MultiTimeRangeData;
    };
}

interface ChartDataConfig {
    power: SingleModeData;
    voltage: SingleModeData;
    current: SingleModeData;
    torque: MultiModeData;
}

interface WheelElements {
    arrow: HTMLElement | null;
    val: HTMLElement | null;
    rpm: HTMLElement | null;
}

interface DOMElements {
    clock: HTMLElement | null;
    running: HTMLElement | null;
    uptime: HTMLElement | null;
    ping: HTMLElement | null;
    valVoltage: HTMLElement | null;
    valCurrent: HTMLElement | null;
    valPower: HTMLElement | null;
    valCell: HTMLElement | null;
    valRPM: HTMLElement | null;
    resArrow: HTMLElement | null;
    resIcon: HTMLElement | null;
    wheels: {
        FL: WheelElements;
        FR: WheelElements;
        RL: WheelElements;
        RR: WheelElements;
    };
}

interface DataBuffer {
    power: number[];
    voltage: number[];
    current: number[];
}

// ============================================================================
// WEBSOCKET MANAGER
// ============================================================================

class WebSocketManager {
    private ws: WebSocket | null = null;
    private reconnectTimer: number | null = null;
    private reconnectAttempts = 0;
    private onDataCallback: ((data: RobotData) => void) | null = null;
    private onConnectCallback: (() => void) | null = null;
    private onDisconnectCallback: (() => void) | null = null;

    connect(): void {
        if (this.ws?.readyState === WebSocket.OPEN) return;

        console.log(`[WS] Connecting to ${WS_CONFIG.URL}...`);

        try {
            this.ws = new WebSocket(WS_CONFIG.URL);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
                this.reconnectAttempts = 0;
                this.onConnectCallback?.();
            };

            this.ws.onmessage = (event) => {
                try {
                    const data: RobotData = JSON.parse(event.data);
                    this.onDataCallback?.(data);
                } catch (err) {
                    console.error('[WS] Failed to parse message:', err);
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WS] Error:', error);
            };

            this.ws.onclose = () => {
                console.log('[WS] Disconnected');
                this.onDisconnectCallback?.();
                this.scheduleReconnect();
            };
        } catch (err) {
            console.error('[WS] Connection failed:', err);
            this.scheduleReconnect();
        }
    }

    send(data: any): void {
        console.log('[WS] Sending data:', data);
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            console.log('[WS] Data sent successfully');
        } else {
            console.error('[WS] Cannot send message: WebSocket not connected');
        }
    }

    private scheduleReconnect(): void {
        if (this.reconnectTimer) return;

        if (WS_CONFIG.MAX_RECONNECT_ATTEMPTS > 0 &&
            this.reconnectAttempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
            console.log('[WS] Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        console.log(`[WS] Reconnecting in ${WS_CONFIG.RECONNECT_INTERVAL}ms... (attempt ${this.reconnectAttempts})`);

        this.reconnectTimer = window.setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, WS_CONFIG.RECONNECT_INTERVAL);
    }

    onData(callback: (data: RobotData) => void): void {
        this.onDataCallback = callback;
    }

    onConnect(callback: () => void): void {
        this.onConnectCallback = callback;
    }

    onDisconnect(callback: () => void): void {
        this.onDisconnectCallback = callback;
    }

    disconnect(): void {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', function () {
    const canvas = document.getElementById('electricalChart') as HTMLCanvasElement | null;
    if (!canvas) {
        console.error('Canvas element not found');
        return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
        console.error('Could not get 2D context');
        return;
    }

    // ========================================================================
    // UTILITY FUNCTIONS
    // ========================================================================

    function createGradient(ctx: CanvasRenderingContext2D, hexColor: string): CanvasGradient {
        let r = 0, g = 0, b = 0;

        if (hexColor.length === 4) {
            r = parseInt(hexColor[1] + hexColor[1], 16);
            g = parseInt(hexColor[2] + hexColor[2], 16);
            b = parseInt(hexColor[3] + hexColor[3], 16);
        } else if (hexColor.length === 7) {
            r = parseInt(hexColor.substr(1, 2), 16);
            g = parseInt(hexColor.substr(3, 2), 16);
            b = parseInt(hexColor.substr(5, 2), 16);
        }

        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.5)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);

        return gradient;
    }

    function logToTerminal(message: string): void {
        const terminalWindow = document.querySelector('.terminal-logs');
        if (!terminalWindow) return;

        const now = new Date();
        const timeString = now.toLocaleTimeString('en-GB', { hour12: false });

        const logLine = document.createElement('div');
        logLine.className = 'log-line';
        logLine.innerHTML = `<span class="log-time">[${timeString}]</span> <span class="log-msg">${message}</span>`;

        terminalWindow.appendChild(logLine);
        terminalWindow.scrollTop = terminalWindow.scrollHeight;
    }

    // ========================================================================
    // CHART CONFIGURATION
    // ========================================================================

    const denseLabels: string[] = Array.from({ length: 60 }, (_, i) => i + 's');
    const denseMinutesLabels: string[] = Array.from({ length: 60 }, (_, i) => i + 'm');
    const denseHoursLabels: string[] = Array.from({ length: 25 }, (_, i) => i + 'h');

    function createEmptyData(count: number): number[] {
        return Array(count).fill(0);
    }

    function createModeData(
        label: string,
        color: string,
        bgColor: string,
        unit: string,
        min: number,
        max: number
    ): SingleModeData {
        return {
            label, color, bgColor, unit, min, max,
            ranges: {
                seconds: { labels: denseLabels, data: createEmptyData(60) },
                minutes: { labels: denseMinutesLabels, data: createEmptyData(60) },
                hours: { labels: denseHoursLabels, data: createEmptyData(25) }
            }
        };
    }

    const chartData: ChartDataConfig = {
        power: createModeData('Power', '#FF6B9C', 'rgba(255, 107, 156, 0.1)', 'W', 0, 400),
        voltage: createModeData('Voltage', '#D56BFF', 'rgba(213, 107, 255, 0.1)', 'V', 20, 24),
        current: createModeData('Current', '#4ADE80', 'rgba(74, 222, 128, 0.1)', 'A', 0, 15),
        torque: {
            type: 'multi',
            unit: 'Nm',
            min: -0.5,
            max: 0.5,
            ranges: {
                seconds: {
                    labels: denseLabels,
                    datasets: [
                        { label: 'FL', data: createEmptyData(60), color: '#FF6B9C' },
                        { label: 'FR', data: createEmptyData(60), color: '#D56BFF' },
                        { label: 'RL', data: createEmptyData(60), color: '#4ADE80' },
                        { label: 'RR', data: createEmptyData(60), color: '#60A5FA' }
                    ]
                },
                minutes: {
                    labels: denseMinutesLabels,
                    datasets: [
                        { label: 'FL', data: createEmptyData(60), color: '#FF6B9C' },
                        { label: 'FR', data: createEmptyData(60), color: '#D56BFF' },
                        { label: 'RL', data: createEmptyData(60), color: '#4ADE80' },
                        { label: 'RR', data: createEmptyData(60), color: '#60A5FA' }
                    ]
                },
                hours: {
                    labels: denseHoursLabels,
                    datasets: [
                        { label: 'FL', data: createEmptyData(25), color: '#FF6B9C' },
                        { label: 'FR', data: createEmptyData(25), color: '#D56BFF' },
                        { label: 'RL', data: createEmptyData(25), color: '#4ADE80' },
                        { label: 'RR', data: createEmptyData(25), color: '#60A5FA' }
                    ]
                }
            }
        }
    };

    let currentMode: keyof ChartDataConfig = 'power';
    let currentTimeRange: 'seconds' | 'minutes' | 'hours' = 'seconds';

    function getDatasetForMode(mode: keyof ChartDataConfig, range: 'seconds' | 'minutes' | 'hours'): any[] {
        const modeData = chartData[mode];
        const rangeData = modeData.ranges[range];

        if (modeData.type === 'multi') {
            const multiRangeData = rangeData as MultiTimeRangeData;
            return multiRangeData.datasets.map((ds: MultiLineDataset) => ({
                label: ds.label,
                data: ds.data,
                borderColor: ds.color,
                backgroundColor: createGradient(ctx!, ds.color),
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointBackgroundColor: '#fff',
                pointBorderColor: ds.color,
                pointBorderWidth: 2,
                fill: true
            }));
        } else {
            const singleModeData = modeData as SingleModeData;
            const singleRangeData = rangeData as TimeRangeData;
            return [{
                label: singleModeData.label,
                data: singleRangeData.data,
                borderColor: singleModeData.color,
                backgroundColor: createGradient(ctx!, singleModeData.color),
                borderWidth: 3,
                tension: 0.4,
                pointBackgroundColor: '#fff',
                pointBorderColor: singleModeData.color,
                pointBorderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 6,
                fill: true
            }];
        }
    }

    const initialRangeData = chartData[currentMode].ranges[currentTimeRange];
    const initialDatasets = getDatasetForMode(currentMode, currentTimeRange);

    const electricalChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: initialRangeData.labels,
            datasets: initialDatasets
        },
        options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            elements: {
                point: { radius: 0 },
                line: { tension: 0.4 }
            },
            plugins: {
                tooltip: {
                    enabled: true,
                    usePointStyle: true,
                    backgroundColor: 'rgba(255, 255, 255, 0.95)',
                    titleColor: '#1E293B',
                    bodyColor: '#475569',
                    borderColor: '#E2E8F0',
                    borderWidth: 1,
                    padding: 12,
                    boxPadding: 4,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', size: 13, weight: 600 as any },
                    bodyFont: { family: 'Inter', size: 12 },
                    callbacks: {
                        label: function (context: any) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.parsed.y !== null) {
                                label += context.parsed.y + ' ' + chartData[currentMode].unit;
                            }
                            return label;
                        }
                    }
                },
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        font: { family: 'Inter', size: 11 },
                        color: '#64748B'
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    min: chartData[currentMode].min,
                    max: chartData[currentMode].max,
                    grid: { color: '#F1F5F9' },
                    ticks: {
                        stepSize: (chartData[currentMode].max - chartData[currentMode].min) / 4,
                        callback: function (value: any) {
                            return value + ' ' + chartData[currentMode].unit;
                        },
                        font: { size: 10, family: 'Inter' },
                        color: '#94A3B8'
                    },
                    border: { display: false }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { size: 10, family: 'Inter' },
                        color: '#94A3B8',
                        maxTicksLimit: 7,
                        autoSkip: true
                    },
                    border: { display: false }
                }
            }
        }
    });

    function resetCharts(): void {
        console.log('[CHART] Resetting all chart data');

        // Reset buffers
        Object.keys(chartData).forEach(key => {
            const mode = key as keyof ChartDataConfig;
            const config = chartData[mode];

            // Reset seconds (60 points)
            if (config.type === 'multi') {
                const multiConfig = config as MultiModeData;
                multiConfig.ranges.seconds.datasets.forEach(ds => ds.data = createEmptyData(60));
                multiConfig.ranges.minutes.datasets.forEach(ds => ds.data = createEmptyData(60));
                multiConfig.ranges.hours.datasets.forEach(ds => ds.data = createEmptyData(25));
            } else {
                const singleConfig = config as SingleModeData;
                singleConfig.ranges.seconds.data = createEmptyData(60);
                singleConfig.ranges.minutes.data = createEmptyData(60);
                singleConfig.ranges.hours.data = createEmptyData(25);
            }
        });

        // Force chart update
        updateChart();
    }

    function updateChart(): void {
        const modeData = chartData[currentMode];
        const rangeData = modeData.ranges[currentTimeRange];

        electricalChart.data.labels = rangeData.labels;
        electricalChart.data.datasets = getDatasetForMode(currentMode, currentTimeRange);

        electricalChart.options.scales!.y!.min = modeData.min;
        electricalChart.options.scales!.y!.max = modeData.max;
        (electricalChart.options.scales!.y!.ticks as any).stepSize = (modeData.max - modeData.min) / 4;
        electricalChart.options.scales!.y!.ticks!.callback = function (value: any) {
            return value + ' ' + modeData.unit;
        };

        electricalChart.update();
    }

    // ========================================================================
    // EVENT HANDLERS
    // ========================================================================

    const modeControls = document.getElementById('graphModeControls');
    if (modeControls) {
        modeControls.addEventListener('click', (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (target.classList.contains('control-btn')) {
                const buttons = modeControls.querySelectorAll('.control-btn');
                buttons.forEach(btn => btn.classList.remove('active'));
                target.classList.add('active');

                currentMode = target.getAttribute('data-value') as keyof ChartDataConfig;
                updateChart();
            }
        });
    }

    const timeControls = document.getElementById('timeRangeControls');
    if (timeControls) {
        timeControls.addEventListener('click', (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (target.classList.contains('control-btn')) {
                const buttons = timeControls.querySelectorAll('.control-btn');
                buttons.forEach(btn => btn.classList.remove('active'));
                target.classList.add('active');

                currentTimeRange = target.getAttribute('data-value') as 'seconds' | 'minutes' | 'hours';
                updateChart();
            }
        });
    }

    // Modal management
    const modal = document.getElementById('confirmationModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalMessage = document.getElementById('modalMessage');
    const btnCancel = document.getElementById('btnCancel');
    const btnConfirm = document.getElementById('btnConfirm');

    let pendingAction: (() => void) | null = null;

    function showConfirmation(title: string, message: string, action: () => void): void {
        console.log('[MODAL] showConfirmation called, title:', title);
        if (modal && modalTitle && modalMessage) {
            modalTitle.textContent = title;
            modalMessage.textContent = message;
            pendingAction = action;
            modal.classList.add('show');
            console.log('[MODAL] Modal shown');
        } else {
            console.error('[MODAL] Modal elements not found');
        }
    }

    function closeConfirmation(): void {
        if (modal) {
            modal.classList.remove('show');
            pendingAction = null;
        }
    }

    if (btnCancel) btnCancel.addEventListener('click', closeConfirmation);
    if (btnConfirm) {
        btnConfirm.addEventListener('click', () => {
            console.log('[MODAL] Confirm button clicked, pendingAction exists:', !!pendingAction);
            if (pendingAction) {
                console.log('[MODAL] Executing pending action');
                pendingAction();
            }
            closeConfirmation();
        });
    }
    // ========================================================================
    // ROBOT CONTROL BUTTONS
    // ========================================================================

    const btnStart = document.getElementById('btnStart');
    const btnReset = document.getElementById('btnReset');

    // State persistence: Load saved state from localStorage
    let isRunning = localStorage.getItem('robot_running') === 'true';

    // Sync UI with saved state on page load
    if (btnStart) {
        if (isRunning) {
            btnStart.textContent = 'Stop Program';
            btnStart.classList.add('stopped');
        } else {
            btnStart.textContent = 'Start Program';
            btnStart.classList.remove('stopped');
        }
    }

    // Start/Stop Program Button
    if (btnStart) {
        btnStart.addEventListener('click', () => {
            console.log('[BTN] Start/Stop button clicked, isRunning:', isRunning);
            if (isRunning) {
                // Stop Program
                showConfirmation(
                    'Stop Program',
                    'Are you sure you want to stop the program? This will disable robot motion and stop all motors.',
                    () => {
                        isRunning = false;
                        localStorage.setItem('robot_running', 'false');
                        btnStart.textContent = 'Start Program';
                        btnStart.classList.remove('stopped');

                        wsManager.send({
                            command: 'stop_program'
                        });

                        logToTerminal('Program stopped - Robot disabled, all motors stopped');
                    }
                );
            } else {
                // Start Program
                showConfirmation(
                    'Start Program',
                    'Are you sure you want to start the program? This will enable robot motion and allow control inputs.',
                    () => {
                        isRunning = true;
                        localStorage.setItem('robot_running', 'true');
                        btnStart.textContent = 'Stop Program';
                        btnStart.classList.add('stopped');

                        wsManager.send({
                            command: 'start_program'
                        });

                        logToTerminal('Program started - Robot enabled, ready for input');
                    }
                );
            }
        });
    }

    // Reset Digital Twin Button
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            console.log('[BTN] Reset button clicked');
            showConfirmation(
                'Reset Digital Twin',
                'Are you sure you want to reset the Digital Twin? This will clear all current data and restart from zero.',
                () => {
                    wsManager.send({
                        command: 'reset_system'
                    });

                    // Reset charts instantly
                    resetCharts();

                    logToTerminal('System reset initiated - Data cleared');
                }
            );
        });
    }

    // ========================================================================
    // REAL-TIME DATA HANDLING
    // ========================================================================

    // Initialize terminal
    const terminalWindow = document.querySelector('.terminal-logs');
    if (terminalWindow && terminalWindow.querySelector('.log-msg') && !terminalWindow.querySelector('.log-time')) {
        terminalWindow.innerHTML = '';
        logToTerminal('System Initialized');
        logToTerminal('Connecting to robot controller...');
    }

    // Data aggregation buffers
    const secBuffer: DataBuffer = { power: [], voltage: [], current: [] };
    const minBuffer: DataBuffer = { power: [], voltage: [], current: [] };
    let lastSecondUpdate = 0;

    // Cache DOM elements
    const dom: DOMElements = {
        clock: document.getElementById('currentTime'),
        running: document.getElementById('runningTime'),
        uptime: document.getElementById('sysUptime'),
        ping: document.querySelector('.status-ping'),
        valVoltage: document.getElementById('valVoltage'),
        valCurrent: document.getElementById('valCurrent'),
        valPower: document.getElementById('valPower'),
        valCell: document.getElementById('valCell'),
        valRPM: document.getElementById('valRPM'),
        resArrow: document.getElementById('resArrow'),
        resIcon: document.getElementById('resArrow') ? document.getElementById('resArrow')!.querySelector('i') : null,
        wheels: {
            FL: {
                arrow: document.getElementById('arrowFL'),
                val: document.getElementById('valFL'),
                rpm: document.getElementById('rpmFL')
            },
            FR: {
                arrow: document.getElementById('arrowFR'),
                val: document.getElementById('valFR'),
                rpm: document.getElementById('rpmFR')
            },
            RL: {
                arrow: document.getElementById('arrowRL'),
                val: document.getElementById('valRL'),
                rpm: document.getElementById('rpmRL')
            },
            RR: {
                arrow: document.getElementById('arrowRR'),
                val: document.getElementById('valRR'),
                rpm: document.getElementById('rpmRR')
            }
        }
    };

    // Battery display elements
    const batteryPercentageText = document.querySelector('.battery-percentage-text');
    const batteryRemainingValue = document.querySelector('.remaining-value');
    const batteryFillLevel = document.querySelector('.battery-fill-level');

    /**
     * Update wheel display
     */
    function setWheel(id: string, torque: number, rpm: number): void {
        const valEl = document.getElementById('val' + id);
        const rpmEl = document.getElementById('rpm' + id);
        const progEl = document.getElementById('prog' + id);

        if (rpmEl) rpmEl.textContent = String(rpm);
        if (valEl) {
            valEl.innerHTML = (torque >= 0 ? '+' : '') + torque.toFixed(2) + ' <span class="torque-unit">Nm</span>';
        }
        if (progEl) {
            const percentage = Math.min((rpm / 250) * 100, 100);
            (progEl as HTMLElement).style.width = percentage + '%';
        }
    }

    /**
     * Update chart data with new value
     */
    function updateModeData(mode: keyof ChartDataConfig, range: 'seconds' | 'minutes' | 'hours', value: number): void {
        if (!chartData[mode] || !chartData[mode].ranges[range]) return;
        if (chartData[mode].type === 'multi') return;

        const rangeData = chartData[mode].ranges[range] as TimeRangeData;
        rangeData.data.push(value);
        rangeData.data.shift();
    }

    /**
     * Update torque chart data
     */
    function updateTorqueData(torques: { FL: number; FR: number; RL: number; RR: number }, range: 'seconds' | 'minutes' | 'hours'): void {
        const rangeData = chartData.torque.ranges[range];

        rangeData.datasets[0].data.push(torques.FL);
        rangeData.datasets[0].data.shift();

        rangeData.datasets[1].data.push(torques.FR);
        rangeData.datasets[1].data.shift();

        rangeData.datasets[2].data.push(torques.RL);
        rangeData.datasets[2].data.shift();

        rangeData.datasets[3].data.push(torques.RR);
        rangeData.datasets[3].data.shift();
    }

    /**
     * Handle incoming robot data
     */
    function handleRobotData(data: RobotData): void {
        const now = new Date();

        // Update clock
        if (dom.clock) {
            dom.clock.textContent = now.toLocaleTimeString('en-GB', { hour12: false });
        }

        // Update running time
        if (dom.running) {
            const hours = Math.floor(data.system.uptime / 3600);
            const minutes = Math.floor((data.system.uptime % 3600) / 60);
            const seconds = Math.floor(data.system.uptime % 60);
            dom.running.textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }

        // Update system status
        if (dom.uptime && dom.running) {
            dom.uptime.textContent = dom.running.textContent;
        }

        // Update ping
        if (dom.ping) {
            dom.ping.textContent = data.system.ping_ms + ' ms';
            (dom.ping as HTMLElement).style.color =
                data.system.ping_ms < 50 ? '#4ADE80' : (data.system.ping_ms < 100 ? '#FACC15' : '#EF4444');
        }

        // Update electrical displays
        if (dom.valVoltage) dom.valVoltage.textContent = data.electrical.voltage.toFixed(1) + ' V';
        if (dom.valCell) dom.valCell.textContent = data.electrical.cell_voltage.toFixed(2) + ' V';
        if (dom.valPower) dom.valPower.textContent = Math.floor(data.electrical.power) + ' W';
        if (dom.valCurrent) {
            dom.valCurrent.textContent = data.electrical.current.toFixed(1) + ' A';
            (dom.valCurrent as HTMLElement).style.color =
                data.electrical.current < 10 ? '#4ADE80' : (data.electrical.current < 20 ? '#FACC15' : '#EF4444');
        }

        // Update wheels
        setWheel('FL', data.motors.torques.FL, data.motors.rpm.FL);
        setWheel('FR', data.motors.torques.FR, data.motors.rpm.FR);
        setWheel('RL', data.motors.torques.RL, data.motors.rpm.RL);
        setWheel('RR', data.motors.torques.RR, data.motors.rpm.RR);

        if (dom.valRPM) dom.valRPM.textContent = String(data.motors.avg_rpm);

        // Update battery display
        if (batteryPercentageText) {
            batteryPercentageText.textContent = Math.round(data.battery.soc) + '%';
        }

        if (batteryRemainingValue) {
            const hours = Math.floor(data.battery.runtime_hours);
            const minutes = Math.round((data.battery.runtime_hours - hours) * 60);
            batteryRemainingValue.textContent = hours + 'h ' + minutes + 'm';
        }

        // Update battery fill bar (SVG animation)
        if (batteryFillLevel) {
            const soc = data.battery.soc; // 0-100
            const maxHeight = 149; // Max height from HTML
            const fillHeight = (soc / 100) * maxHeight;

            // Calculate y position (fill from bottom up)
            const yPosition = 18 + (maxHeight - fillHeight);

            batteryFillLevel.setAttribute('height', fillHeight.toString());
            batteryFillLevel.setAttribute('y', yPosition.toString());
        }

        // Update direction indicator
        const overallDirection = document.getElementById('overallDirection');
        if (overallDirection) {
            const mag = Math.sqrt(data.motion.vx * data.motion.vx + data.motion.vy * data.motion.vy);
            const icon = overallDirection.querySelector('i');

            if (mag < 0.1 && Math.abs(data.motion.w) < 0.1) {
                overallDirection.classList.remove('active');
            } else {
                overallDirection.classList.add('active');

                if (Math.abs(data.motion.w) > 0.5 && mag < 0.3) {
                    overallDirection.classList.add('rotating');
                    if (icon) {
                        // Inverted: w > 0 means rotate right, w < 0 means rotate left
                        icon.className = data.motion.w > 0 ? 'bx bx-rotate-right' : 'bx bx-rotate-left';
                        (icon as HTMLElement).style.transform = '';
                    }
                } else {
                    overallDirection.classList.remove('rotating');
                    if (icon) {
                        // No axis inversion needed for correct direction
                        // Icon is up-arrow (0 deg).
                        // Atan2(vy, vx) gives 0 for Forward(X), 90 for Left(Y).
                        // We want 0 for Forward, -90 for Left.
                        // So rotation = -angle
                        const angle = Math.atan2(data.motion.vy, data.motion.vx) * (180 / Math.PI);
                        const rotation = -angle;
                        icon.className = 'bx bx-up-arrow-alt';
                        (icon as HTMLElement).style.transform = `rotate(${rotation}deg)`;
                    }
                }
            }
        }

        // Data aggregation
        if (Date.now() - lastSecondUpdate >= 1000) {
            lastSecondUpdate = Date.now();

            // Update seconds data
            updateModeData('power', 'seconds', data.electrical.power);
            updateModeData('voltage', 'seconds', data.electrical.voltage);
            updateModeData('current', 'seconds', data.electrical.current);
            updateTorqueData(data.motors.torques, 'seconds');

            secBuffer.power.push(data.electrical.power);
            secBuffer.voltage.push(data.electrical.voltage);
            secBuffer.current.push(data.electrical.current);

            // Update minutes data
            if (secBuffer.power.length >= 60) {
                const avgPower = secBuffer.power.reduce((a, b) => a + b, 0) / 60;
                const avgVoltage = secBuffer.voltage.reduce((a, b) => a + b, 0) / 60;
                const avgCurrent = secBuffer.current.reduce((a, b) => a + b, 0) / 60;

                updateModeData('power', 'minutes', avgPower);
                updateModeData('voltage', 'minutes', avgVoltage);
                updateModeData('current', 'minutes', avgCurrent);

                minBuffer.power.push(avgPower);
                minBuffer.voltage.push(avgVoltage);
                minBuffer.current.push(avgCurrent);

                secBuffer.power = [];
                secBuffer.voltage = [];
                secBuffer.current = [];
            }

            // Update hours data
            if (minBuffer.power.length >= 60) {
                const avgPower = minBuffer.power.reduce((a, b) => a + b, 0) / 60;
                const avgVoltage = minBuffer.voltage.reduce((a, b) => a + b, 0) / 60;
                const avgCurrent = minBuffer.current.reduce((a, b) => a + b, 0) / 60;

                updateModeData('power', 'hours', avgPower);
                updateModeData('voltage', 'hours', avgVoltage);
                updateModeData('current', 'hours', avgCurrent);

                minBuffer.power = [];
                minBuffer.voltage = [];
                minBuffer.current = [];
            }

            // Refresh chart
            if (electricalChart) {
                electricalChart.update('none');
            }
        }
    }

    // ========================================================================
    // WEBSOCKET CONNECTION
    // ========================================================================

    const wsManager = new WebSocketManager();

    wsManager.onConnect(() => {
        logToTerminal('Connected to robot controller');
        console.log('[App] WebSocket connected');
    });

    wsManager.onDisconnect(() => {
        logToTerminal('Disconnected from robot controller');
        console.log('[App] WebSocket disconnected');
    });

    wsManager.onData(handleRobotData);

    // Sync saved state with controller on connection
    wsManager.onConnect(() => {
        const savedState = localStorage.getItem('robot_running') === 'true';
        if (savedState) {
            wsManager.send({ command: 'start_program' });
            logToTerminal('Connected - Syncing state: Robot ENABLED');
        } else {
            wsManager.send({ command: 'stop_program' });
            logToTerminal('Connected - Syncing state: Robot DISABLED');
        }
    });

    // Start connection
    wsManager.connect();

    // ========================================================================
    // BATTERY CONFIGURATION HANDLERS
    // ========================================================================

    const btnBatteryConfig = document.getElementById('btnBatteryConfig');
    const batteryConfigModal = document.getElementById('batteryConfigModal');
    const btnApplyConfig = document.getElementById('btnApplyConfig');
    const btnCancelConfig = document.getElementById('btnCancelConfig');
    const batteryType = document.getElementById('batteryType') as HTMLSelectElement;
    const seriesConfig = document.getElementById('seriesConfig') as HTMLSelectElement;
    const customSeriesConfig = document.getElementById('customSeriesConfig') as HTMLSelectElement;
    const configPreview = document.getElementById('configPreview');
    const customVoltageInputs = document.getElementById('customVoltageInputs');
    const standardSeriesConfig = document.getElementById('standardSeriesConfig');
    const dynamicBatteryInputs = document.getElementById('dynamicBatteryInputs');

    const batterySpecs: { [key: string]: { nominal: number, max: number, min: number, cells: number } } = {
        '2S': { nominal: 7.4, max: 8.4, min: 6.0, cells: 2 },
        '3S': { nominal: 11.1, max: 12.6, min: 9.0, cells: 3 },
        '4S': { nominal: 14.8, max: 16.8, min: 12.0, cells: 4 }
    };

    /**
     * Generate dynamic battery input fields based on series count
     */
    function generateCustomBatteryInputs(seriesCount: number): void {
        if (!dynamicBatteryInputs) return;

        dynamicBatteryInputs.innerHTML = '';

        for (let i = 1; i <= seriesCount; i++) {
            const batteryGroup = document.createElement('div');
            batteryGroup.className = 'battery-input-group';
            batteryGroup.style.cssText = 'background: white; padding: 12px; border-radius: 6px; border: 1px solid #e2e8f0;';

            batteryGroup.innerHTML = `
                <div style="margin-bottom: 8px; font-weight: 500; color: #334155; font-size: 0.9rem;">
                    Battery ${i}
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                    <div>
                        <label for="battery${i}Nominal" style="font-size: 0.75rem; color: #64748b; display: block; margin-bottom: 3px;">Nominal (V)</label>
                        <input type="number" id="battery${i}Nominal" class="config-select custom-battery-input" 
                               value="11.10" step="0.01" min="0" 
                               style="padding: 6px 8px; font-size: 0.85rem;">
                    </div>
                    <div>
                        <label for="battery${i}Max" style="font-size: 0.75rem; color: #64748b; display: block; margin-bottom: 3px;">Max (V)</label>
                        <input type="number" id="battery${i}Max" class="config-select custom-battery-input" 
                               value="12.60" step="0.01" min="0"
                               style="padding: 6px 8px; font-size: 0.85rem;">
                    </div>
                    <div>
                        <label for="battery${i}Min" style="font-size: 0.75rem; color: #64748b; display: block; margin-bottom: 3px;">Min (V)</label>
                        <input type="number" id="battery${i}Min" class="config-select custom-battery-input" 
                               value="9.00" step="0.01" min="0"
                               style="padding: 6px 8px; font-size: 0.85rem;">
                    </div>
                </div>
            `;

            dynamicBatteryInputs.appendChild(batteryGroup);
        }

        // Add event listeners for real-time preview update
        const inputs = dynamicBatteryInputs.querySelectorAll('.custom-battery-input');
        inputs.forEach(input => {
            input.addEventListener('input', updateBatteryPreview);
            input.addEventListener('blur', formatToTwoDecimals);
        });
    }

    /**
     * Format input value to 2 decimal places on blur
     */
    function formatToTwoDecimals(event: Event): void {
        const input = event.target as HTMLInputElement;
        const value = parseFloat(input.value);
        if (!isNaN(value)) {
            input.value = value.toFixed(2);
        }
    }

    /**
     * Read custom battery values from inputs
     */
    function getCustomBatteryValues(): Array<{ nominal: number, max: number, min: number }> | null {
        if (!customSeriesConfig || !dynamicBatteryInputs) return null;

        const seriesCount = parseInt(customSeriesConfig.value);
        const batteries: Array<{ nominal: number, max: number, min: number }> = [];

        for (let i = 1; i <= seriesCount; i++) {
            const nominalInput = document.getElementById(`battery${i}Nominal`) as HTMLInputElement;
            const maxInput = document.getElementById(`battery${i}Max`) as HTMLInputElement;
            const minInput = document.getElementById(`battery${i}Min`) as HTMLInputElement;

            if (!nominalInput || !maxInput || !minInput) return null;

            const nominal = parseFloat(nominalInput.value);
            const max = parseFloat(maxInput.value);
            const min = parseFloat(minInput.value);

            if (isNaN(nominal) || isNaN(max) || isNaN(min)) return null;

            batteries.push({ nominal, max, min });
        }

        return batteries;
    }

    /**
     * Validate custom battery configuration
     */
    function validateCustomBatteries(batteries: Array<{ nominal: number, max: number, min: number }>): { valid: boolean, error?: string } {
        for (let i = 0; i < batteries.length; i++) {
            const b = batteries[i];
            const batteryNum = i + 1;

            if (b.nominal <= 0 || b.max <= 0 || b.min <= 0) {
                return { valid: false, error: `Battery ${batteryNum}: All voltages must be positive` };
            }

            if (!(b.max > b.nominal && b.nominal > b.min)) {
                return { valid: false, error: `Battery ${batteryNum}: Must satisfy Max > Nominal > Min` };
            }
        }

        return { valid: true };
    }

    /**
     * Update battery configuration preview
     */
    function updateBatteryPreview(): void {
        if (!batteryType || !configPreview) return;

        const type = batteryType.value;

        if (type === 'Custom') {
            // Custom battery mode
            const batteries = getCustomBatteryValues();
            if (!batteries) {
                configPreview.innerHTML = `
                    <span class="preview-cells">Custom</span>
                    <span class="preview-voltage">Check inputs</span>
                `;
                return;
            }

            const validation = validateCustomBatteries(batteries);
            if (!validation.valid) {
                configPreview.innerHTML = `
                    <span class="preview-cells" style="color: #ef4444;">⚠ Error</span>
                    <span class="preview-voltage" style="color: #ef4444; font-size: 0.8rem;">${validation.error}</span>
                `;
                return;
            }

            const totalNominal = batteries.reduce((sum, b) => sum + b.nominal, 0);
            const totalMax = batteries.reduce((sum, b) => sum + b.max, 0);

            configPreview.innerHTML = `
                <span class="preview-cells">Custom</span>
                <span class="preview-voltage">${totalNominal.toFixed(2)}V nominal (${totalMax.toFixed(2)}V max)</span>
            `;
        } else {
            // Standard battery mode
            if (!seriesConfig) return;

            const series = parseInt(seriesConfig.value);
            const spec = batterySpecs[type];

            const totalCells = spec.cells * series;
            const totalNominal = spec.nominal * series;
            const totalMax = spec.max * series;

            configPreview.innerHTML = `
                <span class="preview-cells">${totalCells}S</span>
                <span class="preview-voltage">${totalNominal.toFixed(1)}V nominal (${totalMax.toFixed(1)}V max)</span>
            `;
        }
    }

    /**
     * Handle battery type change (show/hide custom inputs)
     */
    function handleBatteryTypeChange(): void {
        if (!batteryType || !customVoltageInputs || !standardSeriesConfig) return;

        const isCustom = batteryType.value === 'Custom';

        if (isCustom) {
            customVoltageInputs.style.display = 'block';
            standardSeriesConfig.style.display = 'none';

            // Generate initial battery inputs
            const seriesCount = customSeriesConfig ? parseInt(customSeriesConfig.value) : 2;
            generateCustomBatteryInputs(seriesCount);
        } else {
            customVoltageInputs.style.display = 'none';
            standardSeriesConfig.style.display = 'block';
        }

        updateBatteryPreview();
    }

    // Event listeners
    if (btnBatteryConfig) {
        btnBatteryConfig.addEventListener('click', () => {
            console.log('[BTN] Battery Config button clicked');
            if (batteryConfigModal) {
                batteryConfigModal.style.display = 'flex';
                handleBatteryTypeChange();
                updateBatteryPreview();
            }
        });
    }

    if (btnCancelConfig) {
        btnCancelConfig.addEventListener('click', () => {
            if (batteryConfigModal) {
                batteryConfigModal.style.display = 'none';
            }
        });
    }

    if (batteryType) {
        batteryType.addEventListener('change', handleBatteryTypeChange);
    }

    if (seriesConfig) {
        seriesConfig.addEventListener('change', updateBatteryPreview);
    }

    if (customSeriesConfig) {
        customSeriesConfig.addEventListener('change', () => {
            const seriesCount = parseInt(customSeriesConfig.value);
            generateCustomBatteryInputs(seriesCount);
            updateBatteryPreview();
        });
    }

    if (btnApplyConfig) {
        btnApplyConfig.addEventListener('click', () => {
            console.log('[BTN] Apply Config button clicked');
            if (!batteryType) return;

            const type = batteryType.value;
            let config: any;

            if (type === 'Custom') {
                const batteries = getCustomBatteryValues();
                if (!batteries) {
                    alert('❌ Error: Please check all battery voltage inputs');
                    return;
                }

                const validation = validateCustomBatteries(batteries);
                if (!validation.valid) {
                    alert(`❌ Validation Error:\n\n${validation.error}\n\nPlease ensure Max > Nominal > Min for each battery.`);
                    return;
                }

                config = {
                    command: 'update_battery_config',
                    battery_type: 'Custom',
                    series_count: batteries.length,
                    custom_batteries: batteries
                };
            } else {
                if (!seriesConfig) return;

                config = {
                    command: 'update_battery_config',
                    battery_type: type,
                    series_count: parseInt(seriesConfig.value)
                };
            }

            wsManager.send(config);

            // Reset charts on config change
            resetCharts();
            logToTerminal('Battery configuration updated - Graphs reset');

            if (batteryConfigModal) {
                batteryConfigModal.style.display = 'none';
            }

            // Update UI Labels
            const seriesCnt = config.series_count;
            const batType = type === 'Custom' ? 'Custom' : type;
            const specTitle = document.getElementById('batterySpecTitle');
            const specDetails = document.getElementById('batterySpecDetails');

            if (specTitle) {
                // Format: "2x LiPo 4S"
                specTitle.textContent = `${seriesCnt}x LiPo ${batType}`;
            }

            if (specDetails) {
                // Format: "5200mAh • Series" or "5200mAh • Single"
                const configStr = seriesCnt > 1 ? 'Series' : 'Single';
                specDetails.textContent = `5200mAh • ${configStr}`;
            }

            const displayType = type === 'Custom' ?
                `Custom (${config.series_count}x batteries)` :
                `${type} x${config.series_count}`;

            alert(`✅ Battery config updated to ${displayType}!\n\nPlease RELOAD controller in Webots for changes to take effect.`);
        });
    }
});
