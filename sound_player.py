"""Disc-callback watch for the BizHawk client.

A normal read stores the music pair, installs the file-read callback, and
copies the music pair back when the read finishes. The stuck state is both
pairs being the file-read callback, so that copy puts the file-read callback
back. A read in progress does not match, and neither does an idle music pair.
"""

from __future__ import annotations

import struct

# Live libcd callbacks, MainRAM. KSEG0 0x800CA13C and 0x800CA140.
LIVE_CALLBACKS = 0xCA13C
# Pair a read restores, MainRAM. KSEG0 0x800CA478 and 0x800CA47C.
SAVED_CALLBACKS = 0xCA478
FILE_READ_CALLBACK = 0x8008C8B8
MUSIC_CALLBACK_0 = 0x80089F20
MUSIC_CALLBACK_1 = 0x80089F48
# Wall time between repeats while the stuck pair holds.
REPEAT_SECONDS = 60.0

SCREEN_MESSAGE = "Sound player is stuck, fix with memory card load"
CLEARED_MESSAGE = "Sound player is no longer stuck."
# The client log keeps the map and both pairs. The on-screen line does not.
_LOG_INSTRUCTION = (
    "Save to the memory card, then load it from the title screen to prevent a game freeze."
)


def _pair(data: bytes) -> tuple[int, int] | None:
    if len(data) != 8:
        return None
    return struct.unpack("<II", data)


def sound_player_stuck(live: bytes, saved: bytes) -> bool:
    """True when a restore would install the file-read callback again."""
    return _pair(live) == (0, FILE_READ_CALLBACK) and _pair(saved) == (0, FILE_READ_CALLBACK)


def sound_player_healthy(live: bytes) -> bool:
    """True when the live slots are the music callbacks."""
    return _pair(live) == (MUSIC_CALLBACK_0, MUSIC_CALLBACK_1)


def next_sound_warning(
    stuck: bool,
    healthy: bool,
    announced_at: float | None,
    now: float,
) -> tuple[bool, float | None]:
    """Whether to show the warning, and when it was last shown.

    A healthy music pair clears the clock. Any other non-stuck read leaves the
    clock alone, so a normal disc read does not start a new warning.
    """
    if healthy:
        return False, None
    if not stuck:
        return False, announced_at
    if announced_at is None or now - announced_at >= REPEAT_SECONDS:
        return True, now
    return False, announced_at


def sound_log_line(map_id: int, live: bytes, saved: bytes) -> str:
    live0, live1 = struct.unpack("<II", live)
    saved0, saved1 = struct.unpack("<II", saved)
    return (
        f"Sound player is stuck on map {map_id}. "
        f"Live {live0:08X} {live1:08X}, saved {saved0:08X} {saved1:08X}. "
        f"{_LOG_INSTRUCTION}"
    )
