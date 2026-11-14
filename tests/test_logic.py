# Progressive item requirements. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
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

from alundra.data import GAME_DATA, REQUIRED_STARTING_ITEMS
from alundra.logic import (
    LogicGraph,
    LogicSettings,
    _slot_groups,
    build_graph,
    build_item_pool,
    convert_requirement,
    explore,
    full_inventory,
)


# The reported seed replaced boots with Boots upgrades and still started with Short Boots.
# Generation then filled every Torla check behind Charm Boots with filler.
REPLACED = LogicSettings(
    progressive_items=True,
    split_boots_effects=False,
    restocking_shop_items="randomized",
)
SPLIT = LogicSettings(
    progressive_items=True,
    split_boots_effects=True,
    restocking_shop_items="randomized",
)

# In front of the boots gate. These stayed reachable.
_ENTRANCE_SOURCES = (230, 231, 232, 233)
# Chest before the boss, and the boss reward.
_BEHIND_BOOTS_SOURCES = (235, 236)
# The pit below the wooden bridge. The spring is past the boots.
_BEHIND_SPRING_SOURCES = (234,)

# Owned slots subtract the starting tier. Empty slots still take tier + 1,
# because the first pickup grants tier 0. Tiers that no current edge names are
# listed here so a later edge cannot ask for more upgrades than the pool holds.
_OWNED = (
    ("Long Boots", "Boots upgrade", 1),
    ("Merman Boots", "Boots upgrade", 2),
    ("Charm Boots", "Boots upgrade", 3),
    ("Sword", "Sword upgrade", 1),
    ("Fiend Blade", "Sword upgrade", 2),
    ("Holy Sword", "Sword upgrade", 3),
    ("Legend Sword", "Sword upgrade", 4),
    ("Leather Armor", "Armor upgrade", 1),
    ("Ancient Armor", "Armor upgrade", 2),
    ("Silver Armor", "Armor upgrade", 3),
)
_EMPTY = (
    ("Hunter's Bow", "Bow upgrade", 1),
    ("Willow Bow", "Bow upgrade", 2),
    ("Iron Flail", "Flail upgrade", 1),
    ("Steel Flail", "Flail upgrade", 2),
    ("Earth Scroll", "Earth Magic upgrade", 1),
    ("Earth Book", "Earth Magic upgrade", 2),
    ("Water Scroll", "Water Magic upgrade", 1),
    ("Water Book", "Water Magic upgrade", 2),
    ("Fire Scroll", "Fire Magic upgrade", 1),
    ("Fire Book", "Fire Magic upgrade", 2),
    ("Wind Scroll", "Wind Magic upgrade", 1),
    ("Wind Book", "Wind Magic upgrade", 2),
)
_UNCHANGED = ("Fire Wand", "Ice Wand")
_ITEMS_REPLACED_BY_UPGRADES = tuple(item for item, _upgrade, _count in _OWNED + _EMPTY) + (
    "Dagger",
    "Cloth Armor",
    "Short Boots",
)


def _names(items: tuple[tuple[str, int], ...]) -> tuple[str, ...]:
    names: list[str] = []
    for name, count in items:
        names.extend([name] * count)
    return tuple(names)


def _edges(graph: LogicGraph, origin: str, destination: str):
    return [
        edge for edge in graph.edges
        if edge.origin == origin and edge.destination == destination
    ]


def _only(graph: LogicGraph, origin: str, destination: str):
    found = _edges(graph, origin, destination)
    if len(found) != 1:
        raise AssertionError(f"{origin} -> {destination} has {len(found)} edges")
    return found[0]


class ProgressiveTorlaTest(unittest.TestCase):
    def test_charm_boots_gate_is_three_upgrades(self) -> None:
        graph = build_graph(GAME_DATA, REPLACED)
        expected = (("Boots upgrade", 3),)
        forward = _only(graph, "torla_mountain", "torla_mountain_behind_charm_boots")
        backward = _only(graph, "torla_mountain_behind_charm_boots", "torla_mountain")
        self.assertEqual(forward.requirement.items, expected)
        self.assertEqual(backward.requirement.items, expected)

        entrance = _only(graph, "overworld_d1", "torla_mountain")
        self.assertEqual(
            entrance.requirement.items,
            (("Fire Wand", 1), ("Flail upgrade", 1), ("Ice Wand", 1)),
        )
        spring = _only(graph, "torla_mountain_behind_charm_boots", "torla_mountain_behind_spring")
        self.assertEqual(spring.requirement.items, (("Spring Bean", 1),))

        # Long Boots and Merman Boots are both on this entrance. The gate stays
        # at Merman Boots, the higher of the two.
        lair = _only(graph, "overworld_d4", "reptile_lair")
        self.assertEqual(
            lair.requirement.items,
            (("Bomb", 1), ("Boots upgrade", 2), ("Bow upgrade", 1)),
        )

    def test_two_upgrades_reach_the_entrance_only(self) -> None:
        graph = build_graph(GAME_DATA, REPLACED)
        inventory = full_inventory(graph)
        inventory["Boots upgrade"] = 2
        reached = explore(graph, inventory)

        self.assertIn("torla_mountain", reached)
        self.assertNotIn("torla_mountain_behind_charm_boots", reached)
        self.assertNotIn("torla_mountain_behind_spring", reached)
        for source_id in _ENTRANCE_SOURCES:
            self.assertIn(GAME_DATA.source_by_id[source_id].node_id, reached, source_id)
        for source_id in _BEHIND_BOOTS_SOURCES + _BEHIND_SPRING_SOURCES:
            self.assertNotIn(GAME_DATA.source_by_id[source_id].node_id, reached, source_id)

    def test_three_upgrades_reach_every_torla_check(self) -> None:
        graph = build_graph(GAME_DATA, REPLACED)
        pool = Counter(build_item_pool(GAME_DATA, REPLACED))
        self.assertEqual(pool["Boots upgrade"], 3)

        inventory = full_inventory(graph)
        inventory["Boots upgrade"] = pool["Boots upgrade"]
        reached = explore(graph, inventory)

        for node_id in (
            "torla_mountain",
            "torla_mountain_behind_charm_boots",
            "torla_mountain_behind_spring",
        ):
            self.assertIn(node_id, reached)
        for source_id in _ENTRANCE_SOURCES + _BEHIND_BOOTS_SOURCES + _BEHIND_SPRING_SOURCES:
            source = GAME_DATA.source_by_id[source_id]
            self.assertIn(source.node_id, reached, source.pretty_name)

    def test_requirement_counts_follow_the_grant(self) -> None:
        groups = _slot_groups(GAME_DATA, False, REQUIRED_STARTING_ITEMS)
        for item, upgrade, count in _OWNED + _EMPTY:
            self.assertEqual(convert_requirement((item,), groups), ((upgrade, count),), item)
        for item in _UNCHANGED:
            self.assertEqual(convert_requirement((item,), groups), ((item, 1),), item)
        for item in ("Dagger", "Cloth Armor", "Short Boots"):
            self.assertEqual(convert_requirement((item,), groups), (), item)
        self.assertEqual(
            convert_requirement(("Bomb", "Hunter's Bow", "Long Boots", "Merman Boots"), groups),
            (("Bomb", 1), ("Boots upgrade", 2), ("Bow upgrade", 1)),
        )

    def test_replaced_edges_use_that_requirement(self) -> None:
        groups = _slot_groups(GAME_DATA, False, REPLACED.starting_inventory)
        plain = build_graph(GAME_DATA, replace(REPLACED, progressive_items=False))
        replaced = build_graph(GAME_DATA, REPLACED)
        self.assertEqual(len(plain.edges), len(replaced.edges))
        for plain_edge, replaced_edge in zip(plain.edges, replaced.edges, strict=True):
            self.assertEqual(replaced_edge.origin, plain_edge.origin)
            self.assertEqual(replaced_edge.destination, plain_edge.destination)
            self.assertEqual(
                replaced_edge.requirement.items,
                convert_requirement(_names(plain_edge.requirement.items), groups),
            )

    def test_pool_can_pay_every_edge(self) -> None:
        graph = build_graph(GAME_DATA, REPLACED)
        pool = Counter(build_item_pool(GAME_DATA, REPLACED))
        self.assertEqual(pool["Boots upgrade"], 3)
        self.assertEqual(pool["Sword upgrade"], 4)
        self.assertEqual(pool["Armor upgrade"], 3)
        self.assertEqual(pool["Bow upgrade"], 2)
        self.assertEqual(pool["Flail upgrade"], 2)
        for element in ("Earth", "Water", "Fire", "Wind"):
            self.assertEqual(pool[f"{element} Magic upgrade"], 2)
        for name in _ITEMS_REPLACED_BY_UPGRADES:
            self.assertEqual(pool[name], 0, name)
        self.assertEqual(pool["Fire Wand"], 1)
        self.assertEqual(pool["Ice Wand"], 1)

        for edge in graph.edges:
            for name, count in edge.requirement.items:
                self.assertLessEqual(
                    count,
                    pool[name],
                    f"{edge.origin} -> {edge.destination} asks for {count} {name}",
                )

    def test_split_boots_still_require_charm_boots(self) -> None:
        graph = build_graph(GAME_DATA, SPLIT)
        forward = _only(graph, "torla_mountain", "torla_mountain_behind_charm_boots")
        backward = _only(graph, "torla_mountain_behind_charm_boots", "torla_mountain")
        self.assertEqual(forward.requirement.items, (("Charm Boots", 1),))
        self.assertEqual(backward.requirement.items, (("Charm Boots", 1),))

        pool = Counter(build_item_pool(GAME_DATA, SPLIT))
        self.assertEqual(pool["Charm Boots"], 1)
        self.assertEqual(pool["Long Boots"], 1)
        self.assertEqual(pool["Merman Boots"], 1)
        self.assertEqual(pool["Boots upgrade"], 0)
        self.assertEqual(pool["Sword upgrade"], 4)

        inventory = full_inventory(graph)
        self.assertGreaterEqual(inventory["Charm Boots"], 1)
        self.assertNotIn("Boots upgrade", inventory)
        reached = explore(graph, inventory)
        self.assertIn("torla_mountain_behind_charm_boots", reached)
        self.assertIn("torla_mountain_behind_spring", reached)

        inventory["Charm Boots"] = 0
        reached = explore(graph, inventory)
        self.assertIn("torla_mountain", reached)
        self.assertNotIn("torla_mountain_behind_charm_boots", reached)
        self.assertNotIn("torla_mountain_behind_spring", reached)


if __name__ == "__main__":
    unittest.main()
