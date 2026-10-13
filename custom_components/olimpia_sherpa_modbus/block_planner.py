"""Turn the register map into the fewest reads the unit will accept.

Two device rules shape every read (both measured on the reference unit):

* a read that spans an address the unit does not have is rejected outright,
  so a block must stay inside one run of answering registers; and
* inside a run anything goes -- every run reads whole in one request.

So each tier's registers are grouped by the run they sit in, and each group is
read as one span from its first to its last register. A 32-bit value is never
split, because spans are built from whole registers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .registers import ANSWERING_RUNS, MAX_READ, Reg, Tier


@dataclass(frozen=True, slots=True)
class Block:
    """One read request: ``count`` registers from ``address``, on one tier."""

    address: int
    count: int
    tier: Tier
    registers: tuple[Reg, ...]

    @property
    def end(self) -> int:
        return self.address + self.count - 1

    @property
    def key(self) -> str:
        return f"{self.address}+{self.count}"

    def __str__(self) -> str:
        return f"{self.tier.name.lower()} {self.address}..{self.end}"


def _run_of(reg: Reg, runs: tuple[tuple[int, int], ...]) -> tuple[int, int] | None:
    for first, last in runs:
        if first <= reg.address and reg.end <= last:
            return (first, last)
    return None


def plan_blocks(
    registers: Iterable[Reg],
    runs: tuple[tuple[int, int], ...] = ANSWERING_RUNS,
    max_count: int = MAX_READ,
) -> tuple[Block, ...]:
    """Group registers into per-tier reads that stay inside answering runs.

    A register outside every known run (a different firmware's map) is read on
    its own; if the unit rejects it, the coordinator marks it unavailable.
    """
    blocks: list[Block] = []
    by_group: dict[tuple[Tier, tuple[int, int] | None], list[Reg]] = {}
    for reg in sorted(registers, key=lambda r: (r.tier.value, r.address)):
        by_group.setdefault((reg.tier, _run_of(reg, runs)), []).append(reg)

    for (tier, run), regs in by_group.items():
        if run is None:
            blocks.extend(Block(r.address, r.words, tier, (r,)) for r in regs)
            continue
        current: list[Reg] = []
        for reg in regs:
            if current and reg.end - current[0].address + 1 > max_count:
                blocks.append(_block(tier, current))
                current = []
            current.append(reg)
        if current:
            blocks.append(_block(tier, current))
    return tuple(sorted(blocks, key=lambda b: (b.tier.value, b.address)))


def split(block: Block) -> tuple[Block, ...]:
    """One read per register: the fallback when the unit rejects a block."""
    return tuple(Block(r.address, r.words, block.tier, (r,)) for r in block.registers)


def _block(tier: Tier, regs: list[Reg]) -> Block:
    start = regs[0].address
    end = max(r.end for r in regs)
    return Block(start, end - start + 1, tier, tuple(regs))


def describe(blocks: Iterable[Block]) -> list[str]:
    """One line per read, for diagnostics."""
    return [
        f"{b}: {b.count} register(s), {', '.join(r.key for r in b.registers)}"
        for b in blocks
    ]
