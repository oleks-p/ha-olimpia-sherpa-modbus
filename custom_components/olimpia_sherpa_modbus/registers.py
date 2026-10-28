"""The Sherpa S2 register map: addresses, encodings and how often to read them.

Protocol only. What an entity shows -- unit, device class, name -- lives with
the entity descriptions in sensor.py and binary_sensor.py.

Sources: the reference unit (SHERPA S2 BIG + S2 14T, firmware 0.57, identify
code 1134), swept and rule-tested by tools/probe_sherpa.py on 2026-10-13
(tests/fixtures/sherpa_s2_big_14t_fw057.json); manual 262860B for meanings,
ranges and enums. Everything is a holding register (FC3, FC4 is unsupported)
and the address is the Olimpia parameter number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

REGISTER_MAP_VERSION = "sherpa-s2-r3"


class Kind(StrEnum):
    U16 = "u16"
    I16 = "i16"
    #: Two registers, HIGH word first.
    U32 = "u32"


class Tier(Enum):
    """Poll cadence in seconds."""

    CONTROL = 10
    PROCESS = 30
    COUNTER = 60
    SETPOINT = 600
    DIAGNOSTIC = 3600

    @property
    def seconds(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class Reg:
    """One logical value in the map."""

    key: str
    address: int
    kind: Kind = Kind.U16
    scale: float = 1.0
    tier: Tier = Tier.SETPOINT
    #: Values outside this band are noise, not readings, and decode to None.
    sane: tuple[float, float] | None = None
    #: Raw words that mean "nothing connected" for this register.
    sentinels: frozenset[int] = frozenset()
    #: Model feature the register exists for (see model.ModelInfo.features).
    feature: str | None = None

    @property
    def words(self) -> int:
        return 2 if self.kind is Kind.U32 else 1

    @property
    def end(self) -> int:
        """Last address the value occupies."""
        return self.address + self.words - 1


#: Contiguous runs of registers that answer on the reference unit. A read that
#: spans anything outside a run is rejected with ILLEGAL_DATA_ADDRESS; every run
#: reads whole in one request (the longest, 217-281, is 65 registers).
ANSWERING_RUNS: tuple[tuple[int, int], ...] = (
    (0, 9), (12, 12), (99, 102), (105, 106), (193, 195), (197, 200), (206, 213),
    (217, 281), (285, 285), (290, 334), (337, 341), (343, 372), (380, 388),
    (401, 408), (500, 507), (561, 624), (900, 900), (910, 914), (951, 955),
    (961, 965), (999, 999),
)
#: Modbus allows 125 registers per FC3 request; nothing here needs more than 65.
MAX_READ = 125

# -- sentinels ----------------------------------------------------------------

#: -501 (-50.1 degC): a probe input with nothing connected.
PROBE_ABSENT = -501 & 0xFFFF
#: -1 (-0.1 degC): also "absent", but only on T5-T8. On T1-T4 it is a real
#: reading -- an outdoor temperature of -0.1 degC must not vanish.
PROBE_ABSENT_ALT = -1 & 0xFFFF
TEMPERATURE_SANE = (-40.0, 120.0)

_T = {"kind": Kind.I16, "scale": 0.1}


def _probes() -> list[Reg]:
    main = frozenset({PROBE_ABSENT})
    optional = frozenset({PROBE_ABSENT, PROBE_ABSENT_ALT})
    common = {**_T, "tier": Tier.PROCESS, "sane": TEMPERATURE_SANE}
    return [
        Reg("water_in", 0, sentinels=main, **common),           # T1, system return
        Reg("water_out", 1, sentinels=main, **common),          # T2, system delivery
        Reg("dhw_tank", 2, sentinels=main, **common),           # T3
        Reg("outdoor_air", 3, sentinels=main, **common),        # T4
        # T5-T7 exist on Aquadue models (the DHW high-temperature circuit), T8 only
        # with a solar-thermal probe. They read -1 / -501 when absent.
        Reg("dhw_compressor_temp", 4, sentinels=optional, **common),   # T5
        Reg("dhw_condenser_temp", 5, sentinels=optional, **common),    # T6
        Reg("dhw_evaporator_temp", 6, sentinels=optional, **common),   # T7
        Reg("solar_temp", 7, sentinels=optional, **common),            # T8
    ]


def _state_words() -> list[Reg]:
    # uint16 matters: read as int16, bit 15 of a bit word turns it negative.
    control = {"tier": Tier.CONTROL}
    return [
        Reg("inputs", 8, **control),
        Reg("status", 12, **control),
        Reg("alarm_1", 100, **control),
        Reg("alarm_2", 101, **control),
        Reg("override", 102, **control),
        Reg("outputs", 105, **control),
        # The mode command (Olimpia RDE448). Read always: with ADDR220 = 1 it is
        # the truth about the mode, and 105-106 is one run, so one request.
        Reg("mode_command", 106, **control),
        Reg("pump_step", 388, **control),
    ]


def _counters() -> list[Reg]:
    counter = {"kind": Kind.U32, "tier": Tier.COUNTER}
    return [
        Reg("compressor_seconds", 270, **counter),
        Reg("pump_seconds", 272, **counter),
        Reg("filter_seconds", 274, **counter),
        Reg("dhw_compressor_seconds", 276, feature="aquadue", **counter),
        Reg("dhw_pump_seconds", 278, feature="aquadue", **counter),
        # Inputs 8 and 9: the Smart Grid / photovoltaic contacts.
        Reg("smart_grid_1_seconds", 343, **counter),
        Reg("smart_grid_2_seconds", 345, **counter),
    ]


def _parameters() -> list[Reg]:
    temp = {**_T, "tier": Tier.SETPOINT}
    plain = {"tier": Tier.SETPOINT}
    return [
        Reg("cooling_setpoint", 206, **temp),
        Reg("cooling_eco_setpoint", 207, **temp),
        Reg("heating_setpoint", 208, **temp),
        Reg("heating_eco_setpoint", 209, **temp),
        Reg("dhw_setpoint", 210, **temp),
        Reg("cooling_curve_enabled", 211, **plain),
        Reg("heating_curve_enabled", 212, **plain),
        Reg("aux_heaters", 217, **plain),
        # CONTROL tier: a flip to serial control (1) must be seen within one poll,
        # and the "unmanaged" repair has to work with mode control off.
        Reg("remote_controls", 220, tier=Tier.CONTROL),
        Reg("external_boiler_enabled", 226, **plain),
        Reg("boiler_threshold", 227, **temp),
        Reg("dhw_source", 228, **plain),
        Reg("legionella_mode", 229, **plain),
        Reg("legionella_interval", 230, **plain),
        Reg("legionella_start_minutes", 231, **plain),
        Reg("legionella_setpoint", 232, **temp),
        Reg("legionella_duration", 233, **plain),
        Reg("freeze_protection", 236, **temp),
        Reg("dhw_hysteresis", 238, **temp),
        # Climatic curves, two points each: the maximum water target and the
        # outdoor temperature (T4) at which it applies, then the same for the
        # minimum. Manual: "outdoor temp. (T4) for max water CP", "max water CP".
        Reg("cooling_curve_max_water_outdoor", 239, **temp),
        Reg("cooling_curve_max_water", 240, **temp),
        Reg("cooling_curve_min_water_outdoor", 241, **temp),
        Reg("cooling_curve_min_water", 242, **temp),
        Reg("heating_curve_max_water_outdoor", 243, **temp),
        Reg("heating_curve_max_water", 244, **temp),
        Reg("heating_curve_min_water_outdoor", 245, **temp),
        Reg("heating_curve_min_water", 246, **temp),
        Reg("dhw_mode", 249, **plain),
        Reg("smart_grid", 341, **plain),
        Reg("water_setpoint_correction", 369, **temp),
        # Pump PWM duty for speed steps 1-8 (step 1 = 5 % = MAXIMUM speed; the
        # PWM is inverted). Decodes pump_step into pump_duty.
        *(Reg(f"pump_duty_{step}", 379 + step, **plain) for step in range(1, 9)),
    ]


def _identity() -> list[Reg]:
    diag = {"tier": Tier.DIAGNOSTIC}
    return [
        Reg("firmware_197", 197, **diag),   # the display/power-board versions;
        Reg("firmware_198", 198, **diag),   # which is which is unconfirmed
        Reg("identify_code", 199, **diag),
        Reg("modbus_address", 247, **diag),
        Reg("idu_model", 370, **diag),
        Reg("odu_model", 371, **diag),
        Reg("protocol", 401, **diag),
    ]


REGISTERS: tuple[Reg, ...] = (
    *_probes(), *_state_words(), *_counters(), *_parameters(), *_identity()
)
BY_KEY: dict[str, Reg] = {reg.key: reg for reg in REGISTERS}

# -- bit words ----------------------------------------------------------------

#: Register 8. INVERTED: a 0 bit means the input is active.
INPUT_BITS: dict[str, int] = {"in_flow": 0, "in_ta": 7}
#: Register 105, active-high.
OUTPUT_BITS: dict[str, int] = {
    "out_pump": 0, "out_dhw_pump": 1, "out_eh1": 2, "out_eh2": 3,
    "out_3way": 4, "out_k5": 5, "out_boiler": 7, "out_alarm": 8,
}
#: Register 12. DHW is either of bits 2 (compressor) and 3 (legionella); the
#: pending pattern is bits 5 and 6 together, which always move as one.
STATUS_MASKS: dict[str, tuple[int, str]] = {
    "mode_cooling": (0x01, "any"),
    "mode_heating": (0x02, "any"),
    "mode_dhw": (0x0C, "any"),
    "mode_legionella": (0x08, "any"),
    "mode_night": (0x80, "any"),
    "mode_pending": (0x60, "all"),
}
#: Register 102, bit 5: OR06, "UE defrosting cycle".
DEFROST_BIT = 5

# -- codes --------------------------------------------------------------------

#: Register 100 bit n -> E(n+1) (E08 confirmed on bit 7); register 101 bit n -> E(20+n).
ALARM_1_CODES: tuple[str, ...] = tuple(f"E{n:02d}" for n in range(1, 10))
ALARM_2_CODES: tuple[str, ...] = tuple(f"E{n}" for n in range(20, 28))
#: Register 102 bit n -> OR(n+1). Inferred: bit 5 is defrost (OR06) and bit 4
#: appeared alone once, consistent with OR05 "UE capacity limitation".
OVERRIDE_CODES: tuple[str, ...] = tuple(f"OR{n:02d}" for n in range(1, 14))

#: Manual 262860B, EN-30. Exposed as attributes (attributes are not translated).
CODE_DESCRIPTIONS: dict[str, str] = {
    "E01": "Inlet water temperature sensor faulty",
    "E02": "Outlet water temperature sensor faulty",
    "E03": "DHW temperature sensor faulty",
    "E04": "External air temperature sensor faulty",
    "E05": "Main exchanger antifreeze protection",
    "E06": "Water flow switch error",
    "E07": "UE communication error",
    "E08": "Disinfection function failed",
    "E09": "RS485 communication error",
    "E20": "DHW circuit flow switch error",
    "E21": "DHW evaporator antifreeze protection",
    "E22": "DHW compressor overheating",
    "E23": "DHW compressor temperature sensor faulty",
    "E24": "DHW condenser temperature sensor faulty",
    "E25": "DHW evaporator temperature sensor faulty",
    "E26": "Solar temperature sensor faulty",
    "E27": "Display communication error",
    "OR01": "Inlet water temperature low",
    "OR02": "Evaporator antifreeze protection",
    "OR03": "External boiler activation request",
    "OR04": "TA input open",
    "OR05": "UE capacity limitation",
    "OR06": "UE defrosting cycle",
    "OR07": "UE not available in DHW_B",
    "OR08": "DHW flow switch protection",
    "OR09": "DHW evaporator antifreeze protection",
    "OR10": "DHW compressor temperature protection",
    "OR11": "Water pump maintenance",
    "OR12": "Water filter maintenance",
    "OR13": "DHW pump maintenance",
}

# -- enumerations (manual 262860B, appendix X) -----------------------------------

IDU_MODELS: dict[int, str] = {
    0: "SHERPA S2 SMALL", 1: "SHERPA S2 3W SMALL", 2: "SHERPA S2 BIG",
    3: "SHERPA S2 3W BIG", 4: "AQUADUE S2 SMALL", 5: "AQUADUE S2 BIG",
    6: "AQUADUE TOWER S2 SMALL", 7: "AQUADUE TOWER S2 BIG",
    8: "SHERPA TOWER S2 SMALL", 9: "SHERPA TOWER S2 BIG",
}
ODU_MODELS: dict[int, str] = {
    0: "SHERPA 24", 1: "SHERPA 36", 2: "SHERPA 48", 3: "SHERPA 48 T", 4: "SHERPA 60",
    5: "SHERPA 60 T", 6: "SHERPA S2 E 4", 7: "SHERPA S2 E 6", 8: "SHERPA S2 E 8",
    9: "SHERPA S2 E 10", 10: "SHERPA S2 12", 11: "SHERPA S2 14", 12: "SHERPA S2 16",
    13: "SHERPA S2 12T", 14: "SHERPA S2 14T", 15: "SHERPA S2 16T",
}
#: Parameter value -> state key, for the enum sensors.
ENUMS: dict[str, dict[int, str]] = {
    "aux_heaters": {0: "none", 1: "one_backup", 2: "two_backup",
                    3: "one_low_temperature_start", 4: "two_low_temperature_start"},
    "remote_controls": {0: "display", 1: "serial", 2: "contacts"},
    "dhw_source": {0: "disabled", 1: "contact", 2: "sensor"},
    "legionella_mode": {0: "heat_pump_and_k5", 1: "k5_only", 2: "electric_heaters"},
    "dhw_mode": {0: "automatic", 1: "dhw_module_only", 2: "heat_pump_only"},
    "smart_grid": {0: "disabled", 1: "photovoltaic"},
}
#: The legacy pump-duty table, used if registers 380-387 have not been read yet.
PUMP_DUTY_FALLBACK: tuple[int, ...] = (5, 20, 30, 50, 60, 70, 70, 70)

# -- write safety (phase P4) -------------------------------------------------------

#: Never writable, whatever a later WriteSpec says. Each would be unsafe, lose
#: communication, or contradict plant the unit does not have.
FORBIDDEN_WRITES: frozenset[int] = frozenset(
    {229, 220, 247, 401, 370, 371, 280, 285, 236, 372, 200, 213, 219, 237, 231}
    | set(range(291, 327))      # cascade
    | set(range(380, 388))      # pump PWM table
    | {217, 226, 227, 228, 234, 235}
    | set(range(341, 369))      # Smart Grid / PV, tariffs, solar
    | set(range(270, 280))      # counters
    | set(range(201, 206))      # not present on this unit
)


@dataclass(frozen=True, slots=True)
class WriteSpec:
    """A register that MAY become writable, and the values it may take.

    Never writable on these terms alone. A register is written only when the
    "allow writes" option is on AND the integration's own write check has
    passed for it on this unit and firmware (see writes.py). The ranges are the
    integration's, deliberately narrower than "whatever the panel accepts":
    the manual gives no limits for most of these.
    """

    key: str
    minimum: float
    maximum: float
    step: float
    platform: str = "number"   # "number" | "switch"


def _temp_spec(key: str, minimum: float, maximum: float) -> WriteSpec:
    return WriteSpec(key, minimum, maximum, 0.5)


WRITE_SPECS: dict[str, WriteSpec] = {spec.key: spec for spec in (
    _temp_spec("cooling_setpoint", 7.0, 25.0),
    _temp_spec("cooling_eco_setpoint", 7.0, 25.0),
    _temp_spec("heating_setpoint", 20.0, 55.0),
    _temp_spec("heating_eco_setpoint", 20.0, 55.0),
    _temp_spec("dhw_setpoint", 30.0, 55.0),
    WriteSpec("legionella_setpoint", 50.0, 80.0, 1.0),       # manual: 50-80 degC
    WriteSpec("legionella_duration", 0, 240, 10),            # manual: 0-240 min
    _temp_spec("dhw_hysteresis", 2.0, 15.0),
    _temp_spec("cooling_curve_max_water_outdoor", 15.0, 45.0),
    _temp_spec("cooling_curve_max_water", 7.0, 25.0),
    _temp_spec("cooling_curve_min_water_outdoor", 15.0, 45.0),
    _temp_spec("cooling_curve_min_water", 7.0, 25.0),
    _temp_spec("heating_curve_max_water_outdoor", -25.0, 25.0),
    _temp_spec("heating_curve_max_water", 20.0, 55.0),
    _temp_spec("heating_curve_min_water_outdoor", -25.0, 25.0),
    _temp_spec("heating_curve_min_water", 20.0, 55.0),
    _temp_spec("water_setpoint_correction", -5.0, 5.0),      # manual: -5.0 to +5.0
    WriteSpec("cooling_curve_enabled", 0, 1, 1, "switch"),
    WriteSpec("heating_curve_enabled", 0, 1, 1, "switch"),
)}

# A forbidden register can never acquire a write spec, whatever is edited above.
assert not {BY_KEY[key].address for key in WRITE_SPECS} & FORBIDDEN_WRITES
assert all(key in BY_KEY for key in WRITE_SPECS)

# -- the mode command (phase P6, Olimpia RDE448) -------------------------------------

#: Register 106, "working mode setting". A command, not a setting: the unit acts
#: on it only while ADDR220 = 1 (serial control), and then raises E09 unless it
#: is written at least every 255 s. It sits below 200, so it is RAM, not EEPROM,
#: and the EEPROM write limits do not apply to it. Polled with the other control
#: words; no WriteSpec: only the mode controller (mode_control.py) and the admin
#: action write_mode_command write it.
MODE_COMMAND = BY_KEY["mode_command"]
#: Bit -> name. Heating and cooling both clear means DHW only.
MODE_COMMAND_BITS: dict[int, str] = {0: "standby", 1: "eco", 2: "cooling", 3: "heating",
                                     4: "night"}
MODE_COMMAND_MAX = (1 << len(MODE_COMMAND_BITS)) - 1
#: Alarm word 1 bit 8: E09, RS485 communication error -- the keep-alive's alarm.
E09_BIT = 8

assert MODE_COMMAND.address not in FORBIDDEN_WRITES and MODE_COMMAND.address < 200
