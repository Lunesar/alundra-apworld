# Location-check flag decoding. Runs without an Archipelago install.

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_world = Path(__file__).resolve().parents[1]
_package = types.ModuleType("alundra")
_package.__path__ = [str(_world)]
_package.__package__ = "alundra"
sys.modules["alundra"] = _package

from alundra.checks import (
    EVENT_FLAGS,
    LOCATION_CHECKS,
    LocationCheck,
    checked_locations,
    flag_read,
    names_for,
)
from alundra.data import GAME_DATA


class CheckTests(unittest.TestCase):
    def test_lutas_house_is_the_only_wired_check(self) -> None:
        source = GAME_DATA.source_by_pretty_name["Inoa: Chest in Lutas's house (Secret Pass)"]
        self.assertEqual(
            [(check.name, check.location_id, check.event_code) for check in LOCATION_CHECKS],
            [(source.pretty_name, source.id, 0x0680)],
        )
        check = LOCATION_CHECKS[0]
        # 0x0680 is bit 0 of flag byte 0xD0, MainRAM 0x1DD404.
        self.assertEqual(check.byte_index, 0xD0)
        self.assertEqual(check.mask, 0x01)
        self.assertEqual(flag_read(), (EVENT_FLAGS + 0xD0, 1))

    def test_open_chest_is_the_low_bit(self) -> None:
        origin = LOCATION_CHECKS[0].byte_index
        self.assertEqual(checked_locations(b"\x00", origin), [])
        self.assertEqual(checked_locations(b"\xfe", origin), [])
        self.assertEqual(checked_locations(b"\x01", origin), [LOCATION_CHECKS[0].location_id])
        self.assertEqual(checked_locations(b"\x81", origin), [LOCATION_CHECKS[0].location_id])
        self.assertEqual(checked_locations(b"", origin), [])

    def test_a_second_row_shares_the_read(self) -> None:
        checks = (
            LocationCheck("near", 1, 0x0680),
            LocationCheck("next byte", 2, 0x0688),
        )
        self.assertEqual(flag_read(checks), (EVENT_FLAGS + 0xD0, 2))
        self.assertEqual(checked_locations(b"\x01\x00", 0xD0, checks), [1])
        self.assertEqual(checked_locations(b"\x00\x01", 0xD0, checks), [2])
        self.assertEqual(checked_locations(b"\x01\x01", 0xD0, checks), [1, 2])
        self.assertEqual(names_for({2, 1}, checks), ["near", "next byte"])

    def test_event_code_outside_the_array_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LocationCheck("too far", 9, 2048)
