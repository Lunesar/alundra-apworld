# Restocking shop stock. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import random
import sys
import types
import unittest
from collections import Counter
from dataclasses import replace
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

from alundra.data import GAME_DATA, HEALING_ITEMS, LOCATION_NAME_TO_ID, restocking_shop_sources
from alundra.logic import (
    LogicError,
    LogicSettings,
    build_graph,
    build_item_pool,
    choose_restock_locks,
    resolved_restock_locks,
)
from alundra.placement import forbid_progression
from alundra.receive import _SOLD_WHEN_FULL


# Retail stock. Lurvy's five shelves are every healing item. Naomi sells three of them.
_RETAIL = {
    262: "Herbs",
    263: "Strength Tonic",
    264: "Strength Elixyr",
    265: "Magic Elixyr",
    268: "Wonder Essence",
    270: "Herbs",
    271: "Strength Tonic",
    272: "Magic Elixyr",
}
_LURVY = {262, 263, 264, 265, 268}


class RestockingShopTests(unittest.TestCase):
    def test_restocking_shelves_are_the_priced_unreported_sources(self) -> None:
        sources = restocking_shop_sources(GAME_DATA)
        self.assertEqual({source.id: source.vanilla_item for source in sources}, _RETAIL)
        for source in sources:
            self.assertTrue(source.forbid_precious, source.name)
            self.assertTrue(source.has_price, source.name)
            self.assertNotIn(source.pretty_name, LOCATION_NAME_TO_ID)
        # One-time shop checks stay locations. The repaired armor has no price.
        for source_id in (266, 267, 273):
            source = GAME_DATA.source_by_id[source_id]
            self.assertTrue(source.has_price, source.name)
            self.assertFalse(source.forbid_precious, source.name)
            self.assertIn(source.pretty_name, LOCATION_NAME_TO_ID)
        repaired = GAME_DATA.source_by_id[269]
        self.assertFalse(repaired.has_price)
        self.assertFalse(repaired.forbid_precious)
        self.assertIn(repaired.pretty_name, LOCATION_NAME_TO_ID)

    def test_vanilla_stock_sells_every_healing_item(self) -> None:
        # A full stack of one of these is sold for gilder. The shelves buy it back.
        self.assertEqual(set(HEALING_ITEMS), set(_SOLD_WHEN_FULL))
        sources = restocking_shop_sources(GAME_DATA)
        sold = {source.vanilla_item for source in sources}
        self.assertEqual(sold, set(HEALING_ITEMS))
        lurvy = {source.vanilla_item for source in sources if source.id in _LURVY}
        self.assertEqual(lurvy, set(HEALING_ITEMS))
        for source in sources:
            item = GAME_DATA.item_by_name[source.vanilla_item]
            self.assertGreater(item.gold_value, 0, source.vanilla_item)
            self.assertFalse(item.precious, source.vanilla_item)

    def test_vanilla_locks_retail_stock_and_drops_filler(self) -> None:
        settings = LogicSettings(restocking_shop_items="vanilla")
        placed = choose_restock_locks(GAME_DATA, settings, random.Random(0))
        self.assertEqual(
            placed,
            {GAME_DATA.source_by_id[source_id].pretty_name: item for source_id, item in _RETAIL.items()},
        )
        vanilla = Counter(build_item_pool(GAME_DATA, settings))
        shuffled = Counter(build_item_pool(
            GAME_DATA, LogicSettings(restocking_shop_items="randomized"),
        ))
        self.assertEqual(sum(shuffled.values()) - sum(vanilla.values()), len(_RETAIL))
        self.assertEqual(shuffled - vanilla, Counter({"Herbs": len(_RETAIL)}))
        for name in set(HEALING_ITEMS) - {"Herbs"}:
            self.assertEqual(vanilla[name], shuffled[name], name)
        self.assertEqual(choose_restock_locks(
            GAME_DATA, LogicSettings(restocking_shop_items="randomized"), random.Random(0),
        ), {})

    def test_full_variety_places_one_of_each_and_drops_five_herbs(self) -> None:
        self.assertEqual(LogicSettings().restocking_shop_items, "full_variety")
        base = LogicSettings()
        retail = {
            GAME_DATA.source_by_id[source_id].pretty_name: item
            for source_id, item in _RETAIL.items()
        }
        naomi = {
            source.pretty_name for source in restocking_shop_sources(GAME_DATA)
            if source.node_id == "naomi_shop"
        }
        seen: list[tuple[tuple[str, str], ...]] = []
        moved_to_naomi = False
        for seed in range(40):
            locks = choose_restock_locks(GAME_DATA, base, random.Random(seed))
            self.assertCountEqual(locks.values(), HEALING_ITEMS)
            self.assertEqual(len(restocking_shop_sources(GAME_DATA)) - len(locks), 3)
            seen.append(tuple(sorted(locks.items())))
            if any(locks.get(shelf) in {"Strength Elixyr", "Wonder Essence"} for shelf in naomi):
                moved_to_naomi = True
        self.assertGreater(len(set(seen)), 1)
        self.assertTrue(any(item != retail[shelf] for locks in seen for shelf, item in locks))
        self.assertTrue(moved_to_naomi)
        settings = replace(base, restock_locks=seen[0])
        guaranteed = Counter(build_item_pool(GAME_DATA, settings))
        shuffled = Counter(build_item_pool(
            GAME_DATA, LogicSettings(restocking_shop_items="randomized"),
        ))
        self.assertEqual(shuffled - guaranteed, Counter({"Herbs": len(HEALING_ITEMS)}))
        for name in set(HEALING_ITEMS) - {"Herbs"}:
            self.assertEqual(guaranteed[name], shuffled[name], name)
        with self.assertRaises(LogicError):
            build_item_pool(GAME_DATA, base)

    def test_restock_modes_skip_merrick(self) -> None:
        for mode in ("vanilla", "full_variety", "randomized"):
            locks = choose_restock_locks(
                GAME_DATA, LogicSettings(restocking_shop_items=mode), random.Random(3),
            )
            for pretty_name in locks:
                self.assertNotIn("Merrick", pretty_name)
                self.assertIn(pretty_name, {
                    GAME_DATA.source_by_id[source_id].pretty_name for source_id in _RETAIL
                })

    def test_fewer_crests_still_only_drops_herbs(self) -> None:
        vanilla = Counter(build_item_pool(
            GAME_DATA, LogicSettings(crest_count=0, restocking_shop_items="vanilla"),
        ))
        shuffled = Counter(build_item_pool(
            GAME_DATA, LogicSettings(crest_count=0, restocking_shop_items="randomized"),
        ))
        self.assertEqual(shuffled - vanilla, Counter({"Herbs": len(_RETAIL)}))
        self.assertEqual(sum(shuffled.values()) - sum(vanilla.values()), len(_RETAIL))

    def test_a_fixed_restocking_shelf_is_not_locked_twice(self) -> None:
        source = GAME_DATA.source_by_id[262]
        settings = LogicSettings(
            restocking_shop_items="vanilla",
            fixed_item_sources=(
                ("Merrick's Shop: Item traded for 50 Gilded Falcons (Spirit Wand)", "Spirit Wand"),
                (source.pretty_name, "Strength Tonic"),
            ),
        )
        placed = resolved_restock_locks(GAME_DATA, settings)
        self.assertNotIn(source.pretty_name, placed)
        self.assertEqual(len(placed), len(_RETAIL) - 1)
        vanilla = Counter(build_item_pool(GAME_DATA, settings))
        default = Counter(build_item_pool(
            GAME_DATA, LogicSettings(restocking_shop_items="vanilla"),
        ))
        self.assertEqual(sum(vanilla.values()), sum(default.values()))
        self.assertEqual(vanilla["Strength Tonic"], default["Strength Tonic"] - 1)
        self.assertEqual(vanilla["Herbs"], default["Herbs"] + 1)

    def test_closing_shelves_without_enough_herbs_fails(self) -> None:
        # The distribution has 60 Herbs. Closing 8 shelves needs 8 of them.
        # Fixing 53 copies on other checks leaves 7, which is not enough.
        names = [
            source.pretty_name for source in GAME_DATA.sources
            if source.id not in _RETAIL
        ]
        settings = LogicSettings(
            restocking_shop_items="vanilla",
            fixed_item_sources=tuple((name, "Herbs") for name in names[:53]),
        )
        with self.assertRaises(LogicError) as caught:
            build_item_pool(GAME_DATA, settings)
        self.assertIn("restocking shelves", str(caught.exception))

    def test_unreported_sources_refuse_progression_items(self) -> None:
        # The room never hears about these placements. A ring opens nothing,
        # so it can still fill one. A check may still hold a progression item.
        progression = build_graph(GAME_DATA, LogicSettings()).progression_items
        self.assertIn("Tree Gem", progression)
        self.assertIn("Bomb", progression)
        self.assertIn("Small Key", progression)
        self.assertIn("Ruby Crest", progression)
        self.assertNotIn("Olga's Ring", progression)
        self.assertNotIn("Herbs", progression)
        unreported = [source for source in GAME_DATA.sources if source.forbid_precious]
        unreported_ids = {source.id for source in unreported}
        self.assertTrue({129, *range(139, 146)} <= unreported_ids)
        self.assertTrue(any(source.has_price for source in unreported))
        for source in unreported:
            self.assertTrue(forbid_progression(
                forbid_precious=source.forbid_precious,
                name="Tree Gem",
                progression=progression,
            ), source.name)
            self.assertTrue(forbid_progression(
                forbid_precious=source.forbid_precious,
                name="Small Key",
                progression=progression,
            ), source.name)
            self.assertFalse(forbid_progression(
                forbid_precious=source.forbid_precious,
                name="Olga's Ring",
                progression=progression,
            ), source.name)
        one_time = GAME_DATA.source_by_id[266]
        self.assertTrue(one_time.has_price)
        self.assertFalse(one_time.forbid_precious)
        self.assertFalse(forbid_progression(
            forbid_precious=one_time.forbid_precious,
            name="Tree Gem",
            progression=progression,
        ))
        plain = build_graph(
            GAME_DATA, LogicSettings(progressive_items=False),
        ).progression_items
        self.assertIn("Hunter's Bow", plain)
        self.assertNotIn("Willow Bow", plain)
        self.assertTrue(forbid_progression(
            forbid_precious=True, name="Hunter's Bow", progression=plain,
        ))
        self.assertFalse(forbid_progression(
            forbid_precious=True, name="Willow Bow", progression=plain,
        ))


if __name__ == "__main__":
    unittest.main()
