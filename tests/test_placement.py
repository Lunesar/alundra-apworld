# Placement file encoding. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import json
import sys
import types
import unittest
from pathlib import Path

# Load the world as a package without running __init__.py, which imports Archipelago.
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

from alundra.data import GAME_DATA, ITEM_COUNT, REQUIRED_STARTING_ITEMS
from alundra.logic import LogicSettings
from alundra.placement import (
    FORMAT_ALUNDRA,
    FORMAT_MULTIWORLD,
    OutsidePlacement,
    PlacementError,
    allows_outside_item,
    apworld_version,
    build_placement_document,
    remote_shop_price,
    remote_shop_price_applies,
    remote_shop_price_for,
    write_placement,
)


def _native_placements() -> dict[int, int]:
    # Spread copies so no item exceeds the randomizer's uint8 distribution count.
    return {
        source.id: (index % (ITEM_COUNT - 1)) + 1
        for index, source in enumerate(GAME_DATA.sources)
    }


def _document(placements: dict, *, player: str | None = "YourName") -> dict:
    return build_placement_document(
        LogicSettings(),
        placements,
        list(REQUIRED_STARTING_ITEMS),
        player=player,
    )


class PlacementTests(unittest.TestCase):
    def test_native_file_stays_item_ids(self) -> None:
        document = _document(_native_placements())
        self.assertEqual(document["format"], FORMAT_ALUNDRA)
        self.assertNotIn("apworldVersion", document)
        self.assertNotIn("player", document)
        self.assertIn("seed", document)
        self.assertTrue(all(isinstance(value, int) for value in document["placements"].values()))
        self.assertEqual(
            sum(document["randomizerSettings"]["itemsDistribution"].values()),
            len(GAME_DATA.sources),
        )

    def test_multiworld_file_records_slot_identity(self) -> None:
        placements = _native_placements()
        source = GAME_DATA.sources[0]
        placements[source.id] = OutsidePlacement(
            player="Very Long Player Name",
            item="Key Item",
            flags=0b00001,
        )
        document = build_placement_document(
            LogicSettings(seed=7),
            placements,
            list(REQUIRED_STARTING_ITEMS),
            player="Néstor\\Room",
        )
        self.assertEqual(
            list(document),
            [
                "format",
                "apworldVersion",
                "player",
                "seed",
                "gameSettings",
                "randomizerSettings",
                "placements",
            ],
        )
        self.assertEqual(document["format"], FORMAT_MULTIWORLD)
        self.assertEqual(document["apworldVersion"], apworld_version())
        self.assertEqual(apworld_version(), "0.1.5")
        # The login name is kept whole. The disc line on the placement is not.
        self.assertEqual(document["player"], "Néstor\\Room")
        self.assertEqual(document["seed"], 7)
        self.assertEqual(document["placements"][str(source.id)]["player"], "Very Long Player")
        self.assertEqual(len(document["placements"][str(source.id)]["player"]), 16)

    def test_multiworld_file_requires_a_slot_name(self) -> None:
        placements = _native_placements()
        placements[GAME_DATA.sources[0].id] = OutsidePlacement(player="Bea", item="Orb", flags=0)
        with self.assertRaises(PlacementError):
            build_placement_document(
                LogicSettings(),
                placements,
                list(REQUIRED_STARTING_ITEMS),
            )
        for name in ("", "   ", "Your\nName", "Your\x7fName", 1):
            with self.assertRaises(PlacementError):
                _document(placements, player=name)

    def test_outside_item_is_an_object_and_is_not_counted(self) -> None:
        placements = _native_placements()
        location_id = GAME_DATA.sources[0].id
        native_id = placements[location_id]
        native_name = GAME_DATA.item_by_id[native_id].name
        placements[location_id] = OutsidePlacement(
            player="Player",
            item="Key Item",
            flags=0b00001,
        )
        document = _document(placements)
        self.assertEqual(document["format"], FORMAT_MULTIWORLD)
        self.assertEqual(
            document["placements"][str(location_id)],
            {
                "player": "Player",
                "item": "Key Item",
                "classification": "progression",
            },
        )
        counted = document["randomizerSettings"]["itemsDistribution"]
        self.assertEqual(sum(counted.values()), len(GAME_DATA.sources) - 1)
        native_count = sum(1 for value in _native_placements().values() if value == native_id)
        self.assertEqual(counted.get(native_name, 0), native_count - 1)

    def test_classification_names(self) -> None:
        placements = _native_placements()
        location_id = GAME_DATA.sources[0].id
        placements[location_id] = OutsidePlacement(player="Bea", item="Empire Orb", flags=0b00110)
        encoded = _document(placements)["placements"][str(location_id)]
        self.assertEqual(encoded["classification"], "trap")

        placements[location_id] = OutsidePlacement(player="Bea", item="Sword", flags=0b00011)
        encoded = _document(placements)["placements"][str(location_id)]
        self.assertEqual(encoded["classification"], "progression")

        placements[location_id] = OutsidePlacement(player="Bea", item="Potion", flags=0)
        encoded = _document(placements)["placements"][str(location_id)]
        self.assertEqual(encoded["classification"], "filler")

    def test_outside_item_round_trip(self) -> None:
        placements = _native_placements()
        location_id = GAME_DATA.sources[1].id
        placements[location_id] = OutsidePlacement(player="Samus", item="Morph Ball", flags=0b01001)
        path = Path(__file__).resolve().parent / "_placement_roundtrip.json"
        try:
            write_placement(path, _document(placements))
            loaded = json.loads(path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(loaded["placements"][str(location_id)]["classification"], "progression")
        self.assertEqual(set(loaded["placements"][str(location_id)]), {"player", "item", "classification"})
        self.assertIsInstance(loaded["placements"][str(GAME_DATA.sources[0].id)], int)

    def test_rejects_a_bad_outside_item(self) -> None:
        placements = _native_placements()
        placements[GAME_DATA.sources[0].id] = OutsidePlacement(player=2, item="Lamp", flags=0)
        with self.assertRaises(PlacementError):
            _document(placements)

    def test_remote_names_fit_the_disc_line(self) -> None:
        placements = _native_placements()
        location_id = GAME_DATA.sources[0].id
        placements[location_id] = OutsidePlacement(
            player="  Very Long Player Name  ",
            item="A\\B \u2605 Progressive Sword of Great Length",
            flags=0b00010,
        )
        encoded = _document(placements)["placements"][str(location_id)]
        self.assertEqual(encoded["player"], "Very Long Player")
        self.assertEqual(len(encoded["player"]), 16)
        self.assertEqual(encoded["item"], "AB Progressive Sword of Grea")
        self.assertEqual(len(encoded["item"]), 28)
        self.assertNotIn("\\", encoded["item"])

        placements[location_id] = OutsidePlacement(player="   ", item="\u2605\u2605", flags=0)
        encoded = _document(placements)["placements"][str(location_id)]
        self.assertEqual(encoded["player"], "Player")
        self.assertEqual(encoded["item"], "Item")

    def test_fairy_pond_chests_refuse_remote_items(self) -> None:
        # The pond seals after the reward scene. Ids 139-145.
        # FIXME: keep the pond open and give id 145 a real collected flag.
        for source_id in range(139, 146):
            source = GAME_DATA.source_by_id[source_id]
            self.assertTrue(source.forbid_precious, source.name)
            self.assertFalse(allows_outside_item(
                block_progression=False, progression=False,
                forbid_precious=source.forbid_precious,
            ))

    def test_remote_shop_prices_follow_classification_and_sphere(self) -> None:
        self.assertEqual(
            [remote_shop_price("progression", sphere) for sphere in range(1, 8)],
            [100, 200, 300, 400, 500, 500, 500],
        )
        self.assertEqual(remote_shop_price("useful", 1), 250)
        self.assertEqual(remote_shop_price("useful", 9), 250)
        self.assertEqual(remote_shop_price("filler", 3), 100)
        self.assertEqual(remote_shop_price("trap", 1), 50)
        self.assertEqual(remote_shop_price("trap", 9), 50)
        # Progression outranks useful and trap. Trap outranks useful.
        self.assertEqual(remote_shop_price_for(0b01001, 2), 200)
        self.assertEqual(remote_shop_price_for(0b00011, 1), 100)
        self.assertEqual(remote_shop_price_for(0b00110, 4), 50)
        self.assertEqual(remote_shop_price_for(0b00010, 4), 250)
        self.assertEqual(remote_shop_price_for(0, 4), 100)
        with self.assertRaises(PlacementError):
            remote_shop_price("progression", 0)
        with self.assertRaises(PlacementError):
            remote_shop_price("currency", 1)

    def test_remote_shop_price_is_recorded_on_a_one_time_shelf(self) -> None:
        priced = {
            source.id for source in GAME_DATA.sources
            if remote_shop_price_applies(
                has_price=source.has_price, forbid_precious=source.forbid_precious,
            )
        }
        # Naomi's Item #4, Lurvy's Item #5, and the Life Vessel that replaces it.
        self.assertEqual(priced, {266, 267, 273})

        placements = _native_placements()
        placements[273] = OutsidePlacement(player="Player", item="Key Item", flags=0b00001, price=100)
        placements[266] = OutsidePlacement(player="Bea", item="Ring", flags=0b00010, price=250)
        placements[267] = OutsidePlacement(player="Sam", item="Map", flags=0, price=100)
        document = _document(placements)
        self.assertEqual(
            document["placements"]["273"],
            {"player": "Player", "item": "Key Item", "classification": "progression", "price": 100},
        )
        self.assertEqual(document["placements"]["266"]["price"], 250)
        self.assertEqual(document["placements"]["267"]["price"], 100)
        self.assertNotIn("Key Item", document["randomizerSettings"]["itemsDistribution"])

        placements[1] = OutsidePlacement(player="Player", item="Key Item", flags=0b00001, price=100)
        with self.assertRaises(PlacementError):
            _document(placements)
        placements = _native_placements()
        placements[262] = OutsidePlacement(player="Bea", item="Ring", flags=0b00010, price=250)
        with self.assertRaises(PlacementError):
            _document(placements)
        placements = _native_placements()
        placements[273] = OutsidePlacement(player="Player", item="Key Item", flags=0b00001, price=10000)
        with self.assertRaises(PlacementError):
            _document(placements)
        placements[273] = OutsidePlacement(player="Player", item="Key Item", flags=0b00001, price=False)
        with self.assertRaises(PlacementError):
            _document(placements)

    def test_non_progression_check_refuses_progression(self) -> None:
        self.assertFalse(allows_outside_item(block_progression=True, progression=True))
        self.assertTrue(allows_outside_item(block_progression=True, progression=False))
        self.assertTrue(allows_outside_item(block_progression=False, progression=True))
        self.assertFalse(allows_outside_item(
            block_progression=False, progression=False, forbid_precious=True,
        ))


if __name__ == "__main__":
    unittest.main()
