# Remote items the BizHawk client can grant.
#
# Every item in item.json has a handler. A handler returns Hold.NO_ROOM when
# the item has to wait because its stack is full and room may open later.
# Otherwise it returns the Grant from finish(), which appends the
# received-index write.
#
# The watcher grants one item per pass, and only the item at the front of
# the queue. An item id with no record stays there until one exists.

from __future__ import annotations

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum

from .data import GAME_DATA, ITEM_COUNT, ITEM_ID_BASE, UPGRADE_TIER, ItemRecord

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
MAX_MP = 4
MAX_GOLD = 9999
MAX_FALCON = 50
# Key's stack. TryIncrease will not store a quantity above this.
MAX_STACK = 99
# Stat block from current MP through the folded falcon total. SAVE_HP ends
# where this begins, and the inventory records begin where this ends.
STAT_REST = 0x1DD820
STAT_REST_SIZE = 14
# GiveItem's progressive replacement scans item ids through 60.
_PROGRESSIVE_SCAN = 60

# Used from the bag, so a full stack can open up again. Herbs holds 9. These
# four cap at 1. The Key holds 99, which is more than the doors in the game,
# so a full key stack is counted instead of waiting.
_USED_ONCE = frozenset({
    "Strength Elixyr",
    "Magic Elixyr",
    "Wonder Essence",
    "Strength Tonic",
})
_WAITS_WHEN_FULL = _USED_ONCE | {"Herbs"}
_GILDER_VALUE = {0x45: 1, 0x46: 5, 0x47: 10, 0x48: 30}
# ROM max quantity is 0. item.json leaves it off, so the parsed max is 1.
# GiveItem does not put these in the inventory array.
_NO_EFFECT_IDS = frozenset({0x00, 0x3A})
# Current MP, then max MP. Seeds and crystals write this pair.
SAVE_MP = STAT_REST
# Gilders s16. AddGold stores 9999 when the sum would pass it.
SAVE_GOLD = STAT_REST + 4
# GiveItem increments this u16, then a later routine folds it into the total.
FALCON_PENDING = STAT_REST + 10
# Event 0x05AA. Bit 2 of this byte, which is bit 0x400 of the word at
# 0x801DD3E8. GiveItem sets it in the same routine that increments pending.
# Merrick's talk tests it before he will fold pending into the total.
# The other bits in the byte are his offer and trade flags, so a grant
# reads the byte and ORs this mask.
FALCON_VISIT = 0x1DD3E9
FALCON_BROUGHT = 0x04
# Vanilla item-info flag bit 0 (table 0x800BBE50, halfword +2). The randomizer
# rewrites slot and tier and leaves this bit. Set: FindOwned keeps the item
# and looks for a higher tier. Clear on the first owned item in the slot: it
# returns that item and stops. A later item replaces the kept one only when
# its tier is higher.
# 0x01-0x1E weapons through the placeholder, Bomb, the spells and rings, Power Glove.
_KEEP_SCANNING = frozenset([*range(0x01, 0x1F), 0x23, *range(0x2B, 0x39), 0x3B])

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
    (STAT_REST, STAT_REST_SIZE),
    (INVENTORY, ITEM_COUNT * 4),
    (FALCON_VISIT, 1),
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
    # Save MP, gold, the equipped weapon id, the unread halfword at +12, and
    # the two falcon halfwords. Pending is what GiveItem increments. Merrick's
    # dialog adds it to the total and clears it. falcon_flags is the raw byte
    # at 0x1DD3E9; bit 2 is event 0x05AA.
    mp_current: int = 0
    mp_max: int = 0
    gold: int = 0
    equipped: int = 0
    stat_gap: int = 0
    falcon_pending: int = 0
    falcon_total: int = 0
    falcon_flags: int = 0
    quantities: tuple[int, ...] = field(default_factory=lambda: (0,) * ITEM_COUNT)


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
    mp_current, mp_max, gold, equipped, stat_gap, falcon_pending, falcon_total = struct.unpack(
        "<hhhhhHH", read_bytes[10]
    )
    inventory = read_bytes[11]
    quantities = tuple(struct.unpack_from("<h", inventory, index * 4 + 2)[0] for index in range(ITEM_COUNT))
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
        mp_current=mp_current,
        mp_max=mp_max,
        gold=gold,
        equipped=equipped,
        stat_gap=stat_gap,
        falcon_pending=falcon_pending,
        falcon_total=falcon_total,
        falcon_flags=read_bytes[12][0],
        quantities=quantities,
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
        struct.pack(
            "<hhhhhHH",
            state.mp_current,
            state.mp_max,
            state.gold,
            state.equipped,
            state.stat_gap,
            state.falcon_pending,
            state.falcon_total,
        ),
        _pack_inventory(state.quantities),
        bytes([state.falcon_flags]),
    )


def _pack_inventory(quantities: Sequence[int]) -> bytes:
    # The owned check ignores the first halfword. Tests round-trip it as 0.
    # The client guards the bytes it actually read.
    padded = tuple(quantities) + (0,) * (ITEM_COUNT - len(quantities))
    return b"".join(struct.pack("<hh", 0, qty) for qty in padded[:ITEM_COUNT])


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
    if state.actor_current != state.save_current or state.actor_max != state.save_max:
        return False
    if not 0 <= state.mp_max <= MAX_MP or not 0 <= state.mp_current <= state.mp_max:
        return False
    if not 0 <= state.gold <= MAX_GOLD:
        return False
    if state.falcon_pending > MAX_FALCON or state.falcon_total > MAX_FALCON:
        return False
    if len(state.quantities) != ITEM_COUNT:
        return False
    return all(0 <= qty <= MAX_STACK for qty in state.quantities)


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
# current and maximum are the HP both pairs hold after the grant. changes are
# the other fields the writes just stored, so the next item does not wait an
# extra watch for this one to settle.
def finish(
    state: PlayState,
    name: str,
    effect_writes: tuple[RamWrite, ...],
    current: int,
    maximum: int,
    detail: str = "",
    **changes: int | tuple[int, ...],
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
            **changes,
        ),
        detail=detail,
    )


def _count(
    state: PlayState,
    name: str,
    effect_writes: tuple[RamWrite, ...] = (),
    detail: str = "",
    **changes: int | tuple[int, ...],
) -> Grant:
    return finish(state, name, effect_writes, state.save_current, state.save_max, detail, **changes)


def _hp_writes(current: int, maximum: int) -> tuple[RamWrite, ...]:
    return (
        RamWrite(ACTOR_HP, struct.pack("<II", current, maximum)),
        RamWrite(SAVE_HP, struct.pack("<hh", current, maximum)),
    )


def _raise_and_fill(maximum: int, cap: int) -> tuple[int, int]:
    # GiveItem fills current to the (possibly raised) max.
    if maximum < cap:
        maximum += 1
    return maximum, maximum


def _with_quantity(state: PlayState, item_id: int, quantity: int) -> tuple[int, ...]:
    quantities = list(state.quantities)
    quantities[item_id] = quantity
    return tuple(quantities)


def _quantity_write(item_id: int, quantity: int) -> RamWrite:
    # The s16 only. A word write would clear the next record's first halfword.
    return RamWrite(INVENTORY + item_id * 4 + 2, struct.pack("<h", quantity))


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
    current, maximum = _raise_and_fill(state.save_max, MAX_HP)
    writes: tuple[RamWrite, ...] = ()
    detail = ""
    if current != state.save_current or maximum != state.save_max:
        writes = _hp_writes(current, maximum)
    else:
        detail = "Health is already at maximum"
    return finish(state, _LIFE_VESSEL.name, writes, current, maximum, detail)


def _grant_gold(state: PlayState, item: ItemRecord) -> Grant:
    # AddGold stores 9999 when the sum would pass it. A pile past that is counted.
    total = state.gold + _GILDER_VALUE[item.in_game_id]
    if total > MAX_GOLD:
        total = MAX_GOLD
    if total == state.gold:
        return _count(state, item.name, detail="Gilders are already at maximum")
    return _count(state, item.name, (RamWrite(SAVE_GOLD, struct.pack("<h", total)),), gold=total)


def _grant_falcon(state: PlayState, item: ItemRecord) -> Grant:
    # GiveItem adds 1 to pending and caps that halfword at 50, then ORs 0x400
    # into the word at 0x801DD3E8. That bit is event 0x05AA. Merrick tests it
    # before he will count today's falcons, and his dialog then folds pending
    # into the total. The fold caps the sum at 50, so a falcon at 50 is
    # counted and the queue moves.
    if state.falcon_pending + state.falcon_total >= MAX_FALCON:
        return _count(state, item.name, detail="Falcons are already at maximum")
    pending = state.falcon_pending + 1
    flags = state.falcon_flags | FALCON_BROUGHT
    writes = [RamWrite(FALCON_PENDING, struct.pack("<H", pending))]
    if flags != state.falcon_flags:
        writes.append(RamWrite(FALCON_VISIT, bytes([flags])))
    return _count(
        state,
        item.name,
        tuple(writes),
        falcon_pending=pending,
        falcon_flags=flags,
    )


def _grant_magic_seed(state: PlayState, item: ItemRecord) -> Grant:
    # Adds 1 to max MP, stores 4 when the sum would pass it, and fills current
    # to that max. The cap does not open again, so a seed at 4 is counted.
    current, maximum = _raise_and_fill(state.mp_max, MAX_MP)
    writes: tuple[RamWrite, ...] = ()
    detail = ""
    if current != state.mp_current or maximum != state.mp_max:
        writes = (RamWrite(SAVE_MP, struct.pack("<hh", current, maximum)),)
    else:
        detail = "Magic is already at maximum"
    return _count(state, item.name, writes, detail, mp_current=current, mp_max=maximum)


def _mp_fill(state: PlayState, item: ItemRecord, current: int) -> Grant:
    return _count(
        state,
        item.name,
        (RamWrite(SAVE_MP, struct.pack("<hh", current, state.mp_max)),),
        mp_current=current,
    )


def _grant_clamped_mp(state: PlayState, item: ItemRecord, current: int) -> Grant:
    # Already at the clamp: count it and leave MP alone. An extra crystal must
    # not sit in front of the queue.
    if current == state.mp_current:
        return _count(state, item.name, detail="Magic is already at maximum")
    return _mp_fill(state, item, current)


def _grant_small_crystal(state: PlayState, item: ItemRecord) -> Grant:
    # Adds 1 to current MP and clamps to max.
    current = state.mp_current + 1
    if current > state.mp_max:
        current = state.mp_max
    return _grant_clamped_mp(state, item, current)


def _grant_large_crystal(state: PlayState, item: ItemRecord) -> Grant:
    return _grant_clamped_mp(state, item, state.mp_max)


def _grant_heal(state: PlayState, item: ItemRecord, amount: int) -> Grant:
    # The pickup is consumed either way. Past max HP the heal is counted and
    # both pairs stay where they are.
    current = state.save_current + amount
    if current > state.save_max:
        current = state.save_max
    if current == state.save_current:
        return _count(state, item.name, detail="Health is already at maximum")
    return finish(state, item.name, _hp_writes(current, state.save_max), current, state.save_max)


def _grant_dew(state: PlayState, item: ItemRecord) -> Grant:
    return _grant_heal(state, item, 2)


def _grant_drop(state: PlayState, item: ItemRecord) -> Grant:
    # max >> 2, and 1 when that is 0. Max is 1..50 here, so the sign fixup
    # in the handler does not apply.
    amount = state.save_max // 4
    if amount <= 0:
        amount = 1
    return _grant_heal(state, item, amount)


def _grant_water(state: PlayState, item: ItemRecord) -> Grant:
    # max / 2, and 5 when that is below 5.
    amount = state.save_max // 2
    if amount < 5:
        amount = 5
    return _grant_heal(state, item, amount)


def _best_owned(state: PlayState, slot: int) -> ItemRecord | None:
    # FindOwnedItemOfBestTierForSlot. Slot 32 and above returns -1. The first
    # owned item in the slot is kept, and returned immediately when its flag
    # bit 0 is clear. A later item replaces it only when the tier is higher.
    if slot >= 32:
        return None
    best: ItemRecord | None = None
    for item in GAME_DATA.items:
        if item.slot_id != slot or state.quantities[item.in_game_id] <= 0:
            continue
        if best is None and item.in_game_id not in _KEEP_SCANNING:
            return item
        if best is None or item.tier > best.tier:
            best = item
    return best


def _item_for_tier(slot: int, tier: int) -> ItemRecord | None:
    # The hook scans ids 0 through 60 for this slot and tier. An upgrade row
    # is tier 64. Storing one would make FindOwned prefer it over Legend Sword.
    if tier == UPGRADE_TIER:
        return None
    for item in GAME_DATA.items[: _PROGRESSIVE_SCAN + 1]:
        if item.slot_id == slot and item.tier == tier:
            return item
    return None


def _grant_upgrade(state: PlayState, item: ItemRecord) -> Grant:
    # Nothing owned: the tier-0 item. Otherwise the best tier plus one. No such
    # item means the top tier is already owned. Count it and leave the upgrade
    # row at 0. The name is the item that was written, or the upgrade itself
    # when nothing was.
    best = _best_owned(state, item.slot_id)
    found = _item_for_tier(item.slot_id, 0 if best is None else best.tier + 1)
    if found is None:
        if best is None:
            return _count(state, item.name, detail="No further tier")
        return _count(state, item.name, detail=f"Already carrying {best.name}")
    return _grant_inventory(state, found)


def _waits_when_full(item: ItemRecord) -> bool:
    # A unique at 1 never leaves, so a duplicate has to be counted or the
    # queue stops. The same is true of a 99th Key.
    return item.name in _WAITS_WHEN_FULL


def _grant_inventory(state: PlayState, item: ItemRecord) -> Grant | Hold:
    owned = state.quantities[item.in_game_id]
    if owned >= item.max_quantity:
        if _waits_when_full(item):
            return Hold.NO_ROOM
        return _count(state, item.name, detail=f"Already carrying {item.name}")
    quantity = owned + 1
    return _count(
        state,
        item.name,
        (_quantity_write(item.in_game_id, quantity),),
        quantities=_with_quantity(state, item.in_game_id, quantity),
    )


def _grant_record(state: PlayState, item: ItemRecord) -> Grant | Hold:
    item_id = item.in_game_id
    if item_id in _GILDER_VALUE:
        return _grant_gold(state, item)
    if item_id == 0x4F:
        return _grant_falcon(state, item)
    if item_id == 0x50:
        return _grant_magic_seed(state, item)
    if item_id == 0x51:
        return _grant_small_crystal(state, item)
    if item_id == 0x52:
        return _grant_large_crystal(state, item)
    if item_id == 0x53:
        return grant_life_vessel(state)
    if item_id == 0x54:
        return _grant_dew(state, item)
    if item_id == 0x55:
        return _grant_drop(state, item)
    if item_id == 0x56:
        return _grant_water(state, item)
    if item_id in _NO_EFFECT_IDS:
        return _count(state, item.name)
    if item.tier == UPGRADE_TIER:
        return _grant_upgrade(state, item)
    return _grant_inventory(state, item)


# ap id -> grant. One handler per item.json id. A handler returns Hold.NO_ROOM
# when it must wait, and otherwise a Grant from finish().
Handler = Callable[[PlayState], Grant | Hold]


def _bind(item: ItemRecord) -> Handler:
    def grant(state: PlayState) -> Grant | Hold:
        return _grant_record(state, item)

    return grant


HANDLERS: dict[int, Handler] = {item.ap_id: _bind(item) for item in GAME_DATA.items}


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
