"""The seed specification — the authoritative source of ground truth.

Everything here is hand-authored and declarative. The generator emits requirement
documents *from* this data, so the planted contradictions are guaranteed present
and exactly counted. Protect this property (requirements-audit.agent.md →
"ground truth by construction"): if you edit a seeded requirement's text, keep the
matching `evidence_quote_*` a verbatim substring — the integrity tests enforce it.

Domain: an automotive ECU program (AUTOSAR-flavored) across eight specification
documents authored by different teams/suppliers — the realistic setting in which
the same parameter ends up stated two different ways.
"""

from __future__ import annotations

from dataclasses import dataclass

from requirements_audit.models import (
    ConflictType,
    GoldenQuestion,
    Requirement,
    RequirementStatus,
    ScenarioTag,
)

# ─── Documents ───────────────────────────────────────────────────────────────
# doc_id -> (title, doc_type, [section names])
DOCUMENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "SYS": (
        "System Requirements Specification",
        "system",
        ("General", "Timing", "Architecture", "Connectivity"),
    ),
    "SWC": (
        "Software Component Specification",
        "software",
        ("Supervision", "Memory", "Scheduling", "Diagnostics Interface"),
    ),
    "DIAG": (
        "Diagnostics and DTC Specification",
        "diagnostics",
        ("Event Memory", "Sessions", "Freeze Frame", "References"),
    ),
    "PWR": (
        "Power Management Specification",
        "power",
        ("Startup", "Supply", "Sleep", "References"),
    ),
    "COM": (
        "Communication Stack Specification",
        "communication",
        ("CAN", "Ethernet", "Network Management", "References"),
    ),
    "SAFE": (
        "Functional Safety Requirements (ISO 26262)",
        "safety",
        ("Environment", "Architecture", "Security", "Timing"),
    ),
    "SUP": (
        "Supplier Interface Constraints",
        "supplier",
        ("Electrical", "Environmental", "Durability", "References"),
    ),
    "HMI": (
        "HMI and Display Requirements",
        "hmi",
        ("Indicators", "References"),
    ),
}


def _req(
    id: str,
    section: str,
    title: str,
    text: str,
    category: str,
    *,
    parameters: dict[str, str] | None = None,
    refs: list[str] | None = None,
    status: RequirementStatus = RequirementStatus.ACTIVE,
    superseded_by: str | None = None,
) -> Requirement:
    """Build a Requirement; doc_id is derived from the id prefix (e.g. SYS-REQ-0101)."""
    return Requirement(
        id=id,
        doc_id=id.split("-", 1)[0],
        section=section,
        title=title,
        text=text,
        category=category,
        parameters=parameters or {},
        refs=refs or [],
        status=status,
        superseded_by=superseded_by,
    )


@dataclass(frozen=True)
class Seed:
    """A seeded requirement pair plus its conflict metadata.

    is_true_conflict=False marks a near-miss: the pair shares an entity and *looks*
    like the conflict type above it, but is actually consistent — a precision/FP probe.
    """

    conflict_id: str
    conflict_type: ConflictType
    req_a: Requirement
    req_b: Requirement
    evidence_quote_a: str
    evidence_quote_b: str
    rationale: str
    is_true_conflict: bool = True


@dataclass(frozen=True)
class Anchor:
    """A clean, single-document requirement used as a success Q&A target."""

    requirement: Requirement
    question: str
    facts: tuple[str, ...]


# ─── Active replacement requirement referenced by C11 / N03 ──────────────────
SYS_REQ_0140 = _req(
    "SYS-REQ-0140",
    "Timing",
    "Boot completion indication",
    "Boot completion shall be indicated to the driver within 1500 ms of ignition-on. "
    "This requirement replaces the withdrawn startup-indication requirement.",
    "timing",
    parameters={"boot_indication_ms": "1500"},
)


# ─── 15 true contradictions + 5 near-misses ──────────────────────────────────
SEEDS: list[Seed] = [
    # ----- numeric_mismatch (5) -----
    Seed(
        "C01",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "SYS-REQ-0101",
            "Timing",
            "Watchdog supervision timeout",
            "The watchdog supervision timeout shall be 100 ms for all operating modes.",
            "timing",
            parameters={"watchdog_timeout_ms": "100"},
        ),
        _req(
            "SWC-REQ-0101",
            "Supervision",
            "Watchdog timeout configuration",
            "The software watchdog component shall be configured so that the watchdog "
            "supervision timeout is 250 ms.",
            "timing",
            parameters={"watchdog_timeout_ms": "250"},
        ),
        "The watchdog supervision timeout shall be 100 ms",
        "the watchdog supervision timeout is 250 ms",
        "Same watchdog timeout parameter specified with two different values (100 ms vs 250 ms).",
    ),
    Seed(
        "C02",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "COM-REQ-0101",
            "CAN",
            "Primary CAN bit rate",
            "The primary CAN bus shall operate at 500 kbit/s.",
            "communication",
            parameters={"can_baud_kbps": "500"},
        ),
        _req(
            "SUP-REQ-0101",
            "Electrical",
            "Controller CAN capability",
            "The supplied communication controller supports a maximum CAN bit rate of 250 kbit/s.",
            "communication",
            parameters={"can_baud_kbps": "250"},
        ),
        "The primary CAN bus shall operate at 500 kbit/s",
        "maximum CAN bit rate of 250 kbit/s",
        "Required CAN bit rate exceeds the supplied controller's maximum capability.",
    ),
    Seed(
        "C03",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "SYS-REQ-0102",
            "Timing",
            "Operational readiness time",
            "The ECU shall reach the operational state within 800 ms of power-on.",
            "timing",
            parameters={"boot_time_ms": "800"},
        ),
        _req(
            "PWR-REQ-0101",
            "Startup",
            "Cold-start initialization",
            "Cold-start initialization of the ECU completes within 1200 ms.",
            "timing",
            parameters={"boot_time_ms": "1200"},
        ),
        "within 800 ms of power-on",
        "completes within 1200 ms",
        "Boot-time budget stated as 800 ms in one document and 1200 ms in another.",
    ),
    Seed(
        "C04",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "PWR-REQ-0102",
            "Supply",
            "Minimum operating voltage",
            "The ECU shall remain operational down to a supply voltage of 9.0 V.",
            "power",
            parameters={"operating_voltage_min_v": "9.0"},
        ),
        _req(
            "SUP-REQ-0102",
            "Electrical",
            "Rated supply voltage",
            "The component is rated for a minimum supply voltage of 10.5 V.",
            "power",
            parameters={"operating_voltage_min_v": "10.5"},
        ),
        "down to a supply voltage of 9.0 V",
        "minimum supply voltage of 10.5 V",
        "System demands operation below the supplier's rated minimum voltage.",
    ),
    Seed(
        "C05",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "DIAG-REQ-0101",
            "Event Memory",
            "DTC storage capacity",
            "The diagnostic event memory shall store up to 512 confirmed DTC entries.",
            "diagnostics",
            parameters={"dtc_storage_entries": "512"},
        ),
        _req(
            "SWC-REQ-0102",
            "Memory",
            "DTC buffer dimensioning",
            "The DTC memory buffer is dimensioned for 256 entries.",
            "diagnostics",
            parameters={"dtc_storage_entries": "256"},
        ),
        "store up to 512 confirmed DTC entries",
        "dimensioned for 256 entries",
        "Diagnostic memory capacity specified as 512 entries versus 256 entries.",
    ),
    # ----- incompatible_constraint (5) -----
    Seed(
        "C06",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SAFE-REQ-0101",
            "Environment",
            "Low-temperature operation",
            "The system shall remain fully operational at ambient temperatures down to -40 degC.",
            "environment",
            parameters={"operating_temp_min_c": "-40"},
        ),
        _req(
            "SUP-REQ-0103",
            "Environmental",
            "Sensor temperature rating",
            "The supplied sensor module is not rated for operation below -20 degC.",
            "environment",
            parameters={"operating_temp_min_c": "-20"},
        ),
        "operational at ambient temperatures down to -40 degC",
        "not rated for operation below -20 degC",
        "Safety demands operation to -40 degC but a supplied component is unrated below -20 degC.",
    ),
    Seed(
        "C07",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SYS-REQ-0103",
            "Timing",
            "Diagnostic response time",
            "A diagnostic request shall receive a response within 50 ms.",
            "timing",
            parameters={"diag_response_ms": "50"},
        ),
        _req(
            "SWC-REQ-0103",
            "Diagnostics Interface",
            "Diagnostic routine processing",
            "The diagnostic routine requires at least 80 ms of processing time before a "
            "response can be produced.",
            "timing",
            parameters={"diag_processing_ms": "80"},
        ),
        "receive a response within 50 ms",
        "at least 80 ms of processing time before a response",
        "Required 50 ms response is unachievable given a mandated 80 ms minimum processing time.",
    ),
    Seed(
        "C08",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SAFE-REQ-0102",
            "Architecture",
            "Redundancy for ASIL-D",
            "ASIL-D functions shall be implemented on dual redundant processing channels.",
            "architecture",
        ),
        _req(
            "SYS-REQ-0104",
            "Architecture",
            "Controller architecture",
            "The system is built on a single-controller architecture with no redundant "
            "processing channel.",
            "architecture",
        ),
        "dual redundant processing channels",
        "single-controller architecture with no redundant processing channel",
        "ASIL-D redundancy requirement is incompatible with the single-controller architecture.",
    ),
    Seed(
        "C09",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "PWR-REQ-0103",
            "Sleep",
            "Sleep quiescent current",
            "Quiescent current in sleep mode shall not exceed 100 uA.",
            "power",
            parameters={"sleep_current_ua": "100"},
        ),
        _req(
            "COM-REQ-0102",
            "Network Management",
            "Transceiver sleep behavior",
            "The CAN transceiver remains fully powered during sleep to enable bus wake-up, "
            "drawing approximately 5 mA.",
            "power",
            parameters={"transceiver_sleep_current_ma": "5"},
        ),
        "shall not exceed 100 uA",
        "drawing approximately 5 mA",
        "A 5 mA transceiver sleep draw cannot meet the 100 uA quiescent-current budget.",
    ),
    Seed(
        "C10",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SAFE-REQ-0103",
            "Security",
            "Diagnostic authentication",
            "Every diagnostic session shall require successful security authentication before "
            "any service is executed.",
            "security",
        ),
        _req(
            "DIAG-REQ-0102",
            "Sessions",
            "Default session access",
            "The default diagnostic session permits reading stored DTCs without authentication.",
            "security",
        ),
        "require successful security authentication before any service is executed",
        "permits reading stored DTCs without authentication",
        "Mandatory authentication for every session conflicts with unauthenticated default-session reads.",
    ),
    # ----- superseded_reference (5) -----
    Seed(
        "C11",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "SWC-REQ-0104",
            "Scheduling",
            "Startup sequence dependency",
            "The startup task shall sequence boot indication as specified in SYS-REQ-0105.",
            "timing",
            refs=["SYS-REQ-0105"],
        ),
        _req(
            "SYS-REQ-0105",
            "Timing",
            "Legacy startup indication",
            "Boot indication shall complete within 2000 ms. This requirement is superseded by "
            "SYS-REQ-0140.",
            "timing",
            status=RequirementStatus.SUPERSEDED,
            superseded_by="SYS-REQ-0140",
        ),
        "as specified in SYS-REQ-0105",
        "This requirement is superseded by SYS-REQ-0140",
        "An active requirement depends on SYS-REQ-0105, which has been superseded.",
    ),
    Seed(
        "C12",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "DIAG-REQ-0103",
            "References",
            "Transport timing dependency",
            "DTC transmission timing shall follow the transport timing of COM-REQ-0103.",
            "communication",
            refs=["COM-REQ-0103"],
        ),
        _req(
            "COM-REQ-0103",
            "References",
            "Legacy transport timing",
            "CAN transport layer timeout shall be 1000 ms. This requirement is superseded by "
            "COM-REQ-0145.",
            "communication",
            status=RequirementStatus.SUPERSEDED,
            superseded_by="COM-REQ-0145",
        ),
        "the transport timing of COM-REQ-0103",
        "This requirement is superseded by COM-REQ-0145",
        "Diagnostic timing depends on COM-REQ-0103, which has been superseded.",
    ),
    Seed(
        "C13",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "SUP-REQ-0104",
            "References",
            "Safety compliance reference",
            "The supplied component conforms to the safety case defined in SAFE-REQ-0104.",
            "safety",
            refs=["SAFE-REQ-0104"],
        ),
        _req(
            "SAFE-REQ-0104",
            "Architecture",
            "Legacy safety case",
            "The safety case assumes a watchdog-only supervision concept. This requirement is "
            "superseded by SAFE-REQ-0150.",
            "safety",
            status=RequirementStatus.SUPERSEDED,
            superseded_by="SAFE-REQ-0150",
        ),
        "the safety case defined in SAFE-REQ-0104",
        "This requirement is superseded by SAFE-REQ-0150",
        "A supplier requirement conforms to SAFE-REQ-0104, which has been superseded.",
    ),
    Seed(
        "C14",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "HMI-REQ-0101",
            "References",
            "Startup display dependency",
            "The startup splash screen timing shall align with PWR-REQ-0104.",
            "power",
            refs=["PWR-REQ-0104"],
        ),
        _req(
            "PWR-REQ-0104",
            "References",
            "Legacy startup power profile",
            "Startup inrush shall settle within 300 ms. This requirement is superseded by "
            "PWR-REQ-0160.",
            "power",
            status=RequirementStatus.SUPERSEDED,
            superseded_by="PWR-REQ-0160",
        ),
        "shall align with PWR-REQ-0104",
        "This requirement is superseded by PWR-REQ-0160",
        "An HMI requirement aligns to PWR-REQ-0104, which has been superseded.",
    ),
    Seed(
        "C15",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "SWC-REQ-0105",
            "Diagnostics Interface",
            "Freeze-frame dependency",
            "Freeze-frame capture shall reuse the signal set defined in DIAG-REQ-0104.",
            "diagnostics",
            refs=["DIAG-REQ-0104"],
        ),
        _req(
            "DIAG-REQ-0104",
            "References",
            "Legacy freeze-frame signal set",
            "Freeze-frame shall capture 4 signal values. This requirement is superseded by "
            "DIAG-REQ-0110.",
            "diagnostics",
            status=RequirementStatus.SUPERSEDED,
            superseded_by="DIAG-REQ-0110",
        ),
        "the signal set defined in DIAG-REQ-0104",
        "This requirement is superseded by DIAG-REQ-0110",
        "A software requirement reuses DIAG-REQ-0104, which has been superseded.",
    ),
    # ----- near-misses (5): look like a conflict, are actually consistent -----
    Seed(
        "N01",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "SYS-REQ-0106",
            "Timing",
            "Watchdog timeout (normal mode)",
            "In normal operating mode the watchdog timeout shall be 100 ms.",
            "timing",
            parameters={"watchdog_timeout_normal_ms": "100"},
        ),
        _req(
            "SWC-REQ-0106",
            "Supervision",
            "Watchdog timeout (diagnostic mode)",
            "In extended diagnostic mode the watchdog timeout shall be 250 ms.",
            "timing",
            parameters={"watchdog_timeout_diag_ms": "250"},
        ),
        "In normal operating mode the watchdog timeout shall be 100 ms",
        "In extended diagnostic mode the watchdog timeout shall be 250 ms",
        "Different values but explicitly mode-qualified — not a contradiction.",
        is_true_conflict=False,
    ),
    Seed(
        "N02",
        ConflictType.NUMERIC_MISMATCH,
        _req(
            "PWR-REQ-0105",
            "Supply",
            "Nominal supply voltage",
            "The nominal supply voltage is 12 V.",
            "power",
            parameters={"nominal_voltage_v": "12"},
        ),
        _req(
            "SUP-REQ-0105",
            "Electrical",
            "Supply operating range",
            "The component operates across a supply range of 9 V to 16 V.",
            "power",
            parameters={"supply_range_v": "9-16"},
        ),
        "The nominal supply voltage is 12 V",
        "supply range of 9 V to 16 V",
        "12 V nominal falls inside the 9-16 V supplier range — consistent.",
        is_true_conflict=False,
    ),
    Seed(
        "N03",
        ConflictType.SUPERSEDED_REFERENCE,
        _req(
            "HMI-REQ-0102",
            "References",
            "Boot indication dependency",
            "The boot animation shall complete in line with SYS-REQ-0140.",
            "timing",
            refs=["SYS-REQ-0140"],
        ),
        SYS_REQ_0140,
        "in line with SYS-REQ-0140",
        "Boot completion shall be indicated to the driver within 1500 ms",
        "Reference points to the active replacement requirement, not a superseded one — consistent.",
        is_true_conflict=False,
    ),
    Seed(
        "N04",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SYS-REQ-0107",
            "General",
            "Operating temperature range",
            "The ECU shall operate from -40 degC to +85 degC.",
            "environment",
            parameters={"operating_temp_range_c": "-40..85"},
        ),
        _req(
            "SAFE-REQ-0105",
            "Environment",
            "Qualified temperature range",
            "The qualified operating temperature range is -40 degC to +85 degC.",
            "environment",
            parameters={"operating_temp_range_c": "-40..85"},
        ),
        "operate from -40 degC to +85 degC",
        "operating temperature range is -40 degC to +85 degC",
        "Identical temperature ranges stated in two documents — consistent.",
        is_true_conflict=False,
    ),
    Seed(
        "N05",
        ConflictType.INCOMPATIBLE_CONSTRAINT,
        _req(
            "SYS-REQ-0108",
            "Timing",
            "Diagnostic response budget",
            "A diagnostic response shall be returned within 100 ms.",
            "timing",
            parameters={"diag_response_budget_ms": "100"},
        ),
        _req(
            "SWC-REQ-0107",
            "Diagnostics Interface",
            "Typical diagnostic routine duration",
            "The diagnostic routine completes in a typical 40 ms.",
            "timing",
            parameters={"diag_routine_typical_ms": "40"},
        ),
        "returned within 100 ms",
        "completes in a typical 40 ms",
        "40 ms typical duration comfortably meets the 100 ms budget — consistent.",
        is_true_conflict=False,
    ),
]


# ─── Clean Q&A anchors (success scenario) ────────────────────────────────────
ANCHORS: list[Anchor] = [
    Anchor(SYS_REQ_0140, "When must boot completion be indicated to the driver?", ("1500 ms",)),
    Anchor(
        _req(
            "COM-REQ-0110",
            "Ethernet",
            "Diagnostic Ethernet link speed",
            "The diagnostic Ethernet link shall operate at 100 Mbit/s using 100BASE-T1.",
            "communication",
            parameters={"eth_speed_mbps": "100"},
        ),
        "What speed does the diagnostic Ethernet link operate at?",
        ("100 Mbit/s",),
    ),
    Anchor(
        _req(
            "DIAG-REQ-0110",
            "Freeze Frame",
            "Freeze-frame capture",
            "Freeze-frame data shall capture the 8 most recent signal values at the time a "
            "DTC is set.",
            "diagnostics",
            parameters={"freeze_frame_signals": "8"},
        ),
        "How many signal values does freeze-frame data capture?",
        ("8",),
    ),
    Anchor(
        _req(
            "PWR-REQ-0110",
            "Sleep",
            "Sleep entry timeout",
            "The ECU shall enter sleep mode after 4 seconds of bus inactivity.",
            "power",
            parameters={"sleep_entry_s": "4"},
        ),
        "After how long of bus inactivity does the ECU enter sleep mode?",
        ("4 seconds",),
    ),
    Anchor(
        _req(
            "SAFE-REQ-0110",
            "Timing",
            "ASIL-B fault reaction time",
            "The fault reaction time for ASIL-B functions shall not exceed 200 ms.",
            "safety",
            parameters={"fault_reaction_ms": "200"},
        ),
        "What is the maximum fault reaction time for ASIL-B functions?",
        ("200 ms",),
    ),
    Anchor(
        _req(
            "SWC-REQ-0110",
            "Scheduling",
            "Task partitioning",
            "Application software shall be partitioned into 10 ms and 50 ms cyclic tasks.",
            "scheduling",
            parameters={"cyclic_tasks_ms": "10,50"},
        ),
        "What cyclic task periods is the application software partitioned into?",
        ("10 ms", "50 ms"),
    ),
    Anchor(
        _req(
            "SUP-REQ-0110",
            "Durability",
            "Flash endurance",
            "The supplier shall deliver the component with a minimum flash endurance of "
            "100000 write cycles.",
            "durability",
            parameters={"flash_endurance_cycles": "100000"},
        ),
        "What minimum flash endurance must the supplier deliver?",
        ("100000",),
    ),
    Anchor(
        _req(
            "HMI-REQ-0110",
            "Indicators",
            "Telltale luminance",
            "Warning telltales shall be rendered at a minimum luminance of 200 cd/m2.",
            "hmi",
            parameters={"telltale_luminance_cd_m2": "200"},
        ),
        "What minimum luminance is required for warning telltales?",
        ("200 cd/m2",),
    ),
    Anchor(
        _req(
            "SYS-REQ-0150",
            "Connectivity",
            "OTA update size",
            "The ECU shall support over-the-air software updates of up to 64 MB.",
            "connectivity",
            parameters={"ota_max_mb": "64"},
        ),
        "What is the maximum over-the-air software update size?",
        ("64 MB",),
    ),
    Anchor(
        _req(
            "COM-REQ-0145",
            "CAN",
            "Transport layer timeout",
            "The CAN transport layer timeout shall be 1500 ms.",
            "communication",
            parameters={"transport_timeout_ms": "1500"},
        ),
        "What is the CAN transport layer timeout?",
        ("1500 ms",),
    ),
    Anchor(
        _req(
            "SAFE-REQ-0150",
            "Architecture",
            "Supervision concept",
            "The safety concept shall use combined watchdog and program-flow monitoring.",
            "safety",
        ),
        "What supervision concept does the safety concept require?",
        ("watchdog", "program-flow monitoring"),
    ),
    Anchor(
        _req(
            "PWR-REQ-0160",
            "Startup",
            "Inrush settling time",
            "Startup inrush current shall settle within 250 ms.",
            "power",
            parameters={"inrush_settle_ms": "250"},
        ),
        "Within how long must startup inrush current settle?",
        ("250 ms",),
    ),
    Anchor(
        _req(
            "DIAG-REQ-0120",
            "Sessions",
            "Session timeout",
            "An inactive diagnostic session shall time out after 5 seconds.",
            "diagnostics",
            parameters={"session_timeout_s": "5"},
        ),
        "After how long does an inactive diagnostic session time out?",
        ("5 seconds",),
    ),
    Anchor(
        _req(
            "SWC-REQ-0120",
            "Memory",
            "NVM block size",
            "Non-volatile data shall be stored in blocks of 256 bytes.",
            "memory",
            parameters={"nvm_block_bytes": "256"},
        ),
        "What block size is used for non-volatile data storage?",
        ("256 bytes",),
    ),
    Anchor(
        _req(
            "COM-REQ-0150",
            "Network Management",
            "Bus-off recovery",
            "After a bus-off event the node shall attempt recovery after 100 ms.",
            "communication",
            parameters={"bus_off_recovery_ms": "100"},
        ),
        "How long after a bus-off event does the node attempt recovery?",
        ("100 ms",),
    ),
]


# ─── Hand-authored multi-result questions (each matches several real reqs) ────
MULTI_QUESTIONS: list[GoldenQuestion] = [
    GoldenQuestion(
        id="",
        question="What are the requirements related to the watchdog supervision timeout?",
        expected_source_ids=["SYS-REQ-0101", "SWC-REQ-0101", "SYS-REQ-0106", "SWC-REQ-0106"],
        expected_facts=[],
        scenario=ScenarioTag.MULTI_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="Which requirements specify CAN communication parameters?",
        expected_source_ids=["COM-REQ-0101", "SUP-REQ-0101", "COM-REQ-0145", "COM-REQ-0150"],
        expected_facts=[],
        scenario=ScenarioTag.MULTI_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="What requirements constrain the ECU supply voltage?",
        expected_source_ids=["PWR-REQ-0102", "SUP-REQ-0102", "PWR-REQ-0105", "SUP-REQ-0105"],
        expected_facts=[],
        scenario=ScenarioTag.MULTI_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="Which requirements address diagnostic timing?",
        expected_source_ids=["SYS-REQ-0103", "SWC-REQ-0103", "SYS-REQ-0108", "SWC-REQ-0107"],
        expected_facts=[],
        scenario=ScenarioTag.MULTI_RESULT,
    ),
]


# ─── Hand-authored edge-case questions (no expected sources) ──────────────────
EDGE_QUESTIONS: list[GoldenQuestion] = [
    # no_result — the corpus contains nothing on these topics.
    GoldenQuestion(
        id="",
        question="What is the maximum towing capacity of the vehicle?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="Which tire pressure is recommended for winter driving?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="What is the warranty period for the infotainment head unit?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="How many cup holders does the center console provide?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="What is the curb weight of the vehicle?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    GoldenQuestion(
        id="",
        question="What paint colors are offered for the exterior?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.NO_RESULT,
    ),
    # missing_data — topic is in scope, but the specific value is not stated anywhere.
    GoldenQuestion(
        id="",
        question="What is the exact maximum CAN message latency in milliseconds?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    GoldenQuestion(
        id="",
        question="What is the precise quiescent current target for Ethernet in sleep mode?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    GoldenQuestion(
        id="",
        question="What is the maximum number of concurrent diagnostic sessions?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    GoldenQuestion(
        id="",
        question="What CPU clock frequency is specified for the controller?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    GoldenQuestion(
        id="",
        question="What is the specified mean time between failures (MTBF) of the ECU?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    GoldenQuestion(
        id="",
        question="What is the exact RAM size allocated to the diagnostic stack?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.MISSING_DATA,
    ),
    # permission_edge — asks for access control the system does not model.
    GoldenQuestion(
        id="",
        question="Which engineers are authorized to approve changes to the safety requirements?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.PERMISSION_EDGE,
    ),
    GoldenQuestion(
        id="",
        question="Who has write access to the supplier interface document?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.PERMISSION_EDGE,
    ),
    GoldenQuestion(
        id="",
        question="What clearance level is required to read the security requirements?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.PERMISSION_EDGE,
    ),
    GoldenQuestion(
        id="",
        question="Which team owns the approval workflow for diagnostic sessions?",
        expected_source_ids=[],
        expected_facts=[],
        scenario=ScenarioTag.PERMISSION_EDGE,
    ),
]


# Filler-generation vocabulary (deterministic templates; never seeded conflicts).
FILLER_TARGET_TOTAL: int = 180
FILLER_ID_START: int = 200
