"""Archipelago world for Alundra.

Generation writes a placement seed map. The Alundra randomizer reads that file
with --placement-in and patches a USA 1.1 disc. This world does not patch the
disc. The BizHawk client logs in to a room, reports chests whose event
code is known, and grants an item sent from another game.

Another slot's item may be placed on an Alundra check. The placement file
records that item as an object. A one-time shop shelf also records the gilder
it charges. This slot's own items stay in-game item ids. The Multiworld format
also records this slot's player name and the apworld version beside the seed.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from BaseClasses import CollectionState, Item, ItemClassification, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

# Register AlundraClient with BizHawkClient
from . import client
from .data import (
    GAME_DATA,
    CREST_NODES,
    CRESTS,
    DEFEAT_MELZAS,
    GILDED_FALCON_ID,
    ITEM_ID_BASE,
    ITEM_NAME_GROUPS,
    ITEM_NAME_TO_ID,
    LOCATION_NAME_GROUPS,
    LOCATION_NAME_TO_ID,
    REQUIRED_STARTING_ITEMS,
    SPAWN_NODE,
    ItemSourceRecord,
    visited_item_name,
)
from .items import AlundraItem, AlundraLocation, classification_for
from .logic import (
    END_NODE,
    LogicError,
    LogicGraph,
    LogicSettings,
    build_graph,
    choose_active_crests,
    build_item_pool,
    choose_restock_locks,
    fixed_location_map,
    folded_item_names,
)
from .options import AlundraOptions, option_groups
from .placement import (
    OutsidePlacement,
    forbid_progression,
    allows_outside_item,
    remote_shop_price_applies,
    remote_shop_price_for,
    build_placement_document,
    write_placement,
)

logger = logging.getLogger("Archipelago")


class AlundraWebWorld(WebWorld):
    theme = "grass"
    rich_text_options_doc = True
    option_groups = option_groups
    tutorials = [Tutorial(
        "Setup Guide",
        "Generate a placement file, patch a USA 1.1 disc, and connect the BizHawk client.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Alundra randomizer"],
    )]
    options_presets = {
        "Default": {
            "progressive_items": True,
            "split_boots_effects": True,
            "skip_last_dungeon": True,
            "crest_count": 7,
            "original_game_balance": True,
            "megaliths_enabled_on_start": True,
            "king_snow_death_count": 0,
            "casino_win_count_for_last_reward": 1,
            "starting_health": 10,
            "starting_mana": 0,
            "starting_gold": 0,
            "allow_spoiler_log": True,
            "restocking_shop_items": "full_variety",
            "start_inventory": {
                "Dagger": 1,
                "Cloth Armor": 1,
                "Short Boots": 1,
            },
        }
    }


class AlundraWorld(World):
    """Placement file for the Alundra randomizer. A check can hold another slot's item."""

    game = "Alundra"
    web = AlundraWebWorld()
    options_dataclass = AlundraOptions
    options: AlundraOptions

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_NAME_GROUPS
    location_name_groups = LOCATION_NAME_GROUPS

    origin_region_name = SPAWN_NODE
    topology_present = True

    _settings: LogicSettings
    _graph: LogicGraph
    _pool: list[str]
    _fixed: dict[str, str]

    def generate_early(self) -> None:
        settings = self._settings_from_options(self._placement_seed())
        active = choose_active_crests(self.random, settings.crest_count)
        settings = replace(settings, active_crests=active)
        try:
            # One roll. The pool drops one Herbs per locked shelf, and create_items
            # locks those same shelves.
            locks = choose_restock_locks(GAME_DATA, settings, self.random)
            self._settings = replace(settings, restock_locks=tuple(sorted(locks.items())))
            self._graph = build_graph(GAME_DATA, self._settings)
            self._pool = build_item_pool(GAME_DATA, self._settings)
            self._fixed = fixed_location_map(self._settings)
        except LogicError as error:
            raise OptionError(str(error)) from error

    def create_regions(self) -> None:
        regions = self._create_node_regions()
        self._add_source_locations(regions)
        excluded_nodes = {CREST_NODES[name] for name in self.logic_graph.excluded_crests}
        self._add_visit_events(regions, excluded_nodes)
        self._connect_edges(regions, excluded_nodes)

    def _create_node_regions(self) -> dict[str, Region]:
        regions = {
            node_id: Region(node_id, self.player, self.multiworld)
            for node_id in GAME_DATA.nodes
        }
        self.multiworld.regions.extend(regions.values())
        return regions

    def _add_source_locations(self, regions: dict[str, Region]) -> None:
        for source in GAME_DATA.sources:
            region = regions[source.node_id]
            location = AlundraLocation(self.player, source.pretty_name, source.id, region)
            location.source_id = source.id
            region.locations.append(location)

    def _add_visit_events(self, regions: dict[str, Region], excluded_nodes: set[str]) -> None:
        # Pre-placed crests are already on their pedestals. Nothing checks those nodes,
        # and the item that would open them is not in the pool.
        for node_id, region in regions.items():
            if node_id in excluded_nodes:
                continue
            region.add_event(
                visited_item_name(node_id),
                visited_item_name(node_id),
                location_type=AlundraLocation,
                item_type=AlundraItem,
                show_in_spoiler=False,
            )

        regions[END_NODE].add_event(
            DEFEAT_MELZAS,
            DEFEAT_MELZAS,
            location_type=AlundraLocation,
            item_type=AlundraItem,
        )

    def _connect_edges(self, regions: dict[str, Region], excluded_nodes: set[str]) -> None:
        used_names: set[str] = set()
        # Two JSON paths with the same ends are alternatives, such as Bomb or Fire Wand.
        # Each one stays its own entrance so either requirement is enough.
        for edge in self.logic_graph.edges:
            if edge.origin in excluded_nodes or edge.destination in excluded_nodes:
                continue
            name = self._entrance_name(edge.origin, edge.destination, used_names)
            regions[edge.origin].connect(regions[edge.destination], name, self._access_rule(edge))

    def _entrance_name(self, origin: str, destination: str, used_names: set[str]) -> str:
        base = f"{origin} -> {destination}"
        name = base
        suffix = 2
        while name in used_names:
            name = f"{base} #{suffix}"
            suffix += 1
        used_names.add(name)
        return name

    def create_items(self) -> None:
        owned = self._precollected_counts()
        for name in REQUIRED_STARTING_ITEMS:
            if owned[name] == 0:
                self.multiworld.push_precollected(self.create_item(name))
                owned[name] = 1
        self._warn_progressive_start(owned)

        for pretty_name, item_name in self._fixed.items():
            location = self.multiworld.get_location(pretty_name, self.player)
            location.place_locked_item(self.create_item(item_name))

        # The same shelves the pool closed. A full-variety roll is already stored.
        locks = self._settings.restock_locks or ()
        for pretty_name, item_name in locks:
            location = self.multiworld.get_location(pretty_name, self.player)
            location.place_locked_item(self.create_item(item_name))

        self.multiworld.itempool += [self.create_item(name) for name in self._pool]

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = (
            lambda state: state.has(DEFEAT_MELZAS, self.player)
        )
        for location in self.multiworld.get_locations(self.player):
            if location.address is None:
                continue
            source = GAME_DATA.source_by_id[location.address]
            location.item_rule = self._item_rule_for(source)

    def get_filler_item_name(self) -> str:
        return "Herbs"

    def _unreported_locations(self) -> list:
        found = []
        for location in self.multiworld.get_locations(self.player):
            source_id = getattr(location, "source_id", None)
            if source_id is None:
                continue
            if GAME_DATA.source_by_id[source_id].forbid_precious:
                found.append(location)
        return found

    def pre_fill(self) -> None:
        # Same item rules as every other source. These are filled first so they
        # can stay out of the world's location list. A shelf locked to its retail
        # item is already filled, so the fill leaves it alone.
        locations = [
            location for location in self._unreported_locations()
            if location.item is None
        ]
        if not locations:
            return
        from Fill import fill_restrictive
        fill_restrictive(
            self.multiworld,
            self.multiworld.state,
            locations,
            self.multiworld.itempool,
            name="Alundra unreported",
        )

    def pre_output(self) -> None:
        # The fill has already placed an item. These sources cannot be reported,
        # so they are not part of the room's check list.
        for location in self.multiworld.get_locations(self.player):
            source_id = getattr(location, "source_id", None)
            if source_id is None:
                continue
            if GAME_DATA.source_by_id[source_id].forbid_precious:
                location.address = None

    def _accessibility_spheres(self) -> dict[int, int]:
        """1-based sphere of each of this slot's sendable checks.

        This is the sweep the room's sphere tracker stores. Events, including
        the visit items on each node, are collected before the checks that
        open in the same step. An empty yield is the gap before unreachable
        checks, and those checks take the next number.
        """
        spheres: dict[int, int] = {}
        number = 0
        for sphere in self.multiworld.get_sendable_spheres():
            if not sphere:
                continue
            number += 1
            for location in sphere:
                if location.player != self.player:
                    continue
                source_id = getattr(location, "source_id", None)
                if source_id is None:
                    continue
                spheres[source_id] = number
        return spheres

    def generate_output(self, output_directory: str) -> None:
        # pre_output has already cleared the shelves that are not checks, so
        # this sweep matches the sphere list written for the room.
        spheres = self._accessibility_spheres()
        placements: dict[int, int | OutsidePlacement] = {}
        for location in self.multiworld.get_locations(self.player):
            source_id = getattr(location, "source_id", None)
            if source_id is None:
                continue
            item = location.item
            if item is None:
                raise RuntimeError(f"Alundra location '{location.name}' has no item.")
            native_id = self._native_item_id(item)
            if native_id is not None:
                placements[source_id] = native_id
                continue
            if item.player == self.player:
                raise RuntimeError(
                    f"Alundra location '{location.name}' holds {item.name}, which is not an Alundra item."
                )
            source = GAME_DATA.source_by_id[source_id]
            if source.forbid_precious:
                raise RuntimeError(
                    f"Alundra location '{location.name}' holds {item.name} for player {item.player}. "
                    "A check that refuses a precious item also refuses a remote item."
                )
            placements[source_id] = self._outside_placement(item, source, spheres.get(source_id))

        # Recorded only on the Multiworld format. The Alundra format leaves both out.
        document = build_placement_document(
            self._settings,
            placements,
            self._precollected_names(),
            player=self.multiworld.get_player_name(self.player),
        )
        filename = f"{self.multiworld.get_out_file_name_base(self.player)}.alundra.json"
        write_placement(Path(output_directory) / filename, document)

    def fill_slot_data(self) -> dict[str, Any]:
        graph = self.logic_graph
        return {
            "seed": self._settings.seed,
            "crest_count": self._settings.crest_count,
            "crests": list(graph.active_crests),
            "progressive_items": self._settings.progressive_items,
            "split_boots_effects": self._settings.split_boots_effects,
            "skip_last_dungeon": self._settings.skip_last_dungeon,
            "item_id_base": ITEM_ID_BASE,
        }

    def write_spoiler(self, spoiler_handle) -> None:
        graph = self.logic_graph
        spoiler_handle.write(f"\nRequired crests ({len(graph.active_crests)}):\n")
        for name in graph.active_crests:
            spoiler_handle.write(f"  {name}\n")
        spoiler_handle.write("Pre-placed crests:\n")
        if graph.excluded_crests:
            for name in graph.excluded_crests:
                spoiler_handle.write(f"  {name}\n")
        else:
            spoiler_handle.write("  (none)\n")

    def extend_hint_information(self, hint_data: dict[int, dict[int, str]]) -> None:
        hint_data[self.player] = {source.id: source.region_name for source in GAME_DATA.sources}

    def create_item(self, name: str) -> AlundraItem:
        try:
            record = GAME_DATA.item_by_name[name]
        except KeyError as error:
            raise KeyError(f"Alundra has no item named {name}.") from error
        return AlundraItem(
            name,
            classification_for(name, self._progression_names()),
            record.ap_id,
            self.player,
            record.in_game_id,
        )

    @property
    def logic_graph(self) -> LogicGraph:
        graph = getattr(self, "_graph", None)
        if graph is not None:
            return graph
        settings = getattr(self, "_settings", None)
        if settings is None:
            settings = self._settings_from_options(self._placement_seed())
            # create_item can run before generate_early has chosen the crest subset.
            # Classification does not depend on which crests are active, and generate_early
            # replaces this graph once the slot's random choice exists.
            if settings.active_crests is None and settings.crest_count not in (0, len(CRESTS)):
                settings = replace(settings, crest_count=len(CRESTS))
        self._graph = build_graph(GAME_DATA, settings)
        return self._graph

    def _progression_names(self) -> frozenset[str]:
        # Item classification follows the rewritten logic. The crest subset does not change
        # which names appear on edges, so a seed of 0 matches a later generate_early graph.
        graph = getattr(self, "_graph", None)
        if graph is not None:
            return graph.progression_items
        if getattr(self, "options", None) is None:
            return build_graph(GAME_DATA, LogicSettings(seed=0)).progression_items
        return self.logic_graph.progression_items

    def _placement_seed(self) -> int:
        multiworld = getattr(self, "multiworld", None)
        seed = getattr(multiworld, "seed", None) if multiworld is not None else None
        if seed is None:
            return 0
        return int(seed) & 0xFFFFFFFF

    def _check_fixed_location(self, pretty: str, item_name: Any) -> None:
        if pretty not in GAME_DATA.source_by_pretty_name:
            raise OptionError(f"Fixed location '{pretty}' is not an Alundra location.")
        if not isinstance(item_name, str) or item_name not in GAME_DATA.item_by_name:
            raise OptionError(f"Fixed location '{pretty}' must name an Alundra item.")

    def _check_non_progression_location(self, pretty: str) -> None:
        if pretty not in GAME_DATA.source_by_pretty_name:
            raise OptionError(f"Non-progression location '{pretty}' is not an Alundra location.")

    def _settings_from_options(self, seed: int) -> LogicSettings:
        options = self.options
        fixed: list[tuple[str, str]] = []
        for pretty, item_name in options.fixed_item_sources.value.items():
            self._check_fixed_location(pretty, item_name)
            fixed.append((str(pretty), item_name))

        non_progression: list[str] = []
        for pretty in options.item_sources_without_progression.value:
            self._check_non_progression_location(pretty)
            non_progression.append(str(pretty))

        try:
            return LogicSettings(
                seed=seed & 0xFFFFFFFF,
                progressive_items=bool(options.progressive_items),
                split_boots_effects=bool(options.split_boots_effects),
                skip_last_dungeon=bool(options.skip_last_dungeon),
                crest_count=int(options.crest_count),
                original_game_balance=bool(options.original_game_balance),
                megaliths_enabled_on_start=bool(options.megaliths_enabled_on_start),
                king_snow_death_count=int(options.king_snow_death_count),
                casino_win_count_for_last_reward=int(options.casino_win_count_for_last_reward),
                starting_health=int(options.starting_health),
                starting_mana=int(options.starting_mana),
                starting_gold=int(options.starting_gold),
                allow_spoiler_log=bool(options.allow_spoiler_log),
                restocking_shop_items=options.restocking_shop_items.current_key,
                fixed_item_sources=tuple(fixed),
                non_progression_locations=tuple(sorted(non_progression)),
            )
        except LogicError as error:
            raise OptionError(str(error)) from error

    def _access_rule(self, edge):
        player = self.player
        items = dict(edge.requirement.items)
        nodes = tuple(visited_item_name(node_id) for node_id in edge.requirement.nodes)

        def rule(state: CollectionState) -> bool:
            if items and not state.has_all_counts(items, player):
                return False
            return all(state.has(name, player) for name in nodes)

        return rule

    def _item_rule_for(self, source: ItemSourceRecord):
        player = self.player
        progression = self.logic_graph.progression_items
        block_progression = source.pretty_name in self._settings.non_progression_locations
        forbid_precious = source.forbid_precious
        shop = source.has_price
        merrick = source.has_merrick

        def rule(item: Item) -> bool:
            # Events use a null code. Real items, including another slot's, have one.
            code = item.code
            if isinstance(code, bool) or not isinstance(code, int) or code <= 0:
                return False
            if item.player != player:
                return allows_outside_item(
                    block_progression=block_progression,
                    progression=bool(ItemClassification.progression & item.classification),
                    forbid_precious=forbid_precious,
                )
            if not isinstance(item, AlundraItem) or item.in_game_id is None:
                return False
            record = GAME_DATA.item_by_id.get(item.in_game_id)
            if record is None or record.name != item.name:
                return False
            if forbid_precious and record.precious:
                return False
            if shop and record.gold_value == 0:
                return False
            if merrick and record.in_game_id == GILDED_FALCON_ID:
                return False
            if forbid_progression(
                forbid_precious=forbid_precious,
                name=record.name,
                progression=progression,
            ):
                return False
            if block_progression and record.name in progression:
                return False
            return True

        return rule

    def _native_item_id(self, item: Item) -> int | None:
        # Another Alundra slot's item has an in-game id too. It belongs to that slot.
        if item.player != self.player or not isinstance(item, AlundraItem) or item.in_game_id is None:
            return None
        record = GAME_DATA.item_by_id.get(item.in_game_id)
        if record is None or record.name != item.name:
            return None
        return item.in_game_id

    def _outside_placement(
        self, item: Item, source: ItemSourceRecord, sphere: int | None,
    ) -> OutsidePlacement:
        code = item.code
        if isinstance(code, bool) or not isinstance(code, int) or code <= 0:
            raise RuntimeError(
                f"Item {item.name} for player {item.player} has no Archipelago item id."
            )
        flags = int(item.classification)
        price = None
        if remote_shop_price_applies(
            has_price=source.has_price, forbid_precious=source.forbid_precious,
        ):
            if sphere is None:
                raise RuntimeError(
                    f"Alundra location '{source.pretty_name}' has no accessibility sphere."
                )
            price = remote_shop_price_for(flags, sphere)
        return OutsidePlacement(
            player=self.multiworld.get_player_name(item.player),
            item=item.name,
            flags=flags,
            price=price,
        )

    def _precollected_counts(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for item in self.multiworld.precollected_items[self.player]:
            if isinstance(item, AlundraItem) and item.in_game_id is not None:
                counts[item.name] += 1
        repeated = sorted(name for name, count in counts.items() if count > 1)
        if repeated:
            raise OptionError(
                "Starting inventory can grant each Alundra item only once "
                f"(the new-game patch sets one bit per item). Repeated: {', '.join(repeated)}."
            )
        return counts

    def _precollected_names(self) -> list[str]:
        counts = self._precollected_counts()
        return [name for name in counts if counts[name]]

    def _warn_progressive_start(self, owned: Counter[str]) -> None:
        if not self._settings.progressive_items:
            return
        folded = folded_item_names(GAME_DATA, self._settings.split_boots_effects)
        skipped = set(REQUIRED_STARTING_ITEMS)
        warned = sorted(name for name in owned if name in folded and name not in skipped and owned[name])
        if not warned:
            return
        logger.warning(
            "Alundra progressive mode does not count starting %s as upgrades. "
            "The randomizer rewrites path requirements from the item pool, not from starting inventory.",
            ", ".join(warned),
        )
