# Before full release

The playable beta generates a placement file, patches a USA 1.1 disc from the command line, and connects a BizHawk client. `archipelago.json` is world version 0.1.5. This is the work to finish before that version leaves beta.

## Quality of life

- [x] Embed a slot block in the patched executable, and have the BizHawk client read it.

  The randomizer writes the block when it patches a Multiworld placement file. The block is the first injected blob, so it stays at KSEG0 `0x8001F780` (MainRAM `0x1F780`). It holds the randomizer version, the apworld version, the placement seed, and the player name. `validate_rom` reads it in the same request as the `TryIncrease` prologue. A vanilla disc, an Alundra-format patch, and a block from an unknown apworld version are left alone. `set_auth` copies the player name into `ctx.auth`. After the room accepts the slot, the client compares the ROM seed with `slot_data["seed"]` and disconnects on a mismatch. The room host and port stay typed in the client.

- [x] Confirm the Launcher generate writes the placement file.

  The Launcher generate window calls `generate_output`. A generate of the YourName YAML wrote `AP_78189084152046214443.zip`. The zip contains `AP_78189084152046214443_P1_YourName.apalundra` and does not contain a bare `.alundra.json`. That file is a zip. `archipelago.json` has `"game": "Alundra"` and `"player": 1`. `placement.json` is the document `write_placement` produces. No separate generator is required for this path.

- [ ] Confirm a generate on the Archipelago website writes the placement file, once Alundra is core.

  The website calls the same `generate_output`. archipelago.gg rolls only worlds installed on that site, and Alundra is not among them until it is core. Uploading a Launcher zip already puts the container on a room. This item is a generate started on the site.

- [ ] Add a patch window so the player does not run the randomizer from a command line.

  The window takes the downloaded `.apalundra` file and a USA 1.1 disc, runs the patcher shipped in this world, and shows where the BIN/CUE was written. The placement file already carries the settings, so the window does not ask for a preset. The randomizer still reads `placement.json` through `--placement-in`, so the window opens the container and passes that member. The Archipelago Launcher hosts the window as a component, the same way other worlds add launcher entries.

- [ ] Ship the world as `alundra.apworld`.

  An `.apworld` is a zip archive. The file name is all lowercase. Inside it, a folder of that same name holds what is now the world folder: `alundra/__init__.py`, the other modules, `docs/`, and `data/`. The name comes from `worlds/alundra`, the link used for development. The directory on disk is `alundra-apworld`.

  Build it from the Archipelago source tree with the Launcher component, which writes the archive to `build/apworlds/alundra.apworld` and fills in the container fields:

  ```
  python Launcher.py "Build APWorlds" -- Alundra --skip_open_folder
  ```

  Leave `version` and `compatible_version` out of the source `archipelago.json`. The builder adds them. The current container version is 7. `game`, `authors`, `world_version`, and `minimum_ap_version` are copied from the file that is already in the world.

  `data.py` reads `data/*.json` with `importlib.resources`, so the same load works from the source tree and from the zip. `.apignore` leaves out `tests/`, `docs/TODO.md`, `README.md`, `data/README.md`, and `docs/client_memory.md`. The setup guide and the game page stay. `__pycache__` is already excluded by Archipelago. `data/` is a data folder next to `data.py`. It does not need an `__init__.py`.

- [x] Write the placement file as a player container with its own extension, so the room page offers it for download.

  `AlundraContainer` subclasses `APPlayerContainer`. `game` is `Alundra` and `patch_file_ending` is `.apalundra`. Archipelago does not apply the patch, so this is not an `APPatch` and `download_slot_file` has no Alundra branch. `generate_output` writes `AP_{seed}_P{n}_{Name}.apalundra`. `write_contents` writes `archipelago.json` through `APPlayerContainer` and `placement.json` beside it. The manifest `player` is the integer slot number. The placement document's `player`, on a Multiworld file, is the login name. `server` is empty at generate time, and `download_patch` fills it in when the file is downloaded.

  Uploading the Launcher zip to archipelago.gg created seed `3JFtaQxUR3OwviseWUDeIQ`. The room page shows Download Patch File... for the Alundra slot. The randomizer still reads `placement.json` through `--placement-in`. Opening the container is the patch window's job.

- [ ] Ship the Linux and Windows patchers inside the apworld, and pick one at runtime.

  A player who has this apworld still has to fetch the randomizer before a disc can be patched. Build `alundra-randomizer` for Linux and for Windows and store both binaries in the world. Store `dumpsxiso` and `mkpsxiso` for both platforms next to them. The randomizer runs those tools from `./tools/` on Linux and from `tools\\dumpsxiso.exe` and `tools\\mkpsxiso.exe` on Windows, and the working directory has to be the folder that contains `tools/`. The apworld is a zip, so the chosen files are extracted to a temporary directory and run from there. `sys.platform` selects the pair: `linux` or `win32`. The window from the patch item passes the downloaded `.apalundra` file and the player's USA 1.1 disc. The BizHawk client is already the Python in this world. Archipelago and BizHawk stay separate installs. The disc stays the player's own copy.

- [ ] Report a location hint when the player reads one in the game, or looks at a shop shelf that is a check.

  The client sends `LocationChecks` for a watched flag. It does not send `LocationScouts`. The randomizer writes hint sentences into dialogue at patch time (`PatchApplyHintText`). The room never hears that the player read one. Archipelago hint points are not spent inside the game.

  When the player reads a hint, or sees the item on a shop shelf that is a location, send `LocationScouts` for those location ids with `create_as_hint` set to 2. That records a hint for the room and broadcasts it once. It does not spend hint points. Skip a location this client has already scouted. A non-zero `create_as_hint` stores a hint even after the location is checked, so a shelf the player already bought stays a check and is not scouted again.

  The twelve speakers are Lars, Jeal, Miming, Vul, Wilda, Uma, Zazan in the Coal Mine, the Ancient Shrine priest, Stenia, Zazan in the Great Tree, Nava, and Jess. An item hint names one item and one place (`random_hint_for_item` picks one source). A region hint says that something useful lies in a region, or that nothing of interest does, and names no check. The dialogue string does not carry a location id. The patch has to store, for each speaker, the location ids that sentence refers to, where the client can read them when that dialogue is on screen. A region hint with no check sends nothing.

  The one-time shelves are the shop checks: Lurvy's Item #5, its first replacement, the repaired Ancient Armor, and Naomi's Item #4. Looking at that stock is the scout. Buying it is already the check. The eight restocking shelves are not locations, so a look at them has no id to send. The client does not yet know which map is on screen or which string is showing. Those reads belong in `docs/client_memory.md` once the addresses are known.

## APworld enhancements

- [x] Turn a full healing item into gilder instead of holding the receive queue.

  A remote Herbs, Strength Tonic, Strength Elixyr, Magic Elixyr, or Wonder Essence whose stack is already full adds that item's `goldValue` to the purse and counts the receipt. The write is the same s16 as a gilder pickup. The amounts are the shop prices: Herbs 5 (stack of 9), Strength Tonic 20, Strength Elixyr 50, Magic Elixyr 30, Wonder Essence 200. The other four cap at 1. The purse caps at 9999. At the cap, the receipt is counted and the purse stays. The stack stays full, so using one later opens a slot. A chest still gives its item through the chest script. This is the remote queue only.

- [x] Keep the restocking shelves vanilla, with an option to randomize them.

  `restocking_shop_items` defaults to full variety. Full variety locks five of the eight shelves, one to each healing item, in a random order at either shop, and the other three are filled from the pool. Vanilla locks all eight to the retail item. Randomized fills all eight from the pool. The placement file records the item id. The pool does not spend a distributed item on a locked shelf; one Herbs leaves the pool per locked shelf so the counts still match. A shelf the fill chooses is placed by `pre_fill`, then `pre_output` clears the address so the room never lists the check. Those shelves refuse a precious item and a remote item. Merrick's trades are not part of this option.

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

  The one-time shelves stay checks: Lurvy's Item #5, its first replacement, the repaired Ancient Armor, and Naomi's Item #4.

  Lurvy sells all five healing items. Wonder Essence is the shelf that replaces the unique slot after it has been bought twice. Naomi sells Herbs, Strength Tonic, and Magic Elixyr. Strength Elixyr and Wonder Essence are bought at Lurvy. The patch already obeys the item id in the placement file, so this option lives in the apworld.

- [x] Keep a progression item off a source that is not a check.

  `forbid_progression` returns true when the source sets `forbidPreciousItems` and the item is progression. That set is the restocking shelves, the table in Tarn's Manor, and the Fairy Pond chests. The fill uses that rule, so the only copy stays on a location the client reports. A one-time shelf may still sell one. When the pond and the table gain a collected flag, `forbidPreciousItems` comes off and a progression item can land there.

  The names come from the logic graph, so progressive items and the crest list follow the seed. A useful item that opens nothing, such as Olga's Ring, can still fill one of the three shelves full variety leaves open. Vanilla locks every shelf to a healing item. `precious` stays the abuse flag in `item.json`, and the standalone randomizer is unchanged.

- [x] Give a remote shop item a price the player can pay when the item is needed early.

  Naomi's Item #4 held another player's item that the seed needed early, and the shelf charged 500 gilder. The other player waited while this player ground the money. That shelf is a legal check. The price was the problem. A remote item has no gold value, so a shelf with no recorded price keeps the disc's word, and the shop line reads that word. An Alundra item still writes its own gold value.

  Naomi's Item #4, Lurvy's Item #5, and the Life Vessel that replaces Lurvy's Item #5 record `price` on a remote placement. The patch writes that word. The price follows the item's classification and the shelf's accessibility sphere, the same numbering as the room's sphere tracker. Sphere 1 is the first set of checks reachable from the start. A progression item costs 100, 200, 300, or 400 gilder in spheres 1 through 4, and 500 from sphere 5 on. A useful item costs 250. A filler item costs 100. A trap costs 50. Lurvy's shelves use the same table. Reaching Lurvy is a later sphere, so a progression item there costs more.

## Randomizer enhancements

The Fairy Pond and the Book of Elna are marked in `world_shuffler.cpp`, `placement.py`, and both copies of `docs/client_memory.md`. `item_source.json` is shared. A flag added for one of these sources is copied into the apworld data, `forbidPreciousItems` comes off that source, and the client watches the new code.

- [ ] Keep the Fairy Pond open.

  The pond seals after the reward, so a chest left behind is missed. Every Fairy Pond chest sets `forbidPreciousItems` and stays out of the location list for that reason. Chests 139–144 already have event codes (959, 957, 950, 954, 955, 956). The pond's clear flag is not named in `flags.hpp`. The patch keeps the pond open after the reward so those chests can be collected later. Once it stays open, drop `forbidPreciousItems` on 139–144 and let the client watch the codes they already have.

- [ ] Give the Fairy Pond reward chest a collected flag.

  Source 145, address `24A57C6`, vanilla Fiend Blade, has no `eventCode`. Add a flag the chest script sets when the chest is taken, and that stays set when the room loads again. The client watches that code. Drop `forbidPreciousItems` on 145 along with the other pond chests.

- [ ] Give the Book of Elna a collected flag, and leave it taken.

  Source 129 is the ground item on the table in Tarn's Manor (`spriteAddress` `1BA5D06`). It has no `eventCode`, so it comes back when the room loads again. `forbidPreciousItems` keeps it out of the check list. The patch already clears the byte at `0x1BA5D05`. Add an event code. Taking the book sets that flag, and entering the room again does not put the book back. The client then watches source 129.

- [x] Require the Iron Flail to get past the three-chest room in the Fire Wand and Bomb cave.

  The Fire Wand opens `overworld_a2_behind_vines`. A Bomb then opens `overworld_a2_behind_vines_and_bomb`. That node is one room too big. The three chests in the bridge cave can be taken with the wand and the Bomb and no flail:

  | Id | Chest |
  | --- | --- |
  | 86 | Overworld A2: Left chest in bridge cave with 3 chests |
  | 87 | Overworld A2: Middle chest in bridge cave with 3 chests |
  | 88 | Overworld A2: Right chest in bridge cave with 3 chests |

  Getting past that room takes the Iron Flail. The same node also holds the spikeball chest, the upper chest, both chests among the trees, and the chest after the Stone Golem (ids 89–93), and its two-way edge opens `overworld_a1` with nothing required. `overworld_a1` then opens `great_tree_tower`. Split the node so 86–88 stay on the Bomb side. Put a new edge behind them that requires the Iron Flail, and move the exit to A1 onto that far side. A check that is past the room moves with the exit. A check that is in the room with the three chests stays. Other flail gates in `world_path.json` name the Iron Flail. Progressive mode already treats a flail upgrade as that item. There is also a one-way edge from the Bomb node back to `overworld_a2`. Keep it from skipping the flail. Edit the randomizer's graph, then copy `world_path.json`, `world_node.json`, and `item_source.json` here.

- [ ] Stop Lurvy from selling an Alundra item whose stack is already full.

  In a multiworld seed, Lurvy completed a purchase of an item the player could not hold any more of. A remote sale is allowed to do that. `install_remote_shop_receive` in `patch_apply_item_sources.cpp` runs whenever the seed contains a remote item. Shop opcode `0x82` calls it with the item id in `a0`. The remote id returns 1 and never reaches the retail receive call at `0x80034814`, because a remote item is not a stack and the retail check treats "the quantity did not grow" as a failed sale. Any other id is supposed to jump to that retail call with `a0` unchanged, and the sale fails when the stack does not grow. The call site's delay slot, `addu s0, a3, zero`, stays in place. A full stack of an Alundra item, such as 9 Herbs or a second Elixyr, has to be refused and the gilder left unspent. The gilder payout for a full healing item is the client's receive path. It does not run when the shop itself makes the sale.
