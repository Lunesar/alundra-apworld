# Remote-item grant decisions. Runs without an Archipelago install.

from __future__ import annotations

import struct
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path

_world = Path(__file__).resolve().parents[1]
_package = types.ModuleType("alundra")
_package.__path__ = [str(_world)]
_package.__package__ = "alundra"
sys.modules["alundra"] = _package

from alundra.data import GAME_DATA
from alundra.receive import (
    ACTOR_HP,
    HANDLERS,
    INDEX_MAGIC,
    INDEX_RECORD,
    MAX_HP,
    MENU_STATE,
    MENU_WINDOW,
    READS,
    SAVE_HP,
    TEXT_WINDOW_A,
    TEXT_WINDOW_B,
    Grant,
    Hold,
    PlayState,
    decode_index,
    gameplay_ready,
    grant_life_vessel,
    hold_message,
    index_bytes,
    pack_play_state,
    parse_play_state,
    pending_ap_id,
    plan,
)


def playing(**overrides) -> PlayState:
    # Map 242 is Jess's house on a randomized image. Any equal pair is fine.
    state = PlayState(
        requested_map=242,
        loaded_map=242,
        text_window_a=0,
        menu_window=0,
        text_window_b=0,
        menu_state=0,
        hud_allowed=True,
        actor_current=10,
        actor_max=10,
        save_current=10,
        save_max=10,
        received_index=0,
    )
    return replace(state, **overrides)


class ReceiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vessel = GAME_DATA.item_by_name["Life Vessel"]

    def test_life_vessel_is_the_only_handler(self) -> None:
        self.assertEqual(self.vessel.in_game_id, 0x53)
        self.assertEqual(self.vessel.ap_id, 800083)
        # Max quantity 0: TryIncrease sees quantity already equal to max and writes nothing.
        self.assertEqual(self.vessel.max_quantity, 0)
        self.assertEqual(set(HANDLERS), {self.vessel.ap_id})

    def test_received_index_sits_above_the_runtime_limit(self) -> None:
        self.assertEqual(INDEX_RECORD, 0x1DD82E + 126 * 4)
        self.assertEqual(INDEX_RECORD, 0x1DDA26)
        self.assertEqual(
            READS,
            (
                (0x1F11FC, 4),
                (0x1F5358, 4),
                (TEXT_WINDOW_A, 4),
                (MENU_WINDOW, 4),
                (TEXT_WINDOW_B, 4),
                (MENU_STATE, 4),
                (0x1DD403, 1),
                (ACTOR_HP, 8),
                (SAVE_HP, 4),
                (INDEX_RECORD, 8),
            ),
        )
        self.assertEqual((TEXT_WINDOW_A, MENU_WINDOW, TEXT_WINDOW_B), (0x107570, 0x107618, 0x1076C0))
        self.assertEqual(MENU_WINDOW - TEXT_WINDOW_A, 0xA8)
        self.assertEqual(TEXT_WINDOW_B - MENU_WINDOW, 0xA8)
        self.assertEqual(MENU_STATE, 0x1531BC)

    def test_play_state_roundtrip(self) -> None:
        state = playing(menu_window=1, actor_current=4, save_current=4, received_index=3)
        self.assertEqual(parse_play_state(pack_play_state(state)), state)
        self.assertEqual(pack_play_state(playing(received_index=0))[-1], bytes(8))
        unreadable = parse_play_state(pack_play_state(playing(received_index=None)))
        self.assertIsNone(unreadable.received_index)
        self.assertEqual(replace(unreadable, received_index=0), playing())

    def test_index_quantities_stay_zero(self) -> None:
        self.assertEqual(decode_index(bytes(8)), 0)
        self.assertEqual(decode_index(index_bytes(40)), 40)
        magic, magic_quantity, index, index_quantity = struct.unpack("<HHHH", index_bytes(40))
        self.assertEqual((magic, magic_quantity, index, index_quantity), (INDEX_MAGIC, 0, 40, 0))
        self.assertIsNone(decode_index(struct.pack("<HHHH", INDEX_MAGIC, 1, 3, 0)))
        self.assertIsNone(decode_index(struct.pack("<HHHH", INDEX_MAGIC, 0, 3, 1)))
        self.assertIsNone(decode_index(struct.pack("<HHHH", 0x1234, 0, 3, 0)))
        self.assertIsNone(decode_index(struct.pack("<HHHH", 0, 0, 3, 0)))

    def test_life_vessel_raises_both_hp_pairs_and_fills_current(self) -> None:
        grant = plan(playing(actor_current=5, save_current=5), self.vessel.ap_id)
        self.assertIsInstance(grant, Grant)
        assert isinstance(grant, Grant)
        self.assertEqual(grant.name, "Life Vessel")
        self.assertEqual(grant.detail, "")
        self.assertEqual(
            [(write.address, write.data) for write in grant.writes],
            [
                (ACTOR_HP, bytes.fromhex("0b0000000b000000")),
                (SAVE_HP, bytes.fromhex("0b000b00")),
                (INDEX_RECORD, bytes.fromhex("5041000001000000")),
            ],
        )
        self.assertEqual(
            grant.next_state,
            playing(
                actor_current=11,
                actor_max=11,
                save_current=11,
                save_max=11,
                received_index=1,
            ),
        )

    def test_life_vessel_from_the_starting_total(self) -> None:
        grant = grant_life_vessel(playing())
        self.assertEqual(grant.writes[0].data, struct.pack("<II", 11, 11))
        self.assertEqual(grant.writes[1].data, struct.pack("<hh", 11, 11))
        self.assertEqual(grant.next_state.received_index, 1)

    def test_a_vessel_at_the_cap_is_still_counted(self) -> None:
        hurt = playing(actor_current=40, actor_max=MAX_HP, save_current=40, save_max=MAX_HP)
        healed = plan(hurt, self.vessel.ap_id)
        assert isinstance(healed, Grant)
        self.assertEqual(healed.next_state.save_current, MAX_HP)
        self.assertEqual(healed.next_state.save_max, MAX_HP)
        self.assertEqual(healed.next_state.actor_current, MAX_HP)
        self.assertEqual(healed.detail, "")
        self.assertEqual(healed.next_state.received_index, 1)

        full = playing(actor_current=MAX_HP, actor_max=MAX_HP, save_current=MAX_HP, save_max=MAX_HP)
        counted = plan(full, self.vessel.ap_id)
        assert isinstance(counted, Grant)
        self.assertEqual([write.address for write in counted.writes], [INDEX_RECORD])
        self.assertEqual(counted.detail, "Health is already at maximum")
        self.assertEqual(counted.next_state.actor_current, MAX_HP)
        self.assertEqual(counted.next_state.save_max, MAX_HP)
        self.assertEqual(counted.next_state.received_index, 1)
        self.assertTrue(counted.writes)

    def test_a_dead_alundra_is_healed_to_the_new_max(self) -> None:
        grant = plan(
            playing(actor_current=0, actor_max=1, save_current=0, save_max=1),
            self.vessel.ap_id,
        )
        assert isinstance(grant, Grant)
        self.assertEqual(grant.next_state.save_current, 2)
        self.assertEqual(grant.next_state.save_max, 2)

    def test_grants_wait_while_a_menu_or_text_box_is_open(self) -> None:
        self.assertIs(plan(playing(menu_window=1), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(menu_state=1), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(text_window_a=1), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(text_window_b=1), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIsInstance(plan(playing(), self.vessel.ap_id), Grant)
        self.assertIs(plan(playing(requested_map=1, loaded_map=2), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(hud_allowed=False), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(actor_max=11), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(save_max=0, actor_max=0), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(save_max=51, actor_max=51), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(
            plan(playing(save_current=11, actor_current=11, save_max=10, actor_max=10), self.vessel.ap_id),
            Hold.GAMEPLAY,
        )
        self.assertIs(
            plan(playing(save_current=-1, actor_current=-1), self.vessel.ap_id),
            Hold.GAMEPLAY,
        )
        self.assertTrue(gameplay_ready(playing(requested_map=0, loaded_map=0)))
        self.assertIsInstance(plan(playing(requested_map=0, loaded_map=0), self.vessel.ap_id), Grant)
        self.assertIsNone(hold_message(Hold.GAMEPLAY, self.vessel.ap_id))

    def test_a_used_index_record_holds_the_queue(self) -> None:
        bad = playing(received_index=None)
        self.assertIs(plan(bad, self.vessel.ap_id), Hold.INDEX)
        self.assertIs(
            plan(playing(hud_allowed=False, received_index=None), self.vessel.ap_id),
            Hold.GAMEPLAY,
        )
        self.assertEqual(
            hold_message(Hold.INDEX, None),
            "Received-item record is in use. Grants wait.",
        )
        self.assertIsNone(pending_ap_id(bad, [self.vessel.ap_id]))

    def test_an_unknown_item_stays_in_front_of_a_life_vessel(self) -> None:
        dagger = GAME_DATA.item_by_name["Dagger"].ap_id
        state = playing()
        self.assertIs(plan(state, dagger), Hold.UNKNOWN)
        self.assertEqual(pending_ap_id(state, [dagger, self.vessel.ap_id]), dagger)
        self.assertEqual(
            pending_ap_id(playing(received_index=1), [dagger, self.vessel.ap_id]),
            self.vessel.ap_id,
        )
        self.assertIsNone(pending_ap_id(playing(received_index=1), [self.vessel.ap_id]))
        self.assertEqual(
            hold_message(Hold.UNKNOWN, dagger),
            "Cannot receive Dagger yet. It stays queued.",
        )

    def test_a_full_stack_returns_no_room_without_writes(self) -> None:
        marker = 799999

        def no_room(state: PlayState) -> Hold:
            return Hold.NO_ROOM

        HANDLERS[marker] = no_room
        try:
            self.assertIs(plan(playing(menu_window=1), marker), Hold.GAMEPLAY)
            self.assertIs(plan(playing(), marker), Hold.NO_ROOM)
        finally:
            del HANDLERS[marker]
        self.assertEqual(
            hold_message(Hold.NO_ROOM, self.vessel.ap_id),
            "No room for Life Vessel yet. It stays queued.",
        )
