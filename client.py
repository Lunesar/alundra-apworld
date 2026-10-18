"""BizHawk client for Alundra.

Archipelago ships the Lua connector (`data/lua/connector_bizhawk_generic.lua`).
This module is the handler that connector talks to. It claims a PlayStation
image and logs in to a room. It does not read checks or grant items.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, ClassVar

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

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

# On 3.11 and newer the connector wraps a script error in ExceptionGroup.
# A refused read has to return False so the watcher retries, same as a timeout.
_READ_ERRORS: tuple[type[BaseException], ...] = (bizhawk.RequestFailedError, bizhawk.ConnectorError)
if sys.version_info >= (3, 11):
    _READ_ERRORS = (*_READ_ERRORS, ExceptionGroup)


class AlundraClient(BizHawkClient):
    system: ClassVar[str] = "PSX"
    game: ClassVar[str] = "Alundra"

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
        # The server sends no items. The watcher does not grant any, so a
        # non-zero mask would only queue grants this client drops.
        ctx.items_handling = 0
        return True

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        """Login does not watch memory. Checks and item grants come later."""

    def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        if cmd != "Connected":
            return
        from CommonClient import logger
        logger.info("Logged in as %s.", ctx.auth)
