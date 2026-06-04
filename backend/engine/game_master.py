# -*- coding: utf-8 -*-
"""
Game Master — AI DM 主持人引擎模块。

AI 地下城主（DM）核心，管理游戏状态机（探索→战斗→对话→休息→升级），
使用 LLM 接口（可切换模拟/真实）推进剧情、描述场景、扮演 NPC、
判定玩家行动效果（基于 DC = 难度等级 + 随机骰子 1d20）。

Classes:
    GameMaster: AI DM 核心引擎
    GameSession: 单个游戏会话
    DiceRoller: 骰子工具
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from backend.engine.character import (
    Character, Stats, Stat, StatusEffect, StatusType,
    EquipmentSlot, GameState, Item,
)
from backend.engine.combat import (
    CombatEngine, CombatPhase, CombatActionType,
    EnemyInstance, DamageRoll,
)
from backend.engine.world import (
    WorldManager, AreaType, Location, WeatherType,
    TimeOfDay, EncounterTable,
)
from backend.engine.story_generator import (
    StoryGenerator, StoryNode, StoryNodeType,
    QuestManager, Quest, QuestType, QuestStatus,
    QuestObjective, ScenarioLoader,
)


# ---------------------------------------------------------------------------
# Dice Roller
# ---------------------------------------------------------------------------

class DiceRoller:
    """骰子工具。

    支持标准 RPG 骰子系统（d4, d6, d8, d10, d12, d20, d100）。

    Usage:
        >>> dr = DiceRoller()
        >>> result = dr.roll("2d6+3")  # 掷 2 个 d6 + 3
        >>> result = dr.d20()           # 掷 1 个 d20
    """

    @staticmethod
    def roll(dice_str: str) -> Dict[str, Any]:
        """解析并掷骰。

        Args:
            dice_str: 骰子字符串，如 "1d20+5", "3d6", "d20"

        Returns:
            包含 results, total, rolls, modifier 的字典
        """
        import re
        match = re.match(r"(\d*)d(\d+)(?:\+(\d+))?(?:\-(\d+))?", dice_str)
        if not match:
            return {"error": f"无效的骰子表达式: {dice_str}", "total": 0}

        count = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        add = int(match.group(3)) if match.group(3) else 0
        sub = int(match.group(4)) if match.group(4) else 0

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + add - sub

        return {
            "dice": dice_str,
            "results": rolls,
            "total": max(0, total),
            "modifier": add - sub,
            "sides": sides,
            "count": count,
            "is_critical": 20 in rolls,
            "is_fumble": all(r == 1 for r in rolls) if count <= 2 else False,
        }

    @staticmethod
    def d20(modifier: int = 0) -> Dict[str, Any]:
        """掷一个 d20。"""
        return DiceRoller.roll(f"1d20{'+' + str(modifier) if modifier else ''}")

    @staticmethod
    def ability_check(modifier: int, dc: int, advantage: bool = False, disadvantage: bool = False) -> Dict[str, Any]:
        """属性检定。

        Args:
            modifier: 调整值
            dc: 难度等级
            advantage: 是否优势
            disadvantage: 是否劣势

        Returns:
            检定结果字典
        """
        if advantage and disadvantage:
            advantage = disadvantage = False

        if advantage:
            roll1 = DiceRoller.d20()
            roll2 = DiceRoller.d20()
            best = max(roll1["results"][0], roll2["results"][0])
            total = best + modifier
            return {
                "roll": best,
                "total": total,
                "modifier": modifier,
                "dc": dc,
                "success": total >= dc,
                "advantage": True,
                "disadvantage": False,
                "natural_roll": best,
                "is_critical": best == 20,
                "is_fumble": best == 1,
                "description": f"优势检定: {best} (骰1: {roll1['results'][0]}, 骰2: {roll2['results'][0]}) + {modifier} = {total} vs DC {dc}",
            }
        elif disadvantage:
            roll1 = DiceRoller.d20()
            roll2 = DiceRoller.d20()
            worst = min(roll1["results"][0], roll2["results"][0])
            total = worst + modifier
            return {
                "roll": worst,
                "total": total,
                "modifier": modifier,
                "dc": dc,
                "success": total >= dc,
                "advantage": False,
                "disadvantage": True,
                "natural_roll": worst,
                "is_critical": worst == 20,
                "is_fumble": worst == 1,
                "description": f"劣势检定: {worst} (骰1: {roll1['results'][0]}, 骰2: {roll2['results'][0]}) + {modifier} = {total} vs DC {dc}",
            }
        else:
            dr = DiceRoller.d20()
            total = dr["total"] + modifier
            return {
                "roll": dr["results"][0],
                "total": total,
                "modifier": modifier,
                "dc": dc,
                "success": total >= dc,
                "advantage": False,
                "disadvantage": False,
                "natural_roll": dr["results"][0],
                "is_critical": dr["results"][0] == 20,
                "is_fumble": dr["results"][0] == 1,
                "description": f"普通检定: {dr['results'][0]} + {modifier} = {total} vs DC {dc}",
            }

    @staticmethod
    def damage(dice_str: str) -> Dict[str, Any]:
        """掷伤害骰。"""
        return DiceRoller.roll(dice_str)

    @staticmethod
    def format_roll_result(result: Dict[str, Any]) -> str:
        """格式化骰子结果为可读字符串。"""
        if "error" in result:
            return result["error"]
        if "description" in result:
            return f"🎲 {result['description']}"
        return f"🎲 {result.get('dice', '')}: [{', '.join(str(r) for r in result['results'])}] = {result['total']}"


# ---------------------------------------------------------------------------
# Game Session
# ---------------------------------------------------------------------------

@dataclass
class GameSession:
    """单个游戏会话。"""
    id: str
    characters: List[Character] = field(default_factory=list)
    world: WorldManager = field(default_factory=WorldManager)
    story: StoryGenerator = field(default_factory=StoryGenerator)
    current_combat: Optional[CombatEngine] = None
    game_state: GameState = GameState.EXPLORATION
    log: List[str] = field(default_factory=list)
    party_gold: int = 0
    dice_roller: DiceRoller = field(default_factory=DiceRoller)

    def add_message(self, message: str) -> None:
        """添加日志消息���"""
        self.log.append(message)

    def get_recent_log(self, count: int = 20) -> List[str]:
        """获取最近的日志。"""
        return self.log[-count:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "game_state": self.game_state.name,
            "party": [c.to_dict() for c in self.characters],
            "log": self.get_recent_log(),
            "world": self.world.to_dict(),
            "story": self.story.to_dict(),
            "combat_active": self.current_combat is not None,
        }


# ---------------------------------------------------------------------------
# Game Master (AI DM)
# ---------------------------------------------------------------------------

class GameMaster:
    """AI DM 主持���引擎。

    核心游戏控制器，管理整个跑团游戏的流程：
    - 创建和管理游戏会话
    - 推进剧情和场景
    - 处理玩家行动判定（DC 检定）
    - 管理战斗状态
    - NPC 交互
    - 触发事件

    Usage:
        >>> gm = GameMaster()
        >>> session = gm.create_session("my_game")
        >>> char = gm.create_character("阿尔萨斯", "human", "fighter")
        >>> gm.join_party(session.id, char)
        >>> result = gm.process_action(session.id, "前进")
    """

    def __init__(self, use_simulated_llm: bool = True):
        self.sessions: Dict[str, GameSession] = {}
        self.dice = DiceRoller()
        self.use_simulated_llm = use_simulated_llm

    def create_session(self, session_id: str = "") -> GameSession:
        """创建新的游戏会话。"""
        if not session_id:
            session_id = f"session_{len(self.sessions) + 1}_{random.randint(1000, 9999)}"
        session = GameSession(id=session_id)
        self.sessions[session_id] = session
        return session

    def create_character(self, name: str, race_id: str = "human", class_id: str = "fighter") -> Character:
        """创建角色（可选自定义属性）。"""
        # 预设属性分配
        stat_presets = {
            "fighter": Stats(strength=15, dexterity=14, constitution=14, intelligence=10, wisdom=12, charisma=10),
            "wizard": Stats(strength=8, dexterity=14, constitution=12, intelligence=17, wisdom=13, charisma=10),
            "ranger": Stats(strength=12, dexterity=17, constitution=13, intelligence=10, wisdom=14, charisma=10),
            "rogue": Stats(strength=10, dexterity=17, constitution=13, intelligence=14, wisdom=12, charisma=10),
            "cleric": Stats(strength=14, dexterity=10, constitution=14, intelligence=10, wisdom=17, charisma=12),
            "monk": Stats(strength=12, dexterity=17, constitution=13, intelligence=10, wisdom=15, charisma=10),
        }

        stats = stat_presets.get(class_id, Stats())
        char = Character(name=name, race_id=race_id, class_id=class_id, stats=stats)
        char.inventory.gold = 50
        # 初始装备
        from backend.engine.character import Item

        return char

    def join_party(self, session_id: str, character: Character) -> bool:
        """加入队伍。"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        session.characters.append(character)
        return True

    def start_game(self, session_id: str, scenario_id: str = "tutorial") -> Dict[str, Any]:
        """开始游戏，加载剧本。"""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "会话不存在", "success": False}

        # 加载剧本
        scenario = session.story.load_scenario(scenario_id)
        if not scenario:
            return {"error": f"无法加载剧本: {scenario_id}", "success": False}

        session.game_state = GameState.EXPLORATION

        # 初始场景描述
        current_node = session.story.get_current_node()
        result = {
            "success": True,
            "scenario_name": scenario.get("name", ""),
            "scenario_description": scenario.get("background", ""),
            "scene": {
                "id": current_node.id if current_node else "",
                "title": current_node.title if current_node else "",
                "description": current_node.description if current_node else "",
                "type": current_node.type.value if current_node else "",
            },
            "choices": session.story.get_choices(),
            "environment": session.world.get_environment(),
            "party": [c.to_dict() for c in session.characters],
        }

        session.add_message(f"🎮 游戏开始！场景: {scenario.get('name', '')}")
        session.add_message(f"📖 {scenario.get('background', '')}")
        session.add_message(f"📍 {current_node.title if current_node else ''}")
        result["log"] = session.get_recent_log()
        return result

    def process_action(self, session_id: str, action: str, **kwargs) -> Dict[str, Any]:
        """处理玩家的行动。

        Args:
            session_id: 会话ID
            action: 行动类型（前进/攻击/对话/使用物品/休息/等）
            **kwargs: 额外参数

        Returns:
            行动结果字典
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "会话不存在", "success": False}

        if session.game_state == GameState.COMBAT:
            return self._process_combat_action(session, action, **kwargs)

        return self._process_exploration_action(session, action, **kwargs)

    def _process_exploration_action(self, session: GameSession, action: str, **kwargs) -> Dict[str, Any]:
        """处理探索状态下的行动。"""
        result = {"action": action, "success": True, "messages": []}

        if action.startswith("choice_"):
            try:
                choice_idx = int(action.replace("choice_", ""))
                story_result = session.story.make_choice(choice_idx)
                if "error" in story_result:
                    result["messages"].append(story_result["error"])
                    result["success"] = False
                else:
                    result["scene"] = {
                        "id": story_result.get("next_scene", ""),
                        "title": story_result.get("scene_title", ""),
                        "description": story_result.get("description", ""),
                        "type": story_result.get("type", ""),
                    }
                    result["choices"] = story_result.get("choices", [])
                    result["messages"].append(story_result.get("description", ""))

                    # 检查是否触发战斗
                    if story_result.get("combat_initiated") and story_result.get("enemies"):
                        combat_result = self._initiate_combat(session, story_result["enemies"])
                        result.update(combat_result)

                    # 检查结局
                    if story_result.get("is_ending"):
                        session.game_state = GameState.GAME_OVER
                        result["game_state"] = "GAME_OVER"

                    # 推进时间
                    session.world.advance_time(hours=1)

            except (ValueError, IndexError):
                result["messages"].append("无效的选择。")
                result["success"] = False

        elif action in ("前进", "向前走", "go"):
            # 随机探索
            env = session.world.get_environment()
            loc_desc = session.story.generate_scene_description(
                location="未知之地",
                time=env["time"]["time_of_day"],
            )
            result["messages"].append(loc_desc)
            session.world.advance_time(hours=random.randint(1, 3))

            # 随机遭遇
            party_level = max((c.level for c in session.characters), default=1)
            encounter = session.world.roll_random_encounter(party_level)
            if encounter:
                monster_id = encounter.get("monster", "goblin")
                result["random_encounter"] = monster_id
                result["messages"].append(f"⚠️ 你遭遇了 {monster_id}！")
                combat_result = self._initiate_combat(session, [monster_id])
                result.update(combat_result)
                result["messages"].extend(combat_result.get("messages", []))

        elif action == "休息" or action == "rest":
            result = self._process_rest(session)
            session.world.advance_time(hours=8)

        elif action == "查看角色" or action == "查看背包" or action == "inventory":
            if session.characters:
                char = session.characters[0]
                result["messages"].append(f"📋 {char.name} - Lv.{char.level} {char._class_data.get('name', '')}")
                result["messages"].append(f"❤️ HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
                result["messages"].append(f"💰 金币: {char.inventory.gold}")
                result["messages"].append(f"🎒 背包物品: {', '.join(f'{i.name}x{i.quantity}' for i in char.inventory.items) if char.inventory.items else '空'}")

                stats = char.stats.to_dict()
                modifiers = char.stats.all_modifiers()
                stat_lines = [f"{Stat(s).value}: {v} ({'+' if modifiers[s] >= 0 else ''}{modifiers[s]})" for s, v in stats.items()]
                result["messages"].extend(stat_lines)

                if char.status_effects:
                    result["messages"].append(f"状态: {', '.join(f'{e.type.value}({e.duration}回合)' for e in char.status_effects)}")

                result["character_dump"] = char.to_dict()

        elif action == "地图" or action == "map":
            area_descs = []
            for area in session.world.areas.values():
                area_descs.append(f"🗺️ {area.name}: {area.description} ({area.area_type.value})")
            result["messages"].extend(area_descs)

        elif action == "天气" or action == "weather":
            env = session.world.get_environment()
            result["messages"].append(f"🌤️ {env['time']['formatted']} - {env['weather']['type']}")
            result["messages"].append(f"🌡️ {env['weather']['temperature']} | 💨 {env['weather']['wind']} | 👁️ {env['weather']['visibility']}")

        elif action.startswith("检定") or action.startswith("check"):
            skill_name = kwargs.get("skill", action.replace("检定", "").strip() or "力量")
            dc = kwargs.get("dc", 12)
            char = session.characters[0] if session.characters else None
            if char:
                check_result = self.perform_skill_check(char, skill_name, dc)
                result.update(check_result)
                result["messages"].append(check_result.get("description", ""))
            else:
                result["messages"].append("没有角色。")

        else:
            # 自由行动：LLM 生成回应
            if self.use_simulated_llm:
                response_text = session.story.generate_scene_description(
                    context=f"玩家想要: {action}",
                    location="当前场景",
                )
                result["messages"].append(response_text)
            else:
                result["messages"].append(f"你做出了行动: {action}（后续将接入 LLM 生成回应）")

        session.add_message(f"🎯 {action}: {result.get('messages', [''])[-1] if result.get('messages') else ''}")
        result["log"] = session.get_recent_log()
        result["game_state"] = session.game_state.name
        result["environment"] = session.world.get_environment()
        return result

    def _process_combat_action(self, session: GameSession, action: str, **kwargs) -> Dict[str, Any]:
        """处理战斗状态下的行动。"""
        if not session.current_combat:
            session.game_state = GameState.EXPLORATION
            return {"error": "���前不在战斗中", "success": False, "game_state": "EXPLORATION"}

        combat = session.current_combat
        result = {"action": action, "success": True, "messages": [], "combat": True}

        if action == "attack":
            target_id = kwargs.get("target")
            if not target_id:
                # 自动选择第一个敌人
                active = combat.active_enemies
                if active:
                    target_id = f"enemy_{session.enemies.index(active[0])}"
                    # 我们需要追踪原始索引，简化处理
                    for i, e in enumerate(session.current_combat.enemies):
                        if e.is_alive and e.template_id == active[0].template_id:
                            target_id = f"enemy_{i}"
                            break

            combat_state = combat.process_action("attack", target_id)
            if combat_state.get("action_result"):
                result["messages"] = combat_state["action_result"].get("messages", [])

            # 战斗状态检查
            if combat.victory:
                session.game_state = GameState.EXPLORATION
                session.current_combat = None
                result["game_state"] = "EXPLORATION"
                result["victory"] = True
            elif combat.phase == CombatPhase.DEFEAT:
                session.game_state = GameState.GAME_OVER
                result["game_state"] = "GAME_OVER"
                result["defeat"] = True
            else:
                result["combat_state"] = combat.get_state()

        elif action in ("cast", "spell"):
            spell_name = kwargs.get("spell_name", "火球术")
            target_id = kwargs.get("target")
            combat_state = combat.process_action("cast_spell", target_id, spell_name=spell_name)
            if combat_state.get("action_result"):
                result["messages"] = combat_state["action_result"].get("messages", [])

        elif action == "use":
            item_id = kwargs.get("item_id", "healing_potion")
            combat_state = combat.process_action("use_item", item_id=item_id)
            if combat_state.get("action_result"):
                result["messages"] = combat_state["action_result"].get("messages", [])

        elif action == "dodge":
            combat_state = combat.process_action("dodge")
            result["messages"].append("你采取了防御姿态！")

        elif action == "flee":
            # 逃跑骰子
            dex_mod = session.characters[0].stats.modifier(Stat.DEXTERITY) if session.characters else 0
            flee_check = self.dice.ability_check(dex_mod, dc=10)
            if flee_check["success"]:
                session.game_state = GameState.EXPLORATION
                session.current_combat = None
                result["messages"].append("🏃 你成功逃离了战斗！")
                result["game_state"] = "EXPLORATION"
                result["fled"] = True
            else:
                result["messages"].append("❌ 逃离失败！")
                # 敌人回合
                combat._run_enemy_turns()

        else:
            result["messages"].append(f"战斗中无法执行 '{action}'，请使用攻击/法术/物品/防御/逃离。")

        session.log.extend(result.get("messages", []))
        result["log"] = session.get_recent_log()
        return result

    def _initiate_combat(self, session: GameSession, enemy_ids: List[str]) -> Dict[str, Any]:
        """初始化战斗。"""
        import json
        from pathlib import Path

        # 加载怪物数据
        monsters_path = Path(__file__).resolve().parent.parent.parent / "data" / "monsters.json"
        try:
            with open(monsters_path, "r", encoding="utf-8") as f:
                all_monsters = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_monsters = []

        enemy_instances = []
        for eid in enemy_ids:
            template = next((m for m in all_monsters if m["id"] == eid), None)
            if template:
                party_level = max((c.level for c in session.characters), default=1)
                scale = max(0.5, party_level / 3.0)
                enemy_instances.append(EnemyInstance.from_template(template, scale))
            else:
                # 默认哥布林
                goblin_template = {
                    "id": "goblin",
                    "name": "哥布林",
                    "armor_class": 13,
                    "hit_points": 12,
                    "stats": {"strength": 8, "dexterity": 14, "constitution": 12, "intelligence": 10, "wisdom": 10, "charisma": 8},
                    "xp": 50,
                    "loot": {"gold": "1d4", "items": []},
                }
                enemy_instances.append(EnemyInstance.from_template(goblin_template))

        if not enemy_instances:
            return {"messages": ["没有找到怪物数据。"]}

        combat = CombatEngine(session.characters, enemy_instances)
        session.current_combat = combat
        session.game_state = GameState.COMBAT

        combat_state = combat.start_combat()
        return {
            "combat_started": True,
            "messages": combat_state.get("log", [])[-5:],
            "combat_state": combat_state,
            "game_state": "COMBAT",
            "enemies": [e.to_dict() for e in enemy_instances],
        }

    def _process_rest(self, session: GameSession) -> Dict[str, Any]:
        """处理休息。"""
        messages = []
        for char in session.characters:
            if char.current_hp < char.max_hp:
                heal_amount = int(char.max_hp * 0.5)  # 长休恢复 50%
                actual = char.heal(heal_amount)
                messages.append(f"💤 {char.name} 休息并恢复了 {actual} 点生命值 (HP: {char.current_hp}/{char.max_hp})")
            else:
                messages.append(f"💤 {char.name} 休息了一会 (HP 已满)")

        return {"messages": messages, "success": True, "action": "休息"}

    def perform_skill_check(self, character: Character, skill_name: str, dc: int = 12) -> Dict[str, Any]:
        """执行技能检定。

        Args:
            character: 检定的角色
            skill_name: 技能名称（力量/敏捷/智力/感知/魅力/杂技/调查等）
            dc: 难度等级

        Returns:
            检定结果字典
        """
        # 属性 -> 技能映射
        stat_map = {
            "力量": Stat.STRENGTH, "strength": Stat.STRENGTH,
            "敏捷": Stat.DEXTERITY, "dexterity": Stat.DEXTERITY,
            "体质": Stat.CONSTITUTION, "constitution": Stat.CONSTITUTION,
            "智力": Stat.INTELLIGENCE, "intelligence": Stat.INTELLIGENCE,
            "感知": Stat.WISDOM, "wisdom": Stat.WISDOM,
            "魅力": Stat.CHARISMA, "charisma": Stat.CHARISMA,
            "运动": Stat.STRENGTH, "athletics": Stat.STRENGTH,
            "杂技": Stat.DEXTERITY, "acrobatics": Stat.DEXTERITY,
            "调查": Stat.INTELLIGENCE, "investigation": Stat.INTELLIGENCE,
            "历史": Stat.INTELLIGENCE, "history": Stat.INTELLIGENCE,
            "洞察": Stat.WISDOM, "insight": Stat.WISDOM,
            "感知检": Stat.WISDOM, "perception": Stat.WISDOM,
            "说服": Stat.CHARISMA, "persuasion": Stat.CHARISMA,
            "威吓": Stat.CHARISMA, "intimidation": Stat.CHARISMA,
        }

        stat = stat_map.get(skill_name.lower().strip())
        if not stat:
            return {
                "success": False,
                "description": f"未知的技能: {skill_name}",
            }

        modifier = character.stats.modifier(stat)
        roll_result = self.dice.ability_check(modifier, dc)

        # 成功/失败叙事
        if roll_result["success"]:
            if roll_result["is_critical"]:
                narrative = f"💫 大成功！{character.name} 的{skill_name}检定自然20！效果拔群！"
            else:
                narrative = f"✅ {character.name} 的{skill_name}检定成功！(骰:{roll_result['roll']}+{modifier}={roll_result['total']} vs DC {dc})"
        else:
            if roll_result["is_fumble"]:
                narrative = f"💥 大失败！{character.name} 的{skill_name}检定自然1！糟糕的结果！"
            else:
                narrative = f"❌ {character.name} 的{skill_name}检定失败。 (骰:{roll_result['roll']}+{modifier}={roll_result['total']} vs DC {dc})"

        roll_result["narrative"] = narrative
        roll_result["skill"] = skill_name
        roll_result["stat_used"] = stat.value
        return roll_result

    def roll_dice(self, dice_str: str) -> Dict[str, Any]:
        """投掷骰子。"""
        return self.dice.roll(dice_str)

    def get_session(self, session_id: str) -> Optional[GameSession]:
        """获取会话。"""
        return self.sessions.get(session_id)

    def to_dict(self) -> Dict[str, Any]:
        """序列化。"""
        return {
            "sessions": {k: v.to_dict() for k, v in self.sessions.items()},
            "total_sessions": len(self.sessions),
        }
