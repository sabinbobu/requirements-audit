# Power Management Specification

Document ID: PWR
Type: power

## Startup

### PWR-REQ-0101 — Cold-start initialization

Cold-start initialization of the ECU completes within 1200 ms.

- Status: active
- Parameters: boot_time_ms = 1200

### PWR-REQ-0160 — Inrush settling time

Startup inrush current shall settle within 250 ms.

- Status: active
- Parameters: inrush_settle_ms = 250

### PWR-REQ-0200 — Supervision logic behavior

The supervision logic shall follow the layered architecture defined for this ECU.

- Status: active
- References: SYS-REQ-0150

### PWR-REQ-0204 — Bootloader behavior

The bootloader shall expose its configuration through the standard diagnostic interface.

- Status: active

### PWR-REQ-0208 — Communication stack behavior

The communication stack shall document its interface in the released specification.

- Status: active
- References: PWR-REQ-0201

### PWR-REQ-0212 — Power management module behavior

The power management module shall persist its state across a controlled reset.

- Status: active
- References: PWR-REQ-0207

## Supply

### PWR-REQ-0102 — Minimum operating voltage

The ECU shall remain operational down to a supply voltage of 9.0 V.

- Status: active
- Parameters: operating_voltage_min_v = 9.0

### PWR-REQ-0105 — Nominal supply voltage

The nominal supply voltage is 12 V.

- Status: active
- Parameters: nominal_voltage_v = 12

### PWR-REQ-0201 — Application software behavior

The application software shall expose its configuration through the standard diagnostic interface.

- Status: active

### PWR-REQ-0205 — Application software behavior

The application software shall expose its configuration through the standard diagnostic interface.

- Status: active

### PWR-REQ-0209 — Communication stack behavior

The communication stack shall document its interface in the released specification.

- Status: active

### PWR-REQ-0213 — Communication stack behavior

The communication stack shall document its interface in the released specification.

- Status: active

## Sleep

### PWR-REQ-0103 — Sleep quiescent current

Quiescent current in sleep mode shall not exceed 100 uA.

- Status: active
- Parameters: sleep_current_ua = 100

### PWR-REQ-0110 — Sleep entry timeout

The ECU shall enter sleep mode after 4 seconds of bus inactivity.

- Status: active
- Parameters: sleep_entry_s = 4

### PWR-REQ-0202 — Power management module behavior

The power management module shall persist its state across a controlled reset.

- Status: active

### PWR-REQ-0206 — Communication stack behavior

The communication stack shall follow the layered architecture defined for this ECU.

- Status: active

### PWR-REQ-0210 — Non-volatile memory handler behavior

The non-volatile memory handler shall follow the layered architecture defined for this ECU.

- Status: active

### PWR-REQ-0214 — Supervision logic behavior

The supervision logic shall be verifiable through the integration test harness.

- Status: active

## References

### PWR-REQ-0104 — Legacy startup power profile

Startup inrush shall settle within 300 ms. This requirement is superseded by PWR-REQ-0160.

- Status: superseded
- Superseded by: PWR-REQ-0160

### PWR-REQ-0203 — Network management layer behavior

The network management layer shall log a status event when the operating mode changes.

- Status: active

### PWR-REQ-0207 — Non-volatile memory handler behavior

The non-volatile memory handler shall follow the layered architecture defined for this ECU.

- Status: active

### PWR-REQ-0211 — Power management module behavior

The power management module shall raise a warning when an inconsistent configuration is detected.

- Status: active

### PWR-REQ-0215 — Application software behavior

The application software shall report its health to the system supervisor each cycle.

- Status: active
