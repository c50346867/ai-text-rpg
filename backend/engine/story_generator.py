# -*- coding: utf-8 -*-
"""
Story Generator — 故事生成器模块。

管理分支剧情节点树、任务系统（主线/支线/随机任务）、
对话树和剧情事件触发器。

Classes:
    StoryGenerator: 故事生成器
    Quest: 任务
    DialogueNode: 对话节点
    StoryNode: 剧情节点
    QuestManager: 任务管理器
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class QuestType(Enum):
    """任务类型。"""
    MAIN = "主线"
    SIDE = "支线"
    RANDOM = "随机"
    DAILY = "日常"
    FACTION = "阵营"


class QuestStatus(Enum):
    """任务状态。"""
    NOT_STARTED = "未开始"
    ACTIVE = "进行中"
    COMPLETED = "已完成"
    FAILED = "已失败"


class StoryNodeType(Enum):
    """剧情节点类型。"""
    EXPLORATION = "探索"
    COMBAT = "战斗"
    DIALOGUE = "对话"
    REST = "休息"
    SHOP = "商店"
    PUZZLE = "解谜"
    EVENT = "事件"
    CHOICE = "选择"
    ENDING = "结局"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class QuestObjective:
    """任务目标。"""
    id: str
    description: str
    type: str  # "kill", "talk", "collect", "explore", "escort", "use"
    target: str
    count_required: int = 1
    count_current: int = 0
    is_completed: bool = False

    def progress(self, count: int = 1) -> bool:
        """推进目标进度。返回是否完成。"""
        if self.is_completed:
            return True
        self.count_current = min(self.count_required, self.count_current + count)
        if self.count_current >= self.count_required:
            self.is_completed = True
        return self.is_completed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "type": self.type,
            "target": self.target,
            "count_required": self.count_required,
            "count_current": self.count_current,
            "is_completed": self.is_completed,
        }


@dataclass
class Quest:
    """任务。"""
    id: str
    name: str
    description: str
    quest_type: QuestType
    status: QuestStatus = QuestStatus.NOT_STARTED
    objectives: List[QuestObjective] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=lambda: {"xp": 100, "gold": 50, "items": []})
    recommended_level: int = 1
    giver: str = ""
    location: str = ""
    next_quest_id: Optional[str] = None  # 后续任务链

    @property
    def all_objectives_completed(self) -> bool:
        return all(obj.is_completed for obj in self.objectives) if self.objectives else True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "quest_type": self.quest_type.value,
            "status": self.status.value,
            "objectives": [obj.to_dict() for obj in self.objectives],
            "rewards": self.rewards,
            "recommended_level": self.recommended_level,
            "giver": self.giver,
            "location": self.location,
            "all_objectives_completed": self.all_objectives_completed,
        }


@dataclass
class DialogueChoice:
    """对话选项。"""
    text: str
    next_node_id: Optional[str] = None
    action: Optional[str] = None
    skill_check: Optional[Dict[str, Any]] = None
    condition: Optional[str] = None


@dataclass
class DialogueNode:
    """对话节点。"""
    id: str
    speaker: str
    text: str
    choices: List[DialogueChoice] = field(default_factory=list)
    emotion: str = "neutral"  # happy, sad, angry, surprised, neutral


@dataclass
class StoryNode:
    """剧情节点。"""
    id: str
    type: StoryNodeType
    title: str
    description: str
    choices: List[Dict[str, Any]] = field(default_factory=list)
    enemies: List[str] = field(default_factory=list)
    npcs: List[Dict[str, Any]] = field(default_factory=list)
    skill_checks: List[Dict[str, Any]] = field(default_factory=list)
    items_gained: List[Dict[str, Any]] = field(default_factory=list)
    flags_set: List[str] = field(default_factory=list)
    is_ending: bool = False


# ---------------------------------------------------------------------------
# Quest Manager
# ---------------------------------------------------------------------------

class QuestManager:
    """任务管理器。

    管理所有任务的状态、进度追踪和��励发放。

    Usage:
        >>> qm = QuestManager()
        >>> qm.add_quest(quest)
        >>> qm.progress("quest_1", "kill_goblins", count=1)
        >>> rewards = qm.complete_quest("quest_1")
    """

    def __init__(self):
        self.quests: Dict[str, Quest] = {}
        self.completed_quests: List[str] = []
        self.active_quests: Dict[str, Quest] = {}

    def add_quest(self, quest: Quest) -> bool:
        """添加新任务。"""
        if quest.id in self.quests:
            return False
        self.quests[quest.id] = quest
        quest.status = QuestStatus.ACTIVE
        self.active_quests[quest.id] = quest
        return True

    def progress_quest(self, quest_id: str, objective_type: str, target: str, count: int = 1) -> List[str]:
        """推进任���进度。返回消息列表。"""
        messages = []
        quest = self.quests.get(quest_id)
        if not quest or quest.status != QuestStatus.ACTIVE:
            return messages

        for obj in quest.objectives:
            if obj.type == objective_type and obj.target == target:
                if obj.progress(count):
                    messages.append(f"✅ 任务目标完成: {obj.description}")
                    if quest.all_objectives_completed:
                        messages.extend(self._complete_quest(quest_id))
                else:
                    messages.append(f"📋 任务进度: {obj.description} ({obj.count_current}/{obj.count_required})")
        return messages

    def complete_quest(self, quest_id: str) -> List[str]:
        """手动完成任务。"""
        return self._complete_quest(quest_id)

    def _complete_quest(self, quest_id: str) -> List[str]:
        """内部：完成任务。"""
        messages = []
        quest = self.quests.get(quest_id)
        if not quest or quest.status != QuestStatus.ACTIVE:
            return messages

        quest.status = QuestStatus.COMPLETED
        self.completed_quests.append(quest_id)
        self.active_quests.pop(quest_id, None)

        messages.append(f"🎉 任务完成: {quest.name}！")
        rewards = quest.rewards
        if rewards.get("xp"):
            messages.append(f"⭐ 获得 {rewards['xp']} 经验值！")
        if rewards.get("gold"):
            messages.append(f"💰 获得 {rewards['gold']} 金币！")
        if rewards.get("items"):
            messages.append(f"📦 获得物品: {', '.join(rewards['items'])}！")

        # 检查后续任务链
        if quest.next_quest_id and quest.next_quest_id in self.quests:
            next_quest = self.quests[quest.next_quest_id]
            next_quest.status = QuestStatus.ACTIVE
            self.active_quests[next_quest.id] = next_quest
            messages.append(f"📜 新任务触发: {next_quest.name}")

        return messages

    def fail_quest(self, quest_id: str) -> None:
        """任务失败。"""
        quest = self.quests.get(quest_id)
        if quest:
            quest.status = QuestStatus.FAILED
            self.active_quests.pop(quest_id, None)

    def get_active_quests(self) -> List[Quest]:
        """获取进行中的任务。"""
        return list(self.active_quests.values())

    def generate_random_quest(self, party_level: int, location: str = "") -> Quest:
        """生成一个随机支线任务。"""
        templates = [
            {
                "name": "清剿怪物",
                "description": f"附近{location or '区域'}的怪物日益猖獗，需要冒险者出手清理。",
                "objective_type": "kill",
                "target": "monster",
                "count": random.randint(3, 6),
                "xp": 100 * party_level,
                "gold": 30 * party_level,
            },
            {
                "name": "寻找失物",
                "description": "有村民丢失了重要的物品，可能在某个危险的地方。",
                "objective_type": "collect",
                "target": "lost_item",
                "count": 1,
                "xp": 80 * party_level,
                "gold": 40 * party_level,
            },
            {
                "name": "探索遗迹",
                "description": "发现了疑似远古遗迹的入口，需要勇敢的冒险者前去调查。",
                "objective_type": "explore",
                "target": "ruins",
                "count": 1,
                "xp": 120 * party_level,
                "gold": 50 * party_level,
            },
        ]

        template = random.choice(templates)
        quest = Quest(
            id=f"random_{random.randint(1000, 9999)}",
            name=template["name"],
            description=template["description"],
            quest_type=QuestType.RANDOM,
            objectives=[
                QuestObjective(
                    id="obj_1",
                    description=f"{template['objective_type']} {template['target']} x{template['count']}",
                    type=template["objective_type"],
                    target=template["target"],
                    count_required=template["count"],
                )
            ],
            rewards={"xp": template["xp"], "gold": template["gold"], "items": []},
            recommended_level=party_level,
            location=location,
        )
        return quest

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_quests": [q.to_dict() for q in self.get_active_quests()],
            "completed_quests": self.completed_quests,
        }


# ---------------------------------------------------------------------------
# Scenario Loader
# ---------------------------------------------------------------------------

class ScenarioLoader:
    """冒险剧本加载器。

    从 JSON 文件加载预设冒险剧本。

    Usage:
        >>> loader = ScenarioLoader()
        >>> scenario = loader.load("tutorial")
        >>> nodes = loader.build_story_tree(scenario)
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = str(Path(__file__).resolve().parent.parent.parent / "data" / "scenarios")
        self.data_dir = data_dir

    def load(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """加载剧本 JSON。"""
        path = Path(self.data_dir) / f"{scenario_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_scenarios(self) -> List[str]:
        """列出可用剧本。"""
        path = Path(self.data_dir)
        if not path.exists():
            return []
        return [f.stem for f in path.glob("*.json")]

    def build_story_tree(self, scenario: Dict[str, Any]) -> Dict[str, StoryNode]:
        """将剧本 JSON 转换为剧情节点树。"""
        nodes = {}
        for scene in scenario.get("scenes", []):
            node_type = StoryNodeType.EXPLORATION
            type_str = scene.get("type", "exploration").lower()
            for nt in StoryNodeType:
                if nt.value.lower() == type_str:
                    node_type = nt
                    break
                if nt.name.lower() == type_str:
                    node_type = nt
                    break

            node = StoryNode(
                id=scene.get("id", "unknown"),
                type=node_type,
                title=scene.get("name", ""),
                description=scene.get("description", ""),
                choices=scene.get("choices", []),
                enemies=scene.get("enemies", []),
                npcs=scene.get("npcs", []),
                items_gained=scene.get("on_victory", {}).get("items", []) if "on_victory" in scene else [],
                is_ending=scene.get("ending", False),
            )
            nodes[node.id] = node

        return nodes


# ---------------------------------------------------------------------------
# Story Generator (LLM Proxy)
# ---------------------------------------------------------------------------

class StoryGenerator:
    """故事生成器。

    管理和驱动游戏剧情推进，使用 LLM 接口（模拟）来生成叙事情节、
    NPC 对话、分支剧情和任务。

    实际 LLM 集成可由子类重写 generate_text 方法实现。

    Usage:
        >>> sg = StoryGenerator()
        >>> result = sg.generate_scene_description("你站在迷雾森林入口...")
        >>> result = sg.generate_npc_dialogue("镇长", "关于森林里的怪事...")
    """

    def __init__(self, model_name: str = "simulated"):
        self.model_name = model_name
        self.scenario_loader = ScenarioLoader()
        self.current_scenario: Optional[Dict[str, Any]] = None
        self.current_node_id: Optional[str] = None
        self.story_nodes: Dict[str, StoryNode] = {}
        self.quest_manager: QuestManager = QuestManager()
        self.story_flags: set = set()
        self.narrative_history: List[str] = []

        # LLM 模拟模板（实际项目应替换为真实 LLM 调用）
        self._scene_templates = [
            "空气中弥漫着{atmosphere}的气息。你环顾四周，{surroundings}。{detail}",
            "{time}的{location}显得{atmosphere}。{surroundings}，{detail}",
            "踏入了{location}。{atmosphere}的风吹过，{surroundings}。{detail}",
        ]

        self._atmosphere_pool = ["神秘", "阴森", "宁静", "危险", "古老", "诡异"]
        self._detail_pool = [
            "远处隐约传来不祥的声响。",
            "地面上有一些奇怪的足迹。",
            "空气中有一种淡淡的魔法气息。",
            "你感到有人在暗处注视着。",
            "这里的能量比你预想的要强烈。",
        ]

    def load_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """加载冒险剧本。"""
        scenario = self.scenario_loader.load(scenario_id)
        if scenario:
            self.current_scenario = scenario
            self.story_nodes = self.scenario_loader.build_story_tree(scenario)
            self.current_node_id = scenario["scenes"][0]["id"] if scenario.get("scenes") else None
            return scenario
        return None

    def get_current_node(self) -> Optional[StoryNode]:
        """获取当前剧情节点。"""
        if self.current_node_id and self.current_node_id in self.story_nodes:
            return self.story_nodes[self.current_node_id]
        return None

    def get_choices(self) -> List[Dict[str, Any]]:
        """获取当前节点的选项。"""
        node = self.get_current_node()
        if node:
            available = []
            for choice in node.choices:
                condition = choice.get("condition", "")
                if condition:
                    # 简单条件检查
                    if condition.startswith("gold>="):
                        min_gold = int(condition.split(">=")[1])
                        # NOTE: 需外部传入金币
                        pass
                    elif condition.startswith("has_item="):
                        item_id = condition.split("=")[1]
                        # NOTE: 需外部传入背包
                        pass
                    elif condition.startswith("flag="):
                        flag = condition.split("=")[1]
                        if flag not in self.story_flags:
                            continue
                available.append(choice)
            return available
        return []

    def make_choice(self, choice_index: int) -> Dict[str, Any]:
        """执行选择，推进剧情。"""
        choices = self.get_choices()
        if choice_index < 0 or choice_index >= len(choices):
            return {"error": "无效的选择", "success": False}

        choice = choices[choice_index]
        next_scene = choice.get("next_scene")
        action = choice.get("action", "")
        skill_check = choice.get("skill_check")

        # 处理技能检定
        if skill_check:
            # 外部进行检定
            pass

        # 设置标志
        if action:
            self.story_flags.add(action)

        # 设置物品
        if "items_gained" in choice:
            for item in choice.get("items_gained", []):
                self.narrative_history.append(f"获得物品: {item.get('name', '?')}")

        # 推进
        if next_scene and next_scene in self.story_nodes:
            self.current_node_id = next_scene
            new_node = self.story_nodes[next_scene]

            result = {
                "success": True,
                "action": action,
                "next_scene": next_scene,
                "scene_title": new_node.title,
                "description": new_node.description,
                "type": new_node.type.value,
                "choices": self.get_choices(),
                "enemies": new_node.enemies,
                "is_ending": new_node.is_ending,
                "npcs": new_node.npcs,
            }

            # 战斗节点自动触发
            if new_node.type == StoryNodeType.COMBAT and new_node.enemies:
                result["combat_initiated"] = True

            self.narrative_history.append(f"[{new_node.type.value}] {new_node.title}: {new_node.description[:50]}...")
            return result

        return {"error": "场景不存在", "success": False}

    def generate_scene_description(
        self,
        context: str = "",
        location: str = "未知之地",
        time: str = "",
    ) -> str:
        """生成场景描述文案。"""
        template = random.choice(self._scene_templates)
        atmosphere = random.choice(self._atmosphere_pool)

        surroundings_options = [
            "树木在风中摇曳，投下诡异的阴影",
            "古老的石墙上爬满了藤蔓",
            "地面铺满了落叶和碎石",
            "空气中漂浮着微光细塵",
            "墙壁上刻满了看不懂的符文",
        ]

        text = template.format(
            time=time or "此刻",
            location=location,
            atmosphere=atmosphere,
            surroundings=random.choice(surroundings_options),
            detail=random.choice(self._detail_pool),
        )

        if context:
            text = f"{context}\n\n{text}"

        return text

    def generate_npc_dialogue(
        self,
        npc_name: str,
        topic: str = "",
        npc_personality: str = "友好",
    ) -> str:
        """生成 NPC 对话文本。"""
        greetings = [
            f"{npc_name} {'微笑着' if npc_personality == '友好' else '冷冷地'}看了你一眼。",
            f"{npc_name} {'热情地' if npc_personality == '友好' else '警惕地'}打量着你。",
            f"{npc_name} {'用温和的' if npc_personality == '友好' else '用冰冷的'}声音开口了。",
        ]

        responses = {
            "友好": [
                f"欢迎来到我们的小镇。{topic if topic else '有什么需要帮忙的吗？'}",
                f"哦，旅行者！{topic if topic else '你来得正是时候。'}",
                f"太好了，终于有冒险者来了！{topic if topic else '我们有麻烦了。'}",
            ],
            "冷漠": [
                f"哼，又一个冒险者。{topic if topic else '说完就走。'}",
                f"我不和陌生人说话。{topic if topic else ''}",
                f"你最好别管闲事...{topic if topic else ''}",
            ],
        }

        greeting = random.choice(greetings)
        response = random.choice(responses.get(npc_personality, responses["友好"]))

        return f"{greeting}\n\n\"{response}\""

    def generate_combat_narrative(self, attacker: str, defender: str, action: str, result: str) -> str:
        """生成战斗叙事文本。"""
        templates = [
            f"{attacker} {action}！{result}{defender}受到冲击。",
            f"只见{attacker}一个闪身，{action}朝{defender}袭去！{result}",
            f"{attacker}蓄力一击，{action}！{result}",
        ]
        return random.choice(templates)

    def generate_quest_narrative(self, quest: Quest, character_name: str) -> str:
        """生成任务叙事文本。"""
        narratives = {
            QuestType.MAIN: f"命运的齿轮开始转动。{character_name}踏上了{quest.name}的征程。",
            QuestType.SIDE: f"一个意外的请求落到了{character_name}身上——{quest.name}。",
            QuestType.RANDOM: f"机缘巧合之下，{character_name}接到了{quest.name}的委托。",
        }
        return narratives.get(quest.quest_type, f"新任务: {quest.name}")

    def to_dict(self) -> Dict[str, Any]:
        """序列化。"""
        current = self.get_current_node()
        return {
            "current_scenario": self.current_scenario.get("name") if self.current_scenario else None,
            "current_node": current.title if current else None,
            "current_node_type": current.type.value if current else None,
            "choices": self.get_choices(),
            "flags": list(self.story_flags),
            "quests": self.quest_manager.to_dict(),
            "narrative_history_count": len(self.narrative_history),
        }
