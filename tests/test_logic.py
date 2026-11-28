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
    LogicError,
    LogicSettings,
    _slot_groups,
    build_graph,
    build_item_pool,
    convert_requirement,
    explore,
    full_inventory,
    search_world,
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


# Source 1 is the chest in Lutas's house, on the spawn node. The Long Boots
# gate is overworld_d4, which the spawn can reach with no other items.
_LUTAS_CHEST = 1
_LONG_BOOTS_NODE = "overworld_d4_behind_long_boots"
_JESS_CHEST_NODE = "inoa_jess_chest"


class WorldSearchTests(unittest.TestCase):
    def test_starting_inventory_opens_its_gate(self) -> None:
        graph = build_graph(GAME_DATA, LogicSettings(progressive_items=False))
        closed = search_world(graph, GAME_DATA, {}, REQUIRED_STARTING_ITEMS)
        self.assertIn("inoa", closed.nodes)
        self.assertNotIn(_LONG_BOOTS_NODE, closed.nodes)
        self.assertEqual(closed.count("Dagger"), 1)

        opened = search_world(
            graph, GAME_DATA, {}, (*REQUIRED_STARTING_ITEMS, "Long Boots"),
        )
        self.assertTrue(opened.reached(_LONG_BOOTS_NODE))

    def test_a_reachable_chest_is_collected(self) -> None:
        graph = build_graph(GAME_DATA, LogicSettings(progressive_items=False))
        # Jess's blue chest is behind a Small Key. The key has to be in a
        # chest the walk can already reach.
        found = search_world(
            graph, GAME_DATA, {_LUTAS_CHEST: "Small Key"}, REQUIRED_STARTING_ITEMS,
        )
        self.assertTrue(found.reached(_JESS_CHEST_NODE))
        self.assertEqual(found.count("Small Key"), 1)

        behind_the_door = search_world(graph, GAME_DATA, {2: "Small Key"}, REQUIRED_STARTING_ITEMS)
        self.assertFalse(behind_the_door.reached(_JESS_CHEST_NODE))
        self.assertEqual(behind_the_door.count("Small Key"), 0)

    def test_a_forbidden_node_or_item_stays_in_the_chest(self) -> None:
        graph = build_graph(GAME_DATA, LogicSettings(progressive_items=False))
        placements = {_LUTAS_CHEST: "Small Key"}
        by_node = search_world(
            graph, GAME_DATA, placements, REQUIRED_STARTING_ITEMS, forbid_nodes=("inoa",),
        )
        by_item = search_world(
            graph, GAME_DATA, placements, REQUIRED_STARTING_ITEMS, forbid_items=("Small Key",),
        )
        self.assertFalse(by_node.reached(_JESS_CHEST_NODE))
        self.assertFalse(by_item.reached(_JESS_CHEST_NODE))
        # Forbidding the pickup leaves the copy Alundra started with.
        owned = search_world(
            graph, GAME_DATA, placements, ("Long Boots",), forbid_items=("Long Boots",),
        )
        self.assertTrue(owned.reached(_LONG_BOOTS_NODE))
        self.assertEqual(owned.count("Long Boots"), 1)

    def test_another_worlds_item_is_not_collected(self) -> None:
        graph = build_graph(GAME_DATA, LogicSettings(progressive_items=False))
        missed = search_world(graph, GAME_DATA, {}, REQUIRED_STARTING_ITEMS)
        self.assertFalse(missed.reached(_JESS_CHEST_NODE))

    def test_one_boots_upgrade_stands_in_for_long_boots(self) -> None:
        graph = build_graph(GAME_DATA, REPLACED)
        closed = search_world(graph, GAME_DATA, {}, REQUIRED_STARTING_ITEMS)
        self.assertFalse(closed.reached(_LONG_BOOTS_NODE))
        opened = search_world(
            graph, GAME_DATA, {_LUTAS_CHEST: "Boots upgrade"}, REQUIRED_STARTING_ITEMS,
        )
        self.assertTrue(opened.reached(_LONG_BOOTS_NODE))
        self.assertEqual(opened.count("Boots upgrade"), 1)

    def test_unknown_names_are_rejected(self) -> None:
        graph = build_graph(GAME_DATA, LogicSettings(progressive_items=False))
        with self.assertRaises(LogicError):
            search_world(graph, GAME_DATA, {99999: "Small Key"})
        with self.assertRaises(LogicError):
            search_world(graph, GAME_DATA, {_LUTAS_CHEST: "Not An Item"})
        with self.assertRaises(LogicError):
            search_world(graph, GAME_DATA, {}, ("Not An Item",))
        with self.assertRaises(LogicError):
            search_world(graph, GAME_DATA, {}, forbid_nodes=("not_a_node",))
        with self.assertRaises(LogicError):
            search_world(graph, GAME_DATA, {}, forbid_items=("Not An Item",))


# Item 73, the lower chest in the left A3 ruins. The elevated ledge and the
# ground below it, overworld_a3_left_behind_merman can only be exited to the
# river_network, and that exit requires the Merman Boots. Dropping in without
# them softlocks the player, so the one-way drop requires them.
_A3_LEFT = "overworld_a3_left"
_A3_LEDGE = "overworld_a3_left_elevated_behind_merman"
_A3_BEHIND_MERMAN = "overworld_a3_left_behind_merman"
_A3_LOWER_CHEST = 73


class A3LowerChestTest(unittest.TestCase):
    def test_chest_is_on_the_ledge_between_the_drops(self) -> None:
        self.assertEqual(GAME_DATA.source_by_id[_A3_LOWER_CHEST].node_id, _A3_LEDGE)
        self.assertEqual(GAME_DATA.nodes[_A3_LEDGE].region_name, GAME_DATA.nodes[_A3_LEFT].region_name)

        graph = build_graph(GAME_DATA, SPLIT)
        onto_ledge = _only(graph, _A3_LEFT, _A3_LEDGE)
        to_lower_ground = _only(graph, _A3_LEDGE, _A3_BEHIND_MERMAN)
        self.assertEqual(onto_ledge.requirement.items, (("Merman Boots", 1),))
        self.assertEqual(to_lower_ground.requirement.items, ())
        self.assertEqual(_edges(graph, _A3_LEDGE, _A3_LEFT), [])
        self.assertEqual(_edges(graph, _A3_BEHIND_MERMAN, _A3_LEDGE), [])
        self.assertEqual(_edges(graph, _A3_LEFT, _A3_BEHIND_MERMAN), [])

    def test_boots_alone_reach_the_lower_ground_and_not_the_chest(self) -> None:
        graph = build_graph(GAME_DATA, SPLIT)
        # The river lands on the lower ground. That ground is below the chest.
        from_the_river = explore(graph, Counter({"Merman Boots": 1}))
        self.assertIn(_A3_BEHIND_MERMAN, from_the_river)
        self.assertNotIn(_A3_LEDGE, from_the_river)
        self.assertNotIn(_A3_LEFT, from_the_river)

        # overworld_a3_left stays open without the boots. The drop onto the chest
        # stays closed, because the river is the only way back out.
        inventory = full_inventory(graph)
        self.assertIn(_A3_LEDGE, explore(graph, inventory))
        inventory["Merman Boots"] = 0
        reached = explore(graph, inventory)
        self.assertIn(_A3_LEFT, reached)
        self.assertNotIn(_A3_LEDGE, reached)


# Two tree stumps divide the ground north of Nava's cabin. The left pocket
# opens onto overworld_a4_right, and the Iron Flail opens it onto
# overworld_b3_megalith. The middle pocket holds item 50, and the Iron Flail
# opens it onto overworld_b3_elevated. Each pocket meets overworld_b4 through
# its own stump, so the chest and the elevated exit both require a Bomb.
_B4 = "overworld_b4"
_B4_LEFT = "overworld_b4_behind_bomb_left"
_B4_MIDDLE = "overworld_b4_behind_bomb_middle"
_A4_RIGHT = "overworld_a4_right"
_B3_MEGALITH = "overworld_b3_megalith"
_B3_ELEVATED = "overworld_b3_elevated"
_B4_STUMP_CHEST = 50
_B3_ELEVATED_CHEST = 53
_LITERAL = LogicSettings(progressive_items=False)


class B4StumpSplitTest(unittest.TestCase):
    def test_the_pockets_meet_b4_through_separate_stumps(self) -> None:
        self.assertEqual(GAME_DATA.source_by_id[_B4_STUMP_CHEST].node_id, _B4_MIDDLE)
        self.assertEqual(GAME_DATA.source_by_id[_B3_ELEVATED_CHEST].node_id, _B3_ELEVATED)
        self.assertNotIn("overworld_b4_behind_bomb", GAME_DATA.nodes)
        region = GAME_DATA.nodes[_B4].region_name
        self.assertEqual(GAME_DATA.nodes[_B4_LEFT].region_name, region)
        self.assertEqual(GAME_DATA.nodes[_B4_MIDDLE].region_name, region)

        graph = build_graph(GAME_DATA, _LITERAL)
        bomb = (("Bomb", 1),)
        flail = (("Iron Flail", 1),)
        self.assertEqual(_only(graph, _B4, _B4_LEFT).requirement.items, bomb)
        self.assertEqual(_only(graph, _B4_LEFT, _B4).requirement.items, bomb)
        self.assertEqual(_only(graph, _B4, _B4_MIDDLE).requirement.items, bomb)
        self.assertEqual(_only(graph, _B4_MIDDLE, _B4).requirement.items, bomb)
        self.assertEqual(_only(graph, _B4_LEFT, _A4_RIGHT).requirement.items, ())
        self.assertEqual(_only(graph, _A4_RIGHT, _B4_LEFT).requirement.items, ())
        self.assertEqual(_only(graph, _B4_LEFT, _B3_MEGALITH).requirement.items, flail)
        self.assertEqual(_only(graph, _B3_MEGALITH, _B4_LEFT).requirement.items, flail)
        self.assertEqual(_only(graph, _B4_MIDDLE, _B3_ELEVATED).requirement.items, flail)
        self.assertEqual(_only(graph, _B3_ELEVATED, _B4_MIDDLE).requirement.items, flail)
        for origin, destination in (
            (_B4_LEFT, _B4_MIDDLE),
            (_B4_MIDDLE, _B4_LEFT),
            (_B4_MIDDLE, _A4_RIGHT),
            (_A4_RIGHT, _B4_MIDDLE),
            (_B4_MIDDLE, _B3_MEGALITH),
            (_B3_MEGALITH, _B4_MIDDLE),
            (_B4_LEFT, _B3_ELEVATED),
            (_B3_ELEVATED, _B4_LEFT),
        ):
            self.assertEqual(_edges(graph, origin, destination), [])

    def test_fire_wand_flail_and_boots_reach_the_megalith_and_miss_the_chests(self) -> None:
        graph = build_graph(GAME_DATA, _LITERAL)
        reached = explore(graph, Counter({
            "Fire Wand": 1,
            "Iron Flail": 1,
            "Merman Boots": 1,
        }))
        self.assertIn(_A4_RIGHT, reached)
        self.assertIn(_B4_LEFT, reached)
        self.assertIn(_B3_MEGALITH, reached)
        self.assertNotIn(_B4_MIDDLE, reached)
        self.assertNotIn(_B3_ELEVATED, reached)

    def test_bomb_opens_the_chest_and_flail_opens_the_elevated_exit(self) -> None:
        graph = build_graph(GAME_DATA, _LITERAL)
        with_bomb = explore(graph, Counter({"Bomb": 1}))
        self.assertIn(_B4, with_bomb)
        self.assertIn(_B4_LEFT, with_bomb)
        self.assertIn(_B4_MIDDLE, with_bomb)
        self.assertIn(_A4_RIGHT, with_bomb)
        self.assertNotIn(_B3_ELEVATED, with_bomb)
        self.assertNotIn(_B3_MEGALITH, with_bomb)

        with_both = explore(graph, Counter({"Bomb": 1, "Iron Flail": 1}))
        self.assertIn(_B4_MIDDLE, with_both)
        self.assertIn(_B3_ELEVATED, with_both)
        self.assertIn(_B3_MEGALITH, with_both)

        # The left pocket and the megalith stay open while both stumps are intact.
        without_bomb = full_inventory(graph)
        without_bomb["Bomb"] = 0
        reached = explore(graph, without_bomb)
        self.assertIn(_B4_LEFT, reached)
        self.assertIn(_A4_RIGHT, reached)
        self.assertIn(_B3_MEGALITH, reached)
        self.assertNotIn(_B4_MIDDLE, reached)
        self.assertNotIn(_B3_ELEVATED, reached)

        without_flail = full_inventory(graph)
        without_flail["Iron Flail"] = 0
        without_flail["Steel Flail"] = 0
        reached = explore(graph, without_flail)
        self.assertIn(_B4_MIDDLE, reached)
        self.assertIn(_B4_LEFT, reached)
        self.assertNotIn(_B3_ELEVATED, reached)
        self.assertNotIn(_B3_MEGALITH, reached)

        self.assertIn(_B4_MIDDLE, explore(graph, full_inventory(graph)))
        self.assertIn(_B3_ELEVATED, explore(graph, full_inventory(graph)))


if __name__ == "__main__":
    unittest.main()
