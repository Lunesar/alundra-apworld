"""Slot block embedded in a patched USA 1.1 executable.

The randomizer writes this as the first injected blob, at KSEG0 0x8001F780.
BizHawk MainRAM drops the top bits, so the client reads 0x1F780. The layout
matches src/patches/slot_block.hpp in the randomizer:

    0x00  ALAP                  4 bytes
    0x04  block version         u16, currently 1
    0x06  reserved              u16, zero
    0x08  seed                  u32
    0x0C  randomizer version    16 bytes, NUL-terminated
    0x1C  apworld version       16 bytes, NUL-terminated
    0x2C  player                64 bytes, NUL-terminated login name
    0x6C  padding               zeros through 0x80
"""

from __future__ import annotations

from dataclasses import dataclass

SLOT_MAIN_RAM = 0x1F780
SLOT_SIZE = 0x80
BLOCK_VERSION = 1
_MAGIC = b"ALAP"
_OFF_VERSION = 0x04
_OFF_SEED = 0x08
_OFF_RANDOMIZER = 0x0C
_OFF_APWORLD = 0x1C
_OFF_PLAYER = 0x2C
_VERSION_FIELD = 16
_PLAYER_FIELD = 64


@dataclass(frozen=True)
class SlotBlock:
    """Identity read from a patched executable."""

    randomizer_version: str
    apworld_version: str
    seed: int
    player: str


def parse_slot_block(data: bytes) -> SlotBlock | None:
    """Return the slot, or None when the bytes are not a block this client can read."""
    if len(data) != SLOT_SIZE or data[:4] != _MAGIC:
        return None
    version = int.from_bytes(data[_OFF_VERSION:_OFF_VERSION + 2], "little")
    if version != BLOCK_VERSION:
        return None
    seed = int.from_bytes(data[_OFF_SEED:_OFF_SEED + 4], "little")
    randomizer = _cstring(data, _OFF_RANDOMIZER, _VERSION_FIELD)
    apworld = _cstring(data, _OFF_APWORLD, _VERSION_FIELD)
    player = _cstring(data, _OFF_PLAYER, _PLAYER_FIELD)
    if randomizer is None or apworld is None or player is None:
        return None
    if not _dotted_version(apworld):
        return None
    return SlotBlock(randomizer, apworld, seed, player)


def room_seed_matches(rom_seed: int, slot_data: object) -> bool:
    """True when the room's slot_data seed is the seed embedded in the disc."""
    if not isinstance(slot_data, dict):
        return False
    seed = slot_data.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        return False
    return seed == rom_seed


def _cstring(data: bytes, offset: int, width: int) -> str | None:
    field = data[offset:offset + width]
    if b"\x00" not in field:
        return None
    raw = field.split(b"\x00", 1)[0]
    if not raw:
        return None
    if any(byte < 0x20 or byte == 0x7F for byte in raw):
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _dotted_version(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 3:
        return False
    return all(part and all("0" <= character <= "9" for character in part) for part in parts)
