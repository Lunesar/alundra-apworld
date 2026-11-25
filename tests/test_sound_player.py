# Disc-callback warning. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import struct
import sys
import types
import unittest
from pathlib import Path

_world = Path(__file__).resolve().parents[1]
_loader = importlib.machinery.SourceFileLoader("alundra", str(_world / "__init__.py"))
_package = types.ModuleType("alundra")
_package.__path__ = [str(_world)]
_package.__package__ = "alundra"
_package.__loader__ = _loader
_package.__spec__ = importlib.machinery.ModuleSpec("alundra", _loader, is_package=True)
_package.__spec__.submodule_search_locations = [str(_world)]
sys.modules["alundra"] = _package

from alundra.sound_player import (
    FILE_READ_CALLBACK,
    MUSIC_CALLBACK_0,
    MUSIC_CALLBACK_1,
    REPEAT_SECONDS,
    CLEARED_MESSAGE,
    SCREEN_MESSAGE,
    next_sound_warning,
    sound_log_line,
    sound_player_healthy,
    sound_player_stuck,
)


def _pair(first: int, second: int) -> bytes:
    return struct.pack("<II", first, second)


_FILE = _pair(0, FILE_READ_CALLBACK)
_MUSIC = _pair(MUSIC_CALLBACK_0, MUSIC_CALLBACK_1)


class SoundPlayerTests(unittest.TestCase):
    def test_stuck_pair_is_both_copies_of_the_file_callback(self) -> None:
        self.assertTrue(sound_player_stuck(_FILE, _FILE))
        self.assertFalse(sound_player_healthy(_FILE))

    def test_normal_read_keeps_the_music_pair_saved(self) -> None:
        self.assertFalse(sound_player_stuck(_FILE, _MUSIC))
        self.assertFalse(sound_player_healthy(_FILE))

    def test_idle_music_pair_is_healthy(self) -> None:
        self.assertFalse(sound_player_stuck(_MUSIC, _MUSIC))
        self.assertTrue(sound_player_healthy(_MUSIC))

    def test_short_read_is_not_stuck(self) -> None:
        self.assertFalse(sound_player_stuck(_FILE[:4], _FILE))
        self.assertFalse(sound_player_healthy(_MUSIC[:4]))

    def test_warning_repeats_every_minute_and_clears_on_the_music_pair(self) -> None:
        warn, shown = next_sound_warning(True, False, None, 1000.0)
        self.assertTrue(warn)
        self.assertEqual(shown, 1000.0)
        warn, shown = next_sound_warning(True, False, shown, 1000.0 + REPEAT_SECONDS - 0.1)
        self.assertFalse(warn)
        self.assertEqual(shown, 1000.0)
        # A normal read between warnings does not start the clock over.
        warn, shown = next_sound_warning(False, False, shown, 1030.0)
        self.assertFalse(warn)
        self.assertEqual(shown, 1000.0)
        warn, shown = next_sound_warning(True, False, shown, 1000.0 + REPEAT_SECONDS)
        self.assertTrue(warn)
        self.assertEqual(shown, 1060.0)
        warn, shown = next_sound_warning(False, True, shown, 1100.0)
        self.assertFalse(warn)
        self.assertIsNone(shown)
        warn, shown = next_sound_warning(True, False, shown, 1100.0)
        self.assertTrue(warn)
        self.assertEqual(shown, 1100.0)

    def test_healthy_before_any_warning_stays_quiet(self) -> None:
        warn, shown = next_sound_warning(False, True, None, 50.0)
        self.assertFalse(warn)
        self.assertIsNone(shown)

    def test_log_line_names_the_map_and_both_pairs(self) -> None:
        line = sound_log_line(144, _FILE, _FILE)
        self.assertIn("map 144", line)
        self.assertIn("Live 00000000 8008C8B8, saved 00000000 8008C8B8", line)
        self.assertIn(
            "Save to the memory card, then load it from the title screen to prevent a game freeze.",
            line,
        )
        self.assertNotIn(SCREEN_MESSAGE, line)
        self.assertNotIn("8008C8B8", SCREEN_MESSAGE)
        self.assertEqual(
            CLEARED_MESSAGE,
            "Sound player is no longer stuck.",
        )
