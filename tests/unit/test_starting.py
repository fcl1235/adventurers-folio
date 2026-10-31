# -*- coding: utf-8 -*-
"""起始装备（2024 的 A/B 选项）：内容、自动穿戴、金币、存档往返。

这一组盯四件事：

  1. **12 个职业都有选项**，且每组引用的物品真的存在（少一件就是少把武器）。
  2. **自动穿戴的推断对不对**：AC 最高的甲上身、主手是第一把武器、双手武器
     不配副手也不配盾。这几条推错了，建出来的卡第一眼就是错的（AC 10、徒手）。
  3. **金币包只有钱**，不会顺手给一套装备。
  4. **`None` 与 `""` 的语义不同**：底层建角色不给装备，界面那条路给默认那一组。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.inventory import EquipSlot, Inventory

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
BARBARIAN = "dnd2024.class.barbarian"
FIGHTER_A = "dnd2024.package.fighter.a"
FIGHTER_B = "dnd2024.package.fighter.b"
FIGHTER_GOLD = "dnd2024.package.fighter.c"
CHAIN_MAIL = "dnd2024.item.armor.chain_mail"
STUDDED = "dnd2024.item.armor.studded_leather"
GREATSWORD = "dnd2024.item.weapon.greatsword"
SCIMITAR = "dnd2024.item.weapon.scimitar"
SHORTSWORD = "dnd2024.item.weapon.shortsword"
LONGBOW = "dnd2024.item.weapon.longbow"

SCORES = {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}


class PackContentTest(unittest.TestCase):
    """内容层：选项齐全、物品都在、职业对得上。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = api.load_content(PLUGINS)

    def test_every_class_has_options(self):
        for class_id in self.bundle.classes:
            with self.subTest(class_id=class_id):
                self.assertTrue(self.bundle.starting_packs(class_id),
                                "%s 没有起始装备选项" % class_id)

    def test_packs_reference_known_items(self):
        known = set(self.bundle.weapons) | set(self.bundle.armors) | set(self.bundle.gears)
        for class_id, packs in self.bundle.starting_gear.items():
            for pack in packs:
                for item_id, _ in pack.items:
                    self.assertIn(item_id, known, "%s 引用了不存在的物品" % pack.id)

    def test_ids_are_globally_unique(self):
        seen = [pack.id for packs in self.bundle.starting_gear.values() for pack in packs]
        self.assertEqual(len(seen), len(set(seen)))

    def test_each_class_has_a_gold_option(self):
        """每组选项里必须有一条纯金币的 —— 否则玩家想自己买东西就没得选。"""
        for class_id, packs in self.bundle.starting_gear.items():
            with self.subTest(class_id=class_id):
                self.assertTrue(any(not pack.items and pack.gold > 0 for pack in packs))

    def test_options_are_listed_for_ui(self):
        rows = api.starting_options(self.bundle, FIGHTER)
        self.assertEqual(rows["count"], 3)
        first = rows["options"][0]
        self.assertTrue(first["label"])
        self.assertIn(CHAIN_MAIL, [item["id"] for item in first["items"]])

    def test_class_without_content_returns_empty(self):
        """没有这份内容的职业返回空列表，不抛错（第三方插件可能不给）。"""
        self.assertEqual(api.starting_options(self.bundle, "dnd2024.class.none")["count"], 0)


class ApplyPackTest(unittest.TestCase):
    """规则层：物品入包、自动穿戴、金币。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = api.load_content(PLUGINS)

    def _build(self, pack):
        return api.new_character(self.bundle, FIGHTER, 1, SCORES,
                                 starting_pack=pack)

    def test_none_means_no_equipment(self):
        actor = api.new_character(self.bundle, FIGHTER, 1, SCORES)
        self.assertEqual(actor.inventory.items, [])
        self.assertEqual(actor.inventory.equipped, {})
        self.assertEqual(actor.inventory.coins_gp, 0)

    def test_default_pack_when_empty_string(self):
        actor = self._build("")
        self.assertEqual({slot: item for slot, item in actor.inventory.equipped.items()},
                         {EquipSlot.ARMOR: CHAIN_MAIL,
                          EquipSlot.MAIN_HAND: GREATSWORD})

    def test_two_handed_gets_no_off_hand(self):
        """战士 A 包是锁甲 + 巨剑（双手）—— 巨剑在手就不能再挂副手武器或盾。"""
        actor = self._build("")
        weapon = self.bundle.weapons[GREATSWORD]
        self.assertIn("two_handed", weapon.properties)
        self.assertNotIn(EquipSlot.OFF_HAND, actor.inventory.equipped)
        self.assertNotIn(EquipSlot.SHIELD, actor.inventory.equipped)

    def test_one_handed_pair_fills_both_hands(self):
        """B 包是弯刀 + 短剑 + 长弓：弯刀主手、短剑副手，长弓留在包里。"""
        actor = self._build(FIGHTER_B)
        self.assertEqual(actor.inventory.equipped[EquipSlot.MAIN_HAND], SCIMITAR)
        self.assertEqual(actor.inventory.equipped[EquipSlot.OFF_HAND], SHORTSWORD)
        self.assertEqual(actor.inventory.equipped[EquipSlot.ARMOR], STUDDED)
        self.assertTrue(actor.inventory.has_item(LONGBOW), "长弓该留在背包里")

    def test_gold_option_gives_only_money(self):
        actor = self._build(FIGHTER_GOLD)
        self.assertEqual(actor.inventory.items, [])
        self.assertEqual(actor.inventory.coins_gp, 155)
        self.assertEqual(actor.inventory.equipped, {})

    def test_pack_gold_is_added(self):
        actor = self._build(FIGHTER_A)
        self.assertEqual(actor.inventory.coins_gp, 4)

    def test_stacked_items_merge(self):
        """箭矢 20 支是一件 ×20，不是 20 条。"""
        actor = self._build(FIGHTER_B)
        refs = [ref for ref in actor.inventory.items
                if ref.item_id == "dnd2024.item.gear.arrows"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].quantity, 20)

    def test_ac_uses_the_equipped_armor(self):
        sheet = api.character_sheet(self._build(""), self.bundle)
        self.assertEqual(sheet["ac"]["total"], 16)          # 锁甲 16
        self.assertIn("锁甲", sheet["ac"]["detail"])

    def test_attack_list_has_the_weapon(self):
        sheet = api.character_sheet(self._build(""), self.bundle)
        names = [row.get("name") for row in sheet["attacks"]]
        self.assertIn("巨剑", names)

    def test_barbarian_axe_keeps_one_hand_free(self):
        """野蛮人 A 包：巨斧（双手）+ 4 把手斧 —— 手斧只能进包，不能进副手。"""
        actor = api.new_character(self.bundle, BARBARIAN, 1, SCORES,
                                  starting_pack="")
        main = actor.inventory.equipped.get(EquipSlot.MAIN_HAND)
        self.assertEqual(main, "dnd2024.item.weapon.greataxe")
        self.assertNotIn(EquipSlot.OFF_HAND, actor.inventory.equipped)

    def test_wrong_class_pack_is_refused(self):
        with self.assertRaises(api.RuleError):
            api.new_character(self.bundle, WIZARD, 1, SCORES,
                              starting_pack=FIGHTER_A)
        with self.assertRaises(api.RuleError):
            api.new_character(self.bundle, FIGHTER, 1, SCORES,
                              starting_pack="dnd2024.package.nope.a")


class InventoryViewTest(unittest.TestCase):
    """投影与存档：背包能显示、金币能存回去。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = api.load_content(PLUGINS)
        cls.actor = api.new_character(cls.bundle, FIGHTER, 1, SCORES,
                                      starting_pack=FIGHTER_B, name_zh="甲",
                                      name_en="A")

    def test_view_lists_names_and_slots(self):
        view = api.inventory_view(self.actor, self.bundle)
        self.assertEqual(view["coins_gp"], 11)
        self.assertEqual(view["count"], len(self.actor.inventory.items))
        by_id = {row["id"]: row for row in view["items"]}
        self.assertEqual(by_id[SCIMITAR]["equipped_in"], ["主手"])
        self.assertEqual(by_id[SHORTSWORD]["equipped_in"], ["副手"])
        self.assertEqual(by_id["dnd2024.item.gear.arrows"]["count"], 20)
        self.assertIn("内含", by_id["dnd2024.item.gear.dungeoneers_pack"]["detail"])

    def test_sheet_carries_inventory(self):
        sheet = api.character_sheet(self.actor, self.bundle)
        self.assertIn("inventory", sheet)
        self.assertEqual(sheet["inventory"]["coins_gp"], 11)

    def test_coins_survive_save_and_load(self):
        data = api.save_character(self.actor)
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.inventory.coins_gp, 11)
        self.assertEqual([(ref.item_id, ref.quantity) for ref in back.inventory.items],
                         [(ref.item_id, ref.quantity) for ref in self.actor.inventory.items])

    def test_old_save_without_coins_loads_as_zero(self):
        """v3 的存档没有 `coins_gp`：读出来是 0，不许因此读不出档。"""
        payload = self.actor.inventory.to_dict()
        payload.pop("coins_gp")
        inv = Inventory.from_dict(payload)
        self.assertEqual(inv.coins_gp, 0)
        self.assertTrue(inv.items)


class RebuildKeepsEquipmentTest(unittest.TestCase):
    """改等级/改卡不该把起始装备洗掉（它们是背包事实，不是派生值）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = api.load_content(PLUGINS)

    def test_level_up_keeps_inventory(self):
        actor = api.new_character(self.bundle, FIGHTER, 1, SCORES,
                                  starting_pack=FIGHTER_B)
        after = api.level_up(self.bundle, actor)
        self.assertEqual(after.inventory.coins_gp, 11)
        self.assertEqual(after.inventory.equipped.get(EquipSlot.ARMOR), STUDDED)


if __name__ == "__main__":
    unittest.main()
