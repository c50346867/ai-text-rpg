# -*- coding: utf-8 -*-
"""
Character System — 角色系统模块。

提供 RPG 角色创建、属性管理、职业与种族系统、等级升级、
装备栏与背包管理、状态效果等核心功能。

Classes:
    Character: 玩家角色
    Stats: 六项属性
    Equipment: 装备栏
    Inventory: 背包
    StatusEffect: 状态效果
    Progression: 等级与经验系统
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Stat(Enum):
    """六项基础属性。"""
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


class Skill(Enum):
    """技能列表。"""
    ACROBATICS = "杂技"
    ANIMAL_HANDLING = "驯兽"
    ARCANA = "奥秘"
    ATHLETICS = "运动"
    DECEPTION = "欺骗"
    HISTORY = "历史"
    INSIGHT = "洞察"
    INTIMIDATION = "威吓"
    INVESTIGATION = "调查"
    MEDICINE = "医药"
    NATURE = "自然"
    PERCEPTION = "感知"
    PERFORMANCE = "表演"
    PERSUASION = "说服"
    RELIGION = "宗教"
    SLEIGHT_OF_HAND = "巧手"
    STEALTH = "潜行"
    SURVIVAL = "生存"


class StatusType(Enum):
    """状态效果类型。"""
    POISONED = "中毒"
    BURNING = "燃烧"
    FROZEN = "冰冻"
    STUNNED = "眩晕"
    BLESSED = "祝福"
    CURSED = "诅咒"
    INVISIBLE = "隐形"
    FRIGHTENED = "惊慌"
    PARALYZED = "麻痹"
    CHARMED = "魅惑"
    BLINDED = "致盲"
    PRONE = "倒地"
    RESTRAINED = "束缚"


class EquipmentSlot(Enum):
    """装备栏位。"""
    WEAPON = "weapon"
    ARMOR = "armor"
    ACCESSORY = "accessory"
    CLOAK = "cloak"


class GameState(Enum):
    """游戏状态机。"""
    EXPLORATION = auto()
    COMBAT = auto()
    DIALOGUE = auto()
    RESTING = auto()
    LEVEL_UP = auto()
    SHOP = auto()
    GAME_OVER = auto()


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    """六项属性值。"""
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    def get(self, stat: Stat) -> int:
        """获取某项属性的值。"""
        return getattr(self, stat.value)

    def set(self, stat: Stat, value: int) -> None:
        """设置某项属性的值。"""
        setattr(self, stat.value, max(1, min(30, value)))

    def modifier(self, stat: Stat) -> int:
        """计算属性调整值 (dnd 5e 规则: (属性-10)//2)。"""
        return (self.get(stat) - 10) // 2

    def all_modifiers(self) -> Dict[str, int]:
        """返回所有属性的调整值字典。"""
        return {s.value: self.modifier(s) for s in Stat}

    def to_dict(self) -> Dict[str, int]:
        return {s.value: self.get(s) for s in Stat}

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> Stats:
        return cls(**{k: v for k, v in data.items() if k in [s.value for s in Stat]})


@dataclass
class StatusEffect:
    """单一状态效果。"""
    type: StatusType
    duration: int  # 剩余回合数（-1 表示永久）
    source: str = ""
    description: str = ""

    def tick(self) -> bool:
        """每回合减少持续时间。返回 True 如果效果已消失。"""
        if self.duration > 0:
            self.duration -= 1
        return self.duration == 0


@dataclass
class Item:
    """物品数据结构。"""
    id: str
    name: str
    name_en: str
    type: str
    subtype: str
    rarity: str
    description: str
    value: int
    weight: float
    equippable: bool
    slot: Optional[str]
    properties: Dict[str, Any]
    effects: List[Dict[str, Any]]
    special: str
    quantity: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Item:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Equipment:
    """装备栏。"""
    weapon: Optional[Item] = None
    armor: Optional[Item] = None
    accessory: Optional[Item] = None
    cloak: Optional[Item] = None

    def equip(self, item: Item) -> Tuple[bool, Optional[Item], str]:
        """装备物品。返回 (成功, 替换下的物品, 消息)。"""
        if not item.equippable or item.slot is None:
            return False, None, f"{item.name} 无法装备。"

        slot_map = {
            "weapon": "weapon",
            "armor": "armor",
            "accessory": "accessory",
            "cloak": "cloak",
        }

        slot_name = slot_map.get(item.slot)
        if slot_name is None:
            return False, None, f"{item.name} 没有有效的装备槽位。"

        old_item = getattr(self, slot_name)
        setattr(self, slot_name, item)
        return True, old_item, f"已装备 {item.name}。"

    def unequip(self, slot: EquipmentSlot) -> Tuple[bool, Optional[Item], str]:
        """卸下装备。"""
        slot_name = slot.value
        old_item = getattr(self, slot_name)
        if old_item is None:
            return False, None, f"{slot.name} 槽位没有装备。"
        setattr(self, slot_name, None)
        return True, old_item, f"已卸下 {old_item.name}。"

    def to_dict(self) -> Dict[str, Any]:
        return {
            k: (v.__dict__ if v else None)
            for k, v in self.__dict__.items()
        }


@dataclass
class Inventory:
    """背包系统。"""
    items: List[Item] = field(default_factory=list)
    gold: int = 0
    max_weight: float = 150.0

    @property
    def total_weight(self) -> float:
        """当前背包总重量。"""
        return sum(item.weight * item.quantity for item in self.items)

    @property
    def is_overloaded(self) -> bool:
        """是否超重。"""
        return self.total_weight > self.max_weight

    def add_item(self, item: Item) -> bool:
        """添加物品到背包。如果超重则返回 False。"""
        if self.total_weight + item.weight * item.quantity > self.max_weight:
            return False
        # 尝试堆叠
        for existing in self.items:
            if existing.id == item.id and existing.type != "weapon" and existing.type != "armor":
                existing.quantity += item.quantity
                return True
        self.items.append(item)
        return True

    def remove_item(self, item_id: str, quantity: int = 1) -> bool:
        """从背包移除物品。返回是否成功。"""
        for item in self.items:
            if item.id == item_id:
                if item.quantity >= quantity:
                    item.quantity -= quantity
                    if item.quantity <= 0:
                        self.items.remove(item)
                    return True
                return False
        return False

    def has_item(self, item_id: str) -> bool:
        """检查背包中是否有某物品。"""
        return any(item.id == item_id for item in self.items)

    def has_item_quantity(self, item_id: str, quantity: int) -> bool:
        """检查背包中是否有足够数量的某物品。"""
        for item in self.items:
            if item.id == item_id and item.quantity >= quantity:
                return True
        return False

    def add_gold(self, amount: int) -> None:
        """增加金币。"""
        self.gold += amount

    def spend_gold(self, amount: int) -> bool:
        """花费金币。返回是否成功。"""
        if self.gold >= amount:
            self.gold -= amount
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.__dict__ for item in self.items],
            "gold": self.gold,
            "total_weight": self.total_weight,
            "max_weight": self.max_weight,
        }


# ---------------------------------------------------------------------------
# Core Character Class
# ---------------------------------------------------------------------------

class Character:
    """RPG 角色。

    管理角色的所有属性，包括基础属性、种族、职业、等级、
    装备、背包、状态效果等。

    Usage:
        >>> from backend.engine.character import Character
        >>> char = Character(name="阿尔萨斯", race_id="human", class_id="fighter")
        >>> char.stats.strength = 16
        >>> char.level_up()
    """

    # 经验值表 (等级 -> 所需总经验)
    XP_TABLE = {
        1: 0, 2: 300, 3: 900, 4: 2700, 5: 6500,
        6: 14000, 7: 23000, 8: 34000, 9: 48000, 10: 64000,
        11: 85000, 12: 100000, 13: 120000, 14: 140000, 15: 165000,
        16: 195000, 17: 225000, 18: 265000, 19: 305000, 20: 355000,
    }

    def __init__(
        self,
        name: str = "",
        race_id: str = "human",
        class_id: str = "fighter",
        stats: Optional[Stats] = None,
    ):
        self.name = name
        self.race_id = race_id
        self.class_id = class_id
        self.level: int = 1
        self.xp: int = 0

        # 数据引用
        self._race_data: Optional[Dict[str, Any]] = None
        self._class_data: Optional[Dict[str, Any]] = None
        self._load_data()

        # 属性
        self.stats = stats or Stats()
        self._apply_racial_bonuses()

        # 生命值
        self.max_hp: int = 0
        self.current_hp: int = 0
        self._calculate_hp()

        # 护甲等级
        self.armor_class: int = 10

        # 装备和背包
        self.equipment: Equipment = Equipment()
        self.inventory: Inventory = Inventory()

        # 状态效果
        self.status_effects: List[StatusEffect] = []

        # 技能熟练项
        self.skill_proficiencies: List[str] = []

        # 游戏状态
        self.state: GameState = GameState.EXPLORATION



    def _load_data(self) -> None:
        """加载种族和职业数据。"""
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        try:
            with open(data_dir / "races.json", "r", encoding="utf-8") as f:
                races = json.load(f)
                for race in races:
                    if race["id"] == self.race_id:
                        self._race_data = race
                        break
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        try:
            with open(data_dir / "classes.json", "r", encoding="utf-8") as f:
                classes = json.load(f)
                for cls_data in classes:
                    if cls_data["id"] == self.class_id:
                        self._class_data = cls_data
                        break
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _apply_racial_bonuses(self) -> None:
        """应用种族属性加成。"""
        if self._race_data and "stat_bonuses" in self._race_data:
            for stat_name, bonus in self._race_data["stat_bonuses"].items():
                try:
                    stat = Stat(stat_name)
                    current = self.stats.get(stat)
                    self.stats.set(stat, current + bonus)
                except ValueError:
                    continue

    def _calculate_hp(self) -> None:
        """根据职业和体质计算生命值。"""
        if self._class_data:
            hit_dice = self._class_data.get("hit_dice", "d8")
            dice_size = int(hit_dice[1:])
            con_mod = self.stats.modifier(Stat.CONSTITUTION)
            # 1级: 最大值 + 体质修正
            # 后续: 每次升级骰1次
            base_hp = dice_size + con_mod
            for lvl in range(2, self.level + 1):
                base_hp += random.randint(1, dice_size) + con_mod
            self.max_hp = max(1, base_hp)
            self.current_hp = self.max_hp

    def _calculate_ac(self) -> None:
        """计算护甲等级。"""
        base_ac = 10
        dex_mod = self.stats.modifier(Stat.DEXTERITY)

        if self.equipment.armor:
            armor_props = self.equipment.armor.properties
            base_ac = armor_props.get("armor_class", 10)
            dex_limit = armor_props.get("dexterity_bonus_limit")
            if dex_limit is not None:
                base_ac += min(dex_mod, dex_limit)
            else:
                base_ac += dex_mod
        else:
            # 武僧无甲防御
            if self.class_id == "monk":
                wis_mod = self.stats.modifier(Stat.WISDOM)
                base_ac = 10 + dex_mod + wis_mod
            else:
                base_ac += dex_mod

        # 防护戒指加值
        if self.equipment.accessory:
            for effect in self.equipment.accessory.effects:
                if effect.get("type") == "ac_bonus":
                    base_ac += effect.get("value", 0)

        self.armor_class = base_ac

    def add_xp(self, amount: int) -> bool:
        """增加经验值。返回是否升级。"""
        self.xp += amount
        new_level = self.level
        for lvl, needed_xp in sorted(self.XP_TABLE.items(), reverse=True):
            if self.xp >= needed_xp and lvl > new_level:
                new_level = lvl
        if new_level > self.level:
            self.level = new_level
            self._calculate_hp()
            return True
        return False

    def level_up(self) -> Dict[str, Any]:
        """升级角色。返回升级详情。"""
        old_level = self.level
        self.level += 1
        self._calculate_hp()

        result = {
            "old_level": old_level,
            "new_level": self.level,
            "new_max_hp": self.max_hp,
            "abilities_unlocked": [],
        }

        if self._class_data:
            abilities = self._class_data.get("class_abilities_levels", {})
            level_str = str(self.level)
            if level_str in abilities:
                result["abilities_unlocked"] = abilities[level_str]

        return result

    def take_damage(self, amount: int) -> int:
        """受到伤害。返回实际伤害值。"""
        actual_damage = max(0, amount)
        self.current_hp = max(0, self.current_hp - actual_damage)
        return actual_damage

    def heal(self, amount: int) -> int:
        """恢复生命值。返回实际恢复值。"""
        before = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        return self.current_hp - before

    def is_alive(self) -> bool:
        """是否存活。"""
        return self.current_hp > 0

    def add_status(self, effect: StatusEffect) -> None:
        """添加状态效果。"""
        # 同类型刷新
        for existing in self.status_effects:
            if existing.type == effect.type:
                existing.duration = max(existing.duration, effect.duration)
                return
        self.status_effects.append(effect)

    def remove_status(self, status_type: StatusType) -> bool:
        """移除指定类型的状态效果。"""
        for effect in self.status_effects:
            if effect.type == status_type:
                self.status_effects.remove(effect)
                return True
        return False

    def has_status(self, status_type: StatusType) -> bool:
        """检查是否有指定类型的状态效果。"""
        return any(ef.type == status_type for ef in self.status_effects)

    def tick_statuses(self) -> List[str]:
        """每回合状态效果更新。返回状态变化描述列表。"""
        messages = []
        remaining = []
        for effect in self.status_effects:
            # 伤害性状态
            if effect.type == StatusType.BURNING:
                self.take_damage(random.randint(1, 6))
                messages.append(f"燃烧造成 {random.randint(1, 6)} 点伤害！")
            elif effect.type == StatusType.POISONED:
                self.take_damage(random.randint(1, 4))
                messages.append(f"中毒造成 {random.randint(1, 4)} 点伤害！")

            if not effect.tick():
                remaining.append(effect)
            else:
                messages.append(f"{effect.type.value} 状态消失了。")

        self.status_effects = remaining
        return messages

    def get_attack_bonus(self) -> int:
        """获取攻击加值。"""
        stat = Stat.STRENGTH
        if self._class_data:
            primary = self._class_data.get("primary_stat", "strength")
            try:
                stat = Stat(primary)
            except ValueError:
                pass

        prof_bonus = self.get_proficiency_bonus()
        stat_mod = self.stats.modifier(stat)

        # 武器加值
        weapon_bonus = 0
        if self.equipment.weapon:
            weapon_bonus = self.equipment.weapon.properties.get("attack_bonus", 0)

        return prof_bonus + stat_mod + weapon_bonus

    def get_proficiency_bonus(self) -> int:
        """获取熟练加值 (基于等级)。"""
        if self.level <= 4:
            return 2
        elif self.level <= 8:
            return 3
        elif self.level <= 12:
            return 4
        elif self.level <= 16:
            return 5
        else:
            return 6

    def get_weapon_damage(self) -> Tuple[str, str]:
        """获取武器伤害骰子和类型。"""
        if self.equipment.weapon:
            props = self.equipment.weapon.properties
            return props.get("damage_dice", "1d4"), props.get("damage_type", "钝击")
        return "1d4", "钝击"  # 徒手

    def get_modifier_for_primary(self) -> int:
        """获取主属性调整值。"""
        if self._class_data:
            stat_name = self._class_data.get("primary_stat", "strength")
            try:
                stat = Stat(stat_name)
                return self.stats.modifier(stat)
            except ValueError:
                pass
        return self.stats.modifier(Stat.STRENGTH)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "name": self.name,
            "race_id": self.race_id,
            "race_name": self._race_data.get("name", self.race_id) if self._race_data else self.race_id,
            "class_id": self.class_id,
            "class_name": self._class_data.get("name", self.class_id) if self._class_data else self.class_id,
            "level": self.level,
            "xp": self.xp,
            "xp_to_next": self.XP_TABLE.get(self.level + 1, 0) - self.xp if self.level < 20 else 0,
            "stats": self.stats.to_dict(),
            "modifiers": self.stats.all_modifiers(),
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "armor_class": self.armor_class,
            "attack_bonus": self.get_attack_bonus(),
            "equipment": self.equipment.to_dict(),
            "inventory": self.inventory.to_dict(),
            "status_effects": [{"type": e.type.value, "duration": e.duration} for e in self.status_effects],
            "state": self.state.name,
            "is_alive": self.is_alive(),
        }

    @classmethod
    def create_default(cls, name: str = "英雄") -> Character:
        """创建一个默认的战士角色。"""
        stats = Stats(strength=15, dexterity=14, constitution=14, intelligence=10, wisdom=12, charisma=10)
        char = cls(name=name, race_id="human", class_id="fighter", stats=stats)
        char.inventory.gold = 50
        return char
