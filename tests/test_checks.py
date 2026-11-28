# Location-check flag decoding. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import sys
import types
import unittest
from pathlib import Path

# importlib.resources.files reads the package spec. The loader is not executed.
_world = Path(__file__).resolve().parents[1]
_loader = importlib.machinery.SourceFileLoader("alundra", str(_world / "__init__.py"))
_package = types.ModuleType("alundra")
_package.__path__ = [str(_world)]
_package.__package__ = "alundra"
_package.__loader__ = _loader
_package.__spec__ = importlib.machinery.ModuleSpec("alundra", _loader, is_package=True)
_package.__spec__.submodule_search_locations = [str(_world)]
sys.modules["alundra"] = _package

from alundra.checks import (
    CASINO_SIGNS,
    EVENT_FLAGS,
    GOAL_ENDING,
    GOAL_PHASE,
    LOCATION_CHECKS,
    MAP_LURVY_SHOP,
    MAP_MERRICK_SHOP,
    MAP_NAOMI_SHOP,
    SHOP_CHECKS,
    SHOP_HINT_ALL,
    SHOP_HINT_NEXT,
    CasinoHintPlan,
    LocationCheck,
    casino_hints_outstanding,
    checked_locations,
    flag_read,
    game_beaten,
    LURVY_SECRET,
    MAP_JESS_HOUSE,
    SPEAKER_LINE_FLAGS,
    WATCHED_LOCATION_IDS,
    jess_talk_step,
    lurvy_repair_hint_locations,
    lurvy_repair_hints_enabled,
    names_for,
    pending_casino_hints,
    pending_jess_hint,
    pending_speaker_hints,
    shop_hint_locations,
    speaker_hints_outstanding,
)
from alundra.data import GAME_DATA, LOCATION_NAME_TO_ID
from alundra.receive import REQUESTED_MAP


class CheckTests(unittest.TestCase):
    def test_lutas_house_is_present_and_rows_match_sources(self) -> None:
        expected = [
            (source.pretty_name, source.id, source.event_code)
            for source in GAME_DATA.sources
            if source.event_code is not None and not source.forbid_precious
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
        self._assert_shared_codes()

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
        self._assert_shared_codes()

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
        self._assert_shared_codes()

    def test_king_snow_and_casino_second_rewards_are_watched(self) -> None:
        # FlagOn in the give script. King Snow sets the bit after 0x82.
        # Each casino second reward sets its bit before 0x82.
        expected = {
            55: 0x06FB,  # King Snow, map 7 B[10]
            57: 0x061C,  # Wheel of Fortune second reward, map 474 B[10]
            59: 0x0616,  # Hit Your Mark second reward, map 473 B[9]
            61: 0x0622,  # Slime Smash second reward, map 472 B[10]
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        snow = by_id[55]
        # 0x06FB is bit 3 of flag byte 0xDF, MainRAM 0x1DD413.
        self.assertEqual(snow.byte_index, 0xDF)
        self.assertEqual(snow.mask, 0x08)
        wheel = by_id[57]
        # 0x061C is bit 4 of flag byte 0xC3, MainRAM 0x1DD3F7.
        self.assertEqual(wheel.byte_index, 0xC3)
        self.assertEqual(wheel.mask, 0x10)
        self._assert_shared_codes()

    def test_jess_blue_chest_reports_both_locations(self) -> None:
        # Map 260 C[8] gives both items, then sets 0x0046 once.
        # Both sources store that code, so one bit reports both locations.
        expected = {
            2: 0x0046,  # Jess's Letter, 0x82 at 0x3AEAB90
            3: 0x0046,  # Broken Armor, 0x82 at 0x3AEABD1
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        letter = by_id[2]
        # 0x0046 is bit 6 of flag byte 0x08, MainRAM 0x1DD33C.
        self.assertEqual(letter.byte_index, 0x08)
        self.assertEqual(letter.mask, 0x40)
        armor = by_id[3]
        self.assertEqual(armor.byte_index, letter.byte_index)
        self.assertEqual(armor.mask, letter.mask)
        origin = letter.byte_index
        both = (letter, armor)
        self.assertEqual(checked_locations(b"\x00", origin, both), [])
        self.assertEqual(checked_locations(b"\x40", origin, both), [2, 3])
        self.assertEqual(checked_locations(b"\xbf", origin, both), [])
        self._assert_shared_codes()

    def test_aqua_cape_shares_the_topaz_bit(self) -> None:
        # Map 17 B[20] gives the Topaz, sets 0x0510, then gives the cape
        # after text 163. Map 439 sets the same bit. Both sources store it.
        expected = {
            247: 0x0510,  # Topaz Crest, 0x82 at 0x54791C
            248: 0x0510,  # Aqua Cape, 0x82 at 0x547935
        }
        by_id = {check.location_id: check for check in LOCATION_CHECKS}
        for source_id, code in expected.items():
            source = GAME_DATA.source_by_id[source_id]
            self.assertEqual(source.event_code, code)
            self.assertEqual(by_id[source_id].event_code, code)
            self.assertEqual(by_id[source_id].name, source.pretty_name)
        topaz = by_id[247]
        # 0x0510 is bit 0 of flag byte 0xA2, MainRAM 0x1DD3D6.
        self.assertEqual(topaz.byte_index, 0xA2)
        self.assertEqual(topaz.mask, 0x01)
        cape = by_id[248]
        self.assertEqual(cape.byte_index, topaz.byte_index)
        self.assertEqual(cape.mask, topaz.mask)
        origin = topaz.byte_index
        both = (topaz, cape)
        self.assertEqual(checked_locations(b"\x00", origin, both), [])
        self.assertEqual(checked_locations(b"\x01", origin, both), [247, 248])
        self.assertEqual(checked_locations(b"\xfe", origin, both), [])
        self._assert_shared_codes()

    def test_diamond_crest_is_watched(self) -> None:
        # Map 432 B[1] gives the crest at 0x5D73781. Map 321 B[1] sets
        # 0x03D0 at 0x477A804 after the fight, then warps back.
        source = GAME_DATA.source_by_id[253]
        self.assertEqual(source.event_code, 0x03D0)
        crest = next(row for row in LOCATION_CHECKS if row.location_id == 253)
        self.assertEqual(crest.event_code, 0x03D0)
        self.assertEqual(crest.name, source.pretty_name)
        # 0x03D0 is bit 0 of flag byte 0x7A, MainRAM 0x1DD3AE.
        self.assertEqual(crest.byte_index, 0x7A)
        self.assertEqual(crest.mask, 0x01)
        origin = crest.byte_index
        one = (crest,)
        self.assertEqual(checked_locations(b"\x00", origin, one), [])
        self.assertEqual(checked_locations(b"\x01", origin, one), [253])
        self.assertEqual(checked_locations(b"\xfe", origin, one), [])
        self._assert_shared_codes()

    def _assert_shared_codes(self) -> None:
        counts: dict[int, int] = {}
        for check in LOCATION_CHECKS:
            counts[check.event_code] = counts.get(check.event_code, 0) + 1
        shared = {code: count for code, count in counts.items() if count != 1}
        self.assertEqual(shared, {0x0046: 2, 0x0510: 2})

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

    def test_forbid_precious_sources_are_not_watched(self) -> None:
        watched = {check.location_id for check in LOCATION_CHECKS}
        precious = [source for source in GAME_DATA.sources if source.forbid_precious]
        self.assertTrue(precious)
        for source in precious:
            self.assertNotIn(source.id, watched, source.pretty_name)
            self.assertNotIn(source.pretty_name, LOCATION_NAME_TO_ID)
        # The pond stays open, so chests 139-145 are watched. The reward flag
        # is 0x03B8.
        for source_id in range(139, 146):
            source = GAME_DATA.source_by_id[source_id]
            self.assertFalse(source.forbid_precious, source.pretty_name)
            self.assertIsNotNone(source.event_code, source.pretty_name)
            self.assertIn(source.id, watched, source.pretty_name)
        self.assertEqual(GAME_DATA.source_by_id[145].event_code, 0x03B8)
        table = GAME_DATA.source_by_id[129]
        self.assertFalse(table.forbid_precious, table.pretty_name)
        self.assertEqual(table.event_code, 0x03B9)
        self.assertIn(table.id, watched, table.pretty_name)

    def test_game_beaten_is_the_ending_word(self) -> None:
        # The phase word is the u32 immediately before the requested map id.
        self.assertEqual(GOAL_PHASE, REQUESTED_MAP - 4)
        self.assertEqual(GOAL_ENDING, 9)
        self.assertTrue(game_beaten((9).to_bytes(4, "little")))
        for value in (0, 8, 10, 11):
            self.assertFalse(game_beaten(value.to_bytes(4, "little")), value)
        self.assertFalse(game_beaten(b"\x09\x00\x00"))
        self.assertFalse(game_beaten(b""))
        self.assertFalse(game_beaten((9).to_bytes(4, "big")))


def _purchase_flags(bought: set[int]) -> bytes:
    size = max(check.byte_index for check in LOCATION_CHECKS) + 1
    buf = bytearray(size)
    by_id = {check.location_id: check for check in LOCATION_CHECKS}
    for location_id in bought:
        check = by_id[location_id]
        buf[check.byte_index] |= check.mask
    return bytes(buf)


class ShopHintTests(unittest.TestCase):
    def test_shop_tables_are_the_one_time_checks(self) -> None:
        self.assertEqual(
            [check.location_id for check in SHOP_CHECKS[MAP_LURVY_SHOP]],
            [266, 267],
        )
        self.assertEqual(
            [check.location_id for check in SHOP_CHECKS[MAP_NAOMI_SHOP]],
            [273],
        )
        self.assertEqual(
            [check.location_id for check in SHOP_CHECKS[MAP_MERRICK_SHOP]],
            [254, 255, 256, 257, 258, 259, 260, 261],
        )
        hinted = {check.location_id for checks in SHOP_CHECKS.values() for check in checks}
        # The repair waits on the chimney bit. Restocking shelves have no id.
        self.assertNotIn(269, hinted)
        for source_id in (262, 263, 264, 265, 268, 270, 271, 272):
            self.assertNotIn(source_id, hinted)

    def test_all_reports_every_remaining_check(self) -> None:
        clear = _purchase_flags(set())
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_ALL, clear, 0),
            [266, 267],
        )
        self.assertEqual(
            shop_hint_locations(MAP_NAOMI_SHOP, SHOP_HINT_ALL, clear, 0),
            [273],
        )
        self.assertEqual(
            shop_hint_locations(MAP_MERRICK_SHOP, SHOP_HINT_ALL, clear, 0),
            [254, 255, 256, 257, 258, 259, 260, 261],
        )
        self.assertEqual(shop_hint_locations(7, SHOP_HINT_ALL, clear, 0), [])
        # A missing slot value is the same as all.
        self.assertEqual(shop_hint_locations(MAP_LURVY_SHOP, None, clear, 0), [266, 267])

    def test_next_reports_the_offer(self) -> None:
        clear = _purchase_flags(set())
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_NEXT, clear, 0),
            [266],
        )
        bought_first = _purchase_flags({266})
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_NEXT, bought_first, 0),
            [267],
        )
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_ALL, bought_first, 0),
            [267],
        )
        both = _purchase_flags({266, 267})
        self.assertEqual(shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_NEXT, both, 0), [])
        self.assertEqual(shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_ALL, both, 0), [])
        # Naomi has one check, so the two modes match.
        self.assertEqual(
            shop_hint_locations(MAP_NAOMI_SHOP, SHOP_HINT_NEXT, clear, 0),
            [273],
        )
        first_trade = _purchase_flags({254})
        self.assertEqual(
            shop_hint_locations(MAP_MERRICK_SHOP, SHOP_HINT_NEXT, first_trade, 0),
            [255],
        )
        self.assertEqual(
            shop_hint_locations(MAP_MERRICK_SHOP, SHOP_HINT_ALL, first_trade, 0),
            [255, 256, 257, 258, 259, 260, 261],
        )

    def test_a_found_check_is_not_scouted(self) -> None:
        clear = _purchase_flags(set())
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_ALL, clear, 0, skip={266}),
            [267],
        )
        # The replacement is not on the counter while Item #5 is still the offer.
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_NEXT, clear, 0, skip={266}),
            [],
        )
        self.assertEqual(
            shop_hint_locations(MAP_MERRICK_SHOP, SHOP_HINT_ALL, clear, 0, skip={254, 261}),
            [255, 256, 257, 258, 259, 260],
        )

    def test_a_short_flag_read_sends_nothing(self) -> None:
        self.assertEqual(
            shop_hint_locations(MAP_LURVY_SHOP, SHOP_HINT_ALL, b"\x00", 0),
            [],
        )


def _with_bit(buf: bytes, event_code: int, on: bool) -> bytes:
    data = bytearray(buf)
    index = event_code >> 3
    mask = 1 << (event_code & 7)
    if on:
        data[index] |= mask
    else:
        data[index] &= ~mask & 0xFF
    return bytes(data)


class LurvyRepairHintTests(unittest.TestCase):
    def test_the_chimney_secret_hints_the_repair(self) -> None:
        clear = _purchase_flags(set())
        self.assertEqual(lurvy_repair_hint_locations(clear, 0), [])
        secret = _with_bit(clear, LURVY_SECRET, True)
        self.assertEqual(lurvy_repair_hint_locations(secret, 0), [269])
        handed = _purchase_flags({269})
        handed = _with_bit(handed, LURVY_SECRET, True)
        self.assertEqual(lurvy_repair_hint_locations(handed, 0), [])
        self.assertEqual(lurvy_repair_hint_locations(secret, 0, skip={269}), [])
        self.assertEqual(lurvy_repair_hint_locations(b"\x00", 0), [])

    def test_a_missing_option_gives_the_hint(self) -> None:
        self.assertTrue(lurvy_repair_hints_enabled({}))
        self.assertTrue(lurvy_repair_hints_enabled({"hint_lurvy_repair": True}))
        self.assertTrue(lurvy_repair_hints_enabled({"hint_lurvy_repair": 1}))
        self.assertFalse(lurvy_repair_hints_enabled({"hint_lurvy_repair": False}))
        self.assertFalse(lurvy_repair_hints_enabled({"hint_lurvy_repair": 0}))


class SpeakerHintSendTests(unittest.TestCase):
    def test_every_speaker_except_jess_has_a_line_bit(self) -> None:
        speakers = {source.id for source in GAME_DATA.hint_sources}
        self.assertEqual(set(SPEAKER_LINE_FLAGS) | {"jess"}, speakers)
        self.assertNotIn("jess", SPEAKER_LINE_FLAGS)

    def test_line_bits_are_inside_the_flag_read(self) -> None:
        read = flag_read()
        self.assertIsNotNone(read)
        assert read is not None
        origin, length = read
        start = origin - EVENT_FLAGS
        for speaker, code in SPEAKER_LINE_FLAGS.items():
            self.assertLess(code, 2048, speaker)
            index = (code >> 3) - start
            self.assertGreaterEqual(index, 0, speaker)
            self.assertLess(index, length, speaker)

    def test_a_heard_local_line_names_its_check(self) -> None:
        clear = _purchase_flags(set())
        rows = [{"speaker": "lars_crypt", "location": 4}]
        self.assertEqual(pending_speaker_hints(rows, clear, 0, {4}, set()).sends, ())
        heard = _with_bit(clear, SPEAKER_LINE_FLAGS["lars_crypt"], True)
        plan = pending_speaker_hints(rows, heard, 0, {4}, set())
        self.assertEqual([(send.speaker, send.location, send.player) for send in plan.sends], [("lars_crypt", 4, None)])
        self.assertEqual(plan.quiet, ())
        # The same connection does not send it again.
        again = pending_speaker_hints(rows, heard, 0, {4}, {"lars_crypt"})
        self.assertEqual(again.sends, ())
        self.assertEqual(again.quiet, ())

    def test_a_found_local_check_sends_nothing(self) -> None:
        heard = _with_bit(_purchase_flags(set()), SPEAKER_LINE_FLAGS["coal_mine"], True)
        rows = [{"speaker": "coal_mine", "location": 12}]
        plan = pending_speaker_hints(rows, heard, 0, set(), set())
        self.assertEqual(plan.sends, ())
        self.assertEqual(plan.quiet, ("coal_mine",))

    def test_an_unknown_place_is_not_gated_on_this_slot(self) -> None:
        heard = _with_bit(_purchase_flags(set()), SPEAKER_LINE_FLAGS["nava_keep"], True)
        rows = [{"speaker": "nava_keep", "location": 4242, "player": 2}]
        plan = pending_speaker_hints(rows, heard, 0, set(), set())
        self.assertEqual(
            [(send.speaker, send.location, send.player) for send in plan.sends],
            [("nava_keep", 4242, 2)],
        )
        self.assertEqual(plan.quiet, ())

    def test_jess_and_bad_rows_are_skipped(self) -> None:
        heard = _with_bit(_purchase_flags(set()), SPEAKER_LINE_FLAGS["lars_crypt"], True)
        rows = [
            {"speaker": "jess", "location": 4},
            {"speaker": "nope", "location": 4},
            {"speaker": "lars_crypt", "location": True},
            {"speaker": "lars_crypt", "location": 4, "player": 0},
            {"speaker": "lars_crypt", "location": 4, "player": True},
            "lars_crypt",
            {"speaker": "lars_crypt", "location": 4},
            {"speaker": "lars_crypt", "location": 9},
        ]
        plan = pending_speaker_hints(rows, heard, 0, {4, 9}, set())
        self.assertEqual([send.location for send in plan.sends], [4])
        self.assertFalse(speaker_hints_outstanding([{"speaker": "jess", "location": 4}], set()))
        self.assertFalse(speaker_hints_outstanding(None, set()))
        self.assertTrue(speaker_hints_outstanding(rows, set()))
        self.assertFalse(speaker_hints_outstanding(rows, {"lars_crypt"}))

    def test_a_short_flag_read_does_not_forget_the_line(self) -> None:
        rows = [{"speaker": "coastal_cave", "location": 8}]
        plan = pending_speaker_hints(rows, b"\x00", 0, {8}, set())
        self.assertEqual(plan.sends, ())
        self.assertEqual(plan.quiet, ())
        self.assertTrue(speaker_hints_outstanding(rows, set()))


class JessTalkTests(unittest.TestCase):
    def test_an_open_jess_row_names_its_check(self) -> None:
        self.assertEqual(MAP_JESS_HOUSE, 260)
        rows = [{"speaker": "jess", "location": 4}]
        plan = pending_jess_hint(rows, {4}, set())
        self.assertEqual(
            [(send.speaker, send.location, send.player) for send in plan.sends],
            [("jess", 4, None)],
        )
        self.assertEqual(plan.quiet, ())
        # His row still does not keep the flag read alive.
        self.assertFalse(speaker_hints_outstanding(rows, set()))
        again = pending_jess_hint(rows, {4}, {"jess"})
        self.assertEqual(again.sends, ())
        self.assertEqual(again.quiet, ())

    def test_a_found_local_check_is_quiet(self) -> None:
        plan = pending_jess_hint([{"speaker": "jess", "location": 4}], set(), set())
        self.assertEqual(plan.sends, ())
        self.assertEqual(plan.quiet, ("jess",))

    def test_an_unknown_place_is_not_gated_on_this_slot(self) -> None:
        plan = pending_jess_hint(
            [{"speaker": "jess", "location": 4242, "player": 2}],
            set(),
            set(),
        )
        self.assertEqual(
            [(send.speaker, send.location, send.player) for send in plan.sends],
            [("jess", 4242, 2)],
        )
        self.assertEqual(plan.quiet, ())

    def test_bad_rows_are_skipped_and_the_first_good_row_wins(self) -> None:
        rows = [
            {"speaker": "jess", "location": True},
            {"speaker": "jess", "location": -1},
            {"speaker": "jess", "player": 2},
            {"speaker": "lars_crypt", "location": 4},
            {"speaker": "jess", "location": 4, "player": 0},
            {"speaker": "jess", "location": 4, "player": True},
            {"speaker": "jess", "location": 7},
            {"speaker": "jess", "location": 8},
        ]
        plan = pending_jess_hint(rows, {7, 8}, set())
        self.assertEqual([send.location for send in plan.sends], [7])
        self.assertEqual(pending_jess_hint(None, {7}, set()).sends, ())
        self.assertEqual(pending_jess_hint([{"speaker": "jess", "location": 4, "player": None}], {4}, set()).sends, ())

    def test_npc_text_in_his_house_sends_once_control_returns(self) -> None:
        latched, send = jess_talk_step(False, MAP_JESS_HOUSE, True, False)
        self.assertEqual((latched, send), (True, False))
        # The box stays up across watches.
        self.assertEqual(jess_talk_step(latched, MAP_JESS_HOUSE, True, False), (True, False))
        # An open box is not a send, even if a caller also says the watch is ready.
        self.assertEqual(jess_talk_step(latched, MAP_JESS_HOUSE, True, True), (True, False))
        self.assertEqual(jess_talk_step(latched, MAP_JESS_HOUSE, False, True), (False, True))

    def test_leaving_the_house_drops_the_talk(self) -> None:
        latched, send = jess_talk_step(False, MAP_JESS_HOUSE, True, False)
        self.assertFalse(send)
        # Map 242 is where the opened blue chest puts him, before control returns.
        self.assertEqual(jess_talk_step(latched, 242, False, True), (False, False))
        self.assertEqual(jess_talk_step(False, 242, True, False), (False, False))

    def test_the_menu_and_an_idle_visit_do_not_latch(self) -> None:
        # npc_text is the two NPC words. The save book is the menu word.
        self.assertEqual(jess_talk_step(False, MAP_JESS_HOUSE, False, True), (False, False))
        self.assertEqual(jess_talk_step(False, MAP_JESS_HOUSE, False, False), (False, False))
        # Armed, and the box has closed, but gameplay is not ready yet.
        self.assertEqual(jess_talk_step(True, MAP_JESS_HOUSE, False, False), (True, False))


# Chest id, then the second reward. These event codes are the prize flags.
# The sign bits are separate, so reading a sign does not report the chest.
_CASINO_PRIZES = {
    "slime_smash": ((60, 1569, "Riverside Casino: 'Slime Smash' chest"),
                    (61, 1570, "Riverside Casino: 'Slime Smash' second reward")),
    "hit_your_mark": ((58, 1557, "Riverside Casino: 'Hit Your Mark' chest"),
                      (59, 1558, "Riverside Casino: 'Hit Your Mark' second reward")),
    "wheel_of_fortune": ((56, 1563, "Riverside Casino: 'Wheel of Fortune' chest"),
                         (57, 1564, "Riverside Casino: 'Wheel of Fortune' second reward")),
}


def _casino_missing() -> set[int]:
    return {location_id for pairs in _CASINO_PRIZES.values() for location_id, _code, _name in pairs}


class CasinoSignHintTests(unittest.TestCase):
    def test_sign_bits_are_inside_the_flag_read(self) -> None:
        read = flag_read()
        self.assertIsNotNone(read)
        assert read is not None
        address, length = read
        start = address - EVENT_FLAGS
        buf = _purchase_flags(set())
        for sign in CASINO_SIGNS:
            self.assertLess(sign.event_code, 2048, sign.name)
            index = (sign.event_code >> 3) - start
            self.assertGreaterEqual(index, 0, sign.name)
            self.assertLess(index, length, sign.name)
            buf = _with_bit(buf, sign.event_code, True)
        # The client passes this slice, not a buffer that starts at byte 0.
        window = buf[start:start + length]
        plan = pending_casino_hints(window, start, _casino_missing(), set())
        self.assertEqual(plan.locations, (60, 61, 58, 59, 56, 57))
        self.assertEqual(
            plan.signs,
            ("slime_smash", "hit_your_mark", "wheel_of_fortune"),
        )
        self.assertEqual(plan.quiet, ())

    def test_sign_codes_are_not_the_prize_flags(self) -> None:
        self.assertEqual([sign.name for sign in CASINO_SIGNS], list(_CASINO_PRIZES))
        sign_codes = {sign.event_code for sign in CASINO_SIGNS}
        self.assertEqual(sign_codes, {0x005A, 0x005B, 0x005C})
        # 0x0058 stays unused. The speaker bits stop at Nava, 0x0059.
        self.assertNotIn(0x0058, sign_codes)
        self.assertTrue(sign_codes.isdisjoint(SPEAKER_LINE_FLAGS.values()))
        watched = {check.event_code for check in LOCATION_CHECKS}
        self.assertTrue(sign_codes.isdisjoint(watched))
        self.assertNotIn(0x0058, watched)
        for sign in CASINO_SIGNS:
            self.assertEqual(
                sign.locations,
                tuple(location_id for location_id, _code, _name in _CASINO_PRIZES[sign.name]),
            )
            for location_id, event_code, name in _CASINO_PRIZES[sign.name]:
                source = GAME_DATA.source_by_id[location_id]
                self.assertEqual(source.name, name)
                self.assertEqual(source.event_code, event_code)
                self.assertNotEqual(source.event_code, sign.event_code)
                self.assertIn(location_id, WATCHED_LOCATION_IDS)
        # Setting only the sign bits does not report a prize.
        flags = _purchase_flags(set())
        for sign in CASINO_SIGNS:
            flags = _with_bit(flags, sign.event_code, True)
        self.assertEqual(checked_locations(flags, 0), [])

    def test_a_clear_sign_sends_nothing(self) -> None:
        missing = _casino_missing()
        plan = pending_casino_hints(_purchase_flags(set()), 0, missing, set())
        self.assertEqual(plan, CasinoHintPlan())
        self.assertTrue(casino_hints_outstanding(missing, set()))

    def test_a_read_sign_names_both_prizes(self) -> None:
        heard = _with_bit(_purchase_flags(set()), 0x005A, True)
        plan = pending_casino_hints(heard, 0, _casino_missing(), set())
        self.assertEqual(plan.locations, (60, 61))
        self.assertEqual(plan.signs, ("slime_smash",))
        self.assertEqual(plan.quiet, ())

    def test_a_found_prize_is_left_out(self) -> None:
        heard = _with_bit(_purchase_flags(set()), 0x005B, True)
        missing = _casino_missing() - {58}
        plan = pending_casino_hints(heard, 0, missing, set())
        self.assertEqual(plan.locations, (59,))
        self.assertEqual(plan.signs, ("hit_your_mark",))
        self.assertEqual(plan.quiet, ())
        self.assertTrue(casino_hints_outstanding(missing, set()))

    def test_a_sign_with_nothing_left_is_quiet(self) -> None:
        heard = _with_bit(_purchase_flags(set()), 0x005C, True)
        missing = _casino_missing() - {56, 57}
        plan = pending_casino_hints(heard, 0, missing, set())
        self.assertEqual(plan.locations, ())
        self.assertEqual(plan.quiet, ("wheel_of_fortune",))
        self.assertEqual(plan.signs, ())
        # The other two signs still have prizes to name.
        self.assertTrue(casino_hints_outstanding(missing, set()))
        self.assertFalse(
            casino_hints_outstanding(missing, {"slime_smash", "hit_your_mark"}),
        )

    def test_a_handled_sign_sends_nothing(self) -> None:
        heard = _with_bit(_purchase_flags(set()), 0x005A, True)
        missing = _casino_missing()
        plan = pending_casino_hints(heard, 0, missing, {"slime_smash"})
        self.assertEqual(plan, CasinoHintPlan())
        self.assertTrue(casino_hints_outstanding(missing, {"slime_smash"}))
        self.assertFalse(casino_hints_outstanding(missing, {sign.name for sign in CASINO_SIGNS}))
        self.assertFalse(casino_hints_outstanding(set(), set()))

    def test_a_short_flag_read_does_not_forget_the_sign(self) -> None:
        missing = _casino_missing()
        plan = pending_casino_hints(b"\x00", 0, missing, set())
        self.assertEqual(plan, CasinoHintPlan())
        self.assertTrue(casino_hints_outstanding(missing, set()))

    def test_two_signs_share_one_list(self) -> None:
        # Hit Your Mark stays clear, so its pair is left out. Order is the
        # sign order: chest, then second reward.
        flags = _with_bit(_purchase_flags(set()), 0x005A, True)
        flags = _with_bit(flags, 0x005C, True)
        plan = pending_casino_hints(flags, 0, _casino_missing(), set())
        self.assertEqual(plan.locations, (60, 61, 56, 57))
        self.assertEqual(plan.signs, ("slime_smash", "wheel_of_fortune"))
        self.assertEqual(plan.quiet, ())
