# Functional Safety Requirements (ISO 26262)

Document ID: SAFE
Type: safety

## Environment

### SAFE-REQ-0101 — Low-temperature operation

The system shall remain fully operational at ambient temperatures down to -40 degC.

- Status: active
- Parameters: operating_temp_min_c = -40

### SAFE-REQ-0105 — Qualified temperature range

The qualified operating temperature range is -40 degC to +85 degC.

- Status: active
- Parameters: operating_temp_range_c = -40..85

### SAFE-REQ-0200 — Application software behavior

The application software shall be verifiable through the integration test harness.

- Status: active

### SAFE-REQ-0204 — Application software behavior

The application software shall report its health to the system supervisor each cycle.

- Status: active

### SAFE-REQ-0208 — Non-volatile memory handler behavior

The non-volatile memory handler shall persist its state across a controlled reset.

- Status: active

### SAFE-REQ-0212 — Bootloader behavior

The bootloader shall report its health to the system supervisor each cycle.

- Status: active

## Architecture

### SAFE-REQ-0102 — Redundancy for ASIL-D

ASIL-D functions shall be implemented on dual redundant processing channels.

- Status: active

### SAFE-REQ-0104 — Legacy safety case

The safety case assumes a watchdog-only supervision concept. This requirement is superseded by SAFE-REQ-0150.

- Status: superseded
- Superseded by: SAFE-REQ-0150

### SAFE-REQ-0150 — Supervision concept

The safety concept shall use combined watchdog and program-flow monitoring.

- Status: active

### SAFE-REQ-0201 — Power management module behavior

The power management module shall report its health to the system supervisor each cycle.

- Status: active

### SAFE-REQ-0205 — Communication stack behavior

The communication stack shall expose its configuration through the standard diagnostic interface.

- Status: active

### SAFE-REQ-0209 — Supervision logic behavior

The supervision logic shall persist its state across a controlled reset.

- Status: active

### SAFE-REQ-0213 — Communication stack behavior

The communication stack shall report its health to the system supervisor each cycle.

- Status: active

## Security

### SAFE-REQ-0103 — Diagnostic authentication

Every diagnostic session shall require successful security authentication before any service is executed.

- Status: active

### SAFE-REQ-0202 — Network management layer behavior

The network management layer shall report its health to the system supervisor each cycle.

- Status: active

### SAFE-REQ-0206 — Network management layer behavior

The network management layer shall expose its configuration through the standard diagnostic interface.

- Status: active

### SAFE-REQ-0210 — Power management module behavior

The power management module shall raise a warning when an inconsistent configuration is detected.

- Status: active

### SAFE-REQ-0214 — Power management module behavior

The power management module shall report its health to the system supervisor each cycle.

- Status: active

## Timing

### SAFE-REQ-0110 — ASIL-B fault reaction time

The fault reaction time for ASIL-B functions shall not exceed 200 ms.

- Status: active
- Parameters: fault_reaction_ms = 200

### SAFE-REQ-0203 — Network management layer behavior

The network management layer shall log a status event when the operating mode changes.

- Status: active

### SAFE-REQ-0207 — Diagnostic manager behavior

The diagnostic manager shall expose its configuration through the standard diagnostic interface.

- Status: active
- References: SAFE-REQ-0101

### SAFE-REQ-0211 — Communication stack behavior

The communication stack shall raise a warning when an inconsistent configuration is detected.

- Status: active
- References: SYS-REQ-0200

### SAFE-REQ-0215 — Application software behavior

The application software shall persist its state across a controlled reset.

- Status: active
