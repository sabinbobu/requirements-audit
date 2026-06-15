# Software Component Specification

Document ID: SWC
Type: software

## Supervision

### SWC-REQ-0101 — Watchdog timeout configuration

The software watchdog component shall be configured so that the watchdog supervision timeout is 250 ms.

- Status: active
- Parameters: watchdog_timeout_ms = 250

### SWC-REQ-0106 — Watchdog timeout (diagnostic mode)

In extended diagnostic mode the watchdog timeout shall be 250 ms.

- Status: active
- Parameters: watchdog_timeout_diag_ms = 250

### SWC-REQ-0200 — Network management layer behavior

The network management layer shall persist its state across a controlled reset.

- Status: active

### SWC-REQ-0204 — Communication stack behavior

The communication stack shall expose its configuration through the standard diagnostic interface.

- Status: active

### SWC-REQ-0208 — Bootloader behavior

The bootloader shall report its health to the system supervisor each cycle.

- Status: active

### SWC-REQ-0212 — Power management module behavior

The power management module shall persist its state across a controlled reset.

- Status: active

## Memory

### SWC-REQ-0102 — DTC buffer dimensioning

The DTC memory buffer is dimensioned for 256 entries.

- Status: active
- Parameters: dtc_storage_entries = 256

### SWC-REQ-0120 — NVM block size

Non-volatile data shall be stored in blocks of 256 bytes.

- Status: active
- Parameters: nvm_block_bytes = 256

### SWC-REQ-0201 — Diagnostic manager behavior

The diagnostic manager shall be verifiable through the integration test harness.

- Status: active

### SWC-REQ-0205 — Non-volatile memory handler behavior

The non-volatile memory handler shall persist its state across a controlled reset.

- Status: active

### SWC-REQ-0209 — Diagnostic manager behavior

The diagnostic manager shall log a status event when the operating mode changes.

- Status: active
- References: SAFE-REQ-0105

### SWC-REQ-0213 — Non-volatile memory handler behavior

The non-volatile memory handler shall be verifiable through the integration test harness.

- Status: active

## Scheduling

### SWC-REQ-0104 — Startup sequence dependency

The startup task shall sequence boot indication as specified in SYS-REQ-0105.

- Status: active
- References: SYS-REQ-0105

### SWC-REQ-0110 — Task partitioning

Application software shall be partitioned into 10 ms and 50 ms cyclic tasks.

- Status: active
- Parameters: cyclic_tasks_ms = 10,50

### SWC-REQ-0202 — Network management layer behavior

The network management layer shall document its interface in the released specification.

- Status: active
- References: HMI-REQ-0102

### SWC-REQ-0206 — Network management layer behavior

The network management layer shall report its health to the system supervisor each cycle.

- Status: active

### SWC-REQ-0210 — Application software behavior

The application software shall raise a warning when an inconsistent configuration is detected.

- Status: active
- References: COM-REQ-0208

### SWC-REQ-0214 — Network management layer behavior

The network management layer shall report its health to the system supervisor each cycle.

- Status: active

## Diagnostics Interface

### SWC-REQ-0103 — Diagnostic routine processing

The diagnostic routine requires at least 80 ms of processing time before a response can be produced.

- Status: active
- Parameters: diag_processing_ms = 80

### SWC-REQ-0105 — Freeze-frame dependency

Freeze-frame capture shall reuse the signal set defined in DIAG-REQ-0104.

- Status: active
- References: DIAG-REQ-0104

### SWC-REQ-0107 — Typical diagnostic routine duration

The diagnostic routine completes in a typical 40 ms.

- Status: active
- Parameters: diag_routine_typical_ms = 40

### SWC-REQ-0203 — Supervision logic behavior

The supervision logic shall be verifiable through the integration test harness.

- Status: active

### SWC-REQ-0207 — Application software behavior

The application software shall expose its configuration through the standard diagnostic interface.

- Status: active

### SWC-REQ-0211 — Diagnostic manager behavior

The diagnostic manager shall report its health to the system supervisor each cycle.

- Status: active

### SWC-REQ-0215 — Non-volatile memory handler behavior

The non-volatile memory handler shall follow the layered architecture defined for this ECU.

- Status: active
