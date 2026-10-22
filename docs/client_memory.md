# Client memory contract

What a future BizHawk or C++ client has to peek and poke on the USA 1.1 image. This is not a client. Addresses below are ones the randomizer already writes, or ones those routines load and store. Anything not in that set is **TBD**. Do not fill a TBD by assuming the next field continues the pattern.

Addresses are KSEG0 (the `0x80xxxxxx` the executable uses). In BizHawk's MainRAM domain, drop the top bits: offset = address & `0x001FFFFF` (so `0x801DD334` is MainRAM `0x1DD334`). Multi-byte values are little-endian.

The patcher prepends code and lowers the EXE load address by the same amount, so the function entry points in this document stay at these addresses on a patched image. One built EXE (load address shifted down by `0x1000`) still had `TryIncrease` at `0x8004FBE4`. A client can sanity-check that entry: the first instruction is `addiu sp, sp, -32` (`27 BD FF E0`).

## Work RAM

`Flag` offsets in `src/constants/flags.hpp` are offsets into one work region. Byte 0 of that region is `0x801D0000`, so flag offset `0xD334` is `0x801DD334`. The new-game patch builds this with `lui` of `0x801E` and a halfword store at the flag offset; that offset is a signed 16-bit displacement, which is why the comments in `game_data.cpp` say `0x1DD403` for offset `0xD403`.

The new-game patch allocates a `0x1000`-byte image of offsets `0xD000`–`0xDFFF` (`0x801DD000`–`0x801DDFFF`) and stores the non-zero flag halfwords. That buffer is not "the memory card save" and it is not all event flags. Inside it, the fields the randomizer actually uses are:

| What | Address | Size |
| --- | --- | --- |
| Save spawn map id | `0x801DD324` | u32, a `map_codes.hpp` id |
| Save spawn X, Y, Z | `0x801DD328`, `0x801DD32C`, `0x801DD330` | u32 each |
| Event-flag bits | `0x801DD334` | 256 bytes (see below) |
| Player stat block | `0x801DD81C` | see below |
| Inventory records | `0x801DD82E` | 128 × 4 bytes |

Map-variant ids (which version of a map is active, not where Alundra is standing) are also u16s in this region. The new-game patch writes these and only these:

| Variant | Address | Value the patch stores |
| --- | --- | --- |
| Overworld C4 (Merrick's shop open) | `0x801DD44C` | `MAP_OVERWORLD_C4_MERRICK_OPEN_VARIANT` (407) |
| Overworld E1 (Nirude) | `0x801DD456` | `0x01B7` (439) |
| Inoa | `0x801DD578` and `0x801DD586` | `MAP_INOA_RANDOMIZER` (241) |
| Jess's house, chest openable | `0x801DD618` | `MAP_JESS_HOUSE_CHEST_OPENABLE` (260) |
| Inoa, blue chest openable | `0x801DD63A` | `MAP_INOA_RANDOMIZER` (241) |

The stride of that variant table is **TBD**. Do not compute other variant slots from these five.

Two pointers are filled by the inventory init at `0x8004F114` and are the indirection the item routines use:

| Pointer | Address | Points at |
| --- | --- | --- |
| Stat block | `0x80119AE8` | `0x801DD81C` |
| Inventory records | `0x80119AEC` | `0x801DD82E` |

The init writes those constants. A client can use the constants, or read the pointers if it wants to notice a future patch that moves the block.

## Inventory and collected items

There is no separate "collected items" bitfield in work RAM. Owning an item means its quantity halfword is greater than 0. The `0x80` bit in the EXE's second item-info table is only the new-game preset: at the end of new game the loop at `0x80031E40` walks item ids 0..97, and for each id whose ROM byte has bit `0x80` set it calls `TryIncrease`. That ROM byte is not live state. Do not poke it to grant an item.

### Stat block (`0x801DD81C`)

| Offset | Address | Type | What the setters do |
| --- | --- | --- | --- |
| +0 | `0x801DD81C` | s16 | Current HP. Second new-game HP store (`0x8004F3A8`). Clamped to max HP. |
| +2 | `0x801DD81E` | s16 | Max HP. First new-game HP store (`0x8004F2DC`). Values above 50 are stored as 50. |
| +4 | `0x801DD820` | s16 | Current MP. Second new-game MP store (`0x8004F540`). Clamped to max MP. |
| +6 | `0x801DD822` | s16 | Max MP. First new-game MP store (`0x8004F474`). Values above 4 are stored as 4. |
| +8 | `0x801DD824` | s16 | Gilders. New-game gold store (`0x8004F60C`). Values above 9999 are stored as 9999. |
| +10 | `0x801DD826` | s16 | Equipped weapon item id. `0x8004FB28` writes it only for -1 or for ids 1..6. |
| +12 | `0x801DD828` | s16 | Written by `0x8004FB80`, which has no direct callers. Meaning **TBD**. |
| +14 | `0x801DD82A` | u16 | Gilded Falcon pending. `0x8004FDB4` adds to it and caps it at 50, then ORs `0x400` into the word at `0x801DD3E8`. That bit is event `0x05AA`, bit 2 of the byte at `0x801DD3E9`. Merrick's talk tests it before folding pending into the total. |
| +16 | `0x801DD82C` | u16 | Gilded Falcon total. `0x8004FE04` adds pending into this, caps the result at 50, clears pending, and clears `0x05AA`. `GetTotal` at `0x8004FE5C` returns only this halfword. Merrick compares it with 15, 20, 25, 30, 35, 40, 45, 50. The printers at `0x8005620C` and `0x80058BE4` add pending to it. |

`TryIncrease` does not equip anything. New game grants the starting gear and then calls `0x8004FB28` with item id 1 so the dagger is in hand. A client that only increments a weapon's quantity has granted the weapon; it has not equipped it.

### Inventory records (`0x801DD82E`)

128 records, 4 bytes each, item id 0 through 127. Init zeroes both halfwords of all 128. The runtime id limit lives in the u32 at `0x8012E234`, which init sets to 99: `TryIncrease` rejects an id that is negative or `>=` that word. Randomizer item ids (`item_codes.hpp`) stop at `0x59`, which is inside that range. Records 126 and 127 are past that limit. The client stores its received-item count there. See Receiving a remote item.

| Field | Location |
| --- | --- |
| Record for item id `I` | `0x801DD82E + I*4` |
| Quantity (the owned/collected value) | s16 at record + 2, i.e. `0x801DD830 + I*4` |
| Record + 0 | s16, cleared to 0 and not read by the owned check. Meaning **TBD**. |

`GetQuantity` is `0x8004FAC4` (item id in `a0`, returns the s16). `FindOwnedItemOfBestTierForSlot` is `0x8004F810` (slot id in `a0`, slot must be `< 32`, returns an item id or -1). It treats quantity `> 0` as owned.

The boots patch loads a word at the quantity address and tests it as a signed word (`0x801DD898` Long Boots `0x1A`, `0x801DD89C` Merman Boots `0x1B`, `0x801DD8A0` Charm Boots `0x1C`). That matches "quantity > 0" only while the following record's first halfword stays 0, which is what init writes and what the quantity routines leave alone. Clients should read the s16, not the word.

Stack sizes come from the ROM item-info table, not from the save. Table at `0x800BBE50`, 10 bytes per item id, for ids the quantity routine will touch:

| Offset | Type | Meaning |
| --- | --- | --- |
| +0 | u16 | Slot id (`item.json` `"slot"`) |
| +2 | u16 | Bit 0 set: `FindOwned` keeps this item and looks for a higher tier. Bit 0 clear on the first owned item in the slot: it returns that item and stops. A later item replaces the kept one only when its tier is higher. |
| +4 | u16 | Tier |
| +6 | s16 | Max quantity. Herbs is 9, the Key is 99, a normal unique item is 1. |

Items with max quantity 0 (Nothing, item `0x3A`, the gilder pickups, Gilded Falcon, Magic Seed, the two crystals, the three life pickups, Life Vessel) never stick in the inventory array. `TryIncrease` sees quantity 0 equal to max 0 and does not increment. They are granted by the paths in the next section.

## What "give item" means

Two different operations, and they are not interchangeable.

**Inventory write.** Store the s16 quantity at `0x801DD830 + id*4`. That is enough for a normal item whose max is at least 1, and it is what the owned check reads. It does not run the progressive-item hook, does not equip, does not add gilders, and does not move HP or MP. Writing the quantity of an upgrade id (`0x0B` sword upgrade, `0x0C` flail, `0x0D` bow, `0x0F` armor, `0x15`–`0x18` magic, `0x1D` boots) does not turn it into the next real tier.

**The game's give routine.** `TryIncrease` at `0x8004FBE4`, item id in `a0`. If quantity is already equal to the max in the item-info table it returns the current quantity and writes nothing. Otherwise it stores quantity + 1 and returns that. New game grants starting items by calling this, not by writing the s16 itself.

On a randomized image the progressive patch overwrites the two instructions at `0x8004FBF4` with a call that may replace `a0`/`a1` with the next tier before the increment. The entry point stays `0x8004FBE4`. Calling it is how an upgrade id becomes a real sword, flail, bow, armor, spell, or boots. A raw quantity write of the upgrade id skips that, and an owned upgrade row outranks the top real tier in `FindOwned`. The connector cannot enter MIPS, so the client performs that replacement itself and writes the resolved item's quantity. See Receiving a remote item.

`TryIncrease` does not play the chest fanfare. The routine that does, and that also handles the items `TryIncrease` cannot represent, is `GiveItem` at `0x800344D4`. Its only caller (`0x8007EB4C`) passes:

- `a0` = `0x801AC6F8` (a fixed global, not a value loaded from a register)
- `a1` = item id

`GiveItem` then dispatches:

| Item ids | What it actually does |
| --- | --- |
| `0x45`–`0x48` (1 / 5 / 10 / 30 Gilder) | `AddGold` at `0x8004F668` with `a0` = 1, 5, 10, or 30. Adds to the gilders s16 and caps at 9999. No inventory write. |
| `0x49`–`0x4E` (Sluice Key through Zolist Stone) | `TryIncrease` |
| `0x4F` Gilded Falcon | Adds 1 to the pending u16 at `0x801DD82A` and caps that halfword at 50. Then ORs `0x400` into the word at `0x801DD3E8`. The folded total is the u16 at `0x801DD82C`. |
| `0x50` Magic Seed | Adds 1 to max MP (cap 4) and sets current MP to that max, then calls effect routines. |
| `0x51` Small Crystal | Adds 1 to current MP, clamped to max MP, then calls effect routines. |
| `0x52` Large Crystal | Sets current MP to max MP, then calls effect routines. |
| `0x53` Life Vessel | Adds 1 to the u32 at `0x801AC710` and sets the u32 at `0x801AC70C` equal to it, then calls effect routines. |
| `0x54` Dew of Life | Adds 2 to the u32 at `0x801AC70C`, clamped to the u32 at `0x801AC710`. No effect call in this handler. |
| `0x55` Drop of Life | Adds max HP / 4 to the u32 at `0x801AC70C`, at least 1, and clamps to the u32 at `0x801AC710`. Then calls an effect routine. |
| `0x56` Water of Life | Adds max HP / 2 to that current HP, at least 5, and clamps to max. Then calls an effect routine. |
| Any other id, including crests and keys | `TryIncrease` |

The u32 pair at `0x801AC70C` / `0x801AC710` is not the save HP s16 pair at `0x801DD81C` / `0x801DD81E`. Life Vessel does not call the HP setters. How the two pairs stay in sync is **TBD**. Do not poke one and assume the other moved.

For a client that cannot enter MIPS, write the stores above and skip the effect calls. The BizHawk client does that for every id in `item.json`. Which bytes move, which caps are counted, and which full stacks wait are in Receiving a remote item.

`GiveItem` itself is the wrong call while a map is loading, because of those effect calls. `TryIncrease`, `AddGold`, and the s16 stores do not call them. They are also what new game uses before any map is running.

## Checked locations (chests and other sources)

A taken source is an event-flag bit, not a byte next to the inventory record. Map scripts turn bits on with opcode `0x05` (`FlagOn`) and test them with `0x30` / `0x31` (`IfFlagOn` / `IfFlagOff`). The same bits are what `flags.hpp` names. `item_source.json` stores that bit index as `eventCode` when the code is known, and omits the key when it is unknown. `eventCode` is the bit index passed to `FlagOn`. It is not a RAM address. `address` and `spriteAddress` are offsets in `DATAS.BIN` where the patch writes the item id. The patcher does not read `eventCode`.

The client watches every source that has `eventCode`. The check name is the source pretty name: the JSON `name`, plus ` (vanillaItem)` when a vanilla item is set. The location id is the source `id`.

A chest that lives in a map entity record stores its collected event code in the u16 at record + 0x10, and the item id in the byte at record + 0x12. That byte is the source `address` only for those entity chests. A shop slot stores the item id as the argument byte of opcode `0x82`. That byte is the source `address`. The two bytes before it are not a flag. Merrick trades and NPC gifts also store an item id in script bytes, and the two bytes before that id are not a flag. Code 0, and any code whose low 15 bits are `>= 0x800`, is omitted. A code shared by two sources is omitted. On the retail disc, a source whose entity records carry two different codes is omitted too. The two Overworld C4 chests below are the exception: the randomizer patch makes the loaded record use one code, and that code is what `item_source.json` stores.

Watched locations are the `eventCode` fields in `item_source.json`. Fairy Pond's reward chest (id 145, code 0) has no key. NPC script gifts have no key. On this disc, no two sources share one code.

Overworld C4 left coast (id 33) and the forest chest near the right border (id 36) disagree on the retail disc. Map 12, the closed shop, stores `0x06D6` (Magic Elixyr, x `0x0D`) and `0x06D7` (Strength Elixyr, x `0x5F`). Map 407, the open shop, stores `0x0540` (Strength Tonic, x `0x0C`) and `0x0542` (Magic Elixyr, x `0x5E`). `PatchFixMapInconsistencies` runs before item placement and copies the map 12 flag, position, and vanilla item onto the map 407 records: `set_word(0x584D6C8, 0xD606)` and `set_word(0x584D6B4, 0xD706)`. `set_word` writes the high byte first, so the stored bytes are `D6 06` and `D7 06`, little-endian flags `0x06D6` and `0x06D7`. New game writes 407 into the halfword at `0x801DD44C`, so the square loads map 407. The chest routine sets the flag in that loaded record. The client watches `0x06D6` (1750) and `0x06D7` (1751). New game does not set either bit. Neither bit is named in `flags.hpp`. No `FlagOn` of either code (`05 D6 06` or `05 D7 06`) exists in `DATAS.BIN`.

A one-time shop purchase sets its flag with opcode `0x05` on the path that has already taken the gilder and called `0x82`. The same script tests that bit, so the shelf does not come back. The client watches the bit the same way it watches a chest. New game does not set these bits. None of them is named in `flags.hpp`.

| Source | Id | Map script | FlagOn | When it is set |
| --- | --- | --- | --- | --- |
| Lurvy's Shop: Item #5 (Leather Armor) | 266 | 398 B[5] | `0x03F1` | `0x82` returned success. The script begins with `IfFlagOn 0x03F1` and does not offer the item when the bit is set. |
| Lurvy's Shop: Item #5 replacement when bought once (Life Vessel) | 267 | 398 B[6] | `0x0454` | After the gilder is taken and `0x82` runs. The script does not test `0x82`'s result. Offered only when `0x03F1` is on and `0x0454` is off. |
| Naomi's Shop: Item #4 (Life Vessel) | 273 | 258 B[5] | `0x02C4` | After the gilder is taken and `0x82` runs. The script does not test `0x82`'s result. Script B[1] activates the shelf entity only while the bit is off. Shop variants 298 and 302 set the same bit on their own purchase. The randomizer keeps Inoa on map 241, whose shop door is 258, and neutralizes later Inoa variant changes. |
| Lurvy's Shop: Item obtained after repairing Broken Armor (Ancient Armor) | 269 | 398 C[2] | `0x0455` | After `UseItem` consumes Broken Armor (item `0x21`) and `0x82` gives the repaired item (item `0x13`). Nothing else in `DATAS.BIN` reads or writes this bit. |

Restocking shelves set no bit in the 2048-flag array. Lurvy items 1–4 (ids 262–265), Lurvy's third Item #5 (Wonder Essence, id 268), and Naomi items 1–3 (ids 270–272) only toggle flags whose bit 15 is set (`0x8384` on map 398, `0x81F4` on map 258). Bit 15 selects the array at `0x801E6378`, and the script clears the bit before it returns control. There is no event code to store, so those sources stay out of the watch table.

A Merrick trade sets its flag in the trade script he spawns, on map 134. Talk script C[1], and C[2] once a trade is already underway, spawns one trade entity and then sets latch `0x8065`. The trade script waits for that latch, calls `FlagOn` for its own bit, plays text 145, and calls `0x82`. The `FlagOn` runs before `0x82`, and the script does not test `0x82`'s result. `0x8065` has bit 15 set, so it lives in the array at `0x801E6378`. The trade script clears it after the give, and other maps use the same latch. It does not name a trade.

The eight bits are `Flag(0xD3E7, 1)` through `Flag(0xD3E7, 7)`, then `Flag(0xD3E8, 0)`. New game does not set them. The new-game Merrick bits are `0x0596`, `0x0597`, `0x0598`, and `0x05A9`. None of the trade bits is named in `flags.hpp`. A walk that starts at each script entry finds each `FlagOn` in exactly one script, the trade script below. `0x059A`, `0x059C`, `0x059E`, and `0x059F` are also tested by B[2], B[3], B[4], and B[1]. Those scripts activate a prop for a later talk and do not give the item again. `0x05A0` is also tested by C[1] and C[2]: when it is on, Merrick uses the finished dialog (text 150) and offers no further trade.

`0x05A1` through `0x05A7` choose which trade entity to spawn. Map scripts only test them, and only on map 134. The completion bits are the eight codes in the table.

A linear walk of a code blob reports `FlagOn 0x05A0` at map 49 address `0xC15FE3`. That halfword is C[19]'s script offset. The C table base there is `0xC15F74`, and `0xC15F74 + 0x05A0` is the script. The same halfword runs sit in other maps' script tables. A walk from each script entry reaches `FlagOn` for these eight codes only in the map 134 trade scripts.

| Source | Id | Map script | FlagOn |
| --- | --- | --- | --- |
| Merrick's Shop: Item traded for 15 Gilded Falcons (Life Vessel) | 254 | 134 C[4] | `0x0599` |
| Merrick's Shop: Item traded for 20 Gilded Falcons (Olga's Ring) | 255 | 134 C[5] | `0x059A` |
| Merrick's Shop: Item traded for 25 Gilded Falcons (Life Vessel) | 256 | 134 C[9] | `0x059B` |
| Merrick's Shop: Item traded for 30 Gilded Falcons (Silver Armlet) | 257 | 134 C[6] | `0x059C` |
| Merrick's Shop: Item traded for 35 Gilded Falcons (Life Vessel) | 258 | 134 C[10] | `0x059D` |
| Merrick's Shop: Item traded for 40 Gilded Falcons (Recovery Ring) | 259 | 134 C[7] | `0x059E` |
| Merrick's Shop: Item traded for 45 Gilded Falcons (Life Vessel) | 260 | 134 C[11] | `0x059F` |
| Merrick's Shop: Item traded for 50 Gilded Falcons (Spirit Wand) | 261 | 134 C[8] | `0x05A0` |

### Event-flag encoding

Bits are packed little-endian at `0x801DD334`. The script event code, which is `Flag::event_code()`, is the bit index:

```
event_code = ((flag_offset - 0xD334) << 3) + bit
byte       = 0x801DD334 + (event_code >> 3)
mask       = 1 << (event_code & 7)
```

`FLAG_CASINO_ROULETTE_2_WINS` is declared as bit 8 of offset `0xD3F6`. That is the same bit as `FLAG_CASINO_ROULETTE_3_WINS` (bit 0 of `0xD3F7`, event code `0x0618`). They are one flag, not two.

The flag reader at `0x80033154` ignores a code whose low 15 bits are `>= 2048`, so the array it indexes is 2048 bits: `0x801DD334` through `0x801DD433` inclusive. A code with bit 15 set uses a different array at `0x801E6378` instead. Nothing in `flags.hpp` sets that bit. Leave that array alone.

Named flags, in the order `flags.hpp` declares them. "Set on new game" is the unconditional set in `GameData::init_starting_flags`, not the option-dependent crest and Lake Shrine sets.

| Flag | Byte | Bit | Event code | Set on new game |
| --- | --- | --- | --- | --- |
| `FLAG_HUD_ALLOWED` | `0x801DD403` | 6 | `0x067E` | yes |
| `FLAG_SEPTIMUS_WAKE_UP_TALKING_ABOUT_RONAN` | `0x801DD358` | 0 | `0x0120` | yes |
| `FLAG_SYBILL_HOLY_SWORD_VISION_1` | `0x801DD3F3` | 6 | `0x05FE` | yes |
| `FLAG_SYBILL_HOLY_SWORD_VISION_2` | `0x801DD3F3` | 5 | `0x05FD` | yes |
| `FLAG_UNDERGROUND_WATERWAY_OPENED` | `0x801DD370` | 4 | `0x01E4` | yes |
| `FLAG_REMOVED_TREE_TO_CLIFFS_OF_MADNESS` | `0x801DD35F` | 5 | `0x015D` | yes |
| `FLAG_CHANGE_SIGN_TO_CLIFFS_OF_MADNESS` | `0x801DD34F` | 3 | `0x00DB` | yes |
| `FLAG_CAN_ACTIVATE_MEGALITHS` | `0x801DD3E6` | 0 | `0x0590` | only if megaliths start on |
| `FLAG_LEARNED_ABOUT_MERRICK_WANTING_FALCONS` | `0x801DD3E6` | 6 | `0x0596` | yes |
| `FLAG_TALKED_WITH_MERRICK` | `0x801DD3E6` | 7 | `0x0597` | yes |
| `FLAG_TALKED_WITH_MERRICK_ABOUT_FALCONS` | `0x801DD3E7` | 0 | `0x0598` | yes |
| `FLAG_ACCEPTED_MERRICK_DEAL_ABOUT_FALCONS` | `0x801DD3E9` | 1 | `0x05A9` | yes |
| `FLAG_OPENED_LAKE_SHRINE_EXTERIOR_MAIN_GATE` | `0x801DD3B2` | 7 | `0x03F7` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_EXTERIOR_RIGHT_GARDEN_BUTTON` | `0x801DD3C1` | 7 | `0x046F` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_EXTERIOR_LEFT_GARDEN_BUTTON` | `0x801DD3C2` | 0 | `0x0470` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_EXTERIOR_GARDEN_MIDDLE_GATE` | `0x801DD3C2` | 6 | `0x0476` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_INTERIOR_MELZAS_INTRO_CUTSCENE_1` | `0x801DD3B3` | 2 | `0x03FA` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_INTERIOR_MELZAS_INTRO_CUTSCENE_2` | `0x801DD3B3` | 3 | `0x03FB` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_NW_SEAL_BROKEN` | `0x801DD3B3` | 4 | `0x03FC` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_W_SEAL_BROKEN` | `0x801DD3B3` | 5 | `0x03FD` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_SW_SEAL_BROKEN` | `0x801DD3B3` | 6 | `0x03FE` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_SE_SEAL_BROKEN` | `0x801DD3B3` | 7 | `0x03FF` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_E_SEAL_BROKEN` | `0x801DD3B4` | 0 | `0x0400` | only if the last dungeon is skipped |
| `FLAG_LAKE_SHRINE_NE_SEAL_BROKEN` | `0x801DD3B4` | 1 | `0x0401` | only if the last dungeon is skipped |
| `FLAG_CAN_ENTER_LARS_CRYPT` | `0x801DD351` | 0 | `0x00E8` | no |
| `FLAG_OTHER_FLOWERS_ARE_IN_GRAVEYARD` | `0x801DD34D` | 7 | `0x00CF` | yes |
| `FLAG_CAN_PUT_FLOWERS_IN_GRAVEYARD` | `0x801DD351` | 1 | `0x00E9` | no |
| `FLAG_CAN_EXIT_LARS_CRYPT` | `0x801DD34E` | 0 | `0x00D0` | yes |
| `FLAG_MAGYSCAR_WALL_IS_CRACKED` | `0x801DD357` | 5 | `0x011D` | yes |
| `FLAG_MAGYSCAR_BOSS_BEATEN` | `0x801DD34E` | 7 | `0x00D7` | no |
| `FLAG_POST_MAGYSCAR_STORY` | `0x801DD38D` | 0 | `0x02C8` | no |
| `FLAG_COAL_MINE_BOSS_BEATEN` | `0x801DD395` | 5 | `0x030D` | no |
| `FLAG_NIRUDE_IS_BROKEN` | `0x801DD34F` | 5 | `0x00DD` | no |
| `FLAG_TORLA_GEYSERS_ACTIVE` | `0x801DD37A` | 3 | `0x0233` | yes |
| `FLAG_NIRUDE_STATUES_VULNERABLE` | `0x801DD3CC` | 6 | `0x04C6` | no. Do not set this at new game; it is the statues' one-shot wake-up. |
| `FLAG_SAW_NIRUDE_STATUES_ACTIVATION_CUTSCENE` | `0x801DD3D0` | 0 | `0x04E0` | no |
| `FLAG_NIRUDE_SAW_TOP_LEFT_CUTSCENE` | `0x801DD3CE` | 6 | `0x04D6` | no |
| `FLAG_NIRUDE_LOWER_BOULDER_REMOVED` | `0x801DD3CE` | 7 | `0x04D7` | yes |
| `FLAG_PLACED_RUBY_CREST` | `0x801DD3CA` | 0 | `0x04B0` | only for a crest excluded from the seed |
| `FLAG_PLACED_SAPPHIRE_CREST` | `0x801DD3CA` | 1 | `0x04B1` | only for a crest excluded from the seed |
| `FLAG_PLACED_TOPAZ_CREST` | `0x801DD3CA` | 2 | `0x04B2` | only for a crest excluded from the seed |
| `FLAG_PLACED_GARNET_CREST` | `0x801DD3CA` | 3 | `0x04B3` | only for a crest excluded from the seed |
| `FLAG_PLACED_EMERALD_CREST` | `0x801DD3CA` | 4 | `0x04B4` | only for a crest excluded from the seed |
| `FLAG_PLACED_AGATE_CREST` | `0x801DD3CA` | 5 | `0x04B5` | only for a crest excluded from the seed |
| `FLAG_PLACED_DIAMOND_CREST` | `0x801DD3CA` | 6 | `0x04B6` | only for a crest excluded from the seed |
| `FLAG_LARS_CRYPT_SAGES_IN_GOOD_ORDER` | `0x801DD3C8` | 6 | `0x04A6` | no |
| `FLAG_LARS_CRYPT_TALKED_WITH_MASTER_SAGE_ONCE` | `0x801DD3C8` | 7 | `0x04A7` | no |
| `FLAG_LARS_CRYPT_SAGES_CUTSCENE_ACTIVE` | `0x801DD343` | 7 | `0x007F` | no |
| `FLAG_CASINO_SHOOTING_RANGE_1_WIN` | `0x801DD3F6` | 1 | `0x0611` | no |
| `FLAG_CASINO_SHOOTING_RANGE_2_WINS` | `0x801DD3F6` | 2 | `0x0612` | no |
| `FLAG_CASINO_SHOOTING_RANGE_3_WINS` | `0x801DD3F6` | 3 | `0x0613` | no |
| `FLAG_CASINO_SHOOTING_RANGE_4_WINS` | `0x801DD3F6` | 4 | `0x0614` | no |
| `FLAG_CASINO_SHOOTING_RANGE_BANNED` | `0x801DD3F6` | 6 | `0x0616` | no |
| `FLAG_CASINO_ROULETTE_1_WIN` | `0x801DD3F6` | 7 | `0x0617` | no |
| `FLAG_CASINO_ROULETTE_2_WINS` | `0x801DD3F7` | 0 | `0x0618` | no. Same bit as roulette 3. |
| `FLAG_CASINO_ROULETTE_3_WINS` | `0x801DD3F7` | 0 | `0x0618` | no. Same bit as roulette 2. |
| `FLAG_CASINO_ROULETTE_4_WINS` | `0x801DD3F7` | 1 | `0x0619` | no |
| `FLAG_CASINO_ROULETTE_BANNED` | `0x801DD3F7` | 3 | `0x061B` | no |
| `FLAG_CASINO_SLIME_1_WIN` | `0x801DD3F7` | 5 | `0x061D` | no |
| `FLAG_CASINO_SLIME_2_WINS` | `0x801DD3F7` | 6 | `0x061E` | no |
| `FLAG_CASINO_SLIME_3_WINS` | `0x801DD3F7` | 7 | `0x061F` | no |
| `FLAG_CASINO_SLIME_4_WINS` | `0x801DD3F8` | 0 | `0x0620` | no |
| `FLAG_CASINO_SLIME_BANNED` | `0x801DD3F8` | 2 | `0x0622` | no |
| `FLAG_LURVY_WELCOMED_US_ONCE` | `0x801DD3BE` | 2 | `0x0452` | yes |
| `FLAG_ANCIENT_SHRINE_SYBOLS_PILLAR_ROOM_CLEARED` | `0x801DD3F8` | 7 | `0x0627` | no |
| `FLAG_JESS_TALKED_LEAVING_HOUSE_ON_GAME_START` | `0x801DD334` | 7 | `0x0007` | no. Reused by the randomizer as the Magyscar bush flag. |

Crests the seed did not roll are placed by setting the matching `FLAG_PLACED_*` bit, not by putting the crest in inventory. Owning a crest is still its inventory quantity. The placed bit is the pedestal.

Boss and clear bits a client can watch without a per-location table:

- Coal Mine boss: `FLAG_COAL_MINE_BOSS_BEATEN`
- Magyscar boss: `FLAG_MAGYSCAR_BOSS_BEATEN`. `FLAG_POST_MAGYSCAR_STORY` is the later Ronan dialog, not the kill.
- Ancient Shrine symbols-pillar room: `FLAG_ANCIENT_SHRINE_SYBOLS_PILLAR_ROOM_CLEARED`. The vanilla bush near Magyscar used this same bit; the randomizer moves that bush to `FLAG_JESS_TALKED_LEAVING_HOUSE_ON_GAME_START`.
- Lake Shrine seals and the exterior gate: the `FLAG_LAKE_SHRINE_*` bits. There is no separate "Melzas dead" flag in `flags.hpp`.
- Nirude broken: `FLAG_NIRUDE_IS_BROKEN`. `FLAG_NIRUDE_STATUES_VULNERABLE` is not a clear flag.

Clear flags for Lars Crypt, the Coastal Cave, the Reptile Lair, the Great Tree, Torla, and the Fairy Pond are **TBD**. They are not named in `flags.hpp`.

## Current map, and when not to grant

| What | Address | Size | Notes |
| --- | --- | --- | --- |
| Requested map id | `0x801F11FC` | u32 | New game and the spawn-apply path store the save spawn map (`0x801DD324`) here. Values are `map_codes.hpp` ids. |
| Map id last passed to the loader | `0x801F5358` | u32 | `0x8002C440` copies the requested id here when it changes, then calls `0x80083F04`. The save-capture path copies this word back to `0x801DD324`. |

Those two words are equal again as soon as the copy happens, which is at the start of the load, not at the end. Inequality is not a "still loading" latch. A fade byte is **TBD**. The menu and text words the client waits on are in Receiving a remote item.

Grants that are only `TryIncrease`, `AddGold`, or an s16/u16 store do not wait on the map. They are safe in the same way new game is, which runs them before the map starts. Do not call `GiveItem` from the client. Its effect calls are unsafe while a map is loading, and the connector cannot enter MIPS. The client writes the stores itself, and it waits on the same gate for every remote item. See Receiving a remote item.

Live X/Y/Z are not the save spawn words. The spawn-apply path scales them before storing elsewhere (`X` becomes `((x * 3) << 3) + 12`, shifted up 16 bits). The live coordinate addresses and the scale for Y/Z are only partly visible and are **TBD**. A client granting items does not need them.

## Receiving a remote item

The BizHawk client grants an item the server sends because a check in another game held this slot's item. It asks for items from other worlds only. A check in Alundra still grants its own item through the chest script, and the new-game patch still grants starting gear. Asking the server for this world's own items would grant them twice.

The client remembers how many of those items it has already granted. That count cannot be derived from HP or from a quantity, because a local Life Vessel and a remote one add to the same counters. It is stored in inventory records 126 and 127, above the runtime id limit of 99 (`0x8012E234`), so `TryIncrease` will not touch them.

| What | Address | Size |
| --- | --- | --- |
| Record 126, magic | `0x801DDA26` | u16. `0x4150` once any item has been granted. `0` on a fresh file, together with a count of 0. |
| Record 126, quantity | `0x801DDA28` | u16. Stays 0. |
| Record 127, count | `0x801DDA2A` | u16. How many remote items have been granted. |
| Record 127, quantity | `0x801DDA2C` | u16. Stays 0. |

Both quantity halfwords stay 0 so the owned check (quantity > 0) ignores the records. A menu that lists owned items never looks up a name for them. A fresh file is magic 0 and count 0. Magic `0x4150` with both quantities at 0 is a stored count. A non-zero quantity, magic 0 with a non-zero count, or any other magic means the game used the record. The client leaves it alone, and it grants nothing until the record is recognizable again.

The decomp save image includes all 128 inventory records. If a real memory-card save does not copy records 126 and 127, loading that save puts the count back at 0. The client then grants the queue again and HP climbs a second time.

The client grants one item per watch, and only when the previous watch saw the same state. It waits, and leaves the count where it is, when any of these is true:

- `FLAG_HUD_ALLOWED` (byte `0x801DD403` bit 6) is off.
- The requested map id at `0x801F11FC` and the loader map id at `0x801F5358` differ. They become equal at the start of a load, so this alone is not a still-loading latch.
- Any of these words is nonzero. Each is a u32, and `1` means that window is open. `0x80107570`, `0x80107618`, and `0x801076C0` are the same field in three records spaced `0xA8` bytes apart. NPC text uses the first and third. The menu uses the middle one. `0x801531BC` is a second menu word and it moved with `0x80107618` in the passing samples.

| State | Address | Gameplay | Menu | NPC text |
| --- | --- | --- | --- | --- |
| Text | `0x80107570` | `0` | `0` | `1` |
| Menu | `0x80107618` | `0` | `1` | `0` |
| Text | `0x801076C0` | `0` | `0` | `1` |
| Menu | `0x801531BC` | `0` | `1` | `0` |

- Save max HP is outside 1..50, save current HP is outside 0..max, or the actor u32 pair at `0x801AC70C` / `0x801AC710` does not equal the save s16 pair.
- Save max MP is outside 0..4, or save current MP is outside 0..max.
- Gilders are outside 0..9999.
- Falcon pending or falcon total is above 50.
- Any inventory quantity for item ids 0..89 is outside 0..99.

`0x800DC4B8` does not change when the menu opens or when NPC text is open, so the client does not read it. `0x8010755C` stays `0` at the start of NPC text and turns on only after the box is already up, so the client does not read that either. A fade byte, a control-lock bit, and a forced-sequence bit are still **TBD**.

The write is a guarded compare of every byte just read. That includes the 14 bytes at `0x801DD820` (current MP, max MP, gilders, equipped weapon, the unread halfword at +12, falcon pending, falcon total), the byte at `0x801DD3E9`, and the 90 inventory records at `0x801DD82E` (360 bytes). The quantity is the s16 at record + 2. The first halfword of each record is guarded and is not part of the play state. A load that changes any guarded byte fails the write, and the same item is tried again. The count moves only together with the item's own bytes. The falcon grant ORs bit 2 of `0x801DD3E9`, so a change to any other bit in that byte fails the write and the grant is tried again.

The client does not call `GiveItem` or `TryIncrease`. It writes the bytes those routines would store and skips their effect calls. No chest fanfare plays. BizHawk shows `Received <name>`. The name is the item that was written. A sword upgrade that became the Fiend Blade shows `Received Fiend Blade`. When the top tier is already owned, the name stays the upgrade. The log can add a suffix, such as `Already carrying Legend Sword`. The toast does not show that suffix.

| Ids | What is written | When it waits |
| --- | --- | --- |
| Inventory item with max quantity at least 1, other than the rows below | Quantity s16 at `0x801DD830 + id*4`, plus 1. Two bytes, so the next record's first halfword is left alone. Nothing is equipped. | Herbs (max 9), Strength Tonic, Strength Elixyr, Magic Elixyr, and Wonder Essence wait when quantity is already at max. Those are used from the bag. The Key caps at 99, and a full stack is counted. A unique already at 1 is counted and the quantity is left alone. |
| Tier 64: sword, flail, bow, armor, the four magic upgrades, boots | The next real tier's quantity. Nothing owned in the slot selects tier 0. Otherwise the best owned tier comes from `FindOwnedItemOfBestTierForSlot`, and the grant is the first id in 0..60 with that slot and best tier + 1. Slot and tier come from `item.json`. Flag bit 0 comes from the vanilla item-info halfword at +2, which the randomizer does not patch. | Never. If that next item is already owned, the receipt is counted. If no further tier exists, the receipt is counted and the upgrade row stays at quantity 0. |
| `0x45`–`0x48` (1 / 5 / 10 / 30 Gilder) | Add that amount to the s16 at `0x801DD824`. A sum past 9999 is stored as 9999. | Never. Already at 9999 is counted and the purse is left alone. |
| `0x4F` Gilded Falcon | Add 1 to the pending u16 at `0x801DD82A`, and OR `0x04` into the byte at `0x801DD3E9` (event `0x05AA`). The other bits in that byte stay. The total at `0x801DD82C` stays for Merrick's dialog to fold. | Never. The fold stores pending plus total and caps that sum at 50. At 50 the falcon is counted. |
| `0x50` Magic Seed | Add 1 to max MP, cap 4, and set current MP to that max. One 4-byte write at `0x801DD820`. | Never. At 4 the seed is counted. If current is already 4, the only write is the received count. |
| `0x51` Small Crystal, `0x52` Large Crystal | Small adds 1 to current MP, clamped to max. Large sets current MP to max MP. `item.json` names these Item `0x51` and Item `0x52`. Their ROM max quantity is 0, so they are not inventory rows. | Never. Already full is counted and MP is left alone. |
| `0x53` Life Vessel | Add 1 to max HP, cap 50, and set current HP to that max. The actor u32 pair and the save s16 pair are both written to those numbers. | Never. At 50 the vessel is counted. If current is below 50 it is filled to 50. |
| `0x54` Dew, `0x55` Drop, `0x56` Water | Heal current HP and write both pairs to the same numbers. Dew adds 2. Drop adds max/4, at least 1. Water adds max/2, at least 5. The result clamps to max. `item.json` names these Item `0x54`, Item `0x55`, and Item `0x56`. | Never. Already at max HP is counted and both pairs are left alone. |
| `0x00` Nothing, `0x3A` | No inventory write. ROM max quantity is 0. `item.json` omits max on `0x3A`, so the parsed max is 1, and that number is not used. | Never. The receipt is counted so the queue moves. |

An item id with no `item.json` record stays at the front of the queue. The client logs that once and waits. A later item is not granted ahead of it. A stack that is only temporarily full waits the same way, without counting the item. Life Vessel, Magic Seed, Gilded Falcon, the two crystals, gilders, and Dew, Drop, and Water do not wait: past the cap they are counted and the stored value stays clamped.

The sync routine between the actor HP pair and the save HP pair is still unidentified. The client writes both pairs itself.
