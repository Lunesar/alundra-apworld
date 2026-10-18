# Alundra setup

## What you need

- Archipelago 0.6.7 or newer
- This world linked into that install
- The Alundra randomizer, built or taken from a release of https://github.com/Lunesar/alundra-randomizer
- A USA 1.1 disc image of Alundra (`input.bin`, `Alundra.bin`, `Alundra (USA).bin`, `Alundra (USA) (Rev 1).bin`, or `Alundra (USA) (v1.1).bin`, or pass another name with `--input=`)

## Install the world

From the Archipelago directory:

```
ln -s /path/to/alundra-apworld worlds/alundra
```

On Windows, a directory junction to that same `alundra` folder works in place of the link.

## Generate

Create a player YAML with the game name `Alundra`. The Default preset matches the randomizer's usual settings: progressive items, split boots, Lake Shrine seals open, all seven crests in the pool, and the starting dagger, cloth armor, and short boots.

```
name: YourName
game: Alundra
Alundra: {}
```

An empty `Alundra` block uses the same defaults as the website's Default preset. The dagger, cloth armor, and short boots are added at generation if the starting inventory does not already list them.

A seed can include other games. Another slot's item may land on an Alundra check. Checks that refuse a precious item also refuse a remote item: the restocking shelves at Lurvy's and Naomi's, and the item on the table in Tarn's Manor. The placement file uses the Multiworld format when it contains a remote item, and the Alundra format when every Alundra check holds an Alundra item.

`local_items` in the YAML keeps a named Alundra item in this slot. Listing every Alundra item there fills every check, so another slot's item has nowhere to land and generation fails.

## Patch

Unzip the generation output. Inside is a file whose name ends in `.alundra.json`. From the randomizer directory, with the disc image in place:

```
alundra-randomizer --placement-in=/path/to/the-file.alundra.json --nopause
```

The randomizer writes the patched BIN/CUE and, unless you turned the spoiler off, the hint log. The placement file already contains the settings, so do not also pass `--preset`.
