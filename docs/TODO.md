# Before full release

The playable beta generates a placement file, patches a USA 1.1 disc from the command line, and connects a BizHawk client. `archipelago.json` is world version 0.1.0. This is the work to finish before that version leaves beta.

## Quality of life

- [ ] Embed a slot block in the patched executable, and have the BizHawk client read it.

  `validate_rom` in `client.py` accepts any image whose `TryIncrease` prologue at MainRAM `0x4FBE4` is `addiu sp, sp, -32`. A vanilla USA 1.1 disc passes that check. The world does not override `set_auth`, so after the client connects to BizHawk the player types the room address and then the slot name.

  The randomizer writes the block when it patches. The client reads it from MainRAM at the same time it reads `TryIncrease`, which means the bytes live in the loaded executable. The block holds:

  - randomizer version
  - apworld version (`world_version` in `archipelago.json`)
  - seed (the placement file seed, also sent in `fill_slot_data`)
  - player name

  `validate_rom` requires the block, so a vanilla disc is left alone. A block whose apworld version this client does not know is left alone. `set_auth` copies the player name into `ctx.auth`, which skips the `Enter slot name:` prompt. After the room accepts the slot, the client compares the ROM seed with `slot_data["seed"]` and disconnects on a mismatch.

  The room host and port stay typed in the client. The server expects the YAML name unchanged. Remote item lines on the disc already keep a player name to 16 printable ASCII characters. The name stored for login is the full slot name.

- [ ] Confirm the existing Archipelago generate UI writes the placement file.

  `generate_output` writes `<slot>.alundra.json` into the generation output. The Archipelago Launcher generate window and the website both call that. Run one generate from each and confirm the zip contains the placement file. Add a separate generator only if one of those paths does not produce it.

- [ ] Add a patch window so the player does not run the randomizer from a command line.

  Patching is `alundra-randomizer --placement-in=<file>`. The world does not patch the disc. The window takes the placement file from the generation zip and a USA 1.1 disc, runs that patch, and shows where the BIN/CUE was written. The placement file already carries the settings, so the window does not ask for a preset.

  The Archipelago Launcher can host the window as a component, the same way other worlds add launcher entries. The randomizer release package can ship the window instead. Either one is enough.

- [ ] Ship the world as `alundra.apworld`.

  An `.apworld` is a zip archive. The file name is all lowercase. Inside it, a folder of that same name holds what is now the world folder: `alundra/__init__.py`, the other modules, `docs/`, and `data/`. The name comes from `worlds/alundra`, the link used for development. The directory on disk is `alundra-apworld`.

  Build it from the Archipelago source tree with the Launcher component, which writes the archive to `build/apworlds/alundra.apworld` and fills in the container fields:

  ```
  python Launcher.py "Build APWorlds" -- Alundra --skip_open_folder
  ```

  Leave `version` and `compatible_version` out of the source `archipelago.json`. The builder adds them. The current container version is 7. `game`, `authors`, `world_version`, and `minimum_ap_version` are copied from the file that is already in the world.

  `data.py` reads `data/*.json` with `importlib.resources`, so the same load works from the source tree and from the zip. `.apignore` leaves out `tests/`, `docs/TODO.md`, `README.md`, `data/README.md`, and `docs/client_memory.md`. The setup guide and the game page stay. `__pycache__` is already excluded by Archipelago. `data/` is a data folder next to `data.py`. It does not need an `__init__.py`.

## APworld enhancements

- [ ] Turn a full healing item into gilder instead of holding the receive queue.

  A remote Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, or Wonder Essence waits at the front of the queue while its stack is full (`_WAITS_WHEN_FULL` in `receive.py`, `Hold.NO_ROOM`). Grant that item's `goldValue` as gilder and count the receipt, using the same gilder write as a gilder pickup. The cap stays 9999. At the cap, count the receipt and add nothing.

  The shop prices already on those items are the amounts: Herbs 5 (stack of 9), Strength Tonic 20, Magic Elixyr 30, Strength Elixyr 50, Wonder Essence 200. The other four cap at 1. A chest in this game still gives its item through the chest script. This change is the remote queue.

- [ ] Keep the restocking shelves vanilla, with an option to randomize them.

  These eight shelves restock, have a price, and are filled from the pool today. `pre_fill` places an item on each, then `pre_output` clears the address so the room never lists the check. They refuse a precious item and a remote item.

  | Id | Shelf | Vanilla item |
  | --- | --- | --- |
  | 262 | Lurvy's Shop: Item #1 | Herbs |
  | 263 | Lurvy's Shop: Item #2 | Strength Tonic |
  | 264 | Lurvy's Shop: Item #3 | Strength Elixyr |
  | 265 | Lurvy's Shop: Item #4 | Magic Elixyr |
  | 268 | Lurvy's Shop: Item #5 replacement when bought twice | Wonder Essence |
  | 270 | Naomi's Shop: Item #1 | Herbs |
  | 271 | Naomi's Shop: Item #2 | Strength Tonic |
  | 272 | Naomi's Shop: Item #3 | Magic Elixyr |

  Add a toggle, default off. Off, the placement file records the vanilla item id and the pool does not spend an item on that shelf. The pool is currently sized to every source, including these eight, so eight items have to leave the pool or generation fails. Drop filler. On, keep the current fill: shuffled, unreported, still no precious item and still no remote item.

  The one-time shelves stay checks: Lurvy's Item #5, its first replacement, the repaired Ancient Armor, and Naomi's Item #4.

  Lurvy sells all five healing items. Wonder Essence is the shelf that replaces the unique slot after Leather Armor and the Life Vessel have been bought. Naomi sells Herbs, Strength Tonic, and Magic Elixyr. Strength Elixyr and Wonder Essence are bought back at Lurvy. The patch already obeys the item id in the placement file, so this option lives in the apworld.

## Randomizer enhancements

The Fairy Pond and the Book of Elna are marked in `world_shuffler.cpp`, `placement.py`, and both copies of `docs/client_memory.md`. `item_source.json` is shared. A flag added for one of these sources is copied into the apworld data, `forbidPreciousItems` comes off that source, and the client watches the new code.

- [ ] Keep the Fairy Pond open.

  The pond seals after the reward, so a chest left behind is missed. Every Fairy Pond chest sets `forbidPreciousItems` and stays out of the location list for that reason. Chests 139–144 already have event codes (959, 957, 950, 954, 955, 956). The pond's clear flag is not named in `flags.hpp`. The patch keeps the pond open after the reward so those chests can be collected later. Once it stays open, drop `forbidPreciousItems` on 139–144 and let the client watch the codes they already have.

- [ ] Give the Fairy Pond reward chest a collected flag.

  Source 145, address `24A57C6`, vanilla Fiend Blade, has no `eventCode`. Add a flag the chest script sets when the chest is taken, and that stays set when the room loads again. The client watches that code. Drop `forbidPreciousItems` on 145 along with the other pond chests.

- [ ] Give the Book of Elna a collected flag, and leave it taken.

  Source 129 is the ground item on the table in Tarn's Manor (`spriteAddress` `1BA5D06`). It has no `eventCode`, so it comes back when the room loads again. `forbidPreciousItems` keeps it out of the check list. The patch already clears the byte at `0x1BA5D05`. Add an event code. Taking the book sets that flag, and entering the room again does not put the book back. The client then watches source 129.
