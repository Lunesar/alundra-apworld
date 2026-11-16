# Alundra

Item placement comes from the Alundra randomizer. Another slot's item can sit on one of your checks, and an item of yours can be placed in another game. The client grants that item once you have control.

Patching and connecting are in the [setup guide](setup_en.md). You supply your own USA 1.1 disc.

## Goal

Defeat Melzas. The client sends the goal when the ending loads, after the fight.

With the default settings, weapons, armor, and spells are progressive, boots stay separate items, all seven crests are in the pool, and the Lake Shrine seals start open. The crests lead to the fight. Checks on the shrine that need the bow, the flail, or the Spring Bean are still in the world. A new game starts with the dagger, cloth armor, and short boots.

Crests past the crest count are already on their pedestals.

## Checks

Chests, one-time shop purchases, and Merrick's trades are checks. The client reports a check once you have control.

Archipelago leaves the following out of the check list. Each one still receives an item. That item is never progression, and never from another slot.

- The eight shelves that restock at Lurvy's and Naomi's. Restocking Shop Items chooses what they sell. A useful item such as a ring can still land on a shelf the fill chooses. A full stack of Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, or Wonder Essence, sent from another game, is paid out as that item's shop price in gilder: 5, 20, 50, 30, or 200. These shelves are where you can buy the item again. At 9999 gilder the payout is still counted and the purse stays full.

NPC hints are written into the dialogue when the disc is patched. Those lines are not sent to the room.

Entering Naomi's shop, Lurvy's shop, or Merrick's shop reports that shop's checks. Shop Hints chooses how many. All, the default, reports every check the shop still has: Naomi's Item #4, Lurvy's Item #5 and the shelf that replaces it, and Merrick's eight Gilded Falcon trades. Next reports the one on offer. That is Naomi's Item #4, Lurvy's Item #5 until it is bought and then its replacement, or Merrick's lowest remaining trade. Shelves that restock are not checks, and Lurvy's armor repair is not reported from the doorway. Jumping down his chimney reports that repair. Hint Lurvy's Repair turns the chimney report off. Handing over the Broken Armor is still the check. A check you have already found is not reported again. This does not spend hint points.

Another player's item is shown as "player - item". The player name is kept to 16 printable ASCII characters and the item name to 28, so the line fits on the disc. The name you log in with is the full slot name.

## Shop prices for another player's item

Naomi's Item #4, Lurvy's Item #5, and the Life Vessel that replaces Lurvy's Item #5 can sell another player's item. The price follows how early that shelf can be reached, and whether the item is progression, useful, filler, or a trap. Sphere 1 is the first set of checks reachable at the start, the same numbering as the room's sphere tracker.

| Item | Price |
| --- | --- |
| Progression in sphere 1 through 4 | 100 gilder times the sphere |
| Progression in sphere 5 and later | 500 |
| Useful | 250 |
| Filler | 100 |
| Trap | 50 |

An Alundra item on those shelves keeps that item's own price.

## Credit

Dinopony wrote the original Alundra randomizer. This world patches with [alundra-randomizer](https://github.com/Lunesar/alundra-randomizer). The logic data in this repository is copied from there.
