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

## Connect

The Lua script ships with Archipelago at `data/lua/connector_bizhawk_generic.lua`. Open BizHawk Client from the Archipelago Launcher. That window loads this world's handler.

1. Open the patched USA 1.1 disc in BizHawk with the NymaShock core. In Config > Customize, enable "Run in background" so the client stays connected when the window is not focused. BizHawk 2.7 and 2.8 need the Lua core set to Lua+LuaInterface under Config > Customize > Advanced, then a restart. 2.9 and newer already use a core the connector can load.
2. In EmuHawk, open Tools > Lua Console and leave that window open. Choose Script > Open Script and open `data/lua/connector_bizhawk_generic.lua` from the Archipelago install.
3. Open BizHawk Client. The first time, it asks for `EmuHawk.exe`.
4. When the log says `Running handler for Alundra`, enter the room address, for example `archipelago.gg:38281`, and connect. At `Enter slot name:`, enter the `name` from the player YAML.

The client logs `Logged in as <slot name>.` when the room accepts the slot. Opening a watched chest logs `Checked <location name>.` and sends that location to the room. A chest that was already open is sent on the next watch after login. An item found for this slot in another game is granted once Alundra has control. The client log says `Received Sword.` for that sword, and `Received Fiend Blade.` when a sword upgrade became that blade. Herbs, tonics, elixyrs, and wonder essence wait at the front of the queue until there is room.
