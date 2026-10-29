"""Placement seed map. --placement-in reads this and patches the disc.

This world always writes the Multiworld format. That file names this
slot, the seed, and version information which the randomizer embeds as a
slot block that the client uses to log in:

    "format": 2, "apworldVersion": "0.1.9", "player": "YourName", "seed": 1

apworldVersion is world_version from archipelago.json. player is this slot's
login name, kept whole. It is not the shortened player on a remote placement.

A remote placement has these keys:

    {"player": "Player", "item": "Key Item", "classification": "progression"}

player is 1..16 printable ASCII characters and item is 1..28, with no backslash.
classification is progression, useful, filler, or trap. A one-time shop shelf
also records price, the gilder that shelf charges. itemsDistribution counts
only the in-game ids. This slot's own items stay those ids.

The randomizer's own --placement-out writes the Alundra format ("format": 1).
That file is only in-game item ids and does not carry apworldVersion or player.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
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
# The JSON field is numeric. This world writes the Multiworld format. The
# randomizer's own --placement-out writes the Alundra format.
FORMAT_ALUNDRA = 1
FORMAT_MULTIWORLD = 2
# world_version in archipelago.json. Three numeric components, nothing else.
_APWORLD_VERSION = re.compile(r"\d+\.\d+\.\d+")


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


def pinned_randomizer_version() -> str:
    """Return the alundra-randomizer release this world was built against.

    randomizer.lock.json names that release. The slot block in a patched disc
    carries the same string, and the client requires them to match.
    """
    resource = files(__package__).joinpath("randomizer.lock.json")
    try:
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PlacementError(
            "randomizer.lock.json is missing, so this world has no randomizer release."
        ) from error
    try:
        pin = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlacementError(f"randomizer.lock.json is malformed: {error}") from error
    version = pin.get("version") if isinstance(pin, dict) else None
    if not isinstance(version, str) or _APWORLD_VERSION.fullmatch(version) is None:
        raise PlacementError(
            f"version {version!r} in randomizer.lock.json must be major.minor.patch."
        )
    return version


def apworld_version() -> str:
    """Return world_version from archipelago.json, the version that writes the file."""
    resource = files(__package__).joinpath("archipelago.json")
    try:
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PlacementError(
            "archipelago.json is missing, so the placement file has no apworld version."
        ) from error
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlacementError(f"archipelago.json is malformed: {error}") from error
    version = manifest.get("world_version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or _APWORLD_VERSION.fullmatch(version) is None:
        raise PlacementError(
            f"world_version {version!r} in archipelago.json must be major.minor.patch."
        )
    return version


def _check_slot_player(player: object) -> str:
    """Return this slot's login name.

    The room matches this string unchanged. It is not run through the disc-line
    limit that shortens a remote placement's player.
    """
    if not isinstance(player, str) or not player.strip():
        raise PlacementError("The Multiworld placement file needs this slot's player name.")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in player):
        raise PlacementError("The slot player name cannot contain a control character.")
    return player


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
    *,
    player: str | None = None,
) -> dict:
    """Return the Multiworld placement document --placement-in accepts.

    The file always records apworldVersion and this slot's player beside seed,
    so a disc patched from it can log in. A file of only in-game item ids is
    still that format. The randomizer writes the Alundra format itself.
    """
    _check_seed(settings.seed)
    _check_location_ids(placements, game_data)
    encoded, counted = _encode_placements(placements, game_data)
    _check_distribution_counts(counted)
    inventory = _starting_inventory(starting_inventory, game_data)
    _check_required_starting_items(inventory)
    return {
        "format": FORMAT_MULTIWORLD,
        "apworldVersion": apworld_version(),
        "player": _check_slot_player(player),
        "seed": settings.seed,
        "gameSettings": _game_settings(settings),
        "randomizerSettings": _randomizer_settings(settings, inventory, counted),
        "placements": encoded,
    }


def write_placement(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=4) + "\n", encoding="utf-8")
