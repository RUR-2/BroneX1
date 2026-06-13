# Mermaid Chart Codes - Digital Twin Robot Omnidirectional

## 1. Diagram Arsitektur Sistem (Functional Diagram)

```mermaid
graph TB
    subgraph "Physical Robot"
        ESP32[ESP32 Motor Controller]
        MOTORS[4x Omnidirectional Motors]
        BATTERY[2x LiPo 3S - 5200mAh Serial]
        ESP32 --> MOTORS
        BATTERY --> ESP32
    end

    subgraph "Orange Pi 5 Pro"
        BRIDGE[orange_tcp_bridge.py]
        ROS2_PUB[ROS2 Publishers]
        ROS2_SUB[ROS2 Subscribers]
        SERIAL[Serial /dev/ttyS0]
        
        BRIDGE --> ROS2_PUB
        ROS2_SUB --> BRIDGE
        BRIDGE --> SERIAL
    end

    subgraph "Laptop"
        WEBOTS[Webots Simulator]
        CONTROLLER[Controller Script]
        WS_SERVER[ws_server.py :8765]
        WEB_DASH[Web Dashboard]
        ROS2_NODE[ROS2 Telemetry Node]
        
        WEBOTS --> CONTROLLER
        CONTROLLER --> ROS2_NODE
        ROS2_NODE --> CONTROLLER
        CONTROLLER <--> WS_SERVER
        WS_SERVER <--> WEB_DASH
    end

    SERIAL -.Serial UART.-> ESP32
    ROS2_PUB -."/robot/motors<br>/robot/battery".-> ROS2_NODE
    ROS2_NODE -."/system/enable".-> ROS2_SUB
    WEB_DASH -.HTTP.-> USER((User))

    style ESP32 fill:#ff9999
    style BRIDGE fill:#ffcc99
    style CONTROLLER fill:#cc99ff
    style WEB_DASH fill:#99ff99
```

---

## 2. Flowchart Startup Sequence (IEEE Standard Format)

```mermaid
flowchart TD
    START([START])
    START --> PROC1[/Launch ws_server.py/]
    PROC1 --> PROC2[/Launch Webots Simulator/]
    PROC2 --> PROC3[/Deploy Remote Scripts/]
    
    PROC3 --> PROC4[Initialize Orange Pi Bridge]
    
    PROC4 --> DEC1{Serial Port<br>Available?}
    DEC1 -->|No| DEC1
    DEC1 -->|Yes| PROC5[Orange Pi Ready]
    
    PROC5 --> PROC6[Start ROS2 Publishers]
    PROC6 --> PROC7[Initialize Telemetry]
    
    PROC2 --> PROC8[Load Controller Script]
    PROC8 --> PROC9[Connect to WebSocket]
    
    PROC7 --> END1
    PROC9 --> END1
    
    END1([SYSTEM ACTIVE])
    
    style START fill:#90EE90
    style END1 fill:#FFD700
    style DEC1 fill:#FFE4B5
```

**Legend (IEEE Standard):**
- `([text])` = Terminal (Start/End)
- `[text]` = Process
- `{text}` = Decision
- `[/text/]` = Input/Output

---

## 3. Flowchart Main Telemetry Loop (IEEE Standard Format)

```mermaid
flowchart TD
    START([START LOOP])
    
    START --> IO1[/Read ROS2 Topics<br>motors & battery/]
    IO1 --> PROC1[Calculate RPM<br>from Velocity]
    PROC1 --> PROC2[Calculate Runtime<br>from Current]
    PROC2 --> PROC3[Calculate Cell Voltage]
    
    PROC3 --> DEC1{Ping Data<br>Updated?}
    DEC1 -->|Yes| PROC4[Use Real Ping Value]
    DEC1 -->|No| PROC5[Use Cached Ping]
    
    PROC4 --> PROC6[Build JSON Payload]
    PROC5 --> PROC6
    
    PROC6 --> IO2[/Send via WebSocket/]
    IO2 --> PROC7[Update Webots 3D Model]
    PROC7 --> PROC8[Sleep 50ms]
    PROC8 --> START
    
    style START fill:#87CEEB
    style DEC1 fill:#FFE4B5
    style IO1 fill:#FFB6C1
    style IO2 fill:#FFB6C1
```

---

## 4. Flowchart Start/Stop Command (IEEE Standard Format)

```mermaid
flowchart TD
    START([USER INPUT])
    
    START --> DEC1{Command<br>Type?}
    DEC1 -->|Stop| PROC1[Dashboard Sends<br>stop_program]
    DEC1 -->|Start| PROC2[Dashboard Sends<br>start_program]
    
    PROC1 --> IO1[/WebSocket Relay<br>to Controller/]
    PROC2 --> IO2[/WebSocket Relay<br>to Controller/]
    
    IO1 --> PROC3[Publish False to<br>/system/enable]
    IO2 --> PROC4[Publish True to<br>/system/enable]
    
    PROC3 --> PROC5[Orange Pi Receives<br>Disable Signal]
    PROC4 --> PROC6[Orange Pi Receives<br>Enable Signal]
    
    PROC5 --> PROC7[Send Stop Command<br>to ESP32]
    PROC6 --> PROC8[Allow Movement<br>Commands]
    
    PROC7 --> END1([MOTORS STOPPED])
    PROC8 --> END2([MOTORS ACTIVE])
    
    style START fill:#90EE90
    style DEC1 fill:#FFE4B5
    style END1 fill:#FF6B6B
    style END2 fill:#4ADE80
    style IO1 fill:#FFB6C1
    style IO2 fill:#FFB6C1
```

---

## 5. Sequence Diagram - Communication Flow

```mermaid
sequenceDiagram
    actor User
    participant Web as Web Dashboard
    participant WS as ws_server.py
    participant Ctrl as Controller
    participant ROS as ROS2 Topic
    participant Orange as Orange Pi Bridge
    participant ESP as ESP32
    
    User->>Web: Click "Stop Program"
    Web->>WS: {"command": "stop_program"}
    WS->>Ctrl: Forward Command
    Ctrl->>ROS: Publish False to /system/enable
    ROS->>Orange: Subscribe /system/enable
    Orange->>Orange: Set system_enabled = False
    Orange->>ESP: Send <127,127,0,0> (Stop)
    ESP->>ESP: Motors Stop
    
    Note over User,ESP: --- Robot Stopped ---
    
    User->>Web: Click "Start Program"
    Web->>WS: {"command": "start_program"}
    WS->>Ctrl: Forward Command
    Ctrl->>ROS: Publish True to /system/enable
    ROS->>Orange: Subscribe /system/enable
    Orange->>Orange: Set system_enabled = True
    Note over Orange: Ready to receive commands
    Orange->>ESP: Resume movement commands
```

---

## IEEE Flowchart Standard - Symbol Guide

### Simbol Standar yang Digunakan:

| Symbol | Mermaid Syntax | Kegunaan | Contoh |
|:---:|:---|:---|:---|
| ![Oval](https://via.placeholder.com/80x40/90EE90/000000?text=START) | `([text])` | Terminal (Start/End) | `([START])` |
| ![Rectangle](https://via.placeholder.com/120x40/87CEEB/000000?text=Process) | `[text]` | Process/Operation | `[Calculate Data]` |
| ![Diamond](https://via.placeholder.com/80x80/FFE4B5/000000?text=?) | `{text}` | Decision | `{Ready?}` |
| ![Parallelogram](https://via.placeholder.com/120x40/FFB6C1/000000?text=Input) | `[/text/]` | Input/Output | `[/Read Data/]` |
| ![Double Rectangle](https://via.placeholder.com/120x40/D3D3D3/000000?text=Predefined) | `[[text]]` | Predefined Process | `[[Init System]]` |

### Aturan Tambahan:
- Aliran dari **atas ke bawah** atau **kiri ke kanan**
- Label decision harus jelas: `Yes/No`, `True/False`, `1/0`
- Setiap proses memiliki 1 input, 1+ output
- Decision memiliki 1 input, 2+ output
- Gunakan warna konsisten untuk kategori yang sama

---

## Cara Pakai

1. **Copy** kode Mermaid di atas
2. **Paste** ke:
   - [Mermaid Live Editor](https://mermaid.live)
   - Markdown viewer yang support Mermaid (GitHub, GitLab, Notion, Obsidian)
   - VSCode dengan extension "Markdown Preview Mermaid Support"
3. Diagram akan ter-render otomatis

## Tips Editing
- Ubah warna: `style NODE_NAME fill:#HEXCOLOR`
- Ubah shape: 
  - `([])` = terminal (oval)
  - `[]` = process (rectangle)
  - `{}` = decision (diamond)
  - `[//]` atau `[\\]` = I/O (parallelogram)
  - `[[]]` = predefined process
- Ubah arrow: 
  - `-->` = solid line
  - `-.->` = dotted line
  - `==>` = thick line

---

**Format:** IEEE Standard Flowchart Symbols  
**Kompatibel dengan:** Mermaid.js, Graphviz, Draw.io
