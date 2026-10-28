# Alundra

Find the crests, open Lake Shrine, and defeat Melzas. Generation writes a placement file for the Alundra randomizer. A BizHawk client can log in to the room, report a check whose event code is known, and grant an item sent from another game.

The randomizer patches a USA 1.1 disc from that file. Hints inside the game are written then, by the randomizer. Archipelago hint points are not shown in the game.

## Goal

The victory event is Defeat Melzas, reached from the Lake Shrine. The BizHawk client sends the goal when the game loads the ending, after Melzas. With the default settings the seven crests are in the item pool and the Lake Shrine seals start open, so the crests lead to the fight. Checks behind the bow, the flail, and the Spring Bean on the shrine itself are still in the world.

Crests past the crest count are already on their pedestals when the file is new. The placement file names those crests. The randomizer reads that list when it patches the disc. The seed in the file is for the hash sentence and the in-game hints.

## What generation produces

A JSON placement file inside the generation zip, named from the slot plus `.alundra.json`. Patch it with the randomizer:

```
alundra-randomizer --placement-in=THAT_FILE.json
```

You need your own USA 1.1 disc image. The world does not contain one.

Another slot's item can be placed on an Alundra check. The file is then the Multiworld format (`"format": 2`). That entry in `placements` names the player, the item, and one classification (`progression`, `useful`, `filler`, or `trap`):

```json
{"player": "Player", "item": "Key Item", "classification": "progression"}
```

The disc shows "player - item", so those names are kept to 16 and 28 printable ASCII characters. Every other entry is still the in-game item id. `itemsDistribution` counts only those ids. A file of only in-game ids stays the Alundra format (`"format": 1`).

Restocking Shop Items defaults to Full Variety. The eight shelves at Lurvy's and Naomi's are shuffled, and one each of Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, and Wonder Essence is always on them, so every healing item can be bought at either shop. The other three shelves are filled from the item pool. They refuse a progression item. A useful item such as a ring can still land on one. Vanilla instead keeps the retail stock: Lurvy sells all five, and Naomi sells Herbs, Strength Tonic, and Magic Elixyr. Wonder Essence replaces Lurvy's one-time shelf after that shelf has been bought twice. Randomized fills all eight from the item pool, with the same refusal. The placement file records the item ids. Those shelves are left out of the world's location list and the room's check list. A remote item cannot sit on one: the shelf would offer it again, which spends gilder and adds nothing. A one-time shelf may still sell a progression item. Merrick's trades are checks and are not part of this option.

The item on the table in Tarn's Manor and the Fairy Pond chests also refuse a precious item, a progression item, and a remote item. The fill still places an item there, and the placement file records it. A check marked non-progression still refuses a progression item.

An Alundra item placed in another game is absent from this file. Archipelago records it on that game's check.

## Credit

Dinopony wrote the original Alundra randomizer. The current version of that project, and the logic data copied into this world, is https://github.com/Lunesar/alundra-randomizer.
