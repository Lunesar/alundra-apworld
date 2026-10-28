"""Placement seed map. --placement-in reads this and patches the disc.

The Alundra format is only in-game item ids. The Multiworld format is the same
file with at least one remote item. A remote placement has these keys:

    {"player": "Player", "item": "Key Item", "classification": "progression"}

player is 1..16 printable ASCII characters and item is 1..28, with no backslash.
classification is progression, useful, filler, or trap. A one-time shop shelf
also records price, the gilder that shelf charges. itemsDistribution counts
only the in-game ids.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .data import GAME_DATA, ITEM_COUNT, REQUIRED_STARTING_ITEMS, GameData
from .logic import LogicSettings, preplaced_crest_names


class PlacementError(Exception):
    pass


# The disc line is "player - item", 47 characters. These limits are the reader's.
_PLAYER_NAME_MAX = 16
_ITEM_NAME_MAX = 28
_PROGRESSION = 0b00001
_USEFUL = 0b00010
_TRAP = 0b00100
# The JSON field is numeric. These names are the Alundra format and the Multiworld format.
FORMAT_ALUNDRA = 1
FORMAT_MULTIWORLD = 2


@dataclass(frozen=True)
class OutsidePlacement:
    """An item from another Archipelago slot, placed on an Alundra check.

    price is the gilder a one-time shop shelf charges. Other checks leave it unset.
    """

    player: str
    item: str
    flags: int
    price: int | None = None


def forbid_progression(
    *, forbid_precious: bool, name: str, progression: frozenset[str],
) -> bool:
    """A source that is not a check refuses this progression item.

    forbidPreciousItems marks the restocking shelves, the table in Tarn's
    Manor, and every Fairy Pond chest. Those sources are filled, then left
    out of the location list, so the room never hears about the item. A
    check may still hold one. When the pond and the table gain a collected
    flag, forbidPreciousItems comes off and this refusal lifts.
    """
    return forbid_precious and name in progression


def allows_outside_item(
    *, block_progression: bool, progression: bool, forbid_precious: bool = False,
) -> bool:
    """A remote item may fill a check.

    forbidPreciousItems marks the restocking shelves, the table in Tarn's
    Manor, and every Fairy Pond chest. A precious Alundra item cannot sit
    there. A remote item cannot either: the shelf offers it again, and the
    pond seals after the reward scene, so a chest left behind is missed.
    FIXME: keep the Fairy Pond open and give the reward chest (id 145) a
    real collected flag, then drop forbidPreciousItems on these chests.
    A non-progression check still refuses a progression item.
    """
    if forbid_precious:
        return False
    return not (block_progression and progression)


# The purse caps at 9999, so a higher price can never be paid.
_SHOP_PRICE_MAX = 9999
# Sphere 5 and later keep the price Naomi's Life Vessel shelf has on the disc.
_PROGRESSION_PRICE_CAP_SPHERE = 5


def remote_shop_price_applies(*, has_price: bool, forbid_precious: bool) -> bool:
    """A one-time shop shelf charges gilder and can hold a remote item.

    A restocking shelf has a price and refuses a remote item. The repaired
    armor is a one-time check and has no price word.
    """
    return has_price and not forbid_precious


def remote_shop_price(classification: str, sphere: int) -> int:
    """Gilder a remote item costs on a one-time shop shelf.

    Sphere 1 is the first set of checks reachable from the start. A
    progression item costs 100 gilder times that sphere, through sphere 4.
    Sphere 5 and later stay at 500. Useful items cost 250. Filler items cost
    100. Trap items cost 50.
    """
    if classification == "progression":
        if isinstance(sphere, bool) or not isinstance(sphere, int) or sphere < 1:
            raise PlacementError(f"Shop sphere {sphere!r} is not a sphere number.")
        return min(sphere, _PROGRESSION_PRICE_CAP_SPHERE) * 100
    if classification == "useful":
        return 250
    if classification == "filler":
        return 100
    if classification == "trap":
        return 50
    raise PlacementError(
        f"Remote shop classification {classification!r} is not progression, useful, filler, or trap."
    )


def _remote_classification(flags: int) -> str:
    if isinstance(flags, bool) or not isinstance(flags, int) or flags < 0:
        raise PlacementError(f"Remote item classification {flags!r} is not a flag value.")
    # One name, matching the reader. Progression outranks the other flags.
    if flags & _PROGRESSION:
        return "progression"
    if flags & _TRAP:
        return "trap"
    if flags & _USEFUL:
        return "useful"
    return "filler"


def remote_shop_price_for(flags: int, sphere: int) -> int:
    """Price a remote item from its Archipelago classification flags."""
    return remote_shop_price(_remote_classification(flags), sphere)


def _check_shop_price(price: object) -> int:
    if isinstance(price, bool) or not isinstance(price, int) or not 0 <= price <= _SHOP_PRICE_MAX:
        raise PlacementError(
            f"Remote shop price {price!r} must be an integer from 0 to {_SHOP_PRICE_MAX}."
        )
    return price


def _remote_text(text: object, limit: int, fallback: str) -> str:
    # Printable ASCII, no backslash. The disc and the reader both stop there.
    if not isinstance(text, str):
        raise PlacementError(f"Remote item {fallback.lower()} name must be a string.")
    kept = [character for character in text if 0x20 <= ord(character) <= 0x7E and character != "\\"]
    # Dropped characters can leave a double space. The disc line is short.
    cleaned = " ".join("".join(kept).split())
    if not cleaned:
        cleaned = fallback
    return cleaned[:limit]


def _encode_outside(placed: OutsidePlacement) -> dict:
    encoded: dict[str, str | int] = {
        "player": _remote_text(placed.player, _PLAYER_NAME_MAX, "Player"),
        "item": _remote_text(placed.item, _ITEM_NAME_MAX, "Item"),
        "classification": _remote_classification(placed.flags),
    }
    if placed.price is not None:
        encoded["price"] = _check_shop_price(placed.price)
    return encoded


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


def _check_location_ids(placements: dict[int, int | OutsidePlacement], game_data: GameData) -> None:
    expected = {source.id for source in game_data.sources}
    got = set(placements)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise PlacementError(f"Placement locations do not match item sources. Missing {missing}, extra {extra}.")


def _encode_placements(
    placements: dict[int, int | OutsidePlacement], game_data: GameData,
) -> tuple[dict[str, int | dict], Counter[str]]:
    # Location ids become the placement map. In-game items are counted for
    # itemsDistribution. Another slot's item is an object and is not counted.
    counted: Counter[str] = Counter()
    encoded: dict[str, int | dict] = {}
    for location_id in sorted(placements):
        placed = placements[location_id]
        if isinstance(placed, OutsidePlacement):
            if placed.price is not None:
                source = game_data.source_by_id[location_id]
                if not remote_shop_price_applies(
                    has_price=source.has_price, forbid_precious=source.forbid_precious,
                ):
                    raise PlacementError(
                        f"Location {location_id} ({source.pretty_name}) has a shop price "
                        "and is not a one-time shop shelf."
                    )
            encoded[str(location_id)] = _encode_outside(placed)
            continue
        if isinstance(placed, bool) or not isinstance(placed, int) or not 0 <= placed < ITEM_COUNT:
            raise PlacementError(f"Location {location_id} has item id {placed}, which is not a game item.")
        record = game_data.item_by_id[placed]
        counted[record.name] += 1
        encoded[str(location_id)] = placed
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
    placements: dict[int, int | OutsidePlacement],
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
    # A remote item selects the Multiworld format. Otherwise the file stays the Alundra format.
    remote = any(isinstance(placed, OutsidePlacement) for placed in placements.values())
    return {
        "format": FORMAT_MULTIWORLD if remote else FORMAT_ALUNDRA,
        "seed": settings.seed,
        "gameSettings": _game_settings(settings),
        "randomizerSettings": _randomizer_settings(settings, inventory, counted),
        "placements": encoded,
    }


def write_placement(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=4) + "\n", encoding="utf-8")
