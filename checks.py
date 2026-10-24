# Locations the BizHawk client can report as checked, and the ending goal.
#
# A taken check is one bit in the event-flag array. The bit index is the event
# code passed to FlagOn, stored on the item source as eventCode.
# LOCATION_CHECKS is every loaded source that has one and does not set
# forbidPreciousItems. Those codes stay on the source. The watcher does not
# read them. The watcher reads the bytes this table names and does not need a
# new code path for a chest.
#
# The goal is not a chest. Beating Melzas leads back to the Lake Shrine, and
# the shrine scene calls opcode 0xBB. When the loaded map is not 477, that
# handler stores 9 in the u32 at KSEG0 0x801F11F8. The map loop then loads
# END.EXE. docs/client_memory.md.
#
# The code for a chest that lives in a map entity record is the u16 at
# record + 0x10. The item id is the byte at record + 0x12, and that byte is
# the source address only for those entity chests. A one-time shop purchase
# sets its FlagOn later in the same script, after opcode 0x82. A Merrick trade
# sets its FlagOn in the spawned trade script, after latch 0x8065 and before
# opcode 0x82. King Snow sets FlagOn after 0x82 on the success path. Each
# casino second reward sets FlagOn in that give script, before 0x82. Those
# codes are eventCode too. The item id is the argument of 0x82, which is the
# source address. The two bytes before it are not a flag. Restocking shelves
# do not set a bit in this array, so they omit eventCode. A script gift with
# no bit in this array does the same. Jess's blue chest sets FlagOn 0x0046
# after both 0x82 gives. Ids 2 and 3 both store that code, and
# checked_locations reports both location ids when the bit is set. Miming's
# reward scene sets FlagOn 0x0510 after the Topaz 0x82 and before the Aqua
# Cape 0x82. Ids 247 and 248 both store that code. The falling Diamond Crest
# sets FlagOn 0x03D0 on map 321 after Zorgia's fight, after the 0x82 on map
# 432. Id 253 stores that code. A code
# whose low 15 bits are >= 0x800, or code 0, does not name one check.
# Sources with no known code stay out of this table.

from __future__ import annotations

from dataclasses import dataclass

from .data import GAME_DATA

# MainRAM offset of event-flag byte 0. KSEG0 0x801DD334 with the top bits dropped.
# docs/client_memory.md. The reader at 0x80033154 indexes 2048 bits.
EVENT_FLAGS = 0x1DD334
EVENT_FLAG_BITS = 2048

# u32 just before the requested map id (0x801F11FC). Opcode 0xBB stores 9 here
# to boot END.EXE. 8, 10, and 11 are other mode changes and are not the goal.
GOAL_PHASE = 0x1F11F8
GOAL_ENDING = 9


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


def _checks_from_sources() -> tuple[LocationCheck, ...]:
    checks: list[LocationCheck] = []
    for source in GAME_DATA.sources:
        if source.event_code is None or source.forbid_precious:
            continue
        checks.append(LocationCheck(source.pretty_name, source.id, source.event_code))
    return tuple(checks)


LOCATION_CHECKS: tuple[LocationCheck, ...] = _checks_from_sources()

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


# True when the four bytes are the ending request. A short read is not a clear.
def game_beaten(phase: bytes) -> bool:
    if len(phase) != 4:
        return False
    return int.from_bytes(phase, "little") == GOAL_ENDING
