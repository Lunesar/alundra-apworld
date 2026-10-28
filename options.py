"""Player options. Each one is written into the placement file under the same meaning."""

from __future__ import annotations
from dataclasses import dataclass
from Options import Choice, OptionDict, OptionGroup, OptionSet, PerGameCommonOptions, Range, Toggle
from .data import (
    DEFAULT_FIXED_LOCATIONS,
    DEFAULT_NON_PROGRESSION_LOCATIONS,
    LOCATION_NAME_TO_ID,
)


class ProgressiveItems(Toggle):
    """Replace weapon, armor, and spell tiers with upgrade items.

    Boots stay as separate items unless Split Boots Effects is off.
    A path that required a tier-T item then requires T+1 upgrades, which is how
    the randomizer rewrites its logic.
    """
    display_name = "Progressive Items"
    default = 1


class SplitBootsEffects(Toggle):
    """Each pair of boots grants only its own effect.

    Turn this off, with Progressive Items on, to fold boots into Boots upgrade.
    """
    display_name = "Split Boots Effects"
    default = 1


class SkipLastDungeon(Toggle):
    """Open the Lake Shrine gates at new game, so the crests lead straight to Melzas.

    The exterior and interior checks behind the bow, flail, and Spring Bean stay
    in the world either way.
    """
    display_name = "Skip Last Dungeon"
    default = 1


class CrestCount(Range):
    """How many crests are in the item pool.

    The rest are already on their pedestals. Generation chooses which crests
    those are and writes the list into the placement file. The randomizer
    reads that list when it patches the disc.
    """
    display_name = "Crest Count"
    range_start = 0
    range_end = 7
    default = 7


class OriginalGameBalance(Toggle):
    """Use the Japanese enemy balance instead of the Working Designs US changes."""
    display_name = "Original Game Balance"
    default = 1


class MegalithsEnabledOnStart(Toggle):
    """Skip Berue's memory minigame. Each megalith still has to be visited once.

    The logic graph does not model that minigame either way. This only changes
    the flag the patch writes.
    """
    display_name = "Megaliths Enabled On Start"
    default = 1


class KingSnowDeathCount(Range):
    """Deaths required before King Snow gives his item. The logic does not count deaths."""
    display_name = "King Snow Death Count"
    range_start = 0
    range_end = 255
    default = 0


class CasinoWinCount(Range):
    """Wins required on each casino game before its second prize. The logic does not count wins."""
    display_name = "Casino Win Count For Last Reward"
    range_start = 1
    range_end = 4
    default = 1


class StartingHealth(Range):
    """Health given at new game."""
    display_name = "Starting Health"
    range_start = 1
    range_end = 50
    default = 10


class StartingMana(Range):
    """Mana given at new game."""
    display_name = "Starting Mana"
    range_start = 0
    range_end = 4
    default = 0


class StartingGold(Range):
    """Gilders given at new game."""
    display_name = "Starting Gold"
    range_start = 0
    range_end = 9999
    default = 0


class AllowSpoilerLog(Toggle):
    """Let --placement-in write the full hint and spoiler log."""
    display_name = "Allow Spoiler Log"
    default = 1


class FixedItemSources(OptionDict):
    """Locations that always contain one item. Keys are location names, values are item names.

    The locked item is removed from the pool. The default keeps Spirit Wand behind
    the 50 Gilded Falcon trade, matching the randomizer preset.
    """
    display_name = "Fixed Item Sources"
    valid_keys = set(LOCATION_NAME_TO_ID)
    default = dict(DEFAULT_FIXED_LOCATIONS)


class ItemSourcesWithoutProgression(OptionSet):
    """Locations that will not contain a progression item.

    These match the randomizer preset: the second casino prizes, and Merrick's
    40 and 45 falcon trades.
    """
    display_name = "Item Sources Without Progression"
    valid_keys = set(LOCATION_NAME_TO_ID)
    default = set(DEFAULT_NON_PROGRESSION_LOCATIONS)


class RestockingShopItems(Choice):
    """What the shelves that restock at Lurvy's and Naomi's sell.

    Full Variety is the default. It shuffles the eight shelves and keeps every
    healing item purchasable. One each of Herbs, Strength Tonic, Strength
    Elixyr, Magic Elixyr, and Wonder Essence is always somewhere on them, in
    any order, at either shop. The other three shelves are filled from the
    item pool. They refuse a progression item. A useful item such as a ring
    can still land on one. A full stack of one of these healing items, sent
    from another game, is sold for gilder. These shelves are where the player
    buys a replacement.

    Vanilla keeps their retail stock, and that stock can be bought again.
    Lurvy sells all five of those items. Naomi sells Herbs, Strength Tonic,
    and Magic Elixyr. Wonder Essence replaces Lurvy's one-time shelf after
    that shelf has been bought twice.

    Randomized fills all eight shelves from the item pool. They are still not
    checks, and they still refuse a precious item, a progression item, and an
    item from another slot.
    The one-time shelves stay checks in every mode. Merrick's trades are checks
    and are not part of this option.
    """
    display_name = "Restocking Shop Items"
    option_vanilla = 0
    option_full_variety = 1
    option_randomized = 2
    default = 1


@dataclass
class AlundraOptions(PerGameCommonOptions):
    progressive_items: ProgressiveItems
    split_boots_effects: SplitBootsEffects
    skip_last_dungeon: SkipLastDungeon
    crest_count: CrestCount
    original_game_balance: OriginalGameBalance
    megaliths_enabled_on_start: MegalithsEnabledOnStart
    king_snow_death_count: KingSnowDeathCount
    casino_win_count_for_last_reward: CasinoWinCount
    starting_health: StartingHealth
    starting_mana: StartingMana
    starting_gold: StartingGold
    allow_spoiler_log: AllowSpoilerLog
    fixed_item_sources: FixedItemSources
    item_sources_without_progression: ItemSourcesWithoutProgression
    restocking_shop_items: RestockingShopItems


option_groups = [
    OptionGroup("Logic", [
        ProgressiveItems,
        SplitBootsEffects,
        SkipLastDungeon,
        CrestCount,
        FixedItemSources,
        ItemSourcesWithoutProgression,
        RestockingShopItems,
    ]),
    OptionGroup("Patch", [
        OriginalGameBalance,
        MegalithsEnabledOnStart,
        KingSnowDeathCount,
        CasinoWinCount,
        StartingHealth,
        StartingMana,
        StartingGold,
        AllowSpoilerLog,
    ]),
]
