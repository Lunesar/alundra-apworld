"""Logic graph and item pool, using the same transforms as RandomizerWorld::apply_options."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass

from .data import (
    CREST_NODES,
    CRESTS,
    DEFAULT_DISTRIBUTION,
    DEFAULT_FIXED_LOCATIONS,
    DEFAULT_NON_PROGRESSION_LOCATIONS,
    END_NODE,
    LAKE_DESTINATION,
    LAKE_ORIGIN,
    MELZAS_NODE,
    REQUIRED_STARTING_ITEMS,
    SPAWN_NODE,
    UPGRADE_TIER,
    AlundraDataError,
    GameData,
    ItemRecord,
)


class LogicError(AlundraDataError):
    pass


@dataclass(frozen=True)
class LogicSettings:
    seed: int = 0
    progressive_items: bool = True
    split_boots_effects: bool = True
    skip_last_dungeon: bool = True
    crest_count: int = 7
    # None means "no choice was supplied". Crest counts 0 and 7 need no choice.
    # Any other count must name the crests that are still in the pool.
    active_crests: tuple[str, ...] | None = None
    original_game_balance: bool = True
    megaliths_enabled_on_start: bool = True
    king_snow_death_count: int = 0
    casino_win_count_for_last_reward: int = 1
    starting_health: int = 10
    starting_mana: int = 0
    starting_gold: int = 0
    allow_spoiler_log: bool = True
    starting_inventory: tuple[str, ...] = REQUIRED_STARTING_ITEMS
    fixed_item_sources: tuple[tuple[str, str], ...] = DEFAULT_FIXED_LOCATIONS
    non_progression_locations: tuple[str, ...] = DEFAULT_NON_PROGRESSION_LOCATIONS


@dataclass(frozen=True)
class Requirement:
    items: tuple[tuple[str, int], ...]
    nodes: tuple[str, ...]

    @property
    def is_open(self) -> bool:
        return not self.items and not self.nodes


@dataclass(frozen=True)
class Edge:
    origin: str
    destination: str
    requirement: Requirement


@dataclass(frozen=True)
class LogicGraph:
    edges: tuple[Edge, ...]
    active_crests: tuple[str, ...]
    excluded_crests: tuple[str, ...]
    progression_items: frozenset[str]


@dataclass(frozen=True)
class _SlotGroup:
    upgrade_name: str
    members: tuple[ItemRecord, ...]


def resolve_active_crests(settings: LogicSettings) -> tuple[str, ...]:
    # Crests that must be found, in the standard crest order.
    # A count of 0 or 7 determines the set by itself. Any other count uses
    # settings.active_crests, which the world chose before writing the file.
    count = settings.crest_count
    if not 0 <= count <= len(CRESTS):
        raise LogicError(f"Crest count must be between 0 and {len(CRESTS)}.")
    if settings.active_crests is None:
        if count == len(CRESTS):
            return CRESTS
        if count == 0:
            return ()
        raise LogicError(
            "A crest count below 7 needs the chosen crest names. "
            "The placement file records the ones left on their pedestals."
        )
    if len(settings.active_crests) != count:
        raise LogicError(
            f"Crest count is {count}, but {len(settings.active_crests)} active crests were chosen."
        )
    unknown = [name for name in settings.active_crests if name not in CREST_NODES]
    if unknown:
        raise LogicError(f"Unknown crests: {', '.join(unknown)}.")
    if len(set(settings.active_crests)) != len(settings.active_crests):
        raise LogicError("The active crest list contains a duplicate.")
    chosen = set(settings.active_crests)
    return tuple(name for name in CRESTS if name in chosen)


def choose_active_crests(rng: random.Random, crest_count: int) -> tuple[str, ...]:
    # Each Archipelago slot passes its own rng.
    if crest_count in (0, len(CRESTS)):
        return resolve_active_crests(LogicSettings(crest_count=crest_count))
    if not 0 <= crest_count <= len(CRESTS):
        raise LogicError(f"Crest count must be between 0 and {len(CRESTS)}.")
    chosen = set(rng.sample(CRESTS, crest_count))
    return tuple(name for name in CRESTS if name in chosen)


def preplaced_crest_names(settings: LogicSettings) -> list[str]:
    # Crests already on their pedestals, in the standard crest order.
    active = set(resolve_active_crests(settings))
    return [name for name in CRESTS if name not in active]


def _slot_groups(game_data: GameData, split_boots: bool) -> tuple[_SlotGroup, ...]:
    by_slot: dict[int, list[ItemRecord]] = defaultdict(list)
    for item in game_data.items:
        if item.in_game_id == 0:
            continue
        by_slot[item.slot_id].append(item)

    groups: list[_SlotGroup] = []
    for slot_id, slot_items in by_slot.items():
        upgrades = [item for item in slot_items if item.tier == UPGRADE_TIER]
        if not upgrades:
            continue
        if len(upgrades) != 1:
            raise LogicError(f"Slot {slot_id} has more than one upgrade item.")
        upgrade = upgrades[0]
        # Boots stay individual items when their effects are split. The randomizer
        # only folds boots into Boots upgrade when splitBootsEffects is false.
        if split_boots and upgrade.name == "Boots upgrade":
            continue
        members = tuple(item for item in slot_items if item.tier != UPGRADE_TIER)
        groups.append(_SlotGroup(upgrade.name, members))
    return tuple(groups)


def convert_requirement(required: tuple[str, ...], groups: tuple[_SlotGroup, ...]) -> tuple[tuple[str, int], ...]:
    # One occurrence of each matching tier item is replaced by (tier + 1) upgrades.
    # This is RandomizerWorld::handle_progressive_items. A Holy Sword (tier 3) gate
    # becomes four Sword upgrades. The player already owns the tier-0 piece (Dagger,
    # Cloth Armor, Short Boots), and the in-game hook advances from that owned tier,
    # so the count is one higher than the number of pickups the hook needs.
    counts: Counter[str] = Counter(required)
    for group in groups:
        highest_tier = 0
        found = False
        for member in group.members:
            if counts[member.name] <= 0:
                continue
            counts[member.name] -= 1
            found = True
            highest_tier = max(highest_tier, member.tier + 1)
        if found:
            counts[group.upgrade_name] += highest_tier
    return tuple(sorted((name, count) for name, count in counts.items() if count > 0))


def convert_distribution(counts: Counter[str], groups: tuple[_SlotGroup, ...]) -> Counter[str]:
    # Move every copy of a tier item onto that slot's upgrade item.
    updated = Counter(counts)
    for group in groups:
        for member in group.members:
            amount = updated[member.name]
            if amount:
                updated[group.upgrade_name] += amount
                updated[member.name] -= amount
    return Counter({name: count for name, count in updated.items() if count > 0})


def _requirement_for(
    required_items: tuple[str, ...],
    required_nodes: tuple[str, ...],
    groups: tuple[_SlotGroup, ...] | None,
) -> Requirement:
    if groups is None:
        counts = Counter(required_items)
        items = tuple(sorted((name, count) for name, count in counts.items() if count > 0))
    else:
        items = convert_requirement(required_items, groups)
    return Requirement(items=items, nodes=tuple(required_nodes))


def build_graph(game_data: GameData, settings: LogicSettings) -> LogicGraph:
    active = resolve_active_crests(settings)
    excluded = tuple(name for name in CRESTS if name not in active)
    excluded_nodes = {CREST_NODES[name] for name in excluded}
    groups = _slot_groups(game_data, settings.split_boots_effects) if settings.progressive_items else None

    edges: list[Edge] = []
    present = {(path.origin, path.destination) for path in game_data.paths}
    lake_adjusted = False
    for path in game_data.paths:
        nodes = path.required_nodes
        if path.origin == LAKE_ORIGIN and path.destination == LAKE_DESTINATION and not lake_adjusted:
            # The first overworld_b1 -> lake_shrine_exterior edge is the crest gate.
            # Excluded crests are set on their pedestals at new game and drop out of the gate.
            nodes = tuple(node_id for node_id in nodes if node_id not in excluded_nodes)
            lake_adjusted = True
        requirement = _requirement_for(path.required_items, nodes, groups)
        edges.append(Edge(path.origin, path.destination, requirement))
        reverse = (path.destination, path.origin)
        if path.two_way and reverse not in present:
            edges.append(Edge(path.destination, path.origin, requirement))

    if not lake_adjusted:
        raise LogicError("Could not find the path from overworld_b1 to lake_shrine_exterior.")

    if settings.skip_last_dungeon:
        edges.append(Edge(LAKE_DESTINATION, MELZAS_NODE, Requirement((), ())))

    # Every crest stays progression, including ones pre-placed on a pedestal.
    # A plando or starting copy of an inactive crest still has to count as one.
    progression: set[str] = set(CRESTS)
    for edge in edges:
        for name, _count in edge.requirement.items:
            progression.add(name)

    return LogicGraph(
        edges=tuple(edges),
        active_crests=active,
        excluded_crests=excluded,
        progression_items=frozenset(progression),
    )


def folded_item_names(game_data: GameData, split_boots: bool) -> frozenset[str]:
    # Tier items that progressive mode rewrites. The upgrade item itself is not included.
    names: set[str] = set()
    for group in _slot_groups(game_data, split_boots):
        for member in group.members:
            names.add(member.name)
    return frozenset(names)


def fixed_location_map(settings: LogicSettings) -> dict[str, str]:
    fixed: dict[str, str] = {}
    for pretty_name, item_name in settings.fixed_item_sources:
        if pretty_name in fixed:
            raise LogicError(f"Location '{pretty_name}' is fixed twice.")
        fixed[pretty_name] = item_name
    return fixed


def _check_fixed_item(pretty_name: str, item_name: str, game_data: GameData, counts: Counter[str]) -> None:
    if pretty_name not in game_data.source_by_pretty_name:
        raise LogicError(f"Fixed location '{pretty_name}' is not an item source.")
    if item_name not in game_data.item_by_name:
        raise LogicError(f"Fixed item '{item_name}' does not exist.")
    if counts[item_name] <= 0:
        raise LogicError(
            f"Fixed location '{pretty_name}' wants a {item_name}, but the item pool has none left."
        )


def build_item_pool(game_data: GameData, settings: LogicSettings) -> list[str]:
    # Item names to submit to the multiworld pool, not counting locked locations.
    # The length is the number of item sources minus locked placements. Extra copies
    # are Herbs. Herbs can sit in a shop; Nothing cannot, because its gold value is 0.
    active = resolve_active_crests(settings)
    groups = _slot_groups(game_data, settings.split_boots_effects) if settings.progressive_items else None
    counts = Counter(DEFAULT_DISTRIBUTION)
    if groups is not None:
        counts = convert_distribution(counts, groups)
    for crest in active:
        counts[crest] += 1

    fixed = fixed_location_map(settings)
    for pretty_name, item_name in fixed.items():
        _check_fixed_item(pretty_name, item_name, game_data, counts)
        counts[item_name] -= 1

    for pretty_name in settings.non_progression_locations:
        if pretty_name not in game_data.source_by_pretty_name:
            raise LogicError(f"Non-progression location '{pretty_name}' is not an item source.")

    pool: list[str] = []
    for name, count in sorted(counts.items()):
        if count < 0:
            raise LogicError(f"Item pool count for {name} went negative.")
        pool.extend([name] * count)

    empty_locations = len(game_data.sources) - len(fixed)
    if len(pool) > empty_locations:
        raise LogicError(
            f"Item pool has {len(pool)} items for {empty_locations} open locations."
        )
    pool.extend(["Herbs"] * (empty_locations - len(pool)))
    return pool


def explore(graph: LogicGraph, inventory: Counter[str], start: str = SPAWN_NODE) -> set[str]:
    # Nodes reachable with a fixed inventory. Ground items are not collected.
    # Used to check the graph. Generation itself is Archipelago's fill.
    owned = Counter(inventory)
    explored: set[str] = set()
    pending = [start]
    blocked: list[Edge] = []
    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in graph.edges:
        outgoing[edge.origin].append(edge)

    while pending:
        while pending:
            node = pending.pop()
            if node in explored:
                continue
            explored.add(node)
            for edge in outgoing.get(node, ()):
                if _satisfied(edge, owned, explored):
                    if edge.destination not in explored:
                        pending.append(edge.destination)
                else:
                    blocked.append(edge)
        still_blocked: list[Edge] = []
        for edge in blocked:
            if _satisfied(edge, owned, explored) and edge.destination not in explored:
                pending.append(edge.destination)
            elif not _satisfied(edge, owned, explored):
                still_blocked.append(edge)
        blocked = still_blocked
    return explored


def _satisfied(edge: Edge, owned: Counter[str], explored: set[str]) -> bool:
    for name, count in edge.requirement.items:
        if owned[name] < count:
            return False
    return all(node_id in explored for node_id in edge.requirement.nodes)


def full_inventory(graph: LogicGraph) -> Counter[str]:
    # Enough of every progression item to satisfy any single edge.
    needed: Counter[str] = Counter()
    for edge in graph.edges:
        for name, count in edge.requirement.items:
            needed[name] = max(needed[name], count)
    for name in graph.progression_items:
        needed[name] = max(needed[name], 1)
    return needed


def reaches_end(graph: LogicGraph, inventory: Counter[str]) -> bool:
    return END_NODE in explore(graph, inventory)
