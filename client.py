"""BizHawk client for Alundra.

Archipelago ships the Lua connector (`data/lua/connector_bizhawk_generic.lua`).
This module is the handler that connector talks to. It claims a PlayStation
image, logs in to a room, reports locations listed in ``checks.py``, and
grants an item the server sends from another game.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, ClassVar

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from .checks import EVENT_FLAGS, WATCHED_LOCATION_IDS, checked_locations, flag_read, names_for
from .receive import READS, Hold, hold_message, parse_play_state, pending_ap_id, plan

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

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        """Claim the image when the TryIncrease prologue matches."""
        try:
            # First instruction of TryIncrease, addiu sp, sp, -32 at MainRAM 0x4FBE4.
            # A match is what distinguishes an Alundra executable from another PlayStation image.
            prologue = (await bizhawk.read(
                ctx.bizhawk_ctx,
                [(_TRY_INCREASE, len(_TRY_INCREASE_PROLOGUE), _MAIN_RAM)],
            ))[0]
        except _READ_ERRORS:
            return False
        if prologue != _TRY_INCREASE_PROLOGUE:
            return False

        ctx.game = self.game
        ctx.items_handling = _ITEMS_FROM_OTHER_WORLDS
        return True

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        """Report checked locations, then grant one queued remote item."""
        received = list(ctx.items_received)
        watching = bool(ctx.missing_locations & WATCHED_LOCATION_IDS)
        if not watching and not received:
            return
        flag = flag_read() if watching else None
        reads: list[tuple[int, int, str]] = []
        if flag is not None:
            offset, length = flag
            reads.append((offset, length, _MAIN_RAM))
        if received:
            reads.extend((address, size, _MAIN_RAM) for address, size in READS)
        if not reads:
            return
        try:
            read_bytes = await bizhawk.read(ctx.bizhawk_ctx, reads)
        except _READ_ERRORS:
            return
        if flag is not None:
            offset, _length = flag
            sent = await ctx.check_locations(checked_locations(read_bytes[0], offset - EVENT_FLAGS))
            unreported = sent - self._reported
            if unreported:
                self._reported.update(unreported)
                logger.info("Checked %s.", ", ".join(names_for(unreported)))
            read_bytes = read_bytes[1:]
        if received:
            await self._receive(ctx, read_bytes, received)

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
        # A new room has its own missing list and its own received items.
        # The saved count still says what this file has already been granted.
        self._reported.clear()
        self._stable = None
        self._holds.clear()
        logger.info("Logged in as %s.", ctx.auth)
