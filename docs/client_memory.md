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
| +14 | `0x801DD82A` | u16 | Gilded Falcon count. The falcon give path adds 1 and caps at 50. Not an inventory quantity. |
| +16 | `0x801DD82C` | — | Not written by inventory init. **TBD**. |

`TryIncrease` does not equip anything. New game grants the starting gear and then calls `0x8004FB28` with item id 1 so the dagger is in hand. A client that only increments a weapon's quantity has granted the weapon; it has not equipped it.

### Inventory records (`0x801DD82E`)

128 records, 4 bytes each, item id 0 through 127. Init zeroes both halfwords of all 128. The runtime id limit lives in the u32 at `0x8012E234`, which init sets to 99: `TryIncrease` rejects an id that is negative or `>=` that word. Randomizer item ids (`item_codes.hpp`) stop at `0x59`, which is inside that range.

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
| +2 | u16 | Bit 0 set: `FindOwned` keeps scanning this slot for a higher tier. Bit 0 clear: it returns this item immediately. |
| +4 | u16 | Tier |
| +6 | s16 | Max quantity. Herbs is 9, the Key is 99, a normal unique item is 1. |

Items with max quantity 0 (gilder pickups, Gilded Falcon, Magic Seed, the three life pickups, Life Vessel) never stick in the inventory array. `TryIncrease` sees quantity 0 equal to max 0 and does not increment. They are granted by the paths in the next section.

## What "give item" means

Two different operations, and they are not interchangeable.

**Inventory write.** Store the s16 quantity at `0x801DD830 + id*4`. That is enough for a normal item whose max is at least 1, and it is what the owned check reads. It does not run the progressive-item hook, does not equip, does not add gilders, and does not move HP or MP. Writing the quantity of an upgrade id (`0x0B` sword upgrade, `0x0C` flail, `0x0D` bow, `0x0F` armor, `0x15`–`0x18` magic, `0x1D` boots) does not turn it into the next real tier.

**The game's give routine.** `TryIncrease` at `0x8004FBE4`, item id in `a0`. If quantity is already equal to the max in the item-info table it returns the current quantity and writes nothing. Otherwise it stores quantity + 1 and returns that. New game grants starting items by calling this, not by writing the s16 itself.

On a randomized image the progressive patch overwrites the two instructions at `0x8004FBF4` with a call that may replace `a0`/`a1` with the next tier before the increment. The entry point stays `0x8004FBE4`. Calling it is how an upgrade id becomes a real sword, flail, bow, armor, spell, or boots. A raw quantity write skips that.

`TryIncrease` does not play the chest fanfare. The routine that does, and that also handles the items `TryIncrease` cannot represent, is `GiveItem` at `0x800344D4`. Its only caller (`0x8007EB4C`) passes:

- `a0` = `0x801AC6F8` (a fixed global, not a value loaded from a register)
- `a1` = item id

`GiveItem` then dispatches:

| Item ids | What it actually does |
| --- | --- |
| `0x45`–`0x48` (1 / 5 / 10 / 30 Gilder) | `AddGold` at `0x8004F668` with `a0` = 1, 5, 10, or 30. Adds to the gilders s16 and caps at 9999. No inventory write. |
| `0x49`–`0x4E` (Sluice Key through Zolist Stone) | `TryIncrease` |
| `0x4F` Gilded Falcon | Adds 1 to the u16 at `0x801DD82A`, caps at 50. The tail of that function (`0x8004FDB4`) loads another word; what it does with it is **TBD**. |
| `0x50` Magic Seed | Adds 1 to max MP (cap 4) and sets current MP to that max, then calls effect routines. |
| `0x51` Small Crystal | Adds 1 to current MP, clamped to max MP, then calls effect routines. |
| `0x52` Large Crystal | Sets current MP to max MP, then calls effect routines. |
| `0x53` Life Vessel | Adds 1 to the u32 at `0x801AC710` and sets the u32 at `0x801AC70C` equal to it, then calls effect routines. |
| `0x54` Dew of Life | Adds 2 to the u32 at `0x801AC70C`, clamped to the u32 at `0x801AC710`. No effect call in this handler. |
| `0x55` Drop of Life, `0x56` Water of Life | Edit that same u32 pair, then call an effect routine. Water's handler clamps one computed value at 5. The exact arithmetic is **TBD**. |
| Any other id, including crests and keys | `TryIncrease` |

The u32 pair at `0x801AC70C` / `0x801AC710` is not the save HP s16 pair at `0x801DD81C` / `0x801DD81E`. Life Vessel does not call the HP setters. How the two pairs stay in sync is **TBD**. Do not poke one and assume the other moved.

For a client, the grant that matches "the player now has the item" without depending on a map being on screen:

- Ordinary item, including a progressive upgrade id: call `0x8004FBE4` with the item id. A quantity write is equivalent only when the id is not an upgrade id and the current quantity is below max.
- Gilders: call `0x8004F668` or add to the s16 at `0x801DD824` (cap 9999).
- Falcon: add 1 to the u16 at `0x801DD82A` (cap 50).
- Magic Seed / crystals: the MP s16 updates above. Calling `GiveItem` also runs effect code.
- Life Vessel / Dew / Drop / Water: only the actor u32 pair is understood, and only Dew and Life Vessel are fully specified. Calling `GiveItem` for these runs effect code.

`GiveItem` itself is the wrong call while a map is loading, because of those effect calls. `TryIncrease`, `AddGold`, and the s16 stores do not call them. They are also what new game uses before any map is running.

## Checked locations (chests and other sources)

A taken source is an event-flag bit, not a byte next to the inventory record. Map scripts turn bits on with opcode `0x05` (`FlagOn`) and test them with `0x30` / `0x31` (`IfFlagOn` / `IfFlagOff`). The same bits are what `flags.hpp` names. `item_source.json` does not store a flag. Its `address` / `spriteAddress` fields are offsets in `DATAS.BIN` where the patch writes the item id, not RAM, and not the checked-bit.

Which event code belongs to which location id is **TBD** except the rows below. Do not derive one from the item-id file offset. A chest that lives in a map entity record stores its collected event code in the u16 at record + 0x10, and the item id in the byte at record + 0x12. That byte is the source `address` only for those entity chests. Shops, Merrick, and NPC gifts store an item id in script bytes, and the two bytes before that id are not a flag. A code whose low 15 bits are `>= 0x800`, or code 0, does not name one chest.

| Location | Source id | Event code | Byte | Bit |
| --- | --- | --- | --- | --- |
| Inoa: Chest in Lutas's house (Secret Pass) | 1 | `0x0680` | `0x801DD404` | 0 |

The Lutas record is at DATAS.BIN `0x499699C` on USA 1.1. Its contents byte is `0x39` (Secret Pass), at source address `0x49969AE`. The client reports this one location. The other source ids stay **TBD**.

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

Those two words are equal again as soon as the copy happens, which is at the start of the load, not at the end. Inequality is not a "still loading" latch. A menu-open byte, a fade byte, and a "player has control" byte are **TBD**. Script opcodes `0x10` / `0x11` (`PlayerLoseControl` / `PlayerGainControl`) exist; their RAM flag does not, in this repo.

Grants that are only `TryIncrease`, `AddGold`, or an s16/u16 store do not wait on the map. They are safe in the same way new game is, which runs them before the map starts. Grants that go through `GiveItem` are not, because of the effect calls. Until the in-control flag is known, do not call `GiveItem` from the client.

Live X/Y/Z are not the save spawn words. The spawn-apply path scales them before storing elsewhere (`X` becomes `((x * 3) << 3) + 12`, shifted up 16 bits). The live coordinate addresses and the scale for Y/Z are only partly visible and are **TBD**. A client granting items does not need them.
