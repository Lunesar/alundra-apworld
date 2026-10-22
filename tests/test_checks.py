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
    def test_lutas_house_is_present_and_rows_match_sources(self) -> None:
        expected = [
            (source.pretty_name, source.id, source.event_code)
            for source in GAME_DATA.sources
            if source.event_code is not None
        ]
        self.assertEqual(
            [(check.name, check.location_id, check.event_code) for check in LOCATION_CHECKS],
            expected,
        )
        lutas = GAME_DATA.source_by_id[1]
        self.assertEqual(lutas.pretty_name, "Inoa: Chest in Lutas's house (Secret Pass)")
        self.assertEqual(lutas.event_code, 0x0680)
        check = next(row for row in LOCATION_CHECKS if row.location_id == lutas.id)
        self.assertEqual((check.name, check.event_code), (lutas.pretty_name, 0x0680))
        # 0x0680 is bit 0 of flag byte 0xD0, MainRAM 0x1DD404.
        self.assertEqual(check.byte_index, 0xD0)
        self.assertEqual(check.mask, 0x01)
        window = flag_read()
        self.assertIsNotNone(window)
        assert window is not None
        origin, length = window
        self.assertLessEqual(origin, EVENT_FLAGS + check.byte_index)
        self.assertGreater(origin + length, EVENT_FLAGS + check.byte_index)

    def test_unique_shop_slots_are_watched(self) -> None:
        # FlagOn bit set by the purchase script. See docs/client_memory.md.
        expected = {
            266: 0x03F1,  # Lurvy's Shop: Item #5 (Leather Armor)
            267: 0x0454,  # Lurvy's Shop: Item #5 replacement when bought once (Life Vessel)
            269: 0x0455,  # Lurvy's Shop: repair Broken Armor (Ancient Armor)
            273: 0x02C4,  # Naomi's Shop: Item #4 (Life Vessel)
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        leather = by_id[266]
        # 0x03F1 is bit 1 of flag byte 0x7E, MainRAM 0x1DD3B2.
        self.assertEqual(leather.byte_index, 0x7E)
        self.assertEqual(leather.mask, 0x02)
        # Restocking shelves set no bit in the event-flag array.
        for source_id in (262, 263, 264, 265, 268, 270, 271, 272):
            self.assertIsNone(GAME_DATA.source_by_id[source_id].event_code)
            self.assertNotIn(source_id, by_id)
        codes = [check.event_code for check in LOCATION_CHECKS]
        self.assertEqual(len(codes), len(set(codes)))

    def test_merrick_trades_are_watched(self) -> None:
        # FlagOn bit set by the spawned trade script on map 134.
        # See docs/client_memory.md.
        expected = {
            254: 0x0599,  # 15 Gilded Falcons (Life Vessel), C[4]
            255: 0x059A,  # 20 Gilded Falcons (Olga's Ring), C[5]
            256: 0x059B,  # 25 Gilded Falcons (Life Vessel), C[9]
            257: 0x059C,  # 30 Gilded Falcons (Silver Armlet), C[6]
            258: 0x059D,  # 35 Gilded Falcons (Life Vessel), C[10]
            259: 0x059E,  # 40 Gilded Falcons (Recovery Ring), C[7]
            260: 0x059F,  # 45 Gilded Falcons (Life Vessel), C[11]
            261: 0x05A0,  # 50 Gilded Falcons (Spirit Wand), C[8]
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        first = by_id[254]
        # 0x0599 is bit 1 of flag byte 0xB3, MainRAM 0x1DD3E7.
        self.assertEqual(first.byte_index, 0xB3)
        self.assertEqual(first.mask, 0x02)
        codes = [check.event_code for check in LOCATION_CHECKS]
        self.assertEqual(len(codes), len(set(codes)))

    def test_overworld_c4_patched_chests_are_watched(self) -> None:
        # PatchFixMapInconsistencies copies these map 12 flags onto the map 407
        # records. New game loads map 407, and the chest routine sets that flag.
        expected = {
            33: 0x06D6,  # Overworld C4: Left coast chest (Magic Elixyr)
            36: 0x06D7,  # Overworld C4: Chest inside forest near the right border
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        coast = by_id[33]
        # 0x06D6 is bit 6 of flag byte 0xDA, MainRAM 0x1DD40E.
        self.assertEqual(coast.byte_index, 0xDA)
        self.assertEqual(coast.mask, 0x40)
        forest = by_id[36]
        # 0x06D7 is bit 7 of the same byte.
        self.assertEqual(forest.byte_index, 0xDA)
        self.assertEqual(forest.mask, 0x80)
        codes = [check.event_code for check in LOCATION_CHECKS]
        self.assertEqual(len(codes), len(set(codes)))

    def test_open_chest_is_the_low_bit(self) -> None:
        lutas = next(row for row in LOCATION_CHECKS if row.location_id == 1)
        origin = lutas.byte_index
        one = (lutas,)
        self.assertEqual(checked_locations(b"\x00", origin, one), [])
        self.assertEqual(checked_locations(b"\xfe", origin, one), [])
        self.assertEqual(checked_locations(b"\x01", origin, one), [lutas.location_id])
        self.assertEqual(checked_locations(b"\x81", origin, one), [lutas.location_id])
        self.assertEqual(checked_locations(b"", origin, one), [])

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
