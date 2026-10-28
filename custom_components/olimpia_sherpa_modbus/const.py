"""Constants for the Olimpia Splendid Sherpa integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "olimpia_sherpa_modbus"
MANUFACTURER: Final = "Olimpia Splendid"
DEFAULT_NAME: Final = "Sherpa"

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.NUMBER,
                     Platform.SWITCH, Platform.SELECT, Platform.WATER_HEATER]

# -- connection ---------------------------------------------------------------

CONF_TRANSPORT: Final = "transport"
CONF_SERIAL_PORT: Final = "serial_port"
CONF_BAUDRATE: Final = "baudrate"
CONF_SLAVE: Final = "slave"
CONF_ENTITY_PREFIX: Final = "entity_prefix"

TRANSPORT_SERIAL: Final = "serial"
# A transparent serial server: raw RTU frames over a TCP socket.
TRANSPORT_RTU_OVER_TCP: Final = "rtu_over_tcp"
# A Modbus-TCP gateway: MBAP framing, the gateway speaks RTU on the bus.
TRANSPORT_TCP: Final = "tcp"
TRANSPORTS: Final = (TRANSPORT_SERIAL, TRANSPORT_RTU_OVER_TCP, TRANSPORT_TCP)

DEFAULT_BAUDRATE: Final = 9600
DEFAULT_TCP_PORT: Final = 502
# ADDR247 on the unit; the factory default is 1, the reference unit uses 201.
DEFAULT_SLAVE: Final = 201
DEFAULT_ENTITY_PREFIX: Final = "sherpa"

#: Response timeout. The unit answers in about 36 ms (180 ms for a 65-register
#: read); 3 s matches the configuration it has run on since commissioning.
REQUEST_TIMEOUT: Final = 3.0
#: Quiet time the unit needs between frames.
FRAME_GAP: Final = 0.060
#: Pause after a failed exchange before the link is used again. RTU has no
#: transaction id, so a late reply must be given time to arrive and be thrown
#: away rather than read as the answer to the next request.
RESYNC_DELAY: Final = 1.0

# -- options ------------------------------------------------------------------

#: How long the link may fail before entities go unavailable. The RTU link
#: stalls for 10-30 s now and then; that is normal and must not flap entities.
CONF_UNAVAILABLE_AFTER: Final = "unavailable_after"
DEFAULT_UNAVAILABLE_AFTER: Final = 120
MIN_UNAVAILABLE_AFTER: Final = 30
MAX_UNAVAILABLE_AFTER: Final = 900

# -- writes (opt-in) ------------------------------------------------------------

#: Off by default. Even on, a register is written only once the write check has
#: passed for it on this unit and firmware.
CONF_ALLOW_WRITES: Final = "allow_writes"
#: A register is written at most once per this many seconds ...
WRITE_MIN_INTERVAL: Final = 10.0
#: ... and the unit at most this many times a day. These values are kept in the
#: controller's non-volatile memory; an automation that writes on every state
#: change would wear it out.
WRITE_DAILY_LIMIT: Final = 50
#: How long the write check holds the neighbour value before reading it again,
#: to catch a controller that accepts a write and then puts its own value back.
CHECK_HOLD_DEFAULT: Final = 5
CHECK_HOLD_MAX: Final = 30
EVENT_PARAMETER_WRITTEN: Final = f"{DOMAIN}_parameter_written"
SERVICE_VERIFY_WRITE: Final = "verify_write"
SERVICE_READ_REGISTERS: Final = "read_registers"
SERVICE_WRITE_MODE_COMMAND: Final = "write_mode_command"

# -- mode control (opt-in, P6; Olimpia RDE448) -----------------------------------

#: Needs CONF_ALLOW_WRITES. Active only while the panel has handed control to
#: RS-485 (ADDR220 = 1); the integration then keeps the unit fed.
CONF_MODE_CONTROL: Final = "mode_control"
#: The controller's own timer, apart from the 10 s poll (which stops on an outage,
#: when the keep-alive matters most).
MODE_TICK: Final = 10
#: With ADDR220 = 1 the unit raises E09 255 s after the last write of 106 (RDE448);
#: measured on the reference unit: 253.6-254.4 s, then every 254 s. Written every
#: 60 s, three writes can fail in a row and it is still in time.
KEEPALIVE_INTERVAL: Final = 60
E09_PERIOD: Final = 254
#: A gap longer than this is a miss: E09 is on its way or has happened. A little
#: under the measured period, so a late tick cannot hide one.
E09_DETECT: Final = 250
#: A panel snapshot older than this is not used at a hand-over.
PANEL_MAX_AGE: Final = 60
#: Polls with ADDR220 != 1 in a row before a later 1 counts as a hand-over: one
#: glitched read must not look like the panel handing control over.
HANDOVER_CONFIRM_POLLS: Final = 2
#: No fresh read for this long: the controller reports "stalled" (and still tries).
STALLED_AFTER: Final = 60
#: ADDR220 = 1 without a controller for this long raises the "unmanaged" repair.
UNMANAGED_AFTER: Final = 60
#: Consecutive writes whose read-back is not the word written: "not applied".
NOT_APPLIED_TICKS: Final = 3
#: The last write at unload or at Home Assistant stop, so the unit starts the
#: outage with a full 255 s.
FINAL_WRITE_TIMEOUT: Final = 5
