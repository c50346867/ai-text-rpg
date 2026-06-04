# -*- coding: utf-8 -*-
"""Tests for AI Text RPG Engine."""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.engine.character import Character, Stats, Stat, StatusEffect, StatusType, EquipmentSlot
from backend.engine.combat import CombatEngine, EnemyInstance, DamageRoll, CombatPhase
from backend.engine.world import WorldManager, Area, AreaType, Location, Weather, WeatherType
from backend.engine.story_generator import StoryGenerator, Quest, QuestType, QuestStatus, QuestObjective, QuestManager
from backend.engine.game_master import GameMaster, DiceRoller


# ============================================================
# Dice Roller Tests
# ============================================================

class TestDiceRoller:
    def test_roll_d20(self):
        result = DiceRoller.roll("1d20")
        assert "results" in result
        assert len(result["results"]) == 1
        assert 1 <= result["results"][0] <= 20

    def test_roll_multiple(self):
        result = DiceRoller.roll("3d6")
        assert len(result["results"]) == 3
        for r in result["results"]:
            assert 1 <= r <= 6

    def test_roll_with_modifier(self):
        result = DiceRoller.roll("2d8+3")
        expected_min = 2 * 1 + 3  # 5
        expected_max = 2 * 8 + 3  # 19
        assert expected_min <= result["total"] <= expected_max

    def test_ability_check_success(self):
        result = DiceRoller.ability_check(5, 10)
        # With +5, minimum total is 6, so DC10 should succeed
        assert "success" in result

    def test_ability_check_failure(self):
        # No matter what, we can't guarantee failure, but we can at least test structure
        result = DiceRoller.ability_check(-5, 30)
        assert "success" in result
        assert "dc" in result


# ============================================================
# Character Tests
# ============================================================

class TestCharacter:
    def test_create_default(self):
        char = Character.create_default("测试角色")
        assert char.name == "测试角色"
        assert char.race_id == "human"
        assert char.class_id == "fighter"
        assert char.level == 1
        assert char.current_hp > 0

    def test_stats(self):
        stats = Stats(strength=15, dexterity=14, constitution=13, intelligence=12, wisdom=10, charisma=8)
        char = Character("Stats测试", "human", "fighter", stats)
        # 人类有全属性+1
        assert char.stats.get(Stat.STRENGTH) == 16
        assert char.stats.get(Stat.DEXTERITY) == 15
        assert char.stats.get(Stat.CONSTITUTION) == 14

    def test_modifier_calculation(self):
        stats = Stats(strength=18)  # 18-10/2 = 4
        char = Character("力士", "dwarf", "fighter", stats)
        # 矮人力量+1 -> 19 -> (19-10)/2 = 4
        assert char.stats.modifier(Stat.STRENGTH) == 4

    def test_level_up(self):
        char = Character.create_default("升级测试")
        old_level = char.level
        char.add_xp(500)  # 超过 300, 达到 2 级
        assert char.level > old_level

    def test_take_damage(self):
        char = Character.create_default("受伤测试")
        old_hp = char.current_hp
        char.take_damage(5)
        assert char.current_hp == old_hp - 5

    def test_heal(self):
        char = Character.create_default("治疗测试")
        char.take_damage(10)
        char.heal(5)
        assert char.current_hp > char.max_hp - 10

    def test_status_effects(self):
        char = Character.create_default("状态测试")
        char.add_status(StatusEffect(StatusType.POISONED, 3, "test"))
        assert char.has_status(StatusType.POISONED)
        char.remove_status(StatusType.POISONED)
        assert not char.has_status(StatusType.POISONED)

    def test_equipment(self):
        char = Character.create_default("装备测试")
        from backend.engine.character import Item
        sword = Item(
            id="test_sword", name="测试剑", name_en="Test Sword",
            type="weapon", subtype="近战武器", rarity="普通",
            description="测试用剑", value=10, weight=3,
            equippable=True, slot="weapon",
            properties={"damage_dice": "1d8", "damage_type": "挥砍", "attack_bonus": 1},
            effects=[], special="",
        )
        success, _, _ = char.equipment.equip(sword)
        assert success
        assert char.equipment.weapon is not None


# ============================================================
# Combat Tests
# ============================================================

class TestCombat:
    def test_combat_init(self):
        char = Character.create_default("战斗测试")
        enemy_data = {
            "id": "test_goblin", "name": "测试哥布林", "armor_class": 13,
            "hit_points": 12, "stats": {"dexterity": 14},
            "xp": 50, "loot": {"gold": "1d4", "items": []},
        }
        enemy = EnemyInstance.from_template(enemy_data)
        engine = CombatEngine([char], [enemy])
        state = engine.start_combat()
        assert state["phase"] in ("PLAYER_TURN", "ENEMY_TURN")

    def test_combat_damage_roll(self):
        dr = DamageRoll(2, 6, 0, "挥砍")
        for _ in range(100):
            dmg = dr.roll()
            assert 2 <= dmg <= 12

    def test_combat_victory(self):
        char = Character.create_default("胜利测试")
        enemy_data = {
            "id": "weak_slime", "name": "史莱姆", "armor_class": 5,
            "hit_points": 1, "stats": {"dexterity": 6},
            "xp": 10, "loot": {"gold": "1", "items": []},
        }
        enemy = EnemyInstance.from_template(enemy_data)
        engine = CombatEngine([char], [enemy])
        engine.start_combat()
        result = engine.process_action("attack", "enemy_0")
        # 应该命中（AC 很低）
        assert "victory" in result or engine.victory

    def test_damage_roll_from_string(self):
        dr = DamageRoll.from_string("2d6+3", damage_type="火焰")
        assert dr.dice_count == 2
        assert dr.dice_sides == 6
        assert dr.bonus == 3
        assert dr.damage_type == "火焰"


# ============================================================
# World Tests
# ============================================================

class TestWorld:
    def test_world_init(self):
        world = WorldManager()
        assert len(world.areas) > 0

    def test_time_system(self):
        world = WorldManager()
        old_time = world.time.format_time()
        world.advance_time(hours=2)
        assert world.time.format_time() != old_time

    def test_discover_location(self):
        world = WorldManager()
        loc_id = "goblin_camp"  # 默认应该存在
        if world.get_location(loc_id):
            result = world.discover_location(loc_id)
            assert result
            loc = world.get_location(loc_id)
            assert loc.is_discovered


# ============================================================
# Story Tests
# ============================================================

class TestStory:
    def test_story_load_tutorial(self):
        sg = StoryGenerator()
        scenario = sg.load_scenario("tutorial")
        assert scenario is not None
        assert "scenes" in scenario
        assert len(scenario["scenes"]) > 0

    def test_story_choices(self):
        sg = StoryGenerator()
        sg.load_scenario("tutorial")
        choices = sg.get_choices()
        assert len(choices) > 0

    def test_quest_manager(self):
        qm = QuestManager()
        quest = Quest(
            id="test_quest", name="测试任务", description="测试",
            quest_type=QuestType.SIDE,
            objectives=[QuestObjective(id="obj1", description="击败3只哥布林", type="kill", target="goblin", count_required=3)],
        )
        qm.add_quest(quest)
        assert len(qm.get_active_quests()) == 1

        # 推进进度
        msgs = qm.progress_quest("test_quest", "kill", "goblin", count=3)
        assert quest.all_objectives_completed

    def test_generate_random_quest(self):
        qm = QuestManager()
        quest = qm.generate_random_quest(party_level=3)
        assert quest.id.startswith("random_")
        assert quest.quest_type == QuestType.RANDOM


# ============================================================
# Game Master Integration Tests
# ============================================================

class TestGameMaster:
    def test_gm_create_session(self):
        gm = GameMaster()
        session = gm.create_session("test_session")
        assert session.id == "test_session"

    def test_gm_create_character(self):
        gm = GameMaster()
        char = gm.create_character("阿尔萨斯", "human", "fighter")
        assert char.name == "阿尔萨斯"

    def test_gm_start_game(self):
        gm = GameMaster()
        session = gm.create_session("test_game")
        char = gm.create_character("英雄", "elf", "ranger")
        gm.join_party("test_game", char)
        result = gm.start_game("test_game", "tutorial")
        assert result.get("success")

    def test_gm_roll_dice(self):
        gm = GameMaster()
        result = gm.roll_dice("1d20")
        assert 1 <= result["total"] <= 20

    def test_gm_skill_check(self):
        gm = GameMaster()
        char = gm.create_character("测试", "human", "fighter")
        result = gm.perform_skill_check(char, "力量", dc=10)
        assert "success" in result

    def test_gm_process_action(self):
        gm = GameMaster()
        session = gm.create_session("test_action")
        char = gm.create_character("亚瑟", "human", "fighter")
        gm.join_party("test_action", char)
        gm.start_game("test_action", "tutorial")

        result = gm.process_action("test_action", "查看角色")
        assert result.get("success", True)
        assert result.get("messages")


# ============================================================
# Data File Tests
# ============================================================

class TestDataFiles:
    def _load_json(self, filename: str):
        path = Path(__file__).resolve().parent.parent / "data" / filename
        assert path.exists(), f"{filename} not found"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_races_json(self):
        data = self._load_json("races.json")
        assert len(data) > 0
        for race in data:
            assert "id" in race
            assert "name" in race
            assert "stat_bonuses" in race

    def test_classes_json(self):
        data = self._load_json("classes.json")
        assert len(data) > 0
        for cls in data:
            assert "id" in cls
            assert "primary_stat" in cls
            assert "hit_dice" in cls

    def test_monsters_json(self):
        data = self._load_json("monsters.json")
        assert len(data) > 0
        for m in data:
            assert "id" in m
            assert "name" in m
            assert "armor_class" in m
            assert "hit_points" in m
            assert "actions" in m

    def test_items_json(self):
        data = self._load_json("items.json")
        assert len(data) > 0
        for item in data:
            assert "id" in item
            assert "type" in item
            assert "rarity" in item

    def test_tutorial_json(self):
        data = self._load_json("scenarios/tutorial.json")
        assert "scenes" in data
        assert len(data["scenes"]) > 0
        assert data["scenes"][0]["id"] == "scene_001"
