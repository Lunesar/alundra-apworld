# Alundra for Archipelago

An [Archipelago](https://archipelago.gg) world for Alundra (PlayStation). It places items with the Alundra randomizer, patches a USA 1.1 disc, and connects that disc to a multiworld through BizHawk.

## Play

Install [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer, then install `alundra.apworld` from this repository's Releases page. You need your own USA 1.1 disc image.

[docs/setup_en.md](docs/setup_en.md) is the player guide: the YAML, the patch button, and BizHawk. [docs/en_Alundra.md](docs/en_Alundra.md) is what a multiworld seed changes.

## Develop

`.apignore` leaves [docs/TODO.md](docs/TODO.md), [docs/client_memory.md](docs/client_memory.md), and [data/README.md](data/README.md) out of the apworld. The setup guide and the game page stay in.

Place the patcher under `patcher/linux` and `patcher/win32` from the [alundra-randomizer](https://github.com/Lunesar/alundra-randomizer) release named in `randomizer.lock.json`. The workflow artifacts are `alundra-aptools-linux` and `alundra-aptools-win64`.

## Credit

Dinopony wrote the original Alundra randomizer. This world patches with [alundra-randomizer](https://github.com/Lunesar/alundra-randomizer).

Released under the MIT License. See [LICENSE](LICENSE).
