"""Which unit is on the other end, and whether this register map fits it.

Register 199 names the register layout. The reference unit reports 1134;
Olimpia's SiOS Control manual lists 1026 for the original Sherpa and 1061 for
Aquadue, so a different code means a different layout, and reading it with
this map would decode garbage with total confidence. Only known codes are
accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .registers import IDU_MODELS, ODU_MODELS, REGISTER_MAP_VERSION
from .transport import SherpaBus, SherpaIllegalError

#: identify code -> the register map that describes it.
SUPPORTED_IDENTIFY: dict[int, str] = {1134: REGISTER_MAP_VERSION}
#: Indoor-unit models with the Aquadue DHW high-temperature circuit.
AQUADUE_IDU = frozenset({4, 5, 6, 7})


class NotASherpa(Exception):
    """The address answered, but not with a Sherpa's identity registers."""


class UnsupportedModel(Exception):
    """A Sherpa, but one whose register layout this integration does not know."""

    def __init__(self, info: ModelInfo) -> None:
        super().__init__(f"identify code {info.identify}")
        self.info = info


@dataclass(frozen=True, slots=True)
class ModelInfo:
    identify: int
    fw_197: int
    fw_198: int
    idu: int | None
    odu: int | None

    @property
    def firmware(self) -> str:
        """57 -> '0.57', as the reference unit's firmware is quoted."""
        return f"{self.fw_197 // 100}.{self.fw_197 % 100:02d}"

    @property
    def idu_name(self) -> str:
        return IDU_MODELS.get(self.idu, f"IDU {self.idu}") if self.idu is not None else "Sherpa"

    @property
    def odu_name(self) -> str | None:
        return ODU_MODELS.get(self.odu, f"ODU {self.odu}") if self.odu is not None else None

    @property
    def model(self) -> str:
        return f"{self.idu_name} / {self.odu_name}" if self.odu_name else self.idu_name

    @property
    def features(self) -> frozenset[str]:
        return frozenset({"aquadue"}) if self.idu in AQUADUE_IDU else frozenset()

    @property
    def supported(self) -> bool:
        return self.identify in SUPPORTED_IDENTIFY


async def async_identify(bus: SherpaBus, slave: int) -> ModelInfo:
    """Read the identity registers. Raises NotASherpa or UnsupportedModel.

    Link failures propagate as SherpaTransientError: the caller decides between
    "try again later" (setup) and "cannot connect" (config flow).
    """
    try:
        fw_197, fw_198, identify = await bus.read(slave, 197, 3)
    except SherpaIllegalError as err:
        raise NotASherpa(str(err)) from err
    try:
        idu, odu = await bus.read(slave, 370, 2)
    except SherpaIllegalError:
        idu = odu = None
    info = ModelInfo(identify, fw_197, fw_198, idu, odu)
    if not info.supported:
        raise UnsupportedModel(info)
    return info
