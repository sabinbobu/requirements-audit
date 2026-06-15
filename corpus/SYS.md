# System Requirements Specification

Document ID: SYS
Type: system

## General

### SYS-REQ-0107 — Operating temperature range

The ECU shall operate from -40 degC to +85 degC.

- Status: active
- Parameters: operating_temp_range_c = -40..85

### SYS-REQ-0200 — Non-volatile memory handler behavior

The non-volatile memory handler shall follow the layered architecture defined for this ECU.

- Status: active

### SYS-REQ-0204 — Network management layer behavior

The network management layer shall report its health to the system supervisor each cycle.

- Status: active
- References: SAFE-REQ-0201

### SYS-REQ-0208 — Application software behavior

The application software shall log a status event when the operating mode changes.

- Status: active

### SYS-REQ-0212 — Diagnostic manager behavior

The diagnostic manager shall log a status event when the operating mode changes.

- Status: active

## Timing

### SYS-REQ-0101 — Watchdog supervision timeout

The watchdog supervision timeout shall be 100 ms for all operating modes.

- Status: active
- Parameters: watchdog_timeout_ms = 100

### SYS-REQ-0102 — Operational readiness time

The ECU shall reach the operational state within 800 ms of power-on.

- Status: active
- Parameters: boot_time_ms = 800

### SYS-REQ-0103 — Diagnostic response time

A diagnostic request shall receive a response within 50 ms.

- Status: active
- Parameters: diag_response_ms = 50

### SYS-REQ-0105 — Legacy startup indication

Boot indication shall complete within 2000 ms. This requirement is superseded by SYS-REQ-0140.

- Status: superseded
- Superseded by: SYS-REQ-0140

### SYS-REQ-0106 — Watchdog timeout (normal mode)

In normal operating mode the watchdog timeout shall be 100 ms.

- Status: active
- Parameters: watchdog_timeout_normal_ms = 100

### SYS-REQ-0108 — Diagnostic response budget

A diagnostic response shall be returned within 100 ms.

- Status: active
- Parameters: diag_response_budget_ms = 100

### SYS-REQ-0140 — Boot completion indication

Boot completion shall be indicated to the driver within 1500 ms of ignition-on. This requirement replaces the withdrawn startup-indication requirement.

- Status: active
- Parameters: boot_indication_ms = 1500

### SYS-REQ-0201 — Supervision logic behavior

The supervision logic shall be verifiable through the integration test harness.

- Status: active

### SYS-REQ-0205 — Power management module behavior

The power management module shall raise a warning when an inconsistent configuration is detected.

- Status: active

### SYS-REQ-0209 — Network management layer behavior

The network management layer shall log a status event when the operating mode changes.

- Status: active
- References: PWR-REQ-0206

### SYS-REQ-0213 — Diagnostic manager behavior

The diagnostic manager shall raise a warning when an inconsistent configuration is detected.

- Status: active

## Architecture

### SYS-REQ-0104 — Controller architecture

The system is built on a single-controller architecture with no redundant processing channel.

- Status: active

### SYS-REQ-0202 — Supervision logic behavior

The supervision logic shall follow the layered architecture defined for this ECU.

- Status: active

### SYS-REQ-0206 — Non-volatile memory handler behavior

The non-volatile memory handler shall expose its configuration through the standard diagnostic interface.

- Status: active

### SYS-REQ-0210 — Power management module behavior

The power management module shall raise a warning when an inconsistent configuration is detected.

- Status: active

### SYS-REQ-0214 — Network management layer behavior

The network management layer shall be verifiable through the integration test harness.

- Status: active

## Connectivity

### SYS-REQ-0150 — OTA update size

The ECU shall support over-the-air software updates of up to 64 MB.

- Status: active
- Parameters: ota_max_mb = 64

### SYS-REQ-0203 — Power management module behavior

The power management module shall document its interface in the released specification.

- Status: active

### SYS-REQ-0207 — Bootloader behavior

The bootloader shall raise a warning when an inconsistent configuration is detected.

- Status: active

### SYS-REQ-0211 — Non-volatile memory handler behavior

The non-volatile memory handler shall raise a warning when an inconsistent configuration is detected.

- Status: active

### SYS-REQ-0215 — Network management layer behavior

The network management layer shall document its interface in the released specification.

- Status: active
