# Alundra

Find the crests, open Lake Shrine, and defeat Melzas. This is a closed world: every check contains an Alundra item, and the generation result is a placement file for the Alundra randomizer rather than a client connection.

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

Play this as its own slot. Another game's item cannot be written into the placement file, so a multiworld that tries to put one here will fail generation.

## Credit

Dinopony wrote the original Alundra randomizer. The current version of that project, and the logic data copied into this world, is https://github.com/Lunesar/alundra-randomizer.
