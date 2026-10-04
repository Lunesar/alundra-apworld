"""Load the logic JSON shipped in this world's data directory.

Those five files are copies of the Alundra randomizer's logic data. The two
repositories must not diverge. Edit the files in the randomizer, then copy
them here. Do not edit the copies in this repository.

    src/game/data/item.json          -> data/item.json
    src/model/data/item_source.json  -> data/item_source.json
    src/model/data/world_node.json   -> data/world_node.json
    src/model/data/world_path.json   -> data/world_path.json
    src/model/data/world_region.json -> data/world_region.json
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ITEM_COUNT = 0x5A
ITEM_ID_BASE = 800000
UPGRADE_TIER = 64
GILDED_FALCON_ID = 0x4F

SPAWN_NODE = "inoa"
END_NODE = "end"
LAKE_ORIGIN = "overworld_b1"
LAKE_DESTINATION = "lake_shrine_exterior"
MELZAS_NODE = "melzas_fight"

# Crest names. prePlacedCrests in the placement file uses this order.
CRESTS: tuple[str, ...] = (
    "Ruby Crest",
    "Sapphire Crest",
    "Topaz Crest",
    "Agate Crest",
    "Emerald Crest",
    "Garnet Crest",
    "Diamond Crest",
)

CREST_NODES: dict[str, str] = {
    "Ruby Crest": "crest_ruby",
    "Sapphire Crest": "crest_sapphire",
    "Topaz Crest": "crest_topaz",
    "Agate Crest": "crest_agate",
    "Emerald Crest": "crest_emerald",
    "Garnet Crest": "crest_garnet",
    "Diamond Crest": "crest_diamond",
}

REQUIRED_STARTING_ITEMS: tuple[str, ...] = ("Dagger", "Cloth Armor", "Short Boots")

# release_package/presets/default.json. Crests are not in this table; the
# randomizer adds the rolled crests on top.
DEFAULT_DISTRIBUTION: dict[str, int] = {
    "Herbs": 60,
    "Strength Tonic": 14,
    "Strength Elixyr": 9,
    "Magic Elixyr": 9,
    "Wonder Essence": 7,
    "1 Gilder": 2,
    "5 Gilder": 8,
    "10 Gilder": 17,
    "30 Gilder": 24,
    "Life Vessel": 40,
    "Magic Seed": 4,
    "Gilded Falcon": 50,
    "Sword": 1,
    "Fiend Blade": 1,
    "Holy Sword": 1,
    "Legend Sword": 1,
    "Iron Flail": 1,
    "Steel Flail": 1,
    "Hunter's Bow": 1,
    "Willow Bow": 1,
    "Olga's Ring": 1,
    "Silver Armlet": 1,
    "Recovery Ring": 1,
    "Nava's Charm": 1,
    "Spirit Wand": 1,
    "Long Boots": 1,
    "Merman Boots": 1,
    "Charm Boots": 1,
    "Leather Armor": 1,
    "Ancient Armor": 1,
    "Silver Armor": 1,
    "Fire Wand": 1,
    "Ice Wand": 1,
    "Bomb": 1,
    "Spring Bean": 1,
    "Sand Cape": 1,
    "Aqua Cape": 1,
    "Power Glove": 1,
    "Secret Pass": 1,
    "Tree Gem": 1,
    "Bouquet": 1,
    "Broken Armor": 1,
    "Small Key": 1,
    "Sluice Key": 1,
    "Earth Scroll": 1,
    "Earth Book": 1,
    "Water Scroll": 1,
    "Water Book": 1,
    "Fire Scroll": 1,
    "Fire Book": 1,
    "Wind Scroll": 1,
    "Wind Book": 1,
}

DEFAULT_FIXED_LOCATIONS: tuple[tuple[str, str], ...] = (
    ("Merrick's Shop: Item traded for 50 Gilded Falcons (Spirit Wand)", "Spirit Wand"),
)

DEFAULT_NON_PROGRESSION_LOCATIONS: tuple[str, ...] = (
    "Riverside Casino: 'Wheel of Fortune' second reward (Gilded Falcon)",
    "Riverside Casino: 'Hit Your Mark' second reward (Gilded Falcon)",
    "Riverside Casino: 'Slime Smash' second reward (Gilded Falcon)",
    "Merrick's Shop: Item traded for 40 Gilded Falcons (Recovery Ring)",
    "Merrick's Shop: Item traded for 45 Gilded Falcons (Life Vessel)",
)

DEFEAT_MELZAS = "Defeat Melzas"

_ITEM_KEYS = {"name", "maxQuantity", "goldValue", "slot", "tier", "precious"}
_SOURCE_KEYS = {
    "id", "name", "nodeId", "address", "spriteAddress", "priceAddress",
    "merrickItemAddress", "hints", "vanillaItem", "forbidPreciousItems",
}
_NODE_KEYS = {"hints", "graphPos", "shouldHaveUniqueItems"}
_PATH_KEYS = {"fromId", "toId", "twoWay", "requiredNodes", "requiredItems", "weight"}
_REGION_KEYS = {"name", "nodeIds", "hintName", "canBeHintedAsRequired"}


class AlundraDataError(Exception):
    pass


@dataclass(frozen=True)
class ItemRecord:
    in_game_id: int
    name: str
    slot_id: int
    tier: int
    gold_value: int
    precious: bool
    max_quantity: int

    @property
    def ap_id(self) -> int:
        return ITEM_ID_BASE + self.in_game_id


@dataclass(frozen=True)
class ItemSourceRecord:
    id: int
    name: str
    pretty_name: str
    node_id: str
    vanilla_item: str | None
    forbid_precious: bool
    has_price: bool
    has_merrick: bool
    region_name: str


@dataclass(frozen=True)
class NodeRecord:
    id: str
    should_have_unique_items: bool
    region_name: str


@dataclass(frozen=True)
class PathRecord:
    origin: str
    destination: str
    two_way: bool
    # One entry per required copy, before the progressive-item transform.
    required_items: tuple[str, ...]
    required_nodes: tuple[str, ...]


@dataclass(frozen=True)
class RegionRecord:
    name: str
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class GameData:
    items: tuple[ItemRecord, ...]
    item_by_name: dict[str, ItemRecord]
    item_by_id: dict[int, ItemRecord]
    sources: tuple[ItemSourceRecord, ...]
    source_by_id: dict[int, ItemSourceRecord]
    source_by_pretty_name: dict[str, ItemSourceRecord]
    nodes: dict[str, NodeRecord]
    paths: tuple[PathRecord, ...]
    regions: tuple[RegionRecord, ...]


def visited_item_name(node_id: str) -> str:
    return f"Visited {node_id}"


def logic_data_directory() -> Path:
    directory = Path(__file__).resolve().parent / "data"
    marker = directory / "item_source.json"
    if not marker.is_file():
        raise AlundraDataError(
            f"Logic data is missing: {marker}. Copy it from the randomizer's "
            "src/model/data/item_source.json."
        )
    return directory


def _load_json(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise AlundraDataError(f"Logic data file is missing: {path}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise AlundraDataError(f"Malformed JSON in {path}: {error}") from error


def _reject_unknown(kind: str, label: str, keys: set[str], allowed: set[str]) -> None:
    unknown = keys - allowed
    if unknown:
        raise AlundraDataError(f"Unknown {kind} key(s) on {label}: {sorted(unknown)}")


def _parse_required_items(value, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AlundraDataError(f"Path {label} requiredItems must be a list.")
    names: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            names.append(entry)
            continue
        if isinstance(entry, dict):
            _reject_unknown("required item", label, set(entry), {"name", "quantity"})
            if "name" not in entry or "quantity" not in entry:
                raise AlundraDataError(f"Path {label} required item objects need name and quantity.")
            quantity = entry["quantity"]
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                raise AlundraDataError(f"Path {label} item quantity must be a positive integer.")
            names.extend([entry["name"]] * quantity)
            continue
        raise AlundraDataError(f"Path {label} has a required item that is not a name or object.")
    return tuple(names)


def _parse_items(items_json) -> tuple[tuple[ItemRecord, ...], dict[str, ItemRecord]]:
    if not isinstance(items_json, list) or len(items_json) != ITEM_COUNT:
        raise AlundraDataError(
            f"item.json must contain {ITEM_COUNT} entries (item ids 0 through {ITEM_COUNT - 1})."
        )

    items: list[ItemRecord] = []
    item_by_name: dict[str, ItemRecord] = {}
    for in_game_id, entry in enumerate(items_json):
        if not isinstance(entry, dict) or "name" not in entry:
            raise AlundraDataError(f"Item {in_game_id} is missing a name.")
        _reject_unknown("item", entry["name"], set(entry), _ITEM_KEYS)
        record = ItemRecord(
            in_game_id=in_game_id,
            name=entry["name"],
            slot_id=int(entry.get("slot", 0)),
            tier=int(entry.get("tier", 0)),
            gold_value=int(entry.get("goldValue", 0)),
            precious=bool(entry.get("precious", False)),
            max_quantity=int(entry.get("maxQuantity", 1)),
        )
        if record.name in item_by_name:
            raise AlundraDataError(f"Duplicate item name '{record.name}'.")
        item_by_name[record.name] = record
        items.append(record)

    if items[-1].name != "Curious Key":
        raise AlundraDataError("The last item in item.json is not Curious Key. ITEM_COUNT would disagree.")
    return tuple(items), item_by_name


def _parse_regions(regions_json) -> tuple[tuple[RegionRecord, ...], dict[str, str]]:
    if not isinstance(regions_json, list):
        raise AlundraDataError("world_region.json must be a list.")
    regions: list[RegionRecord] = []
    node_regions: dict[str, str] = {}
    for entry in regions_json:
        _reject_unknown("region", str(entry.get("name")), set(entry), _REGION_KEYS)
        name = entry["name"]
        node_ids = tuple(entry["nodeIds"])
        for node_id in node_ids:
            if node_id in node_regions:
                raise AlundraDataError(f"Node '{node_id}' is in more than one region.")
            node_regions[node_id] = name
        regions.append(RegionRecord(name=name, node_ids=node_ids))
    return tuple(regions), node_regions


def _parse_nodes(nodes_json, node_regions: dict[str, str]) -> dict[str, NodeRecord]:
    if not isinstance(nodes_json, dict):
        raise AlundraDataError("world_node.json must be an object keyed by node id.")
    nodes: dict[str, NodeRecord] = {}
    for node_id, entry in nodes_json.items():
        _reject_unknown("node", node_id, set(entry), _NODE_KEYS)
        region_name = node_regions.get(node_id)
        if region_name is None:
            raise AlundraDataError(f"Node '{node_id}' does not belong to any region.")
        nodes[node_id] = NodeRecord(
            id=node_id,
            should_have_unique_items=bool(entry.get("shouldHaveUniqueItems", False)),
            region_name=region_name,
        )
    for node_id in node_regions:
        if node_id not in nodes:
            raise AlundraDataError(f"Region lists unknown node '{node_id}'.")
    return nodes


def _parse_item_sources(
    sources_json,
    nodes: dict[str, NodeRecord],
    item_by_name: dict[str, ItemRecord],
) -> tuple[tuple[ItemSourceRecord, ...], dict[int, ItemSourceRecord], dict[str, ItemSourceRecord]]:
    if not isinstance(sources_json, list):
        raise AlundraDataError("item_source.json must be a list.")
    sources: list[ItemSourceRecord] = []
    source_by_id: dict[int, ItemSourceRecord] = {}
    source_by_pretty_name: dict[str, ItemSourceRecord] = {}
    for entry in sources_json:
        label = str(entry.get("name", "<unnamed>"))
        _reject_unknown("item source", label, set(entry), _SOURCE_KEYS)
        source_id = entry.get("id")
        if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0:
            raise AlundraDataError(f"Item source '{label}' needs a positive integer id.")
        node_id = entry.get("nodeId")
        if node_id not in nodes:
            raise AlundraDataError(f"Item source '{label}' is in unknown node '{node_id}'.")
        vanilla = entry.get("vanillaItem")
        if vanilla is not None and vanilla not in item_by_name:
            raise AlundraDataError(f"Item source '{label}' has unknown vanilla item '{vanilla}'.")
        pretty = f"{label} ({vanilla})" if vanilla else label
        source = ItemSourceRecord(
            id=source_id,
            name=label,
            pretty_name=pretty,
            node_id=node_id,
            vanilla_item=vanilla,
            forbid_precious=bool(entry.get("forbidPreciousItems", False)),
            has_price="priceAddress" in entry,
            has_merrick="merrickItemAddress" in entry,
            region_name=nodes[node_id].region_name,
        )
        if source_id in source_by_id:
            raise AlundraDataError(f"Duplicate item source id {source_id}.")
        if pretty in source_by_pretty_name:
            raise AlundraDataError(f"Duplicate item source name '{pretty}'.")
        source_by_id[source_id] = source
        source_by_pretty_name[pretty] = source
        sources.append(source)
    return tuple(sources), source_by_id, source_by_pretty_name


def _parse_paths(
    paths_json,
    nodes: dict[str, NodeRecord],
    item_by_name: dict[str, ItemRecord],
) -> tuple[PathRecord, ...]:
    if not isinstance(paths_json, list):
        raise AlundraDataError("world_path.json must be a list.")
    paths: list[PathRecord] = []
    for entry in paths_json:
        origin = entry.get("fromId")
        destination = entry.get("toId")
        label = f"{origin} -> {destination}"
        _reject_unknown("path", label, set(entry), _PATH_KEYS)
        if origin not in nodes or destination not in nodes:
            raise AlundraDataError(f"Path {label} references a node that does not exist.")
        required_nodes = tuple(entry.get("requiredNodes", []))
        for node_id in required_nodes:
            if node_id not in nodes:
                raise AlundraDataError(f"Path {label} requires unknown node '{node_id}'.")
        required_items = _parse_required_items(entry.get("requiredItems", []), label)
        for item_name in required_items:
            if item_name not in item_by_name:
                raise AlundraDataError(f"Path {label} requires unknown item '{item_name}'.")
        paths.append(PathRecord(
            origin=origin,
            destination=destination,
            two_way=bool(entry.get("twoWay", False)),
            required_items=required_items,
            required_nodes=required_nodes,
        ))
    return tuple(paths)


def _check_builtin_references(
    item_by_name: dict[str, ItemRecord],
    source_by_pretty_name: dict[str, ItemSourceRecord],
    nodes: dict[str, NodeRecord],
) -> None:
    # The preset tables and the named graph anchors must exist in the loaded data.
    for item_name in DEFAULT_DISTRIBUTION:
        if item_name not in item_by_name:
            raise AlundraDataError(f"Default distribution lists unknown item '{item_name}'.")
    for pretty, item_name in DEFAULT_FIXED_LOCATIONS:
        if pretty not in source_by_pretty_name:
            raise AlundraDataError(f"Default fixed location '{pretty}' does not exist.")
        if item_name not in item_by_name:
            raise AlundraDataError(f"Default fixed item '{item_name}' does not exist.")
    for pretty in DEFAULT_NON_PROGRESSION_LOCATIONS:
        if pretty not in source_by_pretty_name:
            raise AlundraDataError(f"Default non-progression location '{pretty}' does not exist.")
    for item_name in CRESTS:
        if item_name not in item_by_name or CREST_NODES[item_name] not in nodes:
            raise AlundraDataError(f"Crest '{item_name}' is missing from items or nodes.")
    if SPAWN_NODE not in nodes or END_NODE not in nodes:
        raise AlundraDataError("Spawn node 'inoa' or end node 'end' is missing.")


def load_game_data(directory: Path | None = None) -> GameData:
    directory = directory or logic_data_directory()
    items, item_by_name = _parse_items(_load_json(directory / "item.json"))
    regions, node_regions = _parse_regions(_load_json(directory / "world_region.json"))
    nodes = _parse_nodes(_load_json(directory / "world_node.json"), node_regions)
    sources, source_by_id, source_by_pretty_name = _parse_item_sources(
        _load_json(directory / "item_source.json"), nodes, item_by_name,
    )
    paths = _parse_paths(_load_json(directory / "world_path.json"), nodes, item_by_name)
    _check_builtin_references(item_by_name, source_by_pretty_name, nodes)
    return GameData(
        items=items,
        item_by_name=item_by_name,
        item_by_id={item.in_game_id: item for item in items},
        sources=sources,
        source_by_id=source_by_id,
        source_by_pretty_name=source_by_pretty_name,
        nodes=nodes,
        paths=paths,
        regions=regions,
    )


def exposed_item_records(game_data: GameData) -> tuple[ItemRecord, ...]:
    # Items a player can name in a YAML. Unused 'Item 0xNN' rows stay internal.
    return tuple(
        item for item in game_data.items
        if item.in_game_id == 0 or not item.name.startswith("Item 0x")
    )


def item_name_to_id_map(game_data: GameData) -> dict[str, int]:
    return {item.name: item.ap_id for item in exposed_item_records(game_data)}


def location_name_to_id_map(game_data: GameData) -> dict[str, int]:
    return {source.pretty_name: source.id for source in game_data.sources}


def location_groups(game_data: GameData) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for source in game_data.sources:
        grouped.setdefault(source.region_name, set()).add(source.pretty_name)
    return grouped


def item_groups(game_data: GameData) -> dict[str, set[str]]:
    exposed = {item.name for item in exposed_item_records(game_data)}

    def names_in_slots(slots: set[int]) -> set[str]:
        return {
            item.name for item in game_data.items
            if item.slot_id in slots and item.name in exposed and item.in_game_id != 0
        }

    groups = {
        "Crests": set(CRESTS),
        "Weapons": names_in_slots({1, 2, 3, 4, 5, 6}),
        "Armor": names_in_slots({7}),
        "Boots": names_in_slots({9}),
        "Spells": names_in_slots({16, 17, 18, 19}),
        "Gilded Falcons": {"Gilded Falcon"},
    }
    for group, names in groups.items():
        missing = names - exposed
        if missing:
            raise AlundraDataError(f"Item group {group} names missing items {sorted(missing)}.")
    return groups


def distribution_counter() -> Counter[str]:
    return Counter(DEFAULT_DISTRIBUTION)


GAME_DATA = load_game_data()
ITEM_NAME_TO_ID = item_name_to_id_map(GAME_DATA)
LOCATION_NAME_TO_ID = location_name_to_id_map(GAME_DATA)
LOCATION_NAME_GROUPS = location_groups(GAME_DATA)
ITEM_NAME_GROUPS = item_groups(GAME_DATA)
