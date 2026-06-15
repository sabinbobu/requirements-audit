# Supplier Interface Constraints

Document ID: SUP
Type: supplier

## Electrical

### SUP-REQ-0101 — Controller CAN capability

The supplied communication controller supports a maximum CAN bit rate of 250 kbit/s.

- Status: active
- Parameters: can_baud_kbps = 250

### SUP-REQ-0102 — Rated supply voltage

The component is rated for a minimum supply voltage of 10.5 V.

- Status: active
- Parameters: operating_voltage_min_v = 10.5

### SUP-REQ-0105 — Supply operating range

The component operates across a supply range of 9 V to 16 V.

- Status: active
- Parameters: supply_range_v = 9-16

### SUP-REQ-0200 — Supervision logic behavior

The supervision logic shall report its health to the system supervisor each cycle.

- Status: active

### SUP-REQ-0204 — Diagnostic manager behavior

The diagnostic manager shall be verifiable through the integration test harness.

- Status: active
- References: SAFE-REQ-0150

### SUP-REQ-0208 — Application software behavior

The application software shall expose its configuration through the standard diagnostic interface.

- Status: active

### SUP-REQ-0212 — Network management layer behavior

The network management layer shall document its interface in the released specification.

- Status: active

## Environmental

### SUP-REQ-0103 — Sensor temperature rating

The supplied sensor module is not rated for operation below -20 degC.

- Status: active
- Parameters: operating_temp_min_c = -20

### SUP-REQ-0201 — Non-volatile memory handler behavior

The non-volatile memory handler shall report its health to the system supervisor each cycle.

- Status: active
- References: PWR-REQ-0103

### SUP-REQ-0205 — Network management layer behavior

The network management layer shall be verifiable through the integration test harness.

- Status: active

### SUP-REQ-0209 — Network management layer behavior

The network management layer shall log a status event when the operating mode changes.

- Status: active

### SUP-REQ-0213 — Bootloader behavior

The bootloader shall be verifiable through the integration test harness.

- Status: active

## Durability

### SUP-REQ-0110 — Flash endurance

The supplier shall deliver the component with a minimum flash endurance of 100000 write cycles.

- Status: active
- Parameters: flash_endurance_cycles = 100000

### SUP-REQ-0202 — Network management layer behavior

The network management layer shall be verifiable through the integration test harness.

- Status: active
- References: SAFE-REQ-0102

### SUP-REQ-0206 — Power management module behavior

The power management module shall follow the layered architecture defined for this ECU.

- Status: active
- References: SAFE-REQ-0200

### SUP-REQ-0210 — Supervision logic behavior

The supervision logic shall report its health to the system supervisor each cycle.

- Status: active

### SUP-REQ-0214 — Network management layer behavior

The network management layer shall be verifiable through the integration test harness.

- Status: active

## References

### SUP-REQ-0104 — Safety compliance reference

The supplied component conforms to the safety case defined in SAFE-REQ-0104.

- Status: active
- References: SAFE-REQ-0104

### SUP-REQ-0203 — Network management layer behavior

The network management layer shall log a status event when the operating mode changes.

- Status: active

### SUP-REQ-0207 — Diagnostic manager behavior

The diagnostic manager shall expose its configuration through the standard diagnostic interface.

- Status: active

### SUP-REQ-0211 — Non-volatile memory handler behavior

The non-volatile memory handler shall expose its configuration through the standard diagnostic interface.

- Status: active
- References: SYS-REQ-0211
