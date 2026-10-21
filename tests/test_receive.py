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

from alundra.data import GAME_DATA, ITEM_COUNT, ITEM_ID_BASE
from alundra.receive import (
    ACTOR_HP,
    FALCON_PENDING,
    HANDLERS,
    INDEX_MAGIC,
    INDEX_RECORD,
    INVENTORY,
    MAX_HP,
    MENU_STATE,
    MENU_WINDOW,
    READS,
    SAVE_GOLD,
    SAVE_HP,
    SAVE_MP,
    STAT_REST,
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


def stacked(name: str, qty: int, **overrides) -> PlayState:
    state = playing(**overrides)
    item = GAME_DATA.item_by_name[name]
    quantities = list(state.quantities)
    quantities[item.in_game_id] = qty
    return replace(state, quantities=tuple(quantities))


def carrying(*names: str, **overrides) -> PlayState:
    state = playing(**overrides)
    quantities = list(state.quantities)
    for name in names:
        quantities[GAME_DATA.item_by_name[name].in_game_id] = 1
    return replace(state, quantities=tuple(quantities))


def grant_of(state: PlayState, name: str) -> Grant:
    result = plan(state, GAME_DATA.item_by_name[name].ap_id)
    assert isinstance(result, Grant)
    return result


class ReceiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vessel = GAME_DATA.item_by_name["Life Vessel"]

    def test_every_item_has_a_handler(self) -> None:
        self.assertEqual(self.vessel.in_game_id, 0x53)
        self.assertEqual(self.vessel.ap_id, 800083)
        # Max quantity 0: TryIncrease sees quantity already equal to max and writes nothing.
        self.assertEqual(self.vessel.max_quantity, 0)
        self.assertEqual(set(HANDLERS), {item.ap_id for item in GAME_DATA.items})
        # A fresh file is in gameplay, so each item.json id grants or waits on a full stack.
        # Nothing in item.json is unknown.
        for item in GAME_DATA.items:
            result = plan(playing(), item.ap_id)
            self.assertNotIn(result, (Hold.UNKNOWN, Hold.GAMEPLAY, Hold.INDEX), item.name)

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
                (STAT_REST, 14),
                (INVENTORY, ITEM_COUNT * 4),
            ),
        )
        self.assertEqual(STAT_REST, 0x1DD820)
        self.assertEqual(SAVE_MP, 0x1DD820)
        self.assertEqual(SAVE_GOLD, 0x1DD824)
        self.assertEqual(FALCON_PENDING, 0x1DD82A)
        self.assertEqual((TEXT_WINDOW_A, MENU_WINDOW, TEXT_WINDOW_B), (0x107570, 0x107618, 0x1076C0))
        self.assertEqual(MENU_WINDOW - TEXT_WINDOW_A, 0xA8)
        self.assertEqual(TEXT_WINDOW_B - MENU_WINDOW, 0xA8)
        self.assertEqual(MENU_STATE, 0x1531BC)

    def test_play_state_roundtrip(self) -> None:
        quantities = tuple(1 if index == 1 else 0 for index in range(ITEM_COUNT))
        state = playing(
            menu_window=1,
            actor_current=4,
            save_current=4,
            received_index=3,
            mp_current=2,
            mp_max=3,
            gold=40,
            equipped=-1,
            stat_gap=7,
            falcon_pending=1,
            falcon_total=2,
            quantities=quantities,
        )
        self.assertEqual(parse_play_state(pack_play_state(state)), state)
        blobs = pack_play_state(playing(received_index=0))
        index_at = next(index for index, (address, _size) in enumerate(READS) if address == INDEX_RECORD)
        self.assertEqual(blobs[index_at], bytes(8))
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
        self.assertIsInstance(plan(playing(equipped=-1), self.vessel.ap_id), Grant)
        self.assertIsNone(hold_message(Hold.GAMEPLAY, self.vessel.ap_id))

    def test_grants_wait_on_a_bad_stat_or_stack(self) -> None:
        self.assertIs(plan(playing(mp_max=5), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(mp_current=1, mp_max=0), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(gold=10000), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(gold=-1), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(falcon_pending=51), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(playing(falcon_total=51), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(stacked("Herbs", 100), self.vessel.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(stacked("Herbs", -1), self.vessel.ap_id), Hold.GAMEPLAY)
        short = replace(playing(), quantities=playing().quantities[:-1])
        self.assertIs(plan(short, self.vessel.ap_id), Hold.GAMEPLAY)

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
        unknown = ITEM_ID_BASE + ITEM_COUNT
        state = playing()
        self.assertIs(plan(state, unknown), Hold.UNKNOWN)
        self.assertEqual(pending_ap_id(state, [unknown, self.vessel.ap_id]), unknown)
        self.assertEqual(
            pending_ap_id(playing(received_index=1), [unknown, self.vessel.ap_id]),
            self.vessel.ap_id,
        )
        self.assertIsNone(pending_ap_id(playing(received_index=1), [self.vessel.ap_id]))
        self.assertEqual(
            hold_message(Hold.UNKNOWN, unknown),
            f"Cannot receive item {unknown} yet. It stays queued.",
        )

    def test_a_full_stack_stays_in_front_of_a_life_vessel(self) -> None:
        herbs = GAME_DATA.item_by_name["Herbs"]
        full = stacked("Herbs", 9)
        self.assertIs(plan(replace(full, menu_window=1), herbs.ap_id), Hold.GAMEPLAY)
        self.assertIs(plan(full, herbs.ap_id), Hold.NO_ROOM)
        self.assertEqual(pending_ap_id(full, [herbs.ap_id, self.vessel.ap_id]), herbs.ap_id)
        self.assertEqual(full.received_index, 0)
        self.assertEqual(
            hold_message(Hold.NO_ROOM, herbs.ap_id),
            "No room for Herbs yet. It stays queued.",
        )

        opened = grant_of(stacked("Herbs", 8), "Herbs")
        self.assertEqual(opened.name, "Herbs")
        self.assertEqual(opened.detail, "")
        self.assertEqual(opened.next_state.quantities[herbs.in_game_id], 9)
        self.assertEqual(opened.writes[0].address, INVENTORY + herbs.in_game_id * 4 + 2)
        self.assertEqual(opened.writes[0].data, struct.pack("<h", 9))
        self.assertEqual(len(opened.writes[0].data), 2)
        following = plan(opened.next_state, self.vessel.ap_id)
        assert isinstance(following, Grant)
        self.assertEqual(following.next_state.save_max, 11)
        self.assertEqual(following.next_state.quantities[herbs.in_game_id], 9)

    def test_used_once_items_wait_and_uniques_do_not(self) -> None:
        for name in ("Strength Tonic", "Wonder Essence", "Strength Elixyr", "Magic Elixyr"):
            item = GAME_DATA.item_by_name[name]
            self.assertIs(plan(stacked(name, 1), item.ap_id), Hold.NO_ROOM)
            granted = grant_of(playing(), name)
            self.assertEqual(granted.next_state.quantities[item.in_game_id], 1)
            self.assertEqual(granted.writes[0].data, struct.pack("<h", 1))

        key = GAME_DATA.item_by_name["Key"]
        capped = grant_of(stacked("Key", 99), "Key")
        self.assertEqual(capped.detail, "Already carrying Key")
        self.assertEqual([write.address for write in capped.writes], [INDEX_RECORD])
        self.assertEqual(capped.next_state.quantities[key.in_game_id], 99)
        opened = grant_of(stacked("Key", 98), "Key")
        self.assertEqual(opened.next_state.quantities[key.in_game_id], 99)

        dagger = grant_of(carrying("Dagger"), "Dagger")
        self.assertEqual(dagger.detail, "Already carrying Dagger")
        self.assertEqual([write.address for write in dagger.writes], [INDEX_RECORD])
        self.assertEqual(dagger.next_state.quantities[GAME_DATA.item_by_name["Dagger"].in_game_id], 1)
        bomb = grant_of(carrying("Bomb"), "Bomb")
        self.assertEqual(bomb.detail, "Already carrying Bomb")
        self.assertEqual(bomb.next_state.received_index, 1)

    def test_sword_upgrades_walk_the_real_tiers(self) -> None:
        upgrade = GAME_DATA.item_by_name["Sword upgrade"]
        dagger = GAME_DATA.item_by_name["Dagger"]
        state = carrying("Dagger")
        for expected in ("Sword", "Fiend Blade", "Holy Sword", "Legend Sword"):
            grant = plan(state, upgrade.ap_id)
            assert isinstance(grant, Grant)
            item = GAME_DATA.item_by_name[expected]
            self.assertEqual(grant.name, expected)
            self.assertEqual(grant.detail, "")
            self.assertEqual(grant.next_state.quantities[item.in_game_id], 1)
            self.assertEqual(grant.next_state.quantities[upgrade.in_game_id], 0)
            self.assertEqual(grant.next_state.quantities[dagger.in_game_id], 1)
            self.assertEqual(grant.writes[0].address, INVENTORY + item.in_game_id * 4 + 2)
            self.assertEqual(grant.writes[0].data, struct.pack("<h", 1))
            self.assertNotIn(INVENTORY + upgrade.in_game_id * 4 + 2, [write.address for write in grant.writes])
            state = grant.next_state

        capped = plan(state, upgrade.ap_id)
        assert isinstance(capped, Grant)
        self.assertEqual(capped.name, "Sword upgrade")
        self.assertEqual(capped.detail, "Already carrying Legend Sword")
        self.assertEqual([write.address for write in capped.writes], [INDEX_RECORD])
        self.assertEqual(capped.next_state.quantities[upgrade.in_game_id], 0)
        self.assertEqual(
            capped.next_state.quantities[GAME_DATA.item_by_name["Legend Sword"].in_game_id],
            1,
        )

        # Best tier plus one, not the first missing id. Fiend Blade is owned and Sword is not.
        skipped = grant_of(carrying("Dagger", "Fiend Blade"), "Sword upgrade")
        self.assertEqual(skipped.name, "Holy Sword")
        self.assertEqual(skipped.next_state.quantities[GAME_DATA.item_by_name["Sword"].in_game_id], 0)

        bare = grant_of(playing(), "Sword upgrade")
        self.assertEqual(bare.name, "Dagger")
        self.assertEqual(bare.next_state.quantities[dagger.in_game_id], 1)

        holy = grant_of(carrying("Dagger"), "Holy Sword")
        self.assertEqual(holy.name, "Holy Sword")
        self.assertEqual(holy.next_state.quantities[GAME_DATA.item_by_name["Sword"].in_game_id], 0)
        self.assertEqual(holy.next_state.quantities[GAME_DATA.item_by_name["Holy Sword"].in_game_id], 1)

    def test_spells_and_boots_resolve_the_same_way(self) -> None:
        first = grant_of(playing(), "Earth Magic upgrade")
        scroll = GAME_DATA.item_by_name["Earth Scroll"]
        book = GAME_DATA.item_by_name["Earth Book"]
        self.assertEqual(first.name, "Earth Scroll")
        self.assertEqual(first.next_state.quantities[scroll.in_game_id], 1)
        second = plan(first.next_state, GAME_DATA.item_by_name["Earth Magic upgrade"].ap_id)
        assert isinstance(second, Grant)
        self.assertEqual(second.name, "Earth Book")
        self.assertEqual(second.next_state.quantities[book.in_game_id], 1)
        third = plan(second.next_state, GAME_DATA.item_by_name["Earth Magic upgrade"].ap_id)
        assert isinstance(third, Grant)
        self.assertEqual(third.name, "Earth Magic upgrade")
        self.assertEqual(third.detail, "Already carrying Earth Book")
        self.assertEqual(third.next_state.quantities[GAME_DATA.item_by_name["Earth Magic upgrade"].in_game_id], 0)

        boots = grant_of(carrying("Short Boots"), "Boots upgrade")
        self.assertEqual(boots.name, "Long Boots")
        self.assertEqual(boots.next_state.quantities[GAME_DATA.item_by_name["Long Boots"].in_game_id], 1)
        self.assertEqual(boots.next_state.quantities[GAME_DATA.item_by_name["Boots upgrade"].in_game_id], 0)

    def test_gilders_clamp_and_count_at_the_cap(self) -> None:
        clipped = grant_of(playing(gold=9990), "30 Gilder")
        self.assertEqual(clipped.next_state.gold, 9999)
        self.assertEqual(clipped.writes[0].address, SAVE_GOLD)
        self.assertEqual(clipped.writes[0].data, struct.pack("<h", 9999))
        full = grant_of(playing(gold=9999), "1 Gilder")
        self.assertEqual(full.detail, "Gilders are already at maximum")
        self.assertEqual([write.address for write in full.writes], [INDEX_RECORD])
        self.assertEqual(full.next_state.gold, 9999)
        exact = grant_of(playing(gold=9969), "30 Gilder")
        self.assertEqual(exact.next_state.gold, 9999)
        one = grant_of(playing(gold=10), "1 Gilder")
        self.assertEqual(one.next_state.gold, 11)
        self.assertEqual(one.writes[0].data, struct.pack("<h", 11))

    def test_falcons_fill_pending_and_count_at_the_cap(self) -> None:
        grant = grant_of(playing(falcon_pending=3, falcon_total=4), "Gilded Falcon")
        self.assertEqual(grant.next_state.falcon_pending, 4)
        self.assertEqual(grant.next_state.falcon_total, 4)
        self.assertEqual([write.address for write in grant.writes], [FALCON_PENDING, INDEX_RECORD])
        self.assertEqual(grant.writes[0].data, struct.pack("<H", 4))
        for state in (
            playing(falcon_pending=25, falcon_total=25),
            playing(falcon_total=50),
            playing(falcon_pending=50),
        ):
            capped = grant_of(state, "Gilded Falcon")
            self.assertEqual(capped.detail, "Falcons are already at maximum")
            self.assertEqual([write.address for write in capped.writes], [INDEX_RECORD])
            self.assertEqual(capped.next_state.falcon_pending, state.falcon_pending)
            self.assertEqual(capped.next_state.falcon_total, state.falcon_total)

    def test_magic_seed_fills_current_and_counts_at_the_cap(self) -> None:
        first = grant_of(playing(), "Magic Seed")
        self.assertEqual((first.next_state.mp_current, first.next_state.mp_max), (1, 1))
        self.assertEqual(first.writes[0].address, SAVE_MP)
        self.assertEqual(first.writes[0].data, struct.pack("<hh", 1, 1))
        raised = grant_of(playing(mp_current=1, mp_max=3), "Magic Seed")
        self.assertEqual((raised.next_state.mp_current, raised.next_state.mp_max), (4, 4))
        filled = grant_of(playing(mp_current=2, mp_max=4), "Magic Seed")
        self.assertEqual(filled.detail, "")
        self.assertEqual((filled.next_state.mp_current, filled.next_state.mp_max), (4, 4))
        capped = grant_of(playing(mp_current=4, mp_max=4), "Magic Seed")
        self.assertEqual(capped.detail, "Magic is already at maximum")
        self.assertEqual([write.address for write in capped.writes], [INDEX_RECORD])

    def test_crystals_clamp_and_count_when_mp_is_full(self) -> None:
        for name, state in (
            ("Item 0x51", playing()),
            ("Item 0x51", playing(mp_current=2, mp_max=2)),
            ("Item 0x52", playing(mp_current=4, mp_max=4)),
        ):
            capped = grant_of(state, name)
            self.assertEqual(capped.detail, "Magic is already at maximum")
            self.assertEqual([write.address for write in capped.writes], [INDEX_RECORD])
            self.assertEqual(capped.next_state.mp_current, state.mp_current)
            self.assertEqual(capped.next_state.mp_max, state.mp_max)
        one = grant_of(playing(mp_current=1, mp_max=4), "Item 0x51")
        self.assertEqual((one.next_state.mp_current, one.next_state.mp_max), (2, 4))
        self.assertEqual(one.writes[0].data, struct.pack("<hh", 2, 4))
        filled = grant_of(playing(mp_current=1, mp_max=4), "Item 0x52")
        self.assertEqual(filled.next_state.mp_current, 4)
        self.assertEqual(filled.writes[0].data, struct.pack("<hh", 4, 4))

    def test_life_pickups_heal_and_count_when_full(self) -> None:
        for name in ("Item 0x54", "Item 0x55", "Item 0x56"):
            full = grant_of(playing(), name)
            self.assertEqual(full.detail, "Health is already at maximum")
            self.assertEqual([write.address for write in full.writes], [INDEX_RECORD])
            self.assertEqual(full.next_state.save_current, 10)
            self.assertEqual(full.next_state.save_max, 10)

        dew = grant_of(playing(actor_current=8, save_current=8), "Item 0x54")
        self.assertEqual(dew.next_state.save_current, 10)
        self.assertEqual(dew.next_state.actor_current, 10)
        self.assertEqual(dew.next_state.save_max, 10)
        self.assertEqual(dew.writes[0].data, struct.pack("<II", 10, 10))
        self.assertEqual(dew.writes[1].data, struct.pack("<hh", 10, 10))
        partial = grant_of(playing(actor_current=9, save_current=9), "Item 0x54")
        self.assertEqual(partial.next_state.save_current, 10)

        drop = grant_of(playing(actor_current=0, save_current=0), "Item 0x55")
        self.assertEqual(drop.next_state.save_current, 2)
        tiny = grant_of(playing(actor_current=0, actor_max=1, save_current=0, save_max=1), "Item 0x55")
        self.assertEqual(tiny.next_state.save_current, 1)
        clamped = grant_of(playing(actor_current=40, actor_max=50, save_current=40, save_max=50), "Item 0x55")
        self.assertEqual(clamped.next_state.save_current, 50)
        self.assertEqual(clamped.next_state.actor_max, 50)

        water = grant_of(playing(actor_current=0, save_current=0), "Item 0x56")
        self.assertEqual(water.next_state.save_current, 5)
        floored = grant_of(playing(actor_current=6, actor_max=8, save_current=6, save_max=8), "Item 0x56")
        self.assertEqual(floored.next_state.save_current, 8)
        half = grant_of(playing(actor_current=0, actor_max=20, save_current=0, save_max=20), "Item 0x56")
        self.assertEqual(half.next_state.save_current, 10)
        self.assertEqual(half.writes[0].address, ACTOR_HP)
        self.assertEqual(half.writes[1].address, SAVE_HP)

    def test_nothing_and_the_empty_item_are_counted(self) -> None:
        nothing = grant_of(playing(), "Nothing")
        self.assertEqual(nothing.name, "Nothing")
        self.assertEqual(nothing.detail, "")
        self.assertEqual([write.address for write in nothing.writes], [INDEX_RECORD])
        self.assertEqual(nothing.next_state.quantities[0], 0)
        empty = grant_of(playing(), "Item 0x3A")
        self.assertEqual(empty.next_state.quantities[0x3A], 0)
        self.assertEqual([write.address for write in empty.writes], [INDEX_RECORD])
