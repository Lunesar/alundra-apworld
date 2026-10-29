"""BizHawk client for Alundra.

Archipelago ships the Lua connector (`data/lua/connector_bizhawk_generic.lua`).
This module is the handler that connector talks to. It claims a PlayStation
image, logs in to a room, reports locations listed in ``checks.py``, grants
an item the server sends from another game, and sends the goal when the
ending is requested.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, ClassVar

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from worlds._bizhawk.client import BizHawkClient

from Utils import async_start

from .checks import (
    EVENT_FLAGS,
    GOAL_PHASE,
    WATCHED_LOCATION_IDS,
    checked_locations,
    flag_read,
    game_beaten,
    names_for,
)
from .placement import apworld_version, pinned_randomizer_version
from .receive import READS, Hold, checks_ready, hold_message, parse_play_state, pending_ap_id, plan
from .slot import SLOT_MAIN_RAM, SLOT_SIZE, parse_slot_block, room_seed_matches

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
        """Report checked locations, grant one queued remote item, and send the goal."""
        received = list(ctx.items_received)
        watching = bool(ctx.missing_locations & WATCHED_LOCATION_IDS)
        # The ending word is not a location. Keep reading it after the last chest.
        send_goal = not ctx.finished_game
        if not watching and not received and not send_goal:
            return
        flag = flag_read() if watching else None
        # Checks use the same ready gate as a grant. The flag array is work
        # RAM, and it can hold bits until new-game setup clears it.
        need_play = flag is not None or bool(received)
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
            sent = await ctx.check_locations(checked_locations(flag_bytes, offset - EVENT_FLAGS))
            unreported = sent - self._reported
            if unreported:
                self._reported.update(unreported)
                logger.info("Checked %s.", ", ".join(names_for(unreported)))
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
        self._stable = None
        self._holds.clear()
        logger.info("Logged in as %s.", ctx.auth)


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
