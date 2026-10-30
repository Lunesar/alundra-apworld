# Remaining work

Generation, the Launcher patch button, and the BizHawk client already run. Open items are below. The world version is `world_version` in `archipelago.json`. The patcher version is `randomizer.lock.json`.

Player pages are `docs/setup_en.md` and `docs/en_Alundra.md`. The address map is `docs/client_memory.md`. This file is a maintainer list, and `.apignore` leaves it out of the apworld.

## Quality of life

- [ ] Confirm a generate on the Archipelago website writes the placement file, once Alundra is core.

  The website calls the same `generate_output`. archipelago.gg rolls only worlds installed on that site. Uploading a Launcher zip already puts the container on a room. This item is a generate started on the site.

- [ ] Ship the world as `alundra.apworld`.

  An `.apworld` is a zip. The file name is all lowercase. Inside it, a folder of that same name holds the world: `alundra/__init__.py`, the other modules, `docs/`, `data/`, and `patcher/`. The folder name comes from `worlds/alundra`, the link used for development. This checkout is `alundra-apworld`.

  Build it from an Archipelago source tree. The archive is written to `build/apworlds/alundra.apworld`:

  ```
  python Launcher.py "Build APWorlds" -- Alundra --skip_open_folder
  ```

  Leave `version` and `compatible_version` out of the source `archipelago.json`. The builder adds them. `game`, `authors`, `world_version`, and `minimum_ap_version` are copied from the file in the world.

  `.apignore` lists what stays out of the zip. The setup guide and the game page stay. `data.py` loads `data/*.json` with `importlib.resources`, so the same load works from this checkout and from the zip.

- [ ] Report a location hint when the player reads one in the game, or looks at a shop shelf that is a check.

  The client sends `LocationChecks` for a watched flag. It does not send `LocationScouts`. The randomizer writes hint sentences into dialogue at patch time (`PatchApplyHintText`). The room never hears that the player read one. Archipelago hint points are not spent inside the game.

  When the player reads a hint, or sees the item on a shop shelf that is a location, send `LocationScouts` for those location ids with `create_as_hint` set to 2. That records a hint for the room and broadcasts it once. It does not spend hint points. Skip a location this client has already scouted. A non-zero `create_as_hint` stores a hint even after the location is checked, so a shelf the player already bought stays a check and is not scouted again.

  The twelve speakers are Lars, Jeal, Miming, Vul, Wilda, Uma, Zazan in the Coal Mine, the Ancient Shrine priest, Stenia, Zazan in the Great Tree, Nava, and Jess. An item hint names one item and one place (`random_hint_for_item` picks one source). A region hint says that something useful lies in a region, or that nothing of interest does, and names no check. The dialogue string does not carry a location id. The patch has to store, for each speaker, the location ids that sentence refers to, where the client can read them when that dialogue is on screen. A region hint with no check sends nothing.

  The one-time shelves are the shop checks: Lurvy's Item #5, its first replacement, the repaired Ancient Armor, and Naomi's Item #4. Looking at that stock is the scout. Buying it is already the check. The eight restocking shelves are not locations, so a look at them has no id to send. The client does not yet know which map is on screen or which string is showing. Those reads belong in `docs/client_memory.md` once the addresses are known.

## Randomizer enhancements

The Fairy Pond and the Book of Elna are marked in `world_shuffler.cpp`, `placement.py`, and both copies of `docs/client_memory.md`. `item_source.json` is shared. A flag added for one of these sources is copied into the apworld data, `forbidPreciousItems` comes off that source, and the client watches the new code.

- [ ] Keep the Fairy Pond open.

  The pond seals after the reward, so a chest left behind is missed. Every Fairy Pond chest sets `forbidPreciousItems` and stays out of the location list for that reason. Chests 139–144 already have event codes (959, 957, 950, 954, 955, 956). The pond's clear flag is not named in `flags.hpp`. The patch keeps the pond open after the reward so those chests can be collected later. Once it stays open, drop `forbidPreciousItems` on 139–144 and let the client watch the codes they already have.

- [ ] Give the Fairy Pond reward chest a collected flag.

  Source 145, address `24A57C6`, vanilla Fiend Blade, has no `eventCode`. Add a flag the chest script sets when the chest is taken, and that stays set when the room loads again. The client watches that code. Drop `forbidPreciousItems` on 145 along with the other pond chests.

- [ ] Give the Book of Elna a collected flag, and leave it taken.

  Source 129 is the ground item on the table in Tarn's Manor (`spriteAddress` `1BA5D06`). It has no `eventCode`, so it comes back when the room loads again. `forbidPreciousItems` keeps it out of the check list. The patch already clears the byte at `0x1BA5D05`. Add an event code. Taking the book sets that flag, and entering the room again does not put the book back. The client then watches source 129.

- [ ] Stop Lurvy from selling an Alundra item whose stack is already full.

  In a multiworld seed, Lurvy completed a purchase of an item the player could not hold any more of. A remote sale is allowed to do that. `install_remote_shop_receive` in `patch_apply_item_sources.cpp` runs whenever the seed contains a remote item. Shop opcode `0x82` calls it with the item id in `a0`. The remote id returns 1 and never reaches the retail receive call at `0x80034814`, because a remote item is not a stack and the retail check treats "the quantity did not grow" as a failed sale. Any other id is supposed to jump to that retail call with `a0` unchanged, and the sale fails when the stack does not grow. The call site's delay slot, `addu s0, a3, zero`, stays in place. A full stack of an Alundra item, such as 9 Herbs or a second Elixyr, has to be refused and the gilder left unspent. The gilder payout for a full healing item is the client's receive path. It does not run when the shop itself makes the sale.

## Done

- The patched executable carries a slot block, and the BizHawk client reads it to log in. The layout is in `docs/client_memory.md`.
- Launcher generate writes one `.apalundra` player file per Alundra slot.
- The Launcher's Alundra Patch button patches a USA 1.1 disc. The placement file already carries the settings.
- The player file is an `APPlayerContainer` with the ending `.apalundra`. `placement.json` sits beside `archipelago.json`.
- The Linux and Windows patchers ship in the apworld. `sys.platform` picks the directory.
- A full healing stack sent from another game pays that item's gold value as gilder.
- `restocking_shop_items` defaults to full variety. Vanilla and randomized are the other choices. Restocking shelves are not checks.
- A source that is not a check refuses a progression item. A one-time shelf may still sell one.
- A remote item on Naomi's Item #4, Lurvy's Item #5, or the Life Vessel that replaces Lurvy's Item #5 stores a gilder price from its classification and sphere.
- Passing the three-chest room in the Fire Wand and Bomb cave requires the Iron Flail.
