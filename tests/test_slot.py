# Slot block parsing. Runs without an Archipelago install.

from __future__ import annotations

import importlib.machinery
import sys
import types
import unittest
from pathlib import Path

_world = Path(__file__).resolve().parents[1]
_loader = importlib.machinery.SourceFileLoader("alundra", str(_world / "__init__.py"))
_package = types.ModuleType("alundra")
_package.__path__ = [str(_world)]
_package.__package__ = "alundra"
_package.__loader__ = _loader
_package.__spec__ = importlib.machinery.ModuleSpec("alundra", _loader, is_package=True)
_package.__spec__.submodule_search_locations = [str(_world)]
sys.modules["alundra"] = _package

from alundra.placement import pinned_randomizer_version
from alundra.slot import SLOT_MAIN_RAM, SLOT_SIZE, parse_slot_block, room_seed_matches


def _block(player: bytes = "Néstor\\Room".encode(), apworld: bytes = b"0.1.5", seed: int = 7) -> bytes:
    data = bytearray(0x80)
    data[0:4] = b"ALAP"
    data[4:6] = (1).to_bytes(2, "little")
    data[8:12] = seed.to_bytes(4, "little")
    data[0x0C:0x0C + len(b"1.2.0")] = b"1.2.0"
    data[0x1C:0x1C + len(apworld)] = apworld
    data[0x2C:0x2C + len(player)] = player
    return bytes(data)


class SlotBlockTests(unittest.TestCase):
    def test_address_and_size_match_the_randomizer(self) -> None:
        self.assertEqual(SLOT_MAIN_RAM, 0x1F780)
        self.assertEqual(SLOT_SIZE, 0x80)

    def test_block_round_trip(self) -> None:
        block = parse_slot_block(_block())
        self.assertIsNotNone(block)
        assert block is not None
        self.assertEqual(block.randomizer_version, "1.2.0")
        self.assertEqual(block.apworld_version, "0.1.5")
        self.assertEqual(block.seed, 7)
        self.assertEqual(block.player, "Néstor\\Room")

    def test_rejects_a_block_this_client_cannot_read(self) -> None:
        self.assertIsNone(parse_slot_block(b"\x00" * 0x80))
        self.assertIsNone(parse_slot_block(_block()[:4]))
        shifted = bytearray(_block())
        shifted[4:6] = (2).to_bytes(2, "little")
        self.assertIsNone(parse_slot_block(bytes(shifted)))
        self.assertIsNone(parse_slot_block(_block(apworld=b"0.1")))
        self.assertIsNone(parse_slot_block(_block(player=b"")))
        self.assertIsNone(parse_slot_block(_block(player=b"Your\nName")))
        unterminated = bytearray(_block())
        unterminated[0x2C:0x2C + 64] = b"A" * 64
        self.assertIsNone(parse_slot_block(bytes(unterminated)))

    def test_world_pins_randomizer_1_3_0(self) -> None:
        self.assertEqual(pinned_randomizer_version(), "1.3.0")

    def test_room_seed_must_be_the_embedded_seed(self) -> None:
        self.assertTrue(room_seed_matches(7, {"seed": 7}))
        self.assertFalse(room_seed_matches(7, {"seed": 8}))
        self.assertFalse(room_seed_matches(7, {}))
        self.assertFalse(room_seed_matches(7, None))
        self.assertFalse(room_seed_matches(7, {"seed": True}))
        self.assertFalse(room_seed_matches(7, {"seed": "7"}))


if __name__ == "__main__":
    unittest.main()
