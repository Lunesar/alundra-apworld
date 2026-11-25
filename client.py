"""BizHawk client for Alundra.

Archipelago ships the Lua connector (`data/lua/connector_bizhawk_generic.lua`).
This module is the handler that connector talks to. It claims a PlayStation
image, logs in to a room, reports locations listed in ``checks.py``, scouts
the shop checks named there when you enter Naomi's, Lurvy's, or Merrick's,
registers a speaker hint when that line's event bit is set, registers Jess's
hint from NPC text in his house while this client is connected, grants an item
the server sends from another game, sends the goal when the ending is
requested, and warns when the disc callbacks are stuck on the file-read pair.
"""

from __future__ import annotations

import enum
import logging
import struct
import sys
import time
from typing import TYPE_CHECKING, ClassVar

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from worlds._bizhawk.client import BizHawkClient

from Utils import async_start

from .checks import (
    EVENT_FLAGS,
    GOAL_PHASE,
    WATCHED_LOCATION_IDS,
    SpeakerHintPlan,
    checked_locations,
    flag_read,
    game_beaten,
    jess_talk_step,
    lurvy_repair_hint_locations,
    lurvy_repair_hints_enabled,
    names_for,
    pending_jess_hint,
    pending_speaker_hints,
    shop_hint_locations,
    speaker_hints_outstanding,
)
from .placement import apworld_version, pinned_randomizer_version
from .receive import (
    LOADED_MAP,
    READS,
    Hold,
    checks_ready,
    hold_message,
    parse_play_state,
    pending_ap_id,
    plan,
)
from .slot import SLOT_MAIN_RAM, SLOT_SIZE, parse_slot_block, room_seed_matches
from .sound_player import (
    LIVE_CALLBACKS,
    SAVED_CALLBACKS,
    CLEARED_MESSAGE,
    SCREEN_MESSAGE,
    next_sound_warning,
    sound_log_line,
    sound_player_healthy,
    sound_player_stuck,
)

logger = logging.getLogger("Client")

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

# TryIncrease, KSEG0 0x8004FBE4. MainRAM offset is address & 0x001FFFFF.
# docs/client_memory.md prints addiu sp, sp, -32 as the word 27 BD FF E0.
# The connector returns RAM order, little-endian, so the bytes are E0 FF BD 27.
# The BIOS screen does not have this word yet, so validate_rom returns False
# and the watcher tries again. After the title screen, a mismatch means the
# handler never logs "Running handler for Alundra".
_TRY_INCREASE = 0x4FBE4
_TRY_INCREASE_PROLOGUE = 0x27BDFFE0.to_bytes(4, "little")
_MAIN_RAM = "MainRAM"

# Remote items only (protocol bit 0). A check in this game grants its own
# item through the chest script, so own-world items would be granted twice.
# Starting gear is already applied by the new-game patch.
_ITEMS_FROM_OTHER_WORLDS = 0b001


class CreateAsHint(enum.IntEnum):
    """``LocationScouts`` field. The item reply is sent either way.

    ``NO_HINT`` stores nothing. ``ONLY_NEW`` stores a hint and stays quiet
    when the server already has it. Any other non-zero value stores the hint
    and tells the room again. None of these spends hint points.
    """

    NO_HINT = 0
    ONLY_NEW = 2

# On 3.11 and newer the connector wraps a script error in ExceptionGroup.
# A refused read has to return False so the watcher retries, same as a timeout.
_READ_ERRORS: tuple[type[BaseException], ...] = (bizhawk.RequestFailedError, bizhawk.ConnectorError)
if sys.version_info >= (3, 11):
    _READ_ERRORS = (*_READ_ERRORS, ExceptionGroup)


class AlundraClient(BizHawkClient):
    system: ClassVar[str] = "PSX"
    game: ClassVar[str] = "Alundra"

    def __init__(self) -> None:
        super().__init__()
        # Locations already written to the log for this connection. The server
        # still receives a repeat until it drops the id from missing_locations.
        self._reported: set[int] = set()
        # Shop checks already scouted for this connection. A repeat would
        # broadcast the hint again only when the first packet never landed,
        # so a new login clears this and the next shop visit sends it.
        self._shop_hinted: set[int] = set()
        # Speakers whose line was already handled this connection. Two rows
        # can name one location, so this is the speaker id, not the location.
        self._speaker_hinted: set[str] = set()
        # NPC text was seen on map 260, and the box has not yet closed there.
        # A connect clears it. Closing the client loses it, so the next
        # session waits for another conversation.
        self._jess_talk_seen = False
        # Previous watch's play state. A grant waits until two watches agree,
        # so a one-frame change during a load is not applied.
        self._stable = None
        # Hold lines already logged for this connection.
        self._holds: set[str] = set()
        # Slot read from the executable. None until a block this client knows is loaded.
        self._slot = None
        self._noted_missing_block = False
        self._unknown_version: str | None = None
        self._unknown_randomizer: str | None = None
        self._client_version: str | None = None
        self._randomizer_version: str | None = None
        # Wall time of the last stuck-sound warning. None after the music
        # pair returns, so the next episode warns on its first watch.
        self._sound_warned_at: float | None = None

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        """Claim the image when it is this client's patched executable.

        The TryIncrease prologue distinguishes Alundra from another PlayStation
        image. The slot block distinguishes a Multiworld patch from a vanilla
        disc. A block written by an apworld version this client is not, or by
        a randomizer release other than the one this world pins, is left alone.
        """
        try:
            # One read: the prologue and the block are both in the loaded executable.
            prologue, block_bytes = await bizhawk.read(
                ctx.bizhawk_ctx,
                [
                    (_TRY_INCREASE, len(_TRY_INCREASE_PROLOGUE), _MAIN_RAM),
                    (SLOT_MAIN_RAM, SLOT_SIZE, _MAIN_RAM),
                ],
            )
        except _READ_ERRORS:
            return False
        if prologue != _TRY_INCREASE_PROLOGUE:
            return False
        block = parse_slot_block(block_bytes)
        if block is None:
            self._slot = None
            if not self._noted_missing_block:
                self._noted_missing_block = True
                logger.info("This disc has no Alundra slot block. The handler leaves it alone.")
            return False
        if self._client_version is None:
            self._client_version = apworld_version()
        if block.apworld_version != self._client_version:
            self._slot = None
            if block.apworld_version != self._unknown_version:
                self._unknown_version = block.apworld_version
                logger.info(
                    "This ROM was patched by alundra-apworld %s, and this client is %s.",
                    block.apworld_version,
                    self._client_version,
                )
            return False
        if self._randomizer_version is None:
            self._randomizer_version = pinned_randomizer_version()
        if block.randomizer_version != self._randomizer_version:
            self._slot = None
            if block.randomizer_version != self._unknown_randomizer:
                self._unknown_randomizer = block.randomizer_version
                logger.info(
                    "This ROM was patched by alundra-randomizer %s, and this world expects %s.",
                    block.randomizer_version,
                    self._randomizer_version,
                )
            return False

        self._slot = block
        self._noted_missing_block = False
        self._unknown_version = None
        self._unknown_randomizer = None
        ctx.game = self.game
        ctx.items_handling = _ITEMS_FROM_OTHER_WORLDS
        return True

    async def set_auth(self, ctx: "BizHawkClientContext") -> None:
        """Log in as the player named in the slot block."""
        if self._slot is None:
            return
        ctx.auth = self._slot.player

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        """Report checks, scout a shop, register a spoken line, grant one item, and send the goal.

        Also warns when the disc callbacks are stuck on the file-read pair.
        """
        await self._watch_sound_player(ctx)
        received = list(ctx.items_received)
        location_watch = bool(ctx.missing_locations & WATCHED_LOCATION_IDS)
        slot_data = ctx.slot_data if isinstance(ctx.slot_data, dict) else {}
        speaker_rows = slot_data.get("speaker_hints")
        # An off-world line is not one of this slot's missing checks. Keep
        # reading flags until every speaker row with a bit has been handled.
        need_speakers = speaker_hints_outstanding(speaker_rows, self._speaker_hinted)
        # Jess has no flag. A found local check is remembered here, and an
        # open row keeps the play-state read alive on its own.
        jess_plan = pending_jess_hint(speaker_rows, ctx.missing_locations, self._speaker_hinted)
        if jess_plan.quiet:
            self._speaker_hinted.update(jess_plan.quiet)
        jess_hint_pending = bool(jess_plan.sends)
        # The ending word is not a location. Keep reading it after the last chest.
        send_goal = not ctx.finished_game
        if not location_watch and not need_speakers and not received and not send_goal and not jess_hint_pending:
            return
        flag = flag_read() if location_watch or need_speakers else None
        # Checks use the same ready gate as a grant. The flag array is work
        # RAM, and it can hold bits until new-game setup clears it.
        need_play = flag is not None or bool(received) or jess_hint_pending
        reads: list[tuple[int, int, str]] = []
        if send_goal:
            reads.append((GOAL_PHASE, 4, _MAIN_RAM))
        if flag is not None:
            offset, length = flag
            reads.append((offset, length, _MAIN_RAM))
        if need_play:
            reads.extend((address, size, _MAIN_RAM) for address, size in READS)
        if not reads:
            return
        try:
            read_bytes = await bizhawk.read(ctx.bizhawk_ctx, reads)
        except _READ_ERRORS:
            return
        cursor = 0
        if send_goal:
            if game_beaten(read_bytes[cursor]):
                await self._complete_goal(ctx)
            cursor += 1
        flag_bytes = None
        if flag is not None:
            flag_bytes = read_bytes[cursor]
            cursor += 1
        play_bytes: list[bytes] = []
        if need_play:
            play_bytes = read_bytes[cursor:cursor + len(READS)]
        if flag is not None and flag_bytes is not None and checks_ready(play_bytes):
            offset, _length = flag
            origin = offset - EVENT_FLAGS
            if location_watch:
                sent = await ctx.check_locations(checked_locations(flag_bytes, origin))
                unreported = sent - self._reported
                if unreported:
                    self._reported.update(unreported)
                    logger.info("Checked %s.", ", ".join(names_for(unreported)))
                await self._hint_shops(ctx, flag_bytes, origin, play_bytes)
            if need_speakers:
                await self._hint_speakers(ctx, flag_bytes, origin, speaker_rows)
        await self._watch_jess(ctx, play_bytes, jess_hint_pending)
        if received:
            await self._receive(ctx, play_bytes, received)

    async def _complete_goal(self, ctx: "BizHawkClientContext") -> None:
        """Tell the room the ending was requested.

        A watch before login does not count. The word is still 9 on the next
        watch, until END.EXE replaces the image.
        """
        if ctx.finished_game or not _can_send(ctx):
            return
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        if not _can_send(ctx):
            return
        ctx.finished_game = True
        logger.info("Goal completed.")

    async def _hint_shops(
        self,
        ctx: "BizHawkClientContext",
        flag_bytes: bytes,
        origin: int,
        play_bytes: list[bytes],
    ) -> None:
        """Scout the checks this shop still has.

        ``CreateAsHint.ONLY_NEW`` records the hint and does not spend hint
        points. The server drops a repeat of a hint it already stored. This
        set stops a second watch in the same visit from sending the packet again.
        """
        if not _can_send(ctx):
            return
        slot_data = ctx.slot_data if isinstance(ctx.slot_data, dict) else {}
        locations = shop_hint_locations(
            parse_play_state(play_bytes).loaded_map,
            slot_data.get("shop_hints"),
            flag_bytes,
            origin,
            skip=ctx.checked_locations,
        )
        if lurvy_repair_hints_enabled(slot_data):
            locations.extend(lurvy_repair_hint_locations(
                flag_bytes,
                origin,
                skip=ctx.checked_locations,
            ))
        pending = [
            location_id
            for location_id in locations
            if location_id not in self._shop_hinted and location_id in ctx.missing_locations
        ]
        if not pending:
            return
        await ctx.send_msgs([{
            "cmd": "LocationScouts",
            "locations": pending,
            "create_as_hint": CreateAsHint.ONLY_NEW,
        }])
        if not _can_send(ctx):
            return
        self._shop_hinted.update(pending)
        logger.info("Hinted %s.", ", ".join(names_for(set(pending))))

    async def _hint_speakers(
        self,
        ctx: "BizHawkClientContext",
        flag_bytes: bytes,
        origin: int,
        rows: object,
    ) -> None:
        """Register the check a speaker just named.

        A local check is ``LocationScouts`` with ``CreateAsHint.ONLY_NEW``.
        An unknown-place check is ``CreateHints`` for the slot that holds it.
        Neither spends hint points. One dropped packet leaves every send in
        this watch unmarked, and the server ignores a hint it already stored.
        """
        hint_plan = pending_speaker_hints(
            rows, flag_bytes, origin, ctx.missing_locations, self._speaker_hinted,
        )
        await self._send_speaker_hints(ctx, hint_plan)

    async def _watch_jess(
        self,
        ctx: "BizHawkClientContext",
        play_bytes: list[bytes],
        jess_hint_pending: bool,
    ) -> None:
        """Latch NPC text in Jess's house, then send his row once control returns.

        The text words are set while the box is up, and a ready watch is the
        one where that box has closed. Seeing the box on map 260 arms the
        send. Leaving the map clears the latch, so the warp after the blue
        chest opens does not register on a later visit. The menu window does
        not arm it. A dropped packet arms the latch again.
        """
        if len(play_bytes) != len(READS):
            return
        if any(len(data) != size for (_, size), data in zip(READS, play_bytes)):
            return
        state = parse_play_state(play_bytes)
        new_latch, talk_ready = jess_talk_step(
            self._jess_talk_seen,
            state.loaded_map,
            bool(state.text_window_a or state.text_window_b),
            checks_ready(play_bytes),
        )
        self._jess_talk_seen = new_latch
        if not jess_hint_pending or not talk_ready:
            return
        # Re-read the row. A check reported earlier in this watch may now be found.
        slot_data = ctx.slot_data if isinstance(ctx.slot_data, dict) else {}
        hint_plan = pending_jess_hint(
            slot_data.get("speaker_hints"),
            ctx.missing_locations,
            self._speaker_hinted,
        )
        if not await self._send_speaker_hints(ctx, hint_plan):
            self._jess_talk_seen = True

    async def _send_speaker_hints(self, ctx: "BizHawkClientContext", hint_plan: SpeakerHintPlan) -> bool:
        """Send one speaker plan. Quiet rows are remembered either way.

        False means a packet was dropped before every sender was remembered,
        so the caller can retry. Shops and the chimney use their own sender.
        """
        if hint_plan.quiet:
            self._speaker_hinted.update(hint_plan.quiet)
        if not hint_plan.sends:
            return True
        if not _can_send(ctx):
            return False
        local_ids = _unique_locations(send for send in hint_plan.sends if send.player is None)
        remote = _remote_by_slot(send for send in hint_plan.sends if send.player is not None)
        if local_ids:
            await ctx.send_msgs([{
                "cmd": "LocationScouts",
                "locations": local_ids,
                "create_as_hint": CreateAsHint.ONLY_NEW,
            }])
            if not _can_send(ctx):
                return False
        for player, locations in remote:
            await ctx.send_msgs([{
                "cmd": "CreateHints",
                "player": player,
                "locations": locations,
            }])
            if not _can_send(ctx):
                return False
        self._speaker_hinted.update(send.speaker for send in hint_plan.sends)
        names = names_for(set(local_ids))
        if names:
            logger.info("Hinted %s.", ", ".join(names))
        for player, _locations in remote:
            logger.info("Hinted a check in slot %s.", player)
        return True

    async def _receive(self, ctx: "BizHawkClientContext", read_bytes: list[bytes], received: list) -> None:
        """Grant the item at the saved count when this watch matches the last one.

        The count lives in the save, so a reconnect does not grant twice and a
        savestate does not skip. One item per watch. A guard failure leaves
        the count where it is and the next watch tries the same item.
        """
        if len(read_bytes) != len(READS):
            return
        if any(len(data) != size for (_, size), data in zip(READS, read_bytes)):
            return
        state = parse_play_state(read_bytes)
        if state != self._stable:
            self._stable = state
            return
        ap_ids = [network_item.item for network_item in received]
        ap_id = pending_ap_id(state, ap_ids)
        # Caught up: the saved count has reached the server's list.
        if ap_id is None and state.received_index is not None:
            return
        decision = plan(state, ap_id)
        if isinstance(decision, Hold):
            self._log_hold(decision, ap_id)
            return
        guards = [
            (address, data, _MAIN_RAM)
            for (address, _size), data in zip(READS, read_bytes, strict=True)
        ]
        writes = [(ram.address, ram.data, _MAIN_RAM) for ram in decision.writes]
        try:
            accepted = await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)
        except _READ_ERRORS:
            return
        if not accepted:
            return
        # Commit before the toast. A failed message must not retry the grant.
        self._stable = decision.next_state
        if decision.detail:
            logger.info("Received %s. %s.", decision.name, decision.detail)
        else:
            logger.info("Received %s.", decision.name)
        try:
            await bizhawk.display_message(ctx.bizhawk_ctx, f"Received {decision.name}")
        except _READ_ERRORS:
            return

    def _log_hold(self, hold: Hold, ap_id: int | None) -> None:
        message = hold_message(hold, ap_id)
        if message is None or message in self._holds:
            return
        self._holds.add(message)
        logger.info("%s", message)

    def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        if cmd != "Connected":
            return
        rom_seed = None if self._slot is None else self._slot.seed
        if rom_seed is None or not room_seed_matches(rom_seed, ctx.slot_data):
            room_seed = ctx.slot_data.get("seed") if isinstance(ctx.slot_data, dict) else None
            logger.info(
                "This ROM was patched from seed %s, and the room sent seed %s. Disconnecting.",
                rom_seed,
                room_seed,
            )
            ctx.auth = None
            async_start(ctx.disconnect(), name="seed mismatch")
            return
        # A new room has its own missing list and its own received items.
        # The saved count still says what this file has already been granted.
        self._reported.clear()
        self._shop_hinted.clear()
        self._speaker_hinted.clear()
        self._jess_talk_seen = False
        self._stable = None
        self._holds.clear()
        self._sound_warned_at = None
        logger.info("Logged in as %s.", ctx.auth)

    async def _watch_sound_player(self, ctx: "BizHawkClientContext") -> None:
        """Warn while a disc restore would put the file-read callback back.

        The log and the on-screen line repeat once a minute. A normal read,
        which keeps the music pair in the saved slots, stays quiet.
        """
        try:
            live, saved, map_bytes = await bizhawk.read(
                ctx.bizhawk_ctx,
                [
                    (LIVE_CALLBACKS, 8, _MAIN_RAM),
                    (SAVED_CALLBACKS, 8, _MAIN_RAM),
                    (LOADED_MAP, 4, _MAIN_RAM),
                ],
            )
        except _READ_ERRORS:
            return
        if len(live) != 8 or len(saved) != 8 or len(map_bytes) != 4:
            return
        stuck = sound_player_stuck(live, saved)
        healthy = sound_player_healthy(live)
        warned_at = self._sound_warned_at
        warn, self._sound_warned_at = next_sound_warning(
            stuck, healthy, warned_at, time.monotonic()
        )
        if healthy and warned_at is not None:
            logger.info("%s", CLEARED_MESSAGE)
            try:
                await bizhawk.display_message(ctx.bizhawk_ctx, CLEARED_MESSAGE)
            except _READ_ERRORS:
                return
        if not warn:
            return
        map_id = struct.unpack("<I", map_bytes)[0]
        logger.info("%s", sound_log_line(map_id, live, saved))
        try:
            await bizhawk.display_message(ctx.bizhawk_ctx, SCREEN_MESSAGE)
        except _READ_ERRORS:
            return


def _unique_locations(sends) -> list[int]:
    locations: list[int] = []
    seen: set[int] = set()
    for send in sends:
        if send.location in seen:
            continue
        seen.add(send.location)
        locations.append(send.location)
    return locations


def _remote_by_slot(sends) -> list[tuple[int, list[int]]]:
    grouped: dict[int, list[int]] = {}
    for send in sends:
        # pending_speaker_hints only puts a player on an unknown-place row.
        if send.player is None:
            continue
        locations = grouped.setdefault(send.player, [])
        if send.location not in locations:
            locations.append(send.location)
    return [(player, grouped[player]) for player in sorted(grouped)]


def _can_send(ctx: "BizHawkClientContext") -> bool:
    """True when a StatusUpdate would leave this process.

    ``send_msgs`` drops the packet when the socket is not open. The goal must
    not be marked done on that drop.
    """
    server = ctx.server
    if server is None or ctx.slot is None:
        return False
    socket = server.socket
    return socket is not None and socket.open and not socket.closed
