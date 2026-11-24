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
# opcode 0x82. King Snow sets FlagOn after 0x82 on the success path. Tarn's Manor
# table (id 129) sets FlagOn 0x03B9 after 0x82 when the give succeeds. Each
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


# Loaded map ids. docs/client_memory.md. Naomi's door stays on 258.
MAP_LURVY_SHOP = 398
MAP_NAOMI_SHOP = 258
MAP_MERRICK_SHOP = 134
# Door variant of Jess's house. This is the copy he can be talked to in.
# Map 242 is the spawn, and the blue chest warps there once it has been opened.
MAP_JESS_HOUSE = 260

# Slot-data value for Shop Hints. Anything else is treated as all.
SHOP_HINT_ALL = "all"
SHOP_HINT_NEXT = "next"

_CHECKS_BY_ID = {check.location_id: check for check in LOCATION_CHECKS}


def _shop_sequence(location_ids: tuple[int, ...]) -> tuple[LocationCheck, ...]:
    return tuple(_CHECKS_BY_ID[location_id] for location_id in location_ids)


# Offer order. The first clear purchase bit is the shelf or trade on offer.
# Lurvy's third Item #5 restocks. The armor repair is LURVY_SECRET, below.
SHOP_CHECKS: dict[int, tuple[LocationCheck, ...]] = {
    MAP_LURVY_SHOP: _shop_sequence((266, 267)),
    MAP_NAOMI_SHOP: _shop_sequence((273,)),
    MAP_MERRICK_SHOP: _shop_sequence((254, 255, 256, 257, 258, 259, 260, 261)),
}


def shop_hint_locations(
    loaded_map: int,
    mode: object,
    flag_bytes: bytes,
    origin: int,
    skip: set[int] | frozenset[int] = frozenset(),
) -> list[int]:
    """Location ids to scout for this shop visit.

    A set purchase bit has already been bought. ``skip`` is the server's
    checked set, so a found check is not scouted again. ``all`` returns every
    remaining check in offer order. ``next`` returns the first remaining one.
    A flag byte outside ``flag_bytes`` returns nothing.
    """
    sequence = SHOP_CHECKS.get(loaded_map)
    if sequence is None:
        return []
    # A missing or unknown slot value reports every remaining check.
    report_all = mode != SHOP_HINT_NEXT
    offered: list[int] = []
    for check in sequence:
        index = check.byte_index - origin
        if index < 0 or index >= len(flag_bytes):
            return []
        if flag_bytes[index] & check.mask:
            continue
        if check.location_id in skip:
            if report_all:
                continue
            return []
        if not report_all:
            return [check.location_id]
        offered.append(check.location_id)
    return offered


# Map 398 script C[2]. The chimney lands on tile (6, 12) at z=4. The first
# landing sets this bit. Flag(0xD403, 7), bit 7 of MainRAM 0x801DD403.
# New game sets bit 6 of that byte and leaves this bit clear.
LURVY_SECRET = 0x067F
# Lurvy's Shop: Item obtained after repairing Broken Armor.
LURVY_REPAIR_ID = 269


def _flag_is_set(event_code: int, flag_bytes: bytes, origin: int) -> bool | None:
    index = (event_code >> 3) - origin
    if index < 0 or index >= len(flag_bytes):
        return None
    return bool(flag_bytes[index] & (1 << (event_code & 7)))


def lurvy_repair_hints_enabled(slot_data: dict) -> bool:
    """True unless the repair hint is explicitly off. A missing key is on."""
    value = slot_data.get("hint_lurvy_repair", True)
    return value is not False and value != 0


def lurvy_repair_hint_locations(
    flag_bytes: bytes,
    origin: int,
    skip: set[int] | frozenset[int] = frozenset(),
) -> list[int]:
    """The repair location once the chimney secret is set and the repair is still open.

    A set repair bit means the Broken Armor was already handed over. A flag
    byte outside ``flag_bytes`` returns nothing.
    """
    repair = _CHECKS_BY_ID[LURVY_REPAIR_ID]
    secret = _flag_is_set(LURVY_SECRET, flag_bytes, origin)
    handed_over = _flag_is_set(repair.event_code, flag_bytes, origin)
    if secret is None or handed_over is None:
        return []
    if not secret or handed_over or repair.location_id in skip:
        return []
    return [repair.location_id]


# Line-played event codes. The client sends that speaker's slot-data row when
# the bit is set. Jess is absent. His script has no safe byte for a flag, so
# the client watches NPC text on map 260 while it is connected. See
# pending_jess_hint and jess_talk_step.
#
# These five are already set by the retail script after the line, and nothing
# clears them. 0x0372 is also Uma's chest. That chest opens in the same scene,
# after the line. The other four are not item-source event codes.
#   lars_crypt 0x015C, reptile_lair 0x0303, coastal_cave 0x06A1,
#   magyscar 0x0372, great_tree 0x0645.
#
# PatchApplyHintText writes the other six. New game does not set them.
#   nirudes_lair 0x0053, torla_mountain 0x0054, coal_mine 0x0055,
#   ancient_shrine 0x0056, fairy_pond 0x0057, nava_keep 0x0059.
SPEAKER_LINE_FLAGS: dict[str, int] = {
    "lars_crypt": 0x015C,
    "reptile_lair": 0x0303,
    "nirudes_lair": 0x0053,
    "coastal_cave": 0x06A1,
    "torla_mountain": 0x0054,
    "magyscar": 0x0372,
    "coal_mine": 0x0055,
    "ancient_shrine": 0x0056,
    "fairy_pond": 0x0057,
    "great_tree": 0x0645,
    "nava_keep": 0x0059,
}


@dataclass(frozen=True)
class SpeakerHintSend:
    """One hint packet for a line that has been heard."""

    speaker: str
    location: int
    player: int | None = None


@dataclass(frozen=True)
class SpeakerHintPlan:
    """Packets still due, and speakers whose check is already found.

    ``quiet`` is remembered without a packet. A local line whose check has
    left the server's missing list has nothing to register.
    """

    sends: tuple[SpeakerHintSend, ...] = ()
    quiet: tuple[str, ...] = ()


def speaker_hints_outstanding(rows: object, sent: set[str]) -> bool:
    """True when a row with a line bit has not been handled this connection.

    Jess has no bit, so his row does not keep the flag read alive. The play
    state read is what watches his house.
    """
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        speaker = row.get("speaker")
        if isinstance(speaker, str) and speaker in SPEAKER_LINE_FLAGS and speaker not in sent:
            return True
    return False


def _location_and_player(row: dict) -> tuple[int, int | None] | None:
    location = row.get("location")
    if isinstance(location, bool) or not isinstance(location, int) or location < 0:
        return None
    if "player" not in row:
        return location, None
    player = row.get("player")
    if isinstance(player, bool) or not isinstance(player, int) or player < 1:
        return None
    return location, player


def _speaker_row(row: object) -> tuple[str, int, int | None] | None:
    if not isinstance(row, dict):
        return None
    speaker = row.get("speaker")
    if not isinstance(speaker, str) or speaker not in SPEAKER_LINE_FLAGS:
        return None
    target = _location_and_player(row)
    if target is None:
        return None
    location, player = target
    return speaker, location, player


def pending_speaker_hints(
    rows: object,
    flag_bytes: bytes,
    origin: int,
    missing: set[int] | frozenset[int],
    sent: set[str],
) -> SpeakerHintPlan:
    """The lines whose bit is set and that this connection has not handled.

    A local check is a packet only while it is still missing. An unknown-place
    check is not gated on this slot's missing set. A bad row is skipped. A bit
    outside ``flag_bytes`` is not handled, so a short read does not forget it.
    """
    if not isinstance(rows, list):
        return SpeakerHintPlan()
    sends: list[SpeakerHintSend] = []
    quiet: list[str] = []
    seen: set[str] = set()
    for row in rows:
        parsed = _speaker_row(row)
        if parsed is None:
            continue
        speaker, location, player = parsed
        if speaker in sent or speaker in seen:
            continue
        heard = _flag_is_set(SPEAKER_LINE_FLAGS[speaker], flag_bytes, origin)
        if heard is None or not heard:
            continue
        seen.add(speaker)
        if player is None and location not in missing:
            quiet.append(speaker)
            continue
        sends.append(SpeakerHintSend(speaker, location, player))
    return SpeakerHintPlan(tuple(sends), tuple(quiet))


def pending_jess_hint(
    rows: object,
    missing: set[int] | frozenset[int],
    sent: set[str],
) -> SpeakerHintPlan:
    """The jess row this connection has not handled.

    Jess has no line bit. The caller decides when his line has played. A
    local check is a packet only while it is still missing, and a found one
    is remembered with no packet. An unknown-place check is not gated on
    this slot's missing set. The first valid row wins. A bad row is skipped.
    """
    if not isinstance(rows, list) or "jess" in sent:
        return SpeakerHintPlan()
    for row in rows:
        if not isinstance(row, dict) or row.get("speaker") != "jess":
            continue
        target = _location_and_player(row)
        if target is None:
            continue
        location, player = target
        if player is None and location not in missing:
            return SpeakerHintPlan((), ("jess",))
        return SpeakerHintPlan((SpeakerHintSend("jess", location, player),), ())
    return SpeakerHintPlan()


def jess_talk_step(
    latched: bool,
    loaded_map: int,
    npc_text: bool,
    ready: bool,
) -> tuple[bool, bool]:
    """The latch after this watch, and whether his hint should be sent.

    NPC text on map 260 arms the latch. The send waits until gameplay is
    ready and the loaded map is still 260, which is the watch after the box
    closes, and then the latch clears. An open box is not ready, so a second
    watch of the same conversation keeps the latch. Any other map clears it.
    The warp after the blue chest opens therefore does not send, and a later
    visit needs a new conversation. The menu window is not NPC text.

    The caller puts the latch back when the packet does not leave, so the
    next ready watch retries.
    """
    if loaded_map != MAP_JESS_HOUSE:
        return False, False
    if npc_text:
        return True, False
    if latched and ready:
        return False, True
    return latched, False
