# -*- coding: utf-8 -*-
"""
World Manager — 世界观管理器模块。

管理游戏地图、地点、区域、随机遭遇、天气和时间系统。

Classes:
    WorldManager: 世界观管理器
    Location: 地点
    Area: 区域
    Weather: 天气
    TimeSystem: 时间系统
    EncounterTable: 随机遭遇表
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AreaType(Enum):
    """区域类型。"""
    FOREST = "森林"
    TOWN = "城镇"
    DUNGEON = "地牢"
    MOUNTAIN = "山脉"
    COAST = "海岸"
    PLAINS = "平原"
    DESERT = "沙漠"
    SWAMP = "沼泽"
    CAVE = "洞穴"
    RUINS = "废墟"
    TEMPLE = "神庙"
    CASTLE = "城堡"


class WeatherType(Enum):
    """天气类型。"""
    CLEAR = "晴朗"
    CLOUDY = "多云"
    RAINY = "下雨"
    STORMY = "暴风雨"
    FOGGY = "大雾"
    SNOWY = "下雪"
    WINDY = "大风"


class TimeOfDay(Enum):
    """时间。"""
    DAWN = "黎明"
    MORNING = "早晨"
    NOON = "正午"
    AFTERNOON = "下午"
    DUSK = "黄昏"
    EVENING = "傍晚"
    NIGHT = "夜晚"
    MIDNIGHT = "深夜"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Location:
    """地图上的一个地点。"""
    id: str
    name: str
    description: str
    area_type: AreaType
    x: int
    y: int
    npcs: List[str] = field(default_factory=list)
    encounters: List[str] = field(default_factory=list)
    is_discovered: bool = False
    is_safe_zone: bool = False
    connections: List[str] = field(default_factory=list)  # 相连的地点ID
    loot: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "area_type": self.area_type.value,
            "x": self.x,
            "y": self.y,
            "npcs": self.npcs,
            "is_discovered": self.is_discovered,
            "is_safe_zone": self.is_safe_zone,
            "connections": self.connections,
        }


@dataclass
class Area:
    """区域（包含多个地点）。"""
    id: str
    name: str
    description: str
    area_type: AreaType
    danger_level: int  # 1-10
    locations: List[Location]
    encounters: List[Dict[str, Any]]
    special_rules: Dict[str, Any] = field(default_factory=dict)

    def get_discovery_progress(self) -> float:
        if not self.locations:
            return 1.0
        discovered = sum(1 for loc in self.locations if loc.is_discovered)
        return discovered / len(self.locations)

    def get_random_location(self) -> Optional[Location]:
        if self.locations:
            return random.choice(self.locations)
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "area_type": self.area_type.value,
            "danger_level": self.danger_level,
            "locations": [loc.to_dict() for loc in self.locations],
            "discovery_progress": self.get_discovery_progress(),
        }


@dataclass
class Weather:
    """天气状态。"""
    type: WeatherType = WeatherType.CLEAR
    temperature: str = "舒适"  # 酷热/热/舒适/凉/寒冷/严寒
    wind_speed: str = "无风"  # 无风/微风/大风/狂风
    visibility: str = "良好"  # 良好/一般/差/极差

    def effects_on_combat(self) -> Dict[str, Any]:
        """天气对战斗的影响。"""
        effects = {}
        if self.type == WeatherType.RAINY:
            effects["range_attack_disadvantage"] = True
            effects["fire_damage_reduction"] = 0.5
        elif self.type == WeatherType.STORMY:
            effects["range_attack_impossible"] = True
            effects["perception_modifier"] = -5
            effects["movement_reduction"] = 0.5
        elif self.type == WeatherType.FOGGY:
            effects["perception_modifier"] = -3
            effects["melee_attack_disadvantage"] = True
        elif self.type == WeatherType.SNOWY:
            effects["movement_reduction"] = 0.75
            effects["cold_damage_bonus"] = 2
        return effects

    def to_dict(self) -> Dict[str, str]:
        return {
            "type": self.type.value,
            "temperature": self.temperature,
            "wind": self.wind_speed,
            "visibility": self.visibility,
        }


@dataclass
class TimeSystem:
    """时间系统。"""
    day: int = 1
    hour: int = 8
    minute: int = 0

    @property
    def time_of_day(self) -> TimeOfDay:
        if 5 <= self.hour < 7:
            return TimeOfDay.DAWN
        elif 7 <= self.hour < 11:
            return TimeOfDay.MORNING
        elif 11 <= self.hour < 13:
            return TimeOfDay.NOON
        elif 13 <= self.hour < 17:
            return TimeOfDay.AFTERNOON
        elif 17 <= self.hour < 19:
            return TimeOfDay.DUSK
        elif 19 <= self.hour < 21:
            return TimeOfDay.EVENING
        elif 21 <= self.hour < 23:
            return TimeOfDay.NIGHT
        else:
            return TimeOfDay.MIDNIGHT

    def advance(self, hours: int = 0, minutes: int = 0) -> None:
        """推进时间。"""
        total_minutes = self.hour * 60 + self.minute + hours * 60 + minutes
        self.day += total_minutes // (24 * 60)
        total_minutes = total_minutes % (24 * 60)
        self.hour = total_minutes // 60
        self.minute = total_minutes % 60

    def format_time(self) -> str:
        return f"第{self.day}天 {self.hour:02d}:{self.minute:02d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "hour": self.hour,
            "minute": self.minute,
            "time_of_day": self.time_of_day.value,
            "formatted": self.format_time(),
        }


# ---------------------------------------------------------------------------
# Encounter Table
# ---------------------------------------------------------------------------

@dataclass
class EncounterEntry:
    """遭遇表条目。"""
    monster_id: str
    weight: int  # 权重，越高越常见
    min_level: int
    max_level: int
    count_range: Tuple[int, int]  # (最小数量, 最大数量)
    is_boss: bool = False


class EncounterTable:
    """随机遭遇表。"""

    def __init__(self, area_type: AreaType, danger_level: int):
        self.entries: List[EncounterEntry] = []
        self.area_type = area_type
        self.danger_level = danger_level
        self._generate_default_encounters()

    def _generate_default_encounters(self) -> None:
        """生成默认遭遇表（基于区域类型和危险等级）。"""
        # 如果危险等级低
        if self.danger_level <= 3:
            self.entries = [
                EncounterEntry("goblin", 30, 1, 3, (1, 4)),
                EncounterEntry("wolf", 25, 1, 2, (1, 3)),
                EncounterEntry("bandit", 20, 1, 2, (1, 3)),
            ]
        elif self.danger_level <= 6:
            self.entries = [
                EncounterEntry("skeleton", 25, 1, 4, (2, 4)),
                EncounterEntry("giant_spider", 20, 2, 4, (1, 2)),
                EncounterEntry("bandit", 15, 1, 3, (2, 5)),
                EncounterEntry("shadow", 10, 3, 5, (1, 2)),
            ]
        else:
            self.entries = [
                EncounterEntry("troll", 20, 4, 7, (1, 2)),
                EncounterEntry("shadow", 15, 3, 6, (2, 3)),
                EncounterEntry("young_dragon_red", 5, 6, 10, (1, 1), is_boss=True),
            ]

    def roll_encounter(self, party_level: int) -> Optional[List[EncounterEntry]]:
        """骰随机遭遇。返回匹配的遭遇条目列表。"""
        if not self.entries:
            return None

        # 过滤符合等级的
        valid = [
            e for e in self.entries
            if e.min_level <= party_level <= e.max_level
        ]
        if not valid:
            return None

        # 按权重选择
        total_weight = sum(e.weight for e in valid)
        roll = random.randint(1, total_weight)
        cumulative = 0
        for entry in valid:
            cumulative += entry.weight
            if roll <= cumulative:
                return [entry]

        return [valid[-1]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "area_type": self.area_type.value,
            "danger_level": self.danger_level,
            "entries": [
                {
                    "monster_id": e.monster_id,
                    "weight": e.weight,
                    "level_range": (e.min_level, e.max_level),
                    "count_range": e.count_range,
                }
                for e in self.entries
            ],
        }


# ---------------------------------------------------------------------------
# World Manager
# ---------------------------------------------------------------------------

class WorldManager:
    """世界观管理器。

    管理系统区域、地点、随机遭遇、天气和时间。

    Usage:
        >>> world = WorldManager()
        >>> world.time.advance(hours=2)
        >>> loc = world.get_location("橡木镇")
        >>> encounter = world.roll_random_encounter(party_level=1)
    """

    DEFAULT_AREAS = {
        "whisperwood": Area(
            id="whisperwood",
            name="迷雾森林",
            description="常年被灰色迷雾笼罩的神秘森林。树木扭曲，暗影潜伏。",
            area_type=AreaType.FOREST,
            danger_level=3,
            locations=[
                Location("forest_edge", "森林入口", "迷雾蔓延的开阔地带，进入森林的必经之路。", AreaType.FOREST, 0, 0, is_discovered=True),
                Location("goblin_camp", "哥布林营地", "一处废弃的猎营，现在被哥布林占据。", AreaType.FOREST, 2, -1),
                Location("ancient_tree", "古巨木", "一棵高耸入云的古老橡树，树皮上刻着神秘的符文。", AreaType.FOREST, -1, 3),
                Location("hidden_pond", "隐湖", "被树木环绕的小湖，湖水异常清澈但深不见底。", AreaType.FOREST, -2, 1),
                Location("forest_ruins", "森林废墟", "远古文明的遗迹，如今被藤蔓覆盖。", AreaType.RUINS, 3, 2, is_safe_zone=True),
            ],
            encounters=[
                {"monster": "goblin", "weight": 40, "min_level": 1, "max_level": 3},
                {"monster": "wolf", "weight": 25, "min_level": 1, "max_level": 2},
                {"monster": "giant_spider", "weight": 15, "min_level": 2, "max_level": 4},
                {"monster": "bandit", "weight": 20, "min_level": 1, "max_level": 3},
            ],
        ),
        "oaktown": Area(
            id="oaktown",
            name="橡木镇",
            description="宁静的边境小镇，以橡木和酿酒闻名。冒险者聚集的起点。",
            area_type=AreaType.TOWN,
            danger_level=1,
            locations=[
                Location("town_center", "镇广场", "小镇的中心，常春藤覆盖的喷泉旁村民们往来不绝。", AreaType.TOWN, 0, 0, is_discovered=True, is_safe_zone=True),
                Location("mayor_office", "市政厅", "镇长的办公和居住地。", AreaType.TOWN, 1, 0, is_safe_zone=True),
                Location("blacksmith", "铁匠铺", "叮当作响的铁匠铺，矮人铁匠日夜忙碌。", AreaType.TOWN, -1, 1, is_safe_zone=True),
                Location("tavern", "醉猫酒馆", "温暖的炉火和麦酒香，冒险者的最佳落脚点。", AreaType.TOWN, -1, -1, is_safe_zone=True),
                Location("temple", "光明圣殿", "小镇唯一的圣殿，供奉着光之神。", AreaType.TOWN, 0, -1, is_safe_zone=True),
            ],
            encounters=[],
            special_rules={"rest_heal_multiplier": 2.0},
        ),
        "dark_delve": Area(
            id="dark_delve",
            name="暗影矿洞",
            description="废弃已久的古老矿洞，深处隐藏着不为人知的秘密。",
            area_type=AreaType.DUNGEON,
            danger_level=5,
            locations=[
                Location("cave_entrance", "矿洞入口", "坍塌了一半的矿洞入口，黑暗从深处涌出。", AreaType.CAVE, 0, 0, is_discovered=True),
                Location("main_shaft", "主矿道", "蜿蜒向下的主矿道，墙上的魔法灯早已熄灭。", AreaType.CAVE, 1, -2),
                Location("crystal_chamber", "水晶室", "天然水晶丛生的大厅，微弱的荧光照亮四周。", AreaType.CAVE, -1, -3),
                Location("deep_temple", "深渊祭坛", "矿洞最深处隐藏的古神祭坛。", AreaType.TEMPLE, 0, -5, is_safe_zone=False),
            ],
            encounters=[
                {"monster": "skeleton", "weight": 30, "min_level": 2, "max_level": 5},
                {"monster": "shadow", "weight": 20, "min_level": 3, "max_level": 5},
                {"monster": "giant_spider", "weight": 25, "min_level": 2, "max_level": 4},
            ],
        ),
    }

    def __init__(self):
        self.areas: Dict[str, Area] = {}
        self.time: TimeSystem = TimeSystem()
        self.weather: Weather = Weather()
        self.locations: Dict[str, Location] = {}

        # 加载默认区域
        for area_id, area in self.DEFAULT_AREAS.items():
            self.add_area(area_id, area)

        # 初始化天气
        self._roll_weather()

    def add_area(self, area_id: str, area: Area) -> None:
        """添加区域。"""
        self.areas[area_id] = area
        for loc in area.locations:
            self.locations[loc.id] = loc

    def get_location(self, location_id: str) -> Optional[Location]:
        """获取地点。"""
        return self.locations.get(location_id)

    def get_area(self, area_id: str) -> Optional[Area]:
        """获取区域。"""
        return self.areas.get(area_id)

    def discover_location(self, location_id: str) -> bool:
        """发现地点。"""
        loc = self.get_location(location_id)
        if loc and not loc.is_discovered:
            loc.is_discovered = True
            return True
        return False

    def roll_random_encounter(self, party_level: int, area_id: str = "whisperwood") -> Optional[Dict[str, Any]]:
        """骰随机遭遇。"""
        area = self.get_area(area_id)
        if not area or not area.encounters:
            return None

        # 25% 概率没有遭遇
        if random.random() < 0.25:
            return None

        valid = [
            e for e in area.encounters
            if e.get("min_level", 1) <= party_level <= e.get("max_level", 99)
        ]
        if not valid:
            return None

        total_weight = sum(e.get("weight", 10) for e in valid)
        roll = random.randint(1, total_weight)
        cumulative = 0
        for entry in valid:
            cumulative += entry.get("weight", 10)
            if roll <= cumulative:
                return entry

        return random.choice(valid)

    def get_connected_locations(self, location_id: str) -> List[Location]:
        """获取相连的地点。"""
        loc = self.get_location(location_id)
        if not loc:
            return []
        return [self.get_location(cid) for cid in loc.connections if self.get_location(cid)]

    def _roll_weather(self) -> None:
        """随机生成天气。"""
        roll = random.randint(1, 100)
        if roll <= 40:
            self.weather.type = WeatherType.CLEAR
        elif roll <= 60:
            self.weather.type = WeatherType.CLOUDY
        elif roll <= 75:
            self.weather.type = WeatherType.RAINY
        elif roll <= 85:
            self.weather.type = WeatherType.FOGGY
        elif roll <= 92:
            self.weather.type = WeatherType.WINDY
        elif roll <= 97:
            self.weather.type = WeatherType.STORMY
        else:
            self.weather.type = WeatherType.SNOWY

        # 温度随季节/时间变化
        if self.time.hour < 6 or self.time.hour > 20:
            self.weather.temperature = "凉"
        elif 10 <= self.time.hour <= 16:
            self.weather.temperature = "暖"
        else:
            self.weather.temperature = "舒适"

    def advance_time(self, hours: int = 1) -> Dict[str, Any]:
        """推进时间，可能改变天气和光照。"""
        old_time = self.time.time_of_day
        self.time.advance(hours=hours)

        # 每天凌晨骰新天气
        if old_time != TimeOfDay.DAWN and self.time.time_of_day == TimeOfDay.DAWN:
            self._roll_weather()

        return self.get_environment()

    def get_environment(self) -> Dict[str, Any]:
        """获取当前环境状态。"""
        return {
            "time": self.time.to_dict(),
            "weather": self.weather.to_dict(),
            "light_level": "黑暗" if self.time.time_of_day in (TimeOfDay.NIGHT, TimeOfDay.MIDNIGHT) else
                          "昏暗" if self.time.time_of_day in (TimeOfDay.DAWN, TimeOfDay.DUSK) else "明亮",
        }

    def get_nearby_area_descriptions(self, location_id: str) -> List[str]:
        """获取附近区域的描述。"""
        loc = self.get_location(location_id)
        if not loc:
            return []

        descs = []
        for area in self.areas.values():
            for area_loc in area.locations:
                if area_loc.id != location_id and not area_loc.is_discovered:
                    dist = abs(area_loc.x - loc.x) + abs(area_loc.y - loc.y)
                    if dist <= 3:  # 附近
                        direction = self._get_direction(loc.x, loc.y, area_loc.x, area_loc.y)
                        descs.append(f"{direction}方向似乎有{'些' if dist > 1 else '着'}{area_loc.name}的踪迹")

        return descs

    @staticmethod
    def _get_direction(x1: int, y1: int, x2: int, y2: int) -> str:
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) > abs(dy):
            return "东" if dx > 0 else "西"
        elif abs(dy) > abs(dx):
            return "北" if dy > 0 else "南"
        else:
            return "东北" if dx > 0 and dy > 0 else \
                   "西北" if dx < 0 and dy > 0 else \
                   "东南" if dx > 0 and dy < 0 else "西南"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "areas": {k: v.to_dict() for k, v in self.areas.items()},
            "time": self.time.to_dict(),
            "weather": self.weather.to_dict(),
            "environment": self.get_environment(),
        }
