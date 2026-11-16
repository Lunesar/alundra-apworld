# Remaining work

Generation, the Launcher patch button, and the BizHawk client already run. Open items are below. The world version is `world_version` in `archipelago.json`. The patcher version is `randomizer.lock.json`.

Player pages are `docs/setup_en.md` and `docs/en_Alundra.md`. The address map is `docs/client_memory.md`. This file is a maintainer list, and `.apignore` leaves it out of the apworld.

## Quality of life

- [x] Ship the world as `alundra.apworld`.

  An `.apworld` is a zip. The file name is all lowercase. Inside it, a folder of that same name holds the world: `alundra/__init__.py`, the other modules, `docs/`, `data/`, and `patcher/`. The folder name comes from `worlds/alundra`, the link used for development. This checkout is `alundra-apworld`.

  Build it from an Archipelago source tree. The archive is written to `build/apworlds/alundra.apworld`:

  ```
  python Launcher.py "Build APWorlds" -- Alundra --skip_open_folder
  ```

  Leave `version` and `compatible_version` out of the source `archipelago.json`. The builder adds them. `game`, `authors`, `world_version`, and `minimum_ap_version` are copied from the file in the world.

  `.apignore` lists what stays out of the zip. The setup guide and the game page stay. `data.py` loads `data/*.json` with `importlib.resources`, so the same load works from this checkout and from the zip.

- [x] Report a shop check when the player enters Naomi's, Lurvy's, or Merrick's.

  Shop Hints is `all` or `next`, default `all`, and `fill_slot_data` sends it as `shop_hints`. A ready watch on map 398, 258, or 134 sends `LocationScouts` with `create_as_hint` 2 for the checks that shop still has. `all` sends every remaining one. `next` sends the first whose purchase bit is clear. Restocking shelves have no location id. The repaired Ancient Armor is separate. Hint Lurvy's Repair, default on, scouts id 269 when chimney bit `0x067F` is set and `0x0455` is still clear.

- [ ] Report a location hint when the player reads one in the game.

  The randomizer writes hint sentences into dialogue at patch time (`PatchApplyHintText`). The room never hears that the player read one. Archipelago hint points are not spent inside the game.

  When the player reads a hint, send `LocationScouts` for those location ids with `create_as_hint` set to 2. That records a hint for the room and broadcasts it once. It does not spend hint points. Skip a location this client has already scouted. A non-zero `create_as_hint` stores a hint even after the location is checked.

  The twelve speakers are Lars, Jeal, Miming, Vul, Wilda, Uma, Zazan in the Coal Mine, the Ancient Shrine priest, Stenia, Zazan in the Great Tree, Nava, and Jess. An item hint names one item and one place (`random_hint_for_item` picks one source). A region hint says that something useful lies in a region, or that nothing of interest does, and names no check. The dialogue string does not carry a location id. The patch has to store, for each speaker, the location ids that sentence refers to, where the client can read them when that dialogue is on screen. A region hint with no check sends nothing. The current sentences are region phrases, so registering one would name a chest the line does not. That generator is a separate change.

## Randomizer enhancements

- [x] Keep the Fairy Pond open.

  `PatchFairyPond` skips `FlagOn 0x03A3` at `0x24A56B6`, and map 158 B[4] skips its wait so the entrance pad warps out before Stenia's scene. The blocks that close the way back to the reward room never spawn, and the overworld whirlpool stays. The pad lands at (2, 27), one tile north of the whirlpool, and the whirlpool entry lands at (5, 53), one tile off the exit pad. Chests 139–145 are checks.

- [x] Give the Fairy Pond reward chest a collected flag.

  Source 145, address `24A57C6`, vanilla Fiend Blade. `PatchFairyPond` writes event code `0x03B8` into the collected halfword. The client watches that code, and the other pond chests with it.

- [x] Give the Tarn's Manor table a collected flag, and leave it taken.

  Source 129, sprite `1BA5D06`, give argument `1BA5730`. `PatchTarnManor` sets event code `0x03B9` when opcode `0x82` adds the item. A later visit does not put the sprite back. Story flag `0x006C` is unchanged. The client watches source 129. A seed generated before this change does not contain the location.

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
