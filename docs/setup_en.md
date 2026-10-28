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

`restocking_shop_items` defaults to `full_variety`. The eight shelves that restock are shuffled, and Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, and Wonder Essence can each be bought at Lurvy's or Naomi's. The other three shelves are filled from the item pool. They refuse a progression item. A useful item such as a ring can still land on one. `vanilla` keeps the retail stock: Lurvy sells all five, and Naomi sells Herbs, Strength Tonic, and Magic Elixyr. Wonder Essence replaces Lurvy's one-time shelf after that shelf has been bought twice. `randomized` fills all eight from the item pool, with the same refusal. They are still not checks. A one-time shelf may still sell a progression item. A full stack of one of those healing items, sent from another game, is sold for gilder, and these shelves are where it can be bought again. Merrick's trades are unchanged.

A seed can include other games. Another slot's item may land on an Alundra check. A source that is not a check refuses a precious item, a progression item, and a remote item: a restocking shelf that the fill chooses, the item on the table in Tarn's Manor, and the Fairy Pond chests. The placement file uses the Multiworld format when it contains a remote item, and the Alundra format when every Alundra check holds an Alundra item.

A remote item on Naomi's Item #4, Lurvy's Item #5, or the Life Vessel that replaces that shelf has a `price` in the placement object. The patch writes that gilder cost. A progression item costs 100 in sphere 1, 200 in sphere 2, 300 in sphere 3, 400 in sphere 4, and 500 from sphere 5 on. A useful item costs 250. A filler item costs 100. A trap costs 50. An Alundra item on those shelves keeps its own gold value.

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

The client logs `Logged in as <slot name>.` when the room accepts the slot. Taking a watched check logs `Checked <location name>.` and sends that location to the room. That is an opened chest, a one-time shop purchase, or a Merrick trade whose flag is now set. A check that was already taken is sent on the next watch after login. An item found for this slot in another game is granted once Alundra has control. The client log says `Received Sword.` for that sword, and `Received Fiend Blade.` when a sword upgrade became that blade. A full stack of Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, or Wonder Essence is paid out as that item's shop price in gilder (`Received 5 Gilder for Herbs.`), and the next item is granted. The prices are 5, 20, 50, 30, and 200. At 9999 gilder the receipt is still counted. When the ending starts, the client logs `Goal completed.` and tells the room the goal is met.
