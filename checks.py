# Locations the BizHawk client can report as checked.
#
# A taken chest is one bit in the event-flag array. The bit index is the event
# code that chest passes to FlagOn. Add a row to LOCATION_CHECKS when another
# location's event code is known. The watcher reads the bytes that table names
# and does not need a new code path.
#
# The code for a chest that lives in a map entity record is the u16 at
# record + 0x10. The item id is the byte at record + 0x12, and that byte is
# the source address only for those entity chests. The two bytes before a
# shop, Merrick, or NPC script byte are not a flag. A code whose low 15 bits
# are >= 0x800, or code 0, does not name one chest.

from __future__ import annotations

from dataclasses import dataclass

from .data import GAME_DATA

# MainRAM offset of event-flag byte 0. KSEG0 0x801DD334 with the top bits dropped.
# docs/client_memory.md. The reader at 0x80033154 indexes 2048 bits.
EVENT_FLAGS = 0x1DD334
EVENT_FLAG_BITS = 2048


# One location whose FlagOn bit the client can see.
@dataclass(frozen=True)
class LocationCheck:
    name: str
    location_id: int
    event_code: int

    def __post_init__(self) -> None:
        if not 0 <= self.event_code < EVENT_FLAG_BITS:
            raise ValueError(
                f"Location {self.name!r} event code {self.event_code:#x} "
                "is outside the event-flag array."
            )

    @property
    def byte_index(self) -> int:
        return self.event_code >> 3

    @property
    def mask(self) -> int:
        return 1 << (self.event_code & 7)


def _check(name: str, event_code: int) -> LocationCheck:
    source = GAME_DATA.source_by_pretty_name[name]
    return LocationCheck(name, source.id, event_code)


# Inoa: Chest in Lutas's house. Entity record at DATAS.BIN 0x499699C on USA 1.1.
# Contents byte 0x39 (Secret Pass) is source address 0x49969AE. Flag halfword
# at record + 0x10 is 0x0680, bit 0 of MainRAM 0x1DD404. The location name is
# the pretty name Archipelago shows, which appends the vanilla item.
LOCATION_CHECKS: tuple[LocationCheck, ...] = (
    _check("Inoa: Chest in Lutas's house (Secret Pass)", 0x0680),
)

WATCHED_LOCATION_IDS = frozenset(check.location_id for check in LOCATION_CHECKS)


# MainRAM offset and length covering every check's flag byte.
# None when there is nothing to watch, so the client does not read.
def flag_read(checks: tuple[LocationCheck, ...] = LOCATION_CHECKS) -> tuple[int, int] | None:
    if not checks:
        return None
    indexes = [check.byte_index for check in checks]
    start = min(indexes)
    end = max(indexes)
    return EVENT_FLAGS + start, end - start + 1


# Location ids whose event bit is set.
#
# origin is the index of flag_bytes[0] in the event-flag array, which is
# flag_read's offset minus EVENT_FLAGS. A short read reports nothing for a
# bit that falls outside the buffer.
def checked_locations(
    flag_bytes: bytes,
    origin: int,
    checks: tuple[LocationCheck, ...] = LOCATION_CHECKS,
) -> list[int]:
    found: list[int] = []
    for check in checks:
        index = check.byte_index - origin
        if index < 0 or index >= len(flag_bytes):
            continue
        if flag_bytes[index] & check.mask:
            found.append(check.location_id)
    return found


# Check names in table order, for the ids the server was just told about.
def names_for(location_ids: set[int], checks: tuple[LocationCheck, ...] = LOCATION_CHECKS) -> list[str]:
    return [check.name for check in checks if check.location_id in location_ids]
