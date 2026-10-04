"""Archipelago item and location types.

Item codes are 800000 plus the in-game id. Nothing is id 0, and Archipelago
drops non-positive codes from the datapackage, so the code cannot be the raw id.
Location codes are the item source ids. Those already start at 1, and they are
the keys of the placement file.
"""

from __future__ import annotations

from BaseClasses import Item, ItemClassification, Location

from .data import GAME_DATA

USEFUL_ITEMS = frozenset({
    "Life Vessel",
    "Magic Seed",
    "Olga's Ring",
    "Silver Armlet",
    "Recovery Ring",
    "Nava's Charm",
    "Leather Armor",
    "Ancient Armor",
    "Silver Armor",
    "Armor upgrade",
})


class AlundraItem(Item):
    game = "Alundra"
    in_game_id: int | None

    def __init__(self, name: str, classification: ItemClassification, code: int | None, player: int,
                 in_game_id: int | None = None) -> None:
        super().__init__(name, classification, code, player)
        self.in_game_id = in_game_id


class AlundraLocation(Location):
    game = "Alundra"


def classification_for(name: str, progression: frozenset[str]) -> ItemClassification:
    if name in progression:
        return ItemClassification.progression
    if name in USEFUL_ITEMS:
        return ItemClassification.useful
    if name not in GAME_DATA.item_by_name:
        raise KeyError(name)
    return ItemClassification.filler
