# -*- coding: utf-8 -*-
"""
Combat System — 战斗系统模块。

提供回合制战斗引擎，支持先攻顺序、攻击命中判定、
伤害计算、技能释放、经验值和战利品等。

Classes:
    CombatEngine: 战斗引擎
    CombatAction: 战斗动作
    DamageRoll: 伤害骰子
"""

from __future__ import annotations

import json
import random
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.engine.character import Character, Stat, StatusEffect, StatusType, GameState


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CombatActionType(Enum):
    """战斗动作类型。"""
    ATTACK = "attack"
    CAST_SPELL = "cast_spell"
    USE_ITEM = "use_item"
    DODGE = "dodge"
    DASH = "dash"
    DISENGAGE = "disengage"
    HIDE = "hide"
    READY = "ready"
    HELP = "help"


class DamageType(Enum):
    """伤害类型。"""
    SLASHING = "挥砍"
    PIERCING = "穿刺"
    BLUDGEONING = "钝击"
    FIRE = "火焰"
    COLD = "冷冻"
    LIGHTNING = "闪电"
    ACID = "强酸"
    POISON = "毒素"
    THUNDER = "雷鸣"
    NECROTIC = "暗蚀"
    RADIANT = "光耀"
    PSYCHIC = "心灵"
    FORCE = "力场"


class CombatPhase(Enum):
    """战斗阶段。"""
    INITIATIVE = auto()
    PLAYER_TURN = auto()
    ENEMY_TURN = auto()
    VICTORY = auto()
    DEFEAT = auto()
    FLEE = auto()


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class DamageRoll:
    """伤害骰子。"""
    dice_count: int
    dice_sides: int
    bonus: int = 0
    damage_type: str = "挥砍"

    @classmethod
    def from_string(cls, dice_str: str, bonus: int = 0, damage_type: str = "挥砍") -> DamageRoll:
        """从字符串解析伤害骰子，如 '2d6+3'。"""
        import re
        match = re.match(r"(\d+)d(\d+)(?:\+(\d+))?", dice_str)
        if match:
            count = int(match.group(1))
            sides = int(match.group(2))
            extra = int(match.group(3)) if match.group(3) else 0
            return cls(count, sides, bonus + extra, damage_type)
        return cls(1, 4, bonus, damage_type)

    def roll(self) -> int:
        """掷骰子并返回总伤害。"""
        total = sum(random.randint(1, self.dice_sides) for _ in range(self.dice_count))
        return total + self.bonus

    def max_possible(self) -> int:
        """最大可能伤害。"""
        return self.dice_count * self.dice_sides + self.bonus


@dataclass
class EnemyInstance:
    """战斗中的怪物实例。"""
    template_id: str
    name: str
    max_hp: int
    current_hp: int
    armor_class: int
    stats: Dict[str, int]
    attack_bonus: int
    damage_roll: DamageRoll
    xp_value: int
    loot: Dict[str, Any]
    traits: List[Dict[str, Any]] = field(default_factory=list)
    status_effects: List[StatusEffect] = field(default_factory=list)
    initiative: int = 0
    is_boss: bool = False
    special_abilities: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_template(cls, monster_data: Dict[str, Any], level_scale: float = 1.0) -> EnemyInstance:
        """从怪物模板数据创建实例。"""
        stats = monster_data.get("stats", {})
        hp = monster_data.get("hit_points", 10)
        scaled_hp = max(1, int(hp * (0.8 + level_scale * 0.4)))

        damage_str = "1d6"
        actions = monster_data.get("actions", [])
        if actions:
            damage_str = actions[0].get("damage", damage_str)

        damage_roll = DamageRoll.from_string(damage_str)
        # 按等级缩放伤害
        if level_scale > 1.0:
            extra_dice = max(0, int(level_scale - 1))
            damage_roll.dice_count += extra_dice

        return cls(
            template_id=monster_data.get("id", "unknown"),
            name=monster_data.get("name", "怪物"),
            max_hp=scaled_hp,
            current_hp=scaled_hp,
            armor_class=monster_data.get("armor_class", 10),
            stats=stats,
            attack_bonus=actions[0].get("attack_bonus", 3) if actions else 3,
            damage_roll=damage_roll,
            xp_value=monster_data.get("xp", 50),
            loot=monster_data.get("loot", {"gold": "1d4", "items": []}),
            traits=monster_data.get("traits", []),
            is_boss="boss" in monster_data.get("id", "").lower(),
            special_abilities=[a for a in actions if "damage" not in a or a.get("attack_bonus") is None] if actions else [],
        )

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    def take_damage(self, amount: int) -> int:
        """受到伤害。返回实际伤害。"""
        actual = max(0, amount)
        self.current_hp = max(0, self.current_hp - actual)
        return actual

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.template_id,
            "name": self.name,
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "armor_class": self.armor_class,
            "is_alive": self.is_alive,
            "is_boss": self.is_boss,
            "initiative": self.initiative,
            "traits": self.traits,
        }


# ---------------------------------------------------------------------------
# Combat Engine
# ---------------------------------------------------------------------------

class CombatEngine:
    """回合制战斗引擎。

    管理战斗状态，处理先攻、攻击命中、伤害计算、
    经验分配、战利品等战斗逻辑。

    Usage:
        >>> engine = CombatEngine(party=[player_char], enemies=[enemy_instances])
        >>> result = engine.start_combat()
        >>> result = engine.process_action("attack", "enemy_0")
    """

    def __init__(self, party: List[Character], enemies: List[EnemyInstance]):
        self.party = party
        self.enemies = enemies
        self.phase: CombatPhase = CombatPhase.INITIATIVE
        self.turn_order: List[Combatant] = []
        self.current_turn_index: int = 0
        self.round: int = 0
        self.log: List[str] = []
        self.victory: bool = False

        # 战斗统计数据
        self.total_damage_dealt: int = 0
        self.total_damage_taken: int = 0
        self.critical_hits: int = 0
        self.enemies_defeated: int = 0

    def _roll_initiative(self) -> None:
        """骰先攻并排序。"""
        from dataclasses import dataclass

        @dataclass
        class Combatant:
            name: str
            initiative: int
            is_player: bool
            character_index: int  # 如果玩家则索引

        self.turn_order = []

        for i, char in enumerate(self.party):
            init_roll = random.randint(1, 20) + char.stats.modifier(Stat.DEXTERITY)
            self.turn_order.append(Combatant(char.name, init_roll, True, i))

        for i, enemy in enumerate(self.enemies):
            dex_mod = (enemy.stats.get("dexterity", 10) - 10) // 2
            init_roll = random.randint(1, 20) + dex_mod
            enemy.initiative = init_roll
            self.turn_order.append(Combatant(enemy.name, init_roll, False, i))

        # 按先攻降序排列
        self.turn_order.sort(key=lambda c: c.initiative, reverse=True)

    @property
    def current_combatant(self) -> Optional["Combatant"]:
        """当前行动的参战者。"""
        if self.turn_order and 0 <= self.current_turn_index < len(self.turn_order):
            return self.turn_order[self.current_turn_index]
        return None

    @property
    def is_player_turn(self) -> bool:
        """是否为玩家回合。"""
        c = self.current_combatant
        return c is not None and c.is_player

    @property
    def active_enemies(self) -> List[EnemyInstance]:
        """存活的敌人。"""
        return [e for e in self.enemies if e.is_alive]

    @property
    def active_party(self) -> List[Character]:
        """存活的队伍成员。"""
        return [c for c in self.party if c.is_alive()]

    def start_combat(self) -> Dict[str, Any]:
        """开始战斗，返回初始状态。"""
        self._roll_initiative()
        self.phase = CombatPhase.PLAYER_TURN if self.turn_order[0].is_player else CombatPhase.ENEMY_TURN
        self.round = 1

        self.log.append("⚔️ 战斗开始！")
        self.log.append(f"🎲 先攻顺序: {' → '.join(f'{c.name}({c.initiative})' for c in self.turn_order)}")

        if self.turn_order[0].is_player:
            self.log.append(f"🎯 {self.turn_order[0].name} 先动！")
        else:
            self.log.append(f"⚠️ 敌人 {self.turn_order[0].name} 先动！")

        return self._get_state()

    def process_action(
        self,
        action_type: str,
        target_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """处理玩家回合的动作。

        Args:
            action_type: 动作类型 (attack, cast_spell, use_item, dodge, etc.)
            target_id: 目标敌人索引（字符串）
            **kwargs: 额外参数（法术名, 物品id等）

        Returns:
            战斗状态字典
        """
        if self.phase not in (CombatPhase.PLAYER_TURN, CombatPhase.ENEMY_TURN):
            return self._get_state()

        if not self.current_combatant or not self.current_combatant.is_player:
            return self._get_state()

        char = self.party[self.current_combatant.character_index]
        result = {"action": action_type, "messages": [], "damage_dealt": 0, "target": target_id}

        if action_type == "attack":
            if target_id is not None:
                try:
                    enemy_idx = int(target_id.replace("enemy_", ""))
                    if 0 <= enemy_idx < len(self.enemies) and self.enemies[enemy_idx].is_alive:
                        atk_result = self._resolve_attack(char, self.enemies[enemy_idx])
                        result.update(atk_result)
                        result["messages"] = atk_result.get("messages", [])
                        self.log.extend(atk_result.get("messages", []))
                    else:
                        result["messages"].append("目标无效或已死亡。")
                except ValueError:
                    result["messages"].append("无效的目标。")
            else:
                result["messages"].append("请选择攻击目标。")

        elif action_type == "cast_spell":
            spell_name = kwargs.get("spell_name", "")
            if spell_name and target_id:
                try:
                    enemy_idx = int(target_id.replace("enemy_", ""))
                    if 0 <= enemy_idx < len(self.enemies) and self.enemies[enemy_idx].is_alive:
                        spell_result = self._resolve_spell(char, spell_name, self.enemies[enemy_idx])
                        result.update(spell_result)
                        self.log.extend(spell_result.get("messages", []))
                    else:
                        result["messages"].append("目标无效或已死亡。")
                except ValueError:
                    result["messages"].append("无效的目标。")
            else:
                result["messages"].append("需要指定法术和目标。")

        elif action_type == "use_item":
            item_id = kwargs.get("item_id", "")
            result = self._resolve_use_item(char, item_id)
            self.log.extend(result.get("messages", []))

        elif action_type == "dodge":
            result["messages"].append(f"{char.name} 进入了防御姿态！下回合前AC+2。")
            char.add_status(StatusEffect(StatusType.BLESSED, 1, "dodge", "防御姿态"))
            self.log.append(f"{char.name} 采取了防御姿态。")

        elif action_type == "disengage":
            result["messages"].append(f"{char.name} 谨慎撤退，不会引发借机攻击。")
            self.log.append(f"{char.name} 采取了撤离动作。")

        # 检查战斗结束
        if not self.active_enemies:
            self.phase = CombatPhase.VICTORY
            self.victory = True
            self.log.append("🎉 战斗胜利！")
        elif not self.active_party:
            self.phase = CombatPhase.DEFEAT
            self.log.append("💀 战斗失败...")

        # 切换到下一个参战者
        self._advance_turn()

        # 如果是敌人回合，自动执行
        if self.phase == CombatPhase.ENEMY_TURN and self.active_enemies and self.active_party:
            self._run_enemy_turns()

        state = self._get_state()
        state["action_result"] = result
        return state

    def _resolve_attack(self, attacker: Character, defender: EnemyInstance) -> Dict[str, Any]:
        """解析一次攻击。"""
        messages = []
        attack_roll = random.randint(1, 20)
        is_critical = attack_roll == 20
        is_fumble = attack_roll == 1

        attack_bonus = attacker.get_attack_bonus()
        total_roll = attack_roll + attack_bonus

        advantage_modifier = ""

        # 检查状态
        if attacker.has_status(StatusType.BLESSED):
            total_roll += random.randint(1, 4)
            advantage_modifier = " (祝福加成)"

        if is_fumble:
            messages.append(f"💥 {attacker.name} 的攻击大失败！武器脱手而出！")
            messages.append(f"🎲 攻击掷骰: 自然 1 (大失败)")
            return {"messages": messages, "hit": False, "critical_miss": True, "damage_dealt": 0}

        hit = total_roll >= defender.armor_class or is_critical

        if hit:
            if is_critical:
                self.critical_hits += 1
                messages.append(f"⚡ 暴击！{attacker.name} 对 {defender.name} 造成了致命一击！")
                messages.append(f"🎲 攻击掷骰: 自然 20{' ' + advantage_modifier if advantage_modifier else ''}")
            else:
                messages.append(f"🎯 {attacker.name} 攻击命中 {defender.name}！")
                messages.append(f"🎲 攻击掷骰: {attack_roll} + {attack_bonus} = {total_roll} vs AC {defender.armor_class}")

            # 计算伤害
            weapon_dice, damage_type = attacker.get_weapon_damage()
            damage_roll = DamageRoll.from_string(weapon_dice, 0, damage_type)

            # 暴击：伤害骰子翻倍
            if is_critical:
                damage_roll.dice_count *= 2

            damage = damage_roll.roll()

            # 附加伤害（如焰舌剑）
            if attacker.equipment.weapon:
                for effect in attacker.equipment.weapon.effects:
                    if effect.get("type") == "bonus_damage":
                        extra_dmg = DamageRoll.from_string(
                            effect.get("damage", "1d4"),
                            0,
                            effect.get("damage_type", "火焰")
                        ).roll()
                        damage += extra_dmg
                        messages.append(f"🔥 额外 {extra_dmg} 点{effect.get('damage_type', '火焰')}伤害！")

            if is_critical:
                damage += attacker.get_modifier_for_primary()

            actual = defender.take_damage(damage)
            self.total_damage_dealt += actual

            messages.append(f"💔 造成 {actual} 点{damage_type}伤害！")
            messages.append(f"❤️ {defender.name} HP: {defender.current_hp}/{defender.max_hp}")

            if not defender.is_alive:
                self.enemies_defeated += 1
                messages.append(f"💀 {defender.name} 被击败了！")
                # 掉落处理
                loot_msgs = self._process_loot(defender)
                messages.extend(loot_msgs)
        else:
            messages.append(f"❌ {attacker.name} 的攻击未命中！")
            messages.append(f"🎲 攻击掷骰: {attack_roll} + {attack_bonus} = {total_roll} vs AC {defender.armor_class}")

        return {
            "messages": messages,
            "hit": hit,
            "critical_hit": is_critical,
            "attack_roll": attack_roll,
            "total_roll": total_roll,
            "damage_dealt": defender.current_hp if not defender.is_alive else 0,
        }

    def _resolve_spell(self, caster: Character, spell_name: str, target: EnemyInstance) -> Dict[str, Any]:
        """解析法术释放。"""
        messages = []

        messages.append(f"🔮 {caster.name} 释放了 {spell_name}！")

        # 简单法术效果
        effects = {
            "火球术": (DamageRoll(6, 8, 0, "火焰"), 15, "敏捷"),
            "魔法飞弹": (DamageRoll(3, 4, 3, "力场"), None, None),
            "闪电束": (DamageRoll(4, 8, 0, "闪电"), 14, "敏捷"),
            "冰冻射线": (DamageRoll(2, 6, 0, "冷冻"), None, None),
            "火焰箭": (DamageRoll(2, 6, 0, "火焰"), None, None),
            "治愈真言": (None, None, None),
        }

        if spell_name in effects:
            dmg_roll, save_dc, save_stat = effects[spell_name]
            if dmg_roll:
                # 豁免判定
                if save_dc and save_stat:
                    stat_value = target.stats.get(save_stat, 10)
                    save_bonus = (stat_value - 10) // 2
                    save_roll = random.randint(1, 20) + save_bonus
                    if save_roll >= save_dc:
                        dmg = dmg_roll.roll() // 2  # 豁免成功半伤
                        messages.append(f"🛡️ {target.name} 豁免成功！只受一半伤害。")
                    else:
                        dmg = dmg_roll.roll()
                        messages.append(f"💥 {target.name} 豁免失败！")
                else:
                    dmg = dmg_roll.roll()

                actual = target.take_damage(dmg)
                self.total_damage_dealt += actual
                messages.append(f"💔 造成 {actual} 点{dmg_roll.damage_type}伤害！")

                if not target.is_alive:
                    self.enemies_defeated += 1
                    messages.append(f"💀 {target.name} 被击败了！")
                    loot_msgs = self._process_loot(target)
                    messages.extend(loot_msgs)
            else:
                # 治疗法术
                heal_amount = DamageRoll(2, 4, 2).roll()
                caster.heal(heal_amount)
                messages.append(f"💚 {caster.name} 恢复了 {heal_amount} 点生命值。")
        else:
            messages.append(f"{spell_name} 释放失败，法术未识别。")

        return {"messages": messages, "damage_dealt": 0, "spell": spell_name}

    def _resolve_use_item(self, user: Character, item_id: str) -> Dict[str, Any]:
        """解析使用物品。"""
        messages = []

        if not user.inventory.has_item(item_id):
            messages.append("❌ 背包中没有该物品��")
            return {"messages": messages, "use_success": False}

        if item_id == "healing_potion":
            heal = DamageRoll(2, 4, 2).roll()
            actual = user.heal(heal)
            user.inventory.remove_item(item_id)
            messages.append(f"💚 饮用治疗药水，恢复了 {heal} 点生命值！")
            messages.append(f"❤️ 当前 HP: {user.current_hp}/{user.max_hp}")
        elif item_id == "mana_potion":
            restore = DamageRoll(1, 4, 1).roll()
            user.inventory.remove_item(item_id)
            messages.append(f"💙 饮用法力药水，恢复了 {restore} 点法力！")
        else:
            messages.append(f"⚠️ 该物品不能在此使用。")
            return {"messages": messages, "use_success": False}

        return {"messages": messages, "use_success": True, "item_used": item_id}

    def _run_enemy_turns(self) -> None:
        """自动执行所有敌人的回合。"""
        for enemy in self.enemies:
            if not enemy.is_alive or not self.active_party:
                continue

            # 选���最弱的玩家目标
            target = min(self.active_party, key=lambda c: c.current_hp)
            if not target:
                continue

            messages = []
            attack_roll = random.randint(1, 20) + enemy.attack_bonus
            is_critical = random.randint(1, 20) == 20

            if attack_roll >= target.armor_class or is_critical:
                dmg = enemy.damage_roll.roll()
                if is_critical:
                    dmg = enemy.damage_roll.roll() * 2
                    messages.append(f"⚡ {enemy.name} 对 {target.name} 造成暴击！")
                else:
                    messages.append(f"🗡️ {enemy.name} 攻击 {target.name}！")

                actual = target.take_damage(dmg)
                self.total_damage_taken += actual
                messages.append(f"💔 {target.name} 受到 {actual} 点伤害 (HP: {target.current_hp}/{target.max_hp})")

                if not target.is_alive():
                    messages.append(f"💀 {target.name} 倒下了！")
            else:
                messages.append(f"🛡️ {enemy.name} 的攻击被 {target.name} 闪避！")

            self.log.extend(messages)

        if not self.active_party:
            self.phase = CombatPhase.DEFEAT
            self.phase = CombatPhase.DEFEAT
            self.log.append("💀 冒险队伍全灭...")
        else:
            self.phase = CombatPhase.PLAYER_TURN

    def _advance_turn(self) -> None:
        """前进到下一个参战者。"""
        self.current_turn_index += 1
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0
            self.round += 1
            # 每轮开始时处理状态效果
            self._process_status_effects()

    def _process_status_effects(self) -> None:
        """处理所有参战者的状态效果。"""
        for char in self.party:
            msgs = char.tick_statuses()
            self.log.extend(msgs)
        for enemy in self.enemies:
            # 简化：敌人也有状态
            pass

    def _process_loot(self, enemy: EnemyInstance) -> List[str]:
        """处理战利品（自动分配给第一个玩家）。"""
        messages = []
        if not self.party:
            return messages

        char = self.party[0]

        # 金币
        gold_str = enemy.loot.get("gold", "1d4")
        import re
        match = re.match(r"(\d+)d(\d+)", str(gold_str))
        if match:
            gold = sum(random.randint(1, int(match.group(2))) for _ in range(int(match.group(1))))
        else:
            gold = 0
        if gold > 0:
            char.inventory.add_gold(gold)
            messages.append(f"💰 获得 {gold} 金币！")

        # 经验
        xp = enemy.xp_value
        for party_char in self.active_party:
            if party_char.add_xp(xp):
                messages.append(f"✨ {party_char.name} 升级了！当前等级 {party_char.level}")
        messages.append(f"⭐ 队伍获得 {xp} 经验值！")

        # 物品掉落（简化）
        loot_items = enemy.loot.get("items", [])
        messages.append(f"📦 获得战利品: {', '.join(loot_items) if loot_items else '无'}")

        return messages

    def _get_state(self) -> Dict[str, Any]:
        """获取当前战斗状态。"""
        return {
            "phase": self.phase.name,
            "round": self.round,
            "is_player_turn": self.is_player_turn,
            "current_combatant": {
                "name": self.current_combatant.name if self.current_combatant else "",
                "is_player": self.current_combatant.is_player if self.current_combatant else False,
            } if self.current_combatant else None,
            "party": [c.to_dict() for c in self.party],
            "enemies": [e.to_dict() for e in self.enemies],
            "active_enemies_count": len(self.active_enemies),
            "active_party_count": len(self.active_party),
            "log": self.log,
            "victory": self.victory,
            "turn_order": [(c.name, c.initiative, c.is_player) for c in self.turn_order],
        }

    def get_state(self) -> Dict[str, Any]:
        """公开获取战斗状态。"""
        return self._get_state()
