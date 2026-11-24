# Speaker hint roll. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import random
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

from alundra.data import GAME_DATA, REQUIRED_STARTING_ITEMS
from alundra.hints import (
    HintLocation,
    SpeakerHint,
    _area_hint,
    encode_speaker_hints,
    _minimal_blocking_checks,
    hintable_item_names,
    offworld_hint_copies,
    roll_hints,
)
from alundra.hints import _Walks
from alundra.logic import LogicError, LogicSettings, build_graph

_BOMB_CHEST = 4
_LARS_CHEST = 195
_NEARBY_GOAL = "naomi_shop"


class SpeakerHintSlotTests(unittest.TestCase):
    def test_slot_rows_omit_the_sentence(self) -> None:
        local = SpeakerHint("jess", "Bomb can be found near Sanctuary", HintLocation(4))
        away = SpeakerHint("lars_crypt", "Ruby Crest can be found in an unknown place", HintLocation(4242, 2))
        self.assertEqual(
            encode_speaker_hints((local, away)),
            [
                {"speaker": "jess", "location": 4},
                {"speaker": "lars_crypt", "location": 4242, "player": 2},
            ],
        )
        self.assertEqual(encode_speaker_hints(()), [])


class HintDataTests(unittest.TestCase):
    def test_speakers_and_region_phrases_load(self) -> None:
        speakers = {speaker.id: speaker for speaker in GAME_DATA.hint_sources}
        self.assertEqual(len(speakers), 12)
        self.assertEqual(speakers["jess"].node_id, "inoa")
        self.assertEqual(speakers["jess"].name, "Jess (Inoa)")
        hinted = [region for region in GAME_DATA.regions if region.can_be_hinted_as_required]
        self.assertEqual(len(hinted), 14)
        by_name = {region.name: region for region in GAME_DATA.regions}
        self.assertEqual(by_name["Lars Crypt"].hint_phrase, "Lars Crypt")
        self.assertEqual(by_name["Overworld C2 (Sanctuary sector)"].hint_phrase, "near Sanctuary")
        self.assertFalse(by_name["Inoa"].can_be_hinted_as_required)

    def test_item_list_follows_the_boots_option(self) -> None:
        joined = hintable_item_names(True, False)
        split = hintable_item_names(True, True)
        plain = hintable_item_names(False, True)
        self.assertIn("Boots upgrade", joined)
        self.assertNotIn("Long Boots", joined)
        self.assertIn("Flail upgrade", joined)
        self.assertIn("Long Boots", split)
        self.assertIn("Merman Boots", split)
        self.assertNotIn("Boots upgrade", split)
        self.assertIn("Iron Flail", plain)
        self.assertNotIn("Flail upgrade", plain)


class MinimalSetTests(unittest.TestCase):
    def test_two_of_three_keeps_one_pair(self) -> None:
        def reachable(removed: frozenset[int]) -> bool:
            return len(removed) < 2

        self.assertEqual(_minimal_blocking_checks([1, 2, 3], reachable), (2, 3))

    def test_a_single_required_check_stays_out(self) -> None:
        def reachable(removed: frozenset[int]) -> bool:
            return 5 not in removed

        self.assertEqual(_minimal_blocking_checks([5, 6], reachable), (5,))

    def test_an_open_goal_has_no_blocking_set(self) -> None:
        self.assertEqual(_minimal_blocking_checks([1, 2], lambda _removed: True), ())


class HintRollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = build_graph(GAME_DATA, LogicSettings())

    def test_a_local_item_names_that_checks_area(self) -> None:
        hints = roll_hints(
            self.graph, GAME_DATA, random.Random(1), {_BOMB_CHEST: "Bomb"},
            starting_inventory=REQUIRED_STARTING_ITEMS,
            region_hint_limit=0,
        )
        self.assertEqual(len(hints), 1)
        hint = hints[0]
        self.assertEqual(hint.text, "Bomb can be found near Sanctuary")
        self.assertEqual(hint.check, HintLocation(_BOMB_CHEST))

    def test_an_item_that_left_names_the_other_world(self) -> None:
        away = HintLocation(location=4242, player=2)
        hints = roll_hints(
            self.graph, GAME_DATA, random.Random(1), {},
            starting_inventory=REQUIRED_STARTING_ITEMS,
            offworld={"Ruby Crest": (away,)},
            region_hint_limit=0,
        )
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].text, "Ruby Crest can be found in an unknown place")
        self.assertEqual(hints[0].check, away)

    def test_starting_inventory_is_not_hinted(self) -> None:
        away = HintLocation(location=4242, player=2)
        hints = roll_hints(
            self.graph, GAME_DATA, random.Random(1), {_BOMB_CHEST: "Bomb"},
            starting_inventory=(*REQUIRED_STARTING_ITEMS, "Bomb"),
            offworld={"Ruby Crest": (away,)},
            region_hint_limit=0,
        )
        self.assertEqual(hints[0].text, "Ruby Crest can be found in an unknown place")
        self.assertNotIn("Bomb", hints[0].text)

    def test_a_barren_area_registers_one_check_there(self) -> None:
        first = roll_hints(
            self.graph, GAME_DATA, random.Random(3), {},
            starting_inventory=REQUIRED_STARTING_ITEMS,
            goal=_NEARBY_GOAL,
        )
        again = roll_hints(
            self.graph, GAME_DATA, random.Random(3), {},
            starting_inventory=REQUIRED_STARTING_ITEMS,
            goal=_NEARBY_GOAL,
        )
        self.assertEqual(first, again)
        self.assertGreaterEqual(len(first), 1)
        self.assertLessEqual(len(first), 5)
        phrases = {region.hint_phrase: region for region in GAME_DATA.regions}
        for hint in first:
            self.assertTrue(hint.text.startswith("nothing of interest can be found "))
            phrase = hint.text.removeprefix("nothing of interest can be found ")
            region = phrases[phrase]
            source = GAME_DATA.source_by_id[hint.check.location]
            self.assertIn(source.node_id, region.node_ids)
            self.assertIsNone(hint.check.player)

    def test_remote_progression_makes_the_area_useful(self) -> None:
        region = next(entry for entry in GAME_DATA.regions if entry.name == "Lars Crypt")
        walks = _Walks(self.graph, GAME_DATA, {}, REQUIRED_STARTING_ITEMS)
        hint = _area_hint(
            "jess", "inoa", [region], walks, GAME_DATA,
            {source.id for source in GAME_DATA.sources},
            (_LARS_CHEST,), _NEARBY_GOAL, random.Random(0),
        )
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint.text, "something useful lies Lars Crypt")
        self.assertEqual(hint.check, HintLocation(_LARS_CHEST))

    def test_offworld_copies_are_grouped_and_ordered(self) -> None:
        grouped = offworld_hint_copies([
            ("Ruby Crest", 50, 3),
            ("Ruby Crest", 10, 2),
            ("Bomb", 9, 2),
            ("Ruby Crest", 4, 2),
        ])
        self.assertEqual(
            grouped["Ruby Crest"],
            (HintLocation(4, 2), HintLocation(10, 2), HintLocation(50, 3)),
        )
        self.assertEqual(grouped["Bomb"], (HintLocation(9, 2),))

    def test_an_offworld_copy_needs_a_slot(self) -> None:
        with self.assertRaises(LogicError):
            offworld_hint_copies([("Bomb", 4, True)])

    def test_a_source_cannot_be_local_and_remote(self) -> None:
        with self.assertRaises(LogicError):
            roll_hints(
                self.graph, GAME_DATA, random.Random(0), {_LARS_CHEST: "Herbs"},
                remote_progression=(_LARS_CHEST,),
            )


if __name__ == "__main__":
    unittest.main()
