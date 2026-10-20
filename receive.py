# Remote items the BizHawk client can grant.
#
# Add a function to HANDLERS when another item can be granted. The function
# returns Hold.NO_ROOM when the item has to wait because its stack is full
# and room may open later. Otherwise it returns the Grant from finish(),
# which appends the received-index write. Life Vessel is the only entry.
#
# The watcher grants one item per pass, and only the item at the front of
# the queue. An item with no handler stays there until one exists.

from __future__ import annotations

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from .data import GAME_DATA, ITEM_ID_BASE

# MainRAM offsets. KSEG0 with the top bits dropped. docs/client_memory.md.

# Requested map id, KSEG0 0x801F11FC.
REQUESTED_MAP = 0x1F11FC
# Map id last passed to the loader, KSEG0 0x801F5358. Equal to the requested
# id at the start of a load, so inequality is not a still-loading latch.
LOADED_MAP = 0x1F5358
# Window records spaced 0xA8 apart. The u32 at the start of each record is 1
# while that window is open and 0 during gameplay. The menu uses the middle
# record. NPC text uses the other two. 0x800DC4B8 does not change for either,
# so it is not read. 0x8010755C turns on after the text box is already open.
TEXT_WINDOW_A = 0x107570
MENU_WINDOW = 0x107618
TEXT_WINDOW_B = 0x1076C0
# A second menu word. It rose and fell with MENU_WINDOW on every passing sample.
MENU_STATE = 0x1531BC
# FLAG_HUD_ALLOWED, event code 0x067E. Byte 0x801DD403 bit 6. Set on new game.
HUD_FLAG = 0x1DD403
HUD_ALLOWED = 0x40
# Actor current HP, then max HP. GiveItem writes this u32 pair for a Life Vessel.
ACTOR_HP = 0x1AC70C
# Save current HP, then max HP. The setter at 0x8004F2DC stores a max above 50 as 50.
SAVE_HP = 0x1DD81C
# Inventory record 0. Records are 4 bytes: an s16 the owned check ignores, then the quantity.
INVENTORY = 0x1DD82E
# Received-item count, in records 126 and 127. The runtime id limit at
# 0x8012E234 is 99, so TryIncrease never touches these. Both quantity
# halfwords stay 0: a menu that lists owned items (quantity > 0) skips them,
# and a name lookup for a high id is never reached.
# The decomp save image is 128 records. A memory-card save that does not copy
# these two reloads a count of 0, and the client grants the queue again.
INDEX_RECORD_ID = 126
INDEX_RECORD = INVENTORY + INDEX_RECORD_ID * 4
INDEX_MAGIC = 0x4150
MAX_HP = 50

# One read, in the order parse_play_state unpacks. The client guards every byte.
READS: tuple[tuple[int, int], ...] = (
    (REQUESTED_MAP, 4),
    (LOADED_MAP, 4),
    (TEXT_WINDOW_A, 4),
    (MENU_WINDOW, 4),
    (TEXT_WINDOW_B, 4),
    (MENU_STATE, 4),
    (HUD_FLAG, 1),
    (ACTOR_HP, 8),
    (SAVE_HP, 4),
    (INDEX_RECORD, 8),
)

_LIFE_VESSEL = GAME_DATA.item_by_name["Life Vessel"]


# One watch of the bytes a grant has to agree on.
@dataclass(frozen=True)
class PlayState:
    requested_map: int
    loaded_map: int
    text_window_a: int
    menu_window: int
    text_window_b: int
    menu_state: int
    hud_allowed: bool
    actor_current: int
    actor_max: int
    save_current: int
    save_max: int
    received_index: int | None


@dataclass(frozen=True)
class RamWrite:
    address: int
    data: bytes


# name is the item the player sees. detail is a log suffix, empty when the
# grant changed the usual fields. next_state is what the next watch should
# read if nothing else moved, so a following item can be granted immediately.
@dataclass(frozen=True)
class Grant:
    name: str
    writes: tuple[RamWrite, ...]
    next_state: PlayState
    detail: str = ""


class Hold(Enum):
    # Loading, a menu, a message, or the two HP pairs disagree. Silent.
    GAMEPLAY = 1
    # The stack is full and room may open. Stays at the front of the queue.
    NO_ROOM = 2
    # No handler yet. Stays at the front so a later item is not granted ahead of it.
    UNKNOWN = 3
    # Records 126 and 127 are not a received-item count. Grants wait.
    INDEX = 4


# 8 bytes: magic, quantity 0, count, quantity 0. A fresh file is eight zeroes,
# which is a count of 0. Anything else the game wrote is not a count.
def decode_index(blob: bytes) -> int | None:
    magic, magic_quantity, index, index_quantity = struct.unpack("<HHHH", blob)
    if magic_quantity != 0 or index_quantity != 0:
        return None
    if magic == 0 and index == 0:
        return 0
    if magic == INDEX_MAGIC:
        return index
    return None


def index_bytes(index: int) -> bytes:
    if index == 0:
        return bytes(8)
    return struct.pack("<HHHH", INDEX_MAGIC, 0, index, 0)


def parse_play_state(read_bytes: Sequence[bytes]) -> PlayState:
    requested_map, loaded_map, text_window_a, menu_window, text_window_b, menu_state = (
        struct.unpack("<I", data)[0] for data in read_bytes[:6]
    )
    save_current, save_max = struct.unpack("<hh", read_bytes[8])
    actor_current, actor_max = struct.unpack("<II", read_bytes[7])
    return PlayState(
        requested_map=requested_map,
        loaded_map=loaded_map,
        text_window_a=text_window_a,
        menu_window=menu_window,
        text_window_b=text_window_b,
        menu_state=menu_state,
        hud_allowed=bool(read_bytes[6][0] & HUD_ALLOWED),
        actor_current=actor_current,
        actor_max=actor_max,
        save_current=save_current,
        save_max=save_max,
        received_index=decode_index(read_bytes[9]),
    )


# Inverse of parse_play_state, for tests. A missing index packs bytes that do
# not decode. The HUD byte is only the allowed bit; other bits in that byte
# are guarded raw by the client and are not part of PlayState.
def pack_play_state(state: PlayState) -> tuple[bytes, ...]:
    if state.received_index is None:
        index = struct.pack("<HHHH", 0xFFFF, 1, 0, 0)
    else:
        index = index_bytes(state.received_index)
    return (
        struct.pack("<I", state.requested_map),
        struct.pack("<I", state.loaded_map),
        struct.pack("<I", state.text_window_a),
        struct.pack("<I", state.menu_window),
        struct.pack("<I", state.text_window_b),
        struct.pack("<I", state.menu_state),
        bytes([HUD_ALLOWED if state.hud_allowed else 0]),
        struct.pack("<II", state.actor_current, state.actor_max),
        struct.pack("<hh", state.save_current, state.save_max),
        index,
    )


# True when a grant can land. Map ids may be 0: once they match, the HUD flag,
# the menu and text words, and the two HP pairs are what keep a grant waiting.
def gameplay_ready(state: PlayState) -> bool:
    if not state.hud_allowed:
        return False
    if state.requested_map != state.loaded_map:
        return False
    if state.text_window_a or state.menu_window or state.text_window_b or state.menu_state:
        return False
    if not 1 <= state.save_max <= MAX_HP:
        return False
    if not 0 <= state.save_current <= state.save_max:
        return False
    return state.actor_current == state.save_current and state.actor_max == state.save_max


def name_for(ap_id: int) -> str:
    record = GAME_DATA.item_by_id.get(ap_id - ITEM_ID_BASE)
    if record is None:
        return f"item {ap_id}"
    return record.name


def hold_message(hold: Hold, ap_id: int | None) -> str | None:
    if hold is Hold.GAMEPLAY:
        return None
    if hold is Hold.INDEX:
        return "Received-item record is in use. Grants wait."
    name = name_for(ap_id) if ap_id is not None else "item"
    if hold is Hold.UNKNOWN:
        return f"Cannot receive {name} yet. It stays queued."
    if hold is Hold.NO_ROOM:
        return f"No room for {name} yet. It stays queued."
    return None


# Append the received-count write and the play state the next watch should see.
# current and maximum are the HP both pairs hold after the grant.
def finish(
    state: PlayState,
    name: str,
    effect_writes: tuple[RamWrite, ...],
    current: int,
    maximum: int,
    detail: str = "",
) -> Grant:
    if state.received_index is None:
        raise RuntimeError("A grant needs a received index.")
    index = state.received_index + 1
    return Grant(
        name=name,
        writes=(*effect_writes, RamWrite(INDEX_RECORD, index_bytes(index))),
        next_state=replace(
            state,
            actor_current=current,
            actor_max=maximum,
            save_current=current,
            save_max=maximum,
            received_index=index,
        ),
        detail=detail,
    )


def grant_life_vessel(state: PlayState) -> Grant:
    """Write the HP pairs a Life Vessel leaves behind.

    Life Vessel's max quantity is 0. TryIncrease sees the stored quantity
    already equal to that max and leaves memory unchanged. GiveItem adds 1 to
    the actor max and sets the actor current equal to it, then calls effect
    routines. The connector cannot enter MIPS, and those calls are unsafe
    during a load, so this writes both HP pairs to the numbers GiveItem's
    store leaves behind. The save setter's cap applies: max stops at 50, and
    current becomes that max.

    A vessel at the cap is still counted. The cap does not come back down, so
    leaving it queued would block every later item. A stack that can shrink
    returns Hold.NO_ROOM instead, and the count stays put.
    """
    maximum = state.save_max
    current = state.save_current
    if maximum < MAX_HP:
        maximum += 1
        current = maximum
    else:
        current = maximum
    writes: list[RamWrite] = []
    detail = ""
    if current != state.save_current or maximum != state.save_max:
        writes.append(RamWrite(ACTOR_HP, struct.pack("<II", current, maximum)))
        writes.append(RamWrite(SAVE_HP, struct.pack("<hh", current, maximum)))
    else:
        detail = "Health is already at maximum"
    return finish(state, _LIFE_VESSEL.name, tuple(writes), current, maximum, detail)


# ap id -> grant. Life Vessel is the only one. A handler returns Hold.NO_ROOM
# when it must wait, and otherwise a Grant from finish().
Handler = Callable[[PlayState], Grant | Hold]
HANDLERS: dict[int, Handler] = {
    _LIFE_VESSEL.ap_id: grant_life_vessel,
}


# The item at received_index, or None when the count is missing or already caught up.
def pending_ap_id(state: PlayState, ap_ids: Sequence[int]) -> int | None:
    index = state.received_index
    if index is None or index >= len(ap_ids):
        return None
    return ap_ids[index]


def plan(state: PlayState, ap_id: int | None) -> Grant | Hold:
    # Gameplay first, so title-screen bytes that are not a count stay silent.
    # A bad record is logged once the menu and the text box are closed.
    if not gameplay_ready(state):
        return Hold.GAMEPLAY
    if state.received_index is None or ap_id is None:
        return Hold.INDEX
    handler = HANDLERS.get(ap_id)
    if handler is None:
        return Hold.UNKNOWN
    return handler(state)
