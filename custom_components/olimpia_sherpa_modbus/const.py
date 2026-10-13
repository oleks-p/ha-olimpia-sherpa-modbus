"""Constants for the Olimpia Splendid Sherpa S2 integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "olimpia_sherpa_modbus"
MANUFACTURER: Final = "Olimpia Splendid"
DEFAULT_NAME: Final = "Sherpa"

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SWITCH]

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
