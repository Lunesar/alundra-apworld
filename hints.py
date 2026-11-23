"""Speaker hints chosen during generation.

The roll asks the collecting search which areas and items a speaker can talk
about, then keeps one check for each spoken line. The patcher writes the
sentence. It does not roll again.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .data import (
    CRESTS,
    END_NODE,
    GameData,
    RegionRecord,
    location_sources,
)
from .logic import LogicError, LogicGraph, search_world

_REGION_HINT_LIMIT = 5
_BASE_HINT_ITEMS: tuple[str, ...] = (
    *CRESTS,
    "Bomb",
    "Sand Cape",
    "Spring Bean",
    "Fire Wand",
    "Ice Wand",
    "Bouquet",
    "Tree Gem",
    "Secret Pass",
    "Power Glove",
)


@dataclass(frozen=True)
class HintLocation:
    """One check a spoken line registers.

    ``player`` is absent when the check is in this world. An unknown-place
    line names the other player's slot and their location id.
    """

    location: int
    player: int | None = None


@dataclass(frozen=True)
class SpeakerHint:
    speaker: str
    text: str
    check: HintLocation


def offworld_hint_copies(
    copies: Iterable[tuple[str, int, int]],
) -> dict[str, tuple[HintLocation, ...]]:
    """Group items that left this world by name.

    Each copy is an item name, the other slot's location id, and that slot's
    number. Copies of one item are ordered by slot, then location id, so the
    roll's choice does not depend on the order the locations were visited.
    """
    grouped: dict[str, list[HintLocation]] = {}
    for item_name, location, player in copies:
        if not isinstance(item_name, str) or not item_name:
            raise LogicError("Off-world hint needs an item name.")
        if isinstance(location, bool) or not isinstance(location, int) or location < 0:
            raise LogicError(f"Off-world {item_name} needs an integer location id.")
        if isinstance(player, bool) or not isinstance(player, int) or player < 1:
            raise LogicError(f"Off-world {item_name} needs the other player's slot.")
        grouped.setdefault(item_name, []).append(HintLocation(location, player))

    def copy_order(copy: HintLocation) -> tuple[int, int]:
        # The constructor above always sets the other slot.
        if copy.player is None:
            raise LogicError("Off-world hint is missing the other player's slot.")
        return copy.player, copy.location

    return {name: tuple(sorted(found, key=copy_order)) for name, found in grouped.items()}


def hintable_item_names(progressive_items: bool, split_boots_effects: bool) -> tuple[str, ...]:
    # The same list the randomizer builds. Joined boots are one upgrade item.
    names = list(_BASE_HINT_ITEMS)
    if progressive_items:
        names.append("Flail upgrade")
    else:
        names.append("Iron Flail")
    if progressive_items and not split_boots_effects:
        names.append("Boots upgrade")
    else:
        names.extend(("Long Boots", "Merman Boots"))
    return tuple(names)


def roll_hints(
    graph: LogicGraph,
    game_data: GameData,
    rng: random.Random,
    placements: Mapping[int, str],
    *,
    starting_inventory: Iterable[str] = (),
    remote_progression: Collection[int] = (),
    offworld: Mapping[str, Sequence[HintLocation]] | None = None,
    progressive_items: bool = True,
    split_boots_effects: bool = True,
    goal: str = END_NODE,
    region_hint_limit: int = _REGION_HINT_LIMIT,
) -> tuple[SpeakerHint, ...]:
    """Choose the spoken lines and the one check each line registers.

    ``placements`` maps a source id to the Alundra item in that chest. A source
    left out is another world's item. ``remote_progression`` is the source ids
    among those whose classification is progression. ``offworld`` lists, for an
    Alundra item with no copy left here, the slots and location ids that hold
    it. The starting inventory is owned from the first step of every search.
    """
    if offworld is None:
        offworld = {}
    _check_hint_inputs(game_data, placements, remote_progression, offworld, goal)
    owned_at_start = frozenset(starting_inventory)
    placed_names = set(placements.values())
    items = [
        name for name in hintable_item_names(progressive_items, split_boots_effects)
        if name not in owned_at_start and (name in placed_names or offworld.get(name))
    ]
    rng.shuffle(items)
    regions = [region for region in game_data.regions if region.can_be_hinted_as_required]
    rng.shuffle(regions)
    speakers = list(game_data.hint_sources)
    rng.shuffle(speakers)

    check_ids = {source.id for source in location_sources(game_data)}
    walks = _Walks(graph, game_data, placements, tuple(starting_inventory))
    hints: list[SpeakerHint] = []
    remaining_regions = region_hint_limit
    for speaker in speakers:
        if remaining_regions > 0:
            area = _area_hint(
                speaker.id, speaker.node_id, regions, walks, game_data, check_ids,
                remote_progression, goal, rng,
            )
            if area is not None:
                hints.append(area)
                remaining_regions -= 1
                continue
        item_hint = _item_hint(
            speaker.id, speaker.node_id, items, walks, game_data, check_ids, offworld, rng,
        )
        if item_hint is not None:
            hints.append(item_hint)
    return tuple(hints)


def _minimal_blocking_checks(
    checks: Sequence[int],
    goal_reachable_without: Callable[[frozenset[int]], bool],
) -> tuple[int, ...]:
    # One minimal set. Start with every check removed, then put back any check
    # the goal can still be finished without. Order is by source id, so the set
    # does not depend on the hint shuffle. A later check can be the one that
    # was put back when any two of three would have done.
    ordered = tuple(sorted(checks))
    if goal_reachable_without(frozenset(ordered)):
        return ()
    kept_out = set(ordered)
    for check in ordered:
        trial = kept_out - {check}
        if not goal_reachable_without(frozenset(trial)):
            kept_out = trial
    return tuple(sorted(kept_out))


class _Walks:
    """Cache of collecting searches for one placed world."""

    def __init__(
        self,
        graph: LogicGraph,
        game_data: GameData,
        placements: Mapping[int, str],
        starting_inventory: tuple[str, ...],
    ) -> None:
        self._graph = graph
        self._game_data = game_data
        self._placements = dict(placements)
        self._starting = starting_inventory
        self._by_forbid: dict[tuple[frozenset[str], frozenset[str]], set[str]] = {}
        self._by_removed: dict[frozenset[int], bool] = {}

    def reached(self, node_id: str, forbid_nodes: frozenset[str], forbid_items: frozenset[str]) -> bool:
        key = (forbid_nodes, forbid_items)
        nodes = self._by_forbid.get(key)
        if nodes is None:
            found = search_world(
                self._graph,
                self._game_data,
                self._placements,
                self._starting,
                forbid_nodes=forbid_nodes,
                forbid_items=forbid_items,
            )
            nodes = set(found.nodes)
            self._by_forbid[key] = nodes
        return node_id in nodes

    def is_local(self, source_id: int) -> bool:
        return source_id in self._placements

    def local_copies(self, item_name: str, check_ids: set[int]) -> list[int]:
        return [
            source_id for source_id, placed in self._placements.items()
            if placed == item_name and source_id in check_ids
        ]

    def goal_without(self, goal: str, removed: frozenset[int]) -> bool:
        known = self._by_removed.get(removed)
        if known is None:
            trimmed = {
                source_id: item_name
                for source_id, item_name in self._placements.items()
                if source_id not in removed
            }
            found = search_world(self._graph, self._game_data, trimmed, self._starting)
            known = goal in found.nodes
            self._by_removed[removed] = known
        return known


def _area_hint(
    speaker_id: str,
    speaker_node: str,
    regions: list[RegionRecord],
    walks: _Walks,
    game_data: GameData,
    check_ids: set[int],
    remote_progression: Collection[int],
    goal: str,
    rng: random.Random,
) -> SpeakerHint | None:
    progression_ids = set(remote_progression)
    for region in list(regions):
        forbid_nodes = frozenset(region.node_ids)
        if not walks.reached(speaker_node, forbid_nodes, frozenset()):
            continue
        checks = _checks_in_region(game_data, region, check_ids)
        # Only another world's progression items. Filler, useful, and trap stay out.
        remote_progression_checks = [
            source_id for source_id in checks if source_id in progression_ids
        ]
        local = [source_id for source_id in checks if walks.is_local(source_id)]
        avoidable = walks.reached(goal, forbid_nodes, frozenset())
        if avoidable and not remote_progression_checks:
            if not checks:
                continue
            chosen = rng.choice(checks)
            text = f"nothing of interest can be found {region.hint_phrase}"
        else:
            blocking = () if avoidable else _minimal_blocking_checks(
                local, lambda removed: walks.goal_without(goal, removed),
            )
            qualifying = list(dict.fromkeys((*blocking, *remote_progression_checks)))
            if not qualifying:
                continue
            chosen = rng.choice(qualifying)
            text = f"something useful lies {region.hint_phrase}"
        regions.remove(region)
        return SpeakerHint(speaker_id, text, HintLocation(chosen))
    return None


def _item_hint(
    speaker_id: str,
    speaker_node: str,
    items: list[str],
    walks: _Walks,
    game_data: GameData,
    check_ids: set[int],
    offworld: Mapping[str, Sequence[HintLocation]],
    rng: random.Random,
) -> SpeakerHint | None:
    for item_name in list(items):
        if not walks.reached(speaker_node, frozenset(), frozenset((item_name,))):
            continue
        local = walks.local_copies(item_name, check_ids)
        if local:
            chosen = rng.choice(local)
            phrase = _region_of(game_data, chosen).hint_phrase
            text = f"{item_name} can be found {phrase}"
            check = HintLocation(chosen)
        else:
            copies = tuple(offworld.get(item_name, ()))
            if not copies:
                items.remove(item_name)
                continue
            check = rng.choice(copies)
            text = f"{item_name} can be found in an unknown place"
        items.remove(item_name)
        return SpeakerHint(speaker_id, text, check)
    return None


def _checks_in_region(game_data: GameData, region: RegionRecord, check_ids: set[int]) -> list[int]:
    nodes = set(region.node_ids)
    return [
        source.id for source in game_data.sources
        if source.id in check_ids and source.node_id in nodes
    ]


def _region_of(game_data: GameData, source_id: int) -> RegionRecord:
    region_name = game_data.source_by_id[source_id].region_name
    for region in game_data.regions:
        if region.name == region_name:
            return region
    raise LogicError(f"Source {source_id} is in unknown region '{region_name}'.")


def _check_hint_inputs(
    game_data: GameData,
    placements: Mapping[int, str],
    remote_progression: Collection[int],
    offworld: Mapping[str, Sequence[HintLocation]],
    goal: str,
) -> None:
    if goal not in game_data.nodes:
        raise LogicError(f"Hint goal '{goal}' does not exist.")
    for source_id, item_name in placements.items():
        if source_id not in game_data.source_by_id:
            raise LogicError(f"Placement names unknown item source {source_id}.")
        if item_name not in game_data.item_by_name:
            raise LogicError(f"Placement on source {source_id} names unknown item '{item_name}'.")
    for source_id in remote_progression:
        if source_id not in game_data.source_by_id:
            raise LogicError(f"Remote progression names unknown item source {source_id}.")
        if source_id in placements:
            raise LogicError(
                f"Source {source_id} is both an Alundra item and a remote progression item."
            )
    for item_name, copies in offworld.items():
        if item_name not in game_data.item_by_name:
            raise LogicError(f"Off-world hint names unknown item '{item_name}'.")
        for copy in copies:
            if not isinstance(copy.location, int) or isinstance(copy.location, bool):
                raise LogicError(f"Off-world {item_name} needs an integer location id.")
            if not isinstance(copy.player, int) or isinstance(copy.player, bool):
                raise LogicError(f"Off-world {item_name} needs the other player's slot.")
