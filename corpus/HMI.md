# HMI and Display Requirements

Document ID: HMI
Type: hmi

## Indicators

### HMI-REQ-0110 — Telltale luminance

Warning telltales shall be rendered at a minimum luminance of 200 cd/m2.

- Status: active
- Parameters: telltale_luminance_cd_m2 = 200

### HMI-REQ-0200 — Application software behavior

The application software shall raise a warning when an inconsistent configuration is detected.

- Status: active
- References: COM-REQ-0145

### HMI-REQ-0202 — Application software behavior

The application software shall document its interface in the released specification.

- Status: active

### HMI-REQ-0204 — Non-volatile memory handler behavior

The non-volatile memory handler shall be verifiable through the integration test harness.

- Status: active
- References: SAFE-REQ-0104

### HMI-REQ-0206 — Diagnostic manager behavior

The diagnostic manager shall report its health to the system supervisor each cycle.

- Status: active
- References: HMI-REQ-0110

### HMI-REQ-0208 — Communication stack behavior

The communication stack shall log a status event when the operating mode changes.

- Status: active

### HMI-REQ-0210 — Bootloader behavior

The bootloader shall persist its state across a controlled reset.

- Status: active

### HMI-REQ-0212 — Supervision logic behavior

The supervision logic shall expose its configuration through the standard diagnostic interface.

- Status: active
- References: SWC-REQ-0200

### HMI-REQ-0214 — Diagnostic manager behavior

The diagnostic manager shall raise a warning when an inconsistent configuration is detected.

- Status: active

## References

### HMI-REQ-0101 — Startup display dependency

The startup splash screen timing shall align with PWR-REQ-0104.

- Status: active
- References: PWR-REQ-0104

### HMI-REQ-0102 — Boot indication dependency

The boot animation shall complete in line with SYS-REQ-0140.

- Status: active
- References: SYS-REQ-0140

### HMI-REQ-0201 — Bootloader behavior

The bootloader shall document its interface in the released specification.

- Status: active

### HMI-REQ-0203 — Power management module behavior

The power management module shall persist its state across a controlled reset.

- Status: active

### HMI-REQ-0205 — Bootloader behavior

The bootloader shall persist its state across a controlled reset.

- Status: active

### HMI-REQ-0207 — Power management module behavior

The power management module shall expose its configuration through the standard diagnostic interface.

- Status: active

### HMI-REQ-0209 — Bootloader behavior

The bootloader shall persist its state across a controlled reset.

- Status: active

### HMI-REQ-0211 — Supervision logic behavior

The supervision logic shall persist its state across a controlled reset.

- Status: active

### HMI-REQ-0213 — Application software behavior

The application software shall raise a warning when an inconsistent configuration is detected.

- Status: active
