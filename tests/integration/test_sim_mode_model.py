"""The fake unit's mode model: 106, ADDR220 and the E09 watchdog, as P6 found them."""

from __future__ import annotations

import pytest

from tests.sim import FakeSherpa, ModeModel

E09 = 1 << 8


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def unit(clock) -> FakeSherpa:
    fake = FakeSherpa()
    fake.mode_model = ModeModel(clock)
    return fake


def _read(unit: FakeSherpa, address: int, count: int = 1) -> list[int]:
    result = unit.read(201, 3, address, count)
    assert isinstance(result, list), result
    return result


def _write(unit: FakeSherpa, value: int) -> None:
    assert unit.write(201, 106, value) is True


def test_106_is_read_back_as_written_whatever_220_says(unit):
    for remote in (0, 1):
        unit.registers[220] = remote
        _write(unit, 24)
        assert _read(unit, 106) == [24]


def test_the_unit_ignores_106_at_220_0(unit):
    unit.registers[12], unit.registers[105] = 0, 0
    _write(unit, 8)
    assert _read(unit, 12) == [0] and _read(unit, 105, 2) == [0, 8]


def test_it_follows_106_at_220_1(unit):
    unit.registers[220] = 1
    expect = {1: (0, 0), 8: (2, 1), 4: (1, 1), 0: (0, 0), 24: (2 | 128, 1), 9: (0, 0),
              10: (2, 1)}
    for word, (status, outputs) in expect.items():
        _write(unit, word)
        assert _read(unit, 12) == [status], word
        assert _read(unit, 105) == [outputs], word


def test_a_dhw_cycle_sets_the_heating_bit_too(unit):
    unit.registers[220] = 1
    unit.mode_model.dhw_cycle = True
    _write(unit, 8)
    assert _read(unit, 12) == [6] and _read(unit, 105) == [0x11]
    _write(unit, 1)                                  # standby stops DHW too
    assert _read(unit, 12) == [0] and _read(unit, 105) == [0]


def test_handing_back_restores_the_panels_state(unit):
    unit.registers[12], unit.registers[105] = 2 | 128, 1
    unit.registers[220] = 1
    _write(unit, 1)
    assert _read(unit, 12) == [0]
    unit.registers[220] = 0
    assert _read(unit, 12) == [2 | 128] and _read(unit, 105) == [1]


def test_e09_after_253_6_s_then_every_period(unit, clock):
    unit.registers[220] = 1
    _write(unit, 8)
    assert _read(unit, 100) == [0]
    clock.now += 253
    assert _read(unit, 100) == [0] and unit.e09_episodes == []
    clock.now += 0.7                                   # 253.7 s: inside the 1 s pulse
    assert _read(unit, 100, 3)[0] == E09
    assert _read(unit, 105) == [E09] and _read(unit, 12) == [0]
    clock.now += 1                                     # and gone again
    assert _read(unit, 100)[0] == 0 and _read(unit, 105) == [1]
    assert _read(unit, 12) == [2]                      # back on the last command
    clock.now += 252.6                                 # the second one, 253.6 s after the first
    assert _read(unit, 100)[0] == E09
    assert len(unit.e09_episodes) == 2
    assert unit.e09_episodes[1] - unit.e09_episodes[0] == pytest.approx(253.6)


def test_a_slow_poll_can_miss_the_pulse_but_the_episode_is_recorded(unit, clock):
    unit.registers[220] = 1
    _write(unit, 8)
    _read(unit, 12)
    for _ in range(30):                                # polled every 10 s, as the integration does
        clock.now += 10
        assert _read(unit, 100)[0] == 0                # never seen: 250 s, then 260 s
    assert len(unit.e09_episodes) == 1                 # at 253.6 s, between two polls


def test_the_pulse_shows_in_status_and_outputs_before_register_100_is_read(unit, clock):
    unit.registers[220] = 1
    _write(unit, 8)
    _read(unit, 12)
    clock.now += 253.7
    assert _read(unit, 12) == [0] and _read(unit, 105) == [E09]
    assert _read(unit, 100)[0] == E09
    clock.now += 2
    assert _read(unit, 12) == [2]


def test_no_e09_when_written_every_60_s(unit, clock):
    unit.registers[220] = 1
    for _ in range(20):
        _write(unit, 8)
        clock.now += 60
        assert _read(unit, 100) == [0]
    assert unit.e09_episodes == []


def test_no_e09_at_220_0(unit, clock):
    _write(unit, 8)
    clock.now += 1000
    assert _read(unit, 100) == [0] and unit.e09_episodes == []


def test_the_watchdog_starts_at_the_flip(unit, clock):
    _write(unit, 8)                                    # written long ago, at 220 = 0
    clock.now += 1000
    unit.registers[220] = 1
    assert _read(unit, 100) == [0]
    clock.now += 253.7
    assert _read(unit, 100)[0] == E09


def test_without_a_model_the_fake_is_the_plain_register_file():
    fake = FakeSherpa()
    fake.registers[220] = 1
    fake.write(201, 106, 8)
    assert fake.read(201, 3, 12, 1) == [fake.registers[12]] and fake.e09_episodes == []
