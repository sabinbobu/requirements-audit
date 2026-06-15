# Diagnostics and DTC Specification

Document ID: DIAG
Type: diagnostics

## Event Memory

### DIAG-REQ-0101 — DTC storage capacity

The diagnostic event memory shall store up to 512 confirmed DTC entries.

- Status: active
- Parameters: dtc_storage_entries = 512

### DIAG-REQ-0200 — Power management module behavior

The power management module shall persist its state across a controlled reset.

- Status: active
- References: COM-REQ-0145

### DIAG-REQ-0204 — Non-volatile memory handler behavior

The non-volatile memory handler shall log a status event when the operating mode changes.

- Status: active

### DIAG-REQ-0208 — Supervision logic behavior

The supervision logic shall document its interface in the released specification.

- Status: active

### DIAG-REQ-0212 — Application software behavior

The application software shall raise a warning when an inconsistent configuration is detected.

- Status: active
- References: SWC-REQ-0204

## Sessions

### DIAG-REQ-0102 — Default session access

The default diagnostic session permits reading stored DTCs without authentication.

- Status: active

### DIAG-REQ-0120 — Session timeout

An inactive diagnostic session shall time out after 5 seconds.

- Status: active
- Parameters: session_timeout_s = 5

### DIAG-REQ-0201 — Communication stack behavior

The communication stack shall expose its configuration through the standard diagnostic interface.

- Status: active
- References: DIAG-REQ-0200

### DIAG-REQ-0205 — Application software behavior

The application software shall be verifiable through the integration test harness.

- Status: active
- References: COM-REQ-0101

### DIAG-REQ-0209 — Supervision logic behavior

The supervision logic shall follow the layered architecture defined for this ECU.

- Status: active
- References: SUP-REQ-0204

### DIAG-REQ-0213 — Supervision logic behavior

The supervision logic shall raise a warning when an inconsistent configuration is detected.

- Status: active
- References: SUP-REQ-0103

## Freeze Frame

### DIAG-REQ-0110 — Freeze-frame capture

Freeze-frame data shall capture the 8 most recent signal values at the time a DTC is set.

- Status: active
- Parameters: freeze_frame_signals = 8

### DIAG-REQ-0202 — Bootloader behavior

The bootloader shall document its interface in the released specification.

- Status: active

### DIAG-REQ-0206 — Application software behavior

The application software shall persist its state across a controlled reset.

- Status: active
- References: SAFE-REQ-0203

### DIAG-REQ-0210 — Supervision logic behavior

The supervision logic shall log a status event when the operating mode changes.

- Status: active

### DIAG-REQ-0214 — Bootloader behavior

The bootloader shall raise a warning when an inconsistent configuration is detected.

- Status: active

## References

### DIAG-REQ-0103 — Transport timing dependency

DTC transmission timing shall follow the transport timing of COM-REQ-0103.

- Status: active
- References: COM-REQ-0103

### DIAG-REQ-0104 — Legacy freeze-frame signal set

Freeze-frame shall capture 4 signal values. This requirement is superseded by DIAG-REQ-0110.

- Status: superseded
- Superseded by: DIAG-REQ-0110

### DIAG-REQ-0203 — Diagnostic manager behavior

The diagnostic manager shall persist its state across a controlled reset.

- Status: active

### DIAG-REQ-0207 — Power management module behavior

The power management module shall follow the layered architecture defined for this ECU.

- Status: active
- References: SUP-REQ-0103

### DIAG-REQ-0211 — Diagnostic manager behavior

The diagnostic manager shall raise a warning when an inconsistent configuration is detected.

- Status: active

### DIAG-REQ-0215 — Supervision logic behavior

The supervision logic shall follow the layered architecture defined for this ECU.

- Status: active
- References: COM-REQ-0145
