"""Placement seed map, format 1. --placement-in reads this and patches the disc."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .data import GAME_DATA, ITEM_COUNT, REQUIRED_STARTING_ITEMS, GameData
from .logic import LogicSettings, preplaced_crest_names


class PlacementError(Exception):
    pass


_GAME_SETTING_KEYS = (
    "originalGameBalance",
    "megalithsEnabledOnStart",
    "skipLastDungeon",
    "splitBootsEffects",
    "progressiveItems",
    "kingSnowDeathCount",
    "casinoWinCountForLastReward",
    "startingHealth",
    "startingMana",
    "startingGold",
)


def _check_seed(seed: int) -> None:
    if not 0 <= seed <= 0xFFFFFFFF:
        raise PlacementError("Placement seed must fit in an unsigned 32-bit value.")


def _check_location_ids(placements: dict[int, int], game_data: GameData) -> None:
    expected = {source.id for source in game_data.sources}
    got = set(placements)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise PlacementError(f"Placement locations do not match item sources. Missing {missing}, extra {extra}.")


def _encode_placements(
    placements: dict[int, int], game_data: GameData,
) -> tuple[dict[str, int], Counter[str]]:
    # Location ids become the placement map. Item names are counted for itemsDistribution.
    counted: Counter[str] = Counter()
    encoded: dict[str, int] = {}
    for location_id in sorted(placements):
        item_id = placements[location_id]
        if isinstance(item_id, bool) or not isinstance(item_id, int) or not 0 <= item_id < ITEM_COUNT:
            raise PlacementError(f"Location {location_id} has item id {item_id}, which is not a game item.")
        record = game_data.item_by_id[item_id]
        counted[record.name] += 1
        encoded[str(location_id)] = item_id
    return encoded, counted


def _check_distribution_counts(counted: Counter[str]) -> None:
    # The randomizer reads each distribution count into a uint8_t.
    overflow = sorted(name for name, count in counted.items() if count > 255)
    if overflow:
        raise PlacementError(
            "These items are placed more than 255 times, which does not fit the randomizer's "
            f"distribution count: {', '.join(overflow)}."
        )


def _starting_inventory(names: list[str], game_data: GameData) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in list(REQUIRED_STARTING_ITEMS) + list(names):
        # The new-game patch sets a bit per item id, so a repeat does nothing.
        if name in seen:
            continue
        if name not in game_data.item_by_name:
            raise PlacementError(f"Starting inventory item '{name}' does not exist.")
        seen.add(name)
        ordered.append(name)
    return ordered


def _check_required_starting_items(inventory: list[str]) -> None:
    for name in REQUIRED_STARTING_ITEMS:
        if name not in inventory:
            raise PlacementError(f"Starting inventory is missing {name}.")


def _game_settings(settings: LogicSettings) -> dict:
    game_settings = {
        "originalGameBalance": settings.original_game_balance,
        "megalithsEnabledOnStart": settings.megaliths_enabled_on_start,
        "skipLastDungeon": settings.skip_last_dungeon,
        "splitBootsEffects": settings.split_boots_effects,
        "progressiveItems": settings.progressive_items,
        "kingSnowDeathCount": settings.king_snow_death_count,
        "casinoWinCountForLastReward": settings.casino_win_count_for_last_reward,
        "startingHealth": settings.starting_health,
        "startingMana": settings.starting_mana,
        "startingGold": settings.starting_gold,
    }
    if set(game_settings) != set(_GAME_SETTING_KEYS):
        raise PlacementError("gameSettings keys drifted from the randomizer reader.")
    return game_settings


def _randomizer_settings(settings: LogicSettings, inventory: list[str], counted: Counter[str]) -> dict:
    return {
        "allowSpoilerLog": settings.allow_spoiler_log,
        "startingInventory": inventory,
        "crestCount": settings.crest_count,
        "prePlacedCrests": preplaced_crest_names(settings),
        "fixedItemSources": {pretty: item for pretty, item in settings.fixed_item_sources},
        "itemSourcesWithoutProgression": list(settings.non_progression_locations),
        "itemsDistribution": {name: count for name, count in sorted(counted.items()) if count},
    }


def build_placement_document(
    settings: LogicSettings,
    placements: dict[int, int],
    starting_inventory: list[str],
    game_data: GameData = GAME_DATA,
) -> dict:
    """Return the JSON object --placement-in accepts."""
    _check_seed(settings.seed)
    _check_location_ids(placements, game_data)
    encoded, counted = _encode_placements(placements, game_data)
    _check_distribution_counts(counted)
    inventory = _starting_inventory(starting_inventory, game_data)
    _check_required_starting_items(inventory)
    return {
        "format": 1,
        "seed": settings.seed,
        "gameSettings": _game_settings(settings),
        "randomizerSettings": _randomizer_settings(settings, inventory, counted),
        "placements": encoded,
    }


def write_placement(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=4) + "\n", encoding="utf-8")
