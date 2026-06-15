# Communication Stack Specification

Document ID: COM
Type: communication

## CAN

### COM-REQ-0101 — Primary CAN bit rate

The primary CAN bus shall operate at 500 kbit/s.

- Status: active
- Parameters: can_baud_kbps = 500

### COM-REQ-0145 — Transport layer timeout

The CAN transport layer timeout shall be 1500 ms.

- Status: active
- Parameters: transport_timeout_ms = 1500

### COM-REQ-0200 — Communication stack behavior

The communication stack shall log a status event when the operating mode changes.

- Status: active

### COM-REQ-0204 — Supervision logic behavior

The supervision logic shall persist its state across a controlled reset.

- Status: active
- References: SYS-REQ-0106

### COM-REQ-0208 — Non-volatile memory handler behavior

The non-volatile memory handler shall report its health to the system supervisor each cycle.

- Status: active

### COM-REQ-0212 — Power management module behavior

The power management module shall raise a warning when an inconsistent configuration is detected.

- Status: active

## Ethernet

### COM-REQ-0110 — Diagnostic Ethernet link speed

The diagnostic Ethernet link shall operate at 100 Mbit/s using 100BASE-T1.

- Status: active
- Parameters: eth_speed_mbps = 100

### COM-REQ-0201 — Network management layer behavior

The network management layer shall report its health to the system supervisor each cycle.

- Status: active
- References: SAFE-REQ-0110

### COM-REQ-0205 — Bootloader behavior

The bootloader shall document its interface in the released specification.

- Status: active

### COM-REQ-0209 — Supervision logic behavior

The supervision logic shall follow the layered architecture defined for this ECU.

- Status: active
- References: DIAG-REQ-0209

### COM-REQ-0213 — Non-volatile memory handler behavior

The non-volatile memory handler shall expose its configuration through the standard diagnostic interface.

- Status: active

## Network Management

### COM-REQ-0102 — Transceiver sleep behavior

The CAN transceiver remains fully powered during sleep to enable bus wake-up, drawing approximately 5 mA.

- Status: active
- Parameters: transceiver_sleep_current_ma = 5

### COM-REQ-0150 — Bus-off recovery

After a bus-off event the node shall attempt recovery after 100 ms.

- Status: active
- Parameters: bus_off_recovery_ms = 100

### COM-REQ-0202 — Non-volatile memory handler behavior

The non-volatile memory handler shall follow the layered architecture defined for this ECU.

- Status: active
- References: DIAG-REQ-0103

### COM-REQ-0206 — Communication stack behavior

The communication stack shall be verifiable through the integration test harness.

- Status: active
- References: PWR-REQ-0110

### COM-REQ-0210 — Application software behavior

The application software shall follow the layered architecture defined for this ECU.

- Status: active

### COM-REQ-0214 — Non-volatile memory handler behavior

The non-volatile memory handler shall log a status event when the operating mode changes.

- Status: active
- References: COM-REQ-0208

## References

### COM-REQ-0103 — Legacy transport timing

CAN transport layer timeout shall be 1000 ms. This requirement is superseded by COM-REQ-0145.

- Status: superseded
- Superseded by: COM-REQ-0145

### COM-REQ-0203 — Bootloader behavior

The bootloader shall log a status event when the operating mode changes.

- Status: active

### COM-REQ-0207 — Diagnostic manager behavior

The diagnostic manager shall document its interface in the released specification.

- Status: active

### COM-REQ-0211 — Non-volatile memory handler behavior

The non-volatile memory handler shall expose its configuration through the standard diagnostic interface.

- Status: active
- References: DIAG-REQ-0102

### COM-REQ-0215 — Diagnostic manager behavior

The diagnostic manager shall be verifiable through the integration test harness.

- Status: active
