# Alundra

Find the crests, open Lake Shrine, and defeat Melzas. Generation writes a placement file for the Alundra randomizer. The world does not connect a client.

The randomizer patches a USA 1.1 disc from that file. Hints inside the game are written then, by the randomizer. Archipelago's own hint points are not shown in the game until a client exists.

## Goal

The victory event is Defeat Melzas, reached from the Lake Shrine. With the default settings the seven crests are in the item pool and the Lake Shrine seals start open, so the crests lead to the fight. Checks behind the bow, the flail, and the Spring Bean on the shrine itself are still in the world.

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

A check that refuses a precious item also refuses a remote item. Those checks are the restocking shop shelves and the item on the table in Tarn's Manor. A remote item on a restocking shelf can be bought again, which spends gilder and adds nothing. A check marked non-progression still refuses a progression item.

An Alundra item placed in another game is absent from this file. Archipelago records it on that game's check.

## Credit

Dinopony wrote the original Alundra randomizer. The current version of that project, and the logic data copied into this world, is https://github.com/Lunesar/alundra-randomizer.
