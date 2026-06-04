# -*- coding: utf-8 -*-
"""
Streamlit Frontend — AI 文本跑团交互面板。

提供完整的跑团游戏 UI：
- 左侧：角色卡（头像、属性、装备、状态）
- 中间：主剧情窗口（聊天风格，AI DM 消息+玩家操作）
- 右侧：战斗面板、背包、地图
- 底部：操作输入框（文字指令）
- 骰子动画效果

Usage:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# 尝试导入后端引擎（在完整项目中）
try:
    from backend.engine.game_master import GameMaster, DiceRoller
    from backend.engine.character import Character, Stat, Stats
    from backend.engine.combat import CombatEngine, EnemyInstance
    from backend.engine.world import WorldManager, AreaType, WeatherType
    from backend.engine.story_generator import StoryGenerator, QuestManager, Quest
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False
    # 回退：定义最小接口
    class GameMaster:
        pass


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Text RPG — 文本跑团",
    page_icon="🎲",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS 自定义
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #16213e 100%);
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid;
    }
    .dm-message {
        background: rgba(30, 30, 60, 0.8);
        border-left-color: #ffd700;
        color: #e0e0e0;
    }
    .player-message {
        background: rgba(40, 80, 120, 0.5);
        border-left-color: #4fc3f7;
        color: #b0e0e0;
    }
    .system-message {
        background: rgba(20, 40, 20, 0.5);
        border-left-color: #66bb6a;
        color: #a5d6a7;
    }
    .combat-message {
        background: rgba(80, 20, 20, 0.5);
        border-left-color: #ef5350;
        color: #ef9a9a;
    }
    .stat-box {
        background: rgba(30, 30, 60, 0.6);
        border-radius: 0.5rem;
        padding: 0.5rem;
        margin: 0.25rem 0;
        text-align: center;
    }
    .stat-label {
        font-size: 0.7rem;
        color: #aaa;
        text-transform: uppercase;
    }
    .stat-value {
        font-size: 1.2rem;
        font-weight: bold;
        color: #ffd700;
    }
    .stat-mod {
        font-size: 0.9rem;
        color: #4fc3f7;
    }
    h1, h2, h3 {
        color: #ffd700 !important;
    }
    .dice-animation {
        font-size: 2rem;
        text-align: center;
        animation: dice-roll 0.5s ease-in-out;
    }
    @keyframes dice-roll {
        0% { transform: rotate(0deg); }
        25% { transform: rotate(90deg); }
        50% { transform: rotate(180deg); }
        75% { transform: rotate(270deg); }
        100% { transform: rotate(360deg); }
    }
    .stButton button {
        background: linear-gradient(135deg, #ffd700, #ff8c00) !important;
        color: #1a1a2e !important;
        font-weight: bold !important;
        border: none !important;
    }
    .stButton button:hover {
        background: linear-gradient(135deg, #ffe44d, #ffa726) !important;
    }
    div[data-testid="stSidebar"] {
        background: rgba(15, 15, 35, 0.95);
        border-right: 1px solid rgba(255, 215, 0, 0.2);
    }
    .health-bar {
        background: linear-gradient(90deg, #ef5350, #ff7043);
        height: 8px;
        border-radius: 4px;
        transition: width 0.5s;
    }
    .xp-bar {
        background: linear-gradient(90deg, #42a5f5, #ab47bc);
        height: 4px;
        border-radius: 2px;
    }
    .combat-badge {
        background: #ef5350;
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
        animation: pulse 1s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session State 初始化
# ---------------------------------------------------------------------------

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.gm = GameMaster() if BACKEND_AVAILABLE else None
    st.session_state.session_id = None
    st.session_state.game_started = False
    st.session_state.current_scene = None
    st.session_state.messages = []
    st.session_state.in_combat = False
    st.session_state.character_data = None
    st.session_state.enemies = None
    st.session_state.combat_state = None

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def add_message(role: str, content: str, msg_type: str = "dm"):
    """添加聊天消息。"""
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "type": msg_type,
    })


def roll_dice_animation(dice_str: str) -> None:
    """显示骰子动画。"""
    if st.session_state.gm:
        result = st.session_state.gm.roll_dice(dice_str)
        dice_text = f"🎲 {dice_str}: [{', '.join(str(r) for r in result.get('results', []))}] = **{result.get('total', 0)}**"
        add_message("系统", dice_text, "system")
        return result
    return None


def render_stat_bar(stat_name: str, value: int, modifier: int) -> str:
    """渲染属性��� HTML。"""
    sign = "+" if modifier >= 0 else ""
    return f"""
    <div class="stat-box">
        <div class="stat-label">{stat_name}</div>
        <div class="stat-value">{value}</div>
        <div class="stat-mod">({sign}{modifier})</div>
    </div>
    """


def render_health_bar(current: int, maximum: int) -> str:
    """渲染生命条 HTML。"""
    pct = min(100, max(0, int(current / maximum * 100))) if maximum > 0 else 0
    color = "#4caf50" if pct > 60 else "#ff9800" if pct > 30 else "#f44336"
    return f"""
    <div style="margin: 0.5rem 0;">
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem;">
            <span>❤️ HP</span>
            <span>{current}/{maximum}</span>
        </div>
        <div style="background: #333; height: 10px; border-radius: 5px; overflow: hidden;">
            <div style="background: {color}; width: {pct}%; height: 100%; border-radius: 5px;
                        transition: width 0.5s ease;"></div>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Sidebar — Character Card
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🦐 AI Text RPG")
    st.markdown("---")

    if not st.session_state.game_started:
        st.markdown("### 创建角色")

        char_name = st.text_input("角色名", value="英雄", key="char_name")
        col1, col2 = st.columns(2)
        with col1:
            race_options = {
                "human": "人类", "elf": "精灵", "dwarf": "矮人",
                "orc": "兽人", "dragonborn": "龙裔",
            }
            race_id = st.selectbox("种族", options=list(race_options.keys()),
                                   format_func=lambda x: race_options.get(x, x), key="race_sel")
        with col2:
            class_options = {
                "fighter": "战士", "wizard": "法师", "ranger": "游侠",
                "rogue": "盗贼", "cleric": "牧师", "monk": "武僧",
            }
            class_id = st.selectbox("职业", options=list(class_options.keys()),
                                    format_func=lambda x: class_options.get(x, x), key="class_sel")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🎮 开始新游戏", use_container_width=True):
                if st.session_state.gm:
                    # 创建会话
                    session = st.session_state.gm.create_session()
                    st.session_state.session_id = session.id

                    # 创建角色并加入队伍
                    char = st.session_state.gm.create_character(char_name, race_id, class_id)
                    st.session_state.gm.join_party(session.id, char)
                    st.session_state.character_data = char.to_dict()

                    # 开始游戏
                    result = st.session_state.gm.start_game(session.id, "tutorial")
                    if result.get("success"):
                        st.session_state.game_started = True

                        add_message("系统",
                                    f"🎮 欢迎来到 **{result.get('scenario_name', '冒险之旅')}**！\n\n"
                                    f"{result.get('scenario_description', '')}",
                                    "system")

                        scene = result.get("scene", {})
                        st.session_state.current_scene = scene
                        add_message("DM", f"**📍 {scene.get('title', '')}**\n\n{scene.get('description', '')}", "dm")

                        choices = result.get("choices", [])
                        if choices:
                            choice_text = "**📋 你可以：**\n" + "\n".join(
                                f"{i+1}. {c['text']}" for i, c in enumerate(choices)
                            )
                            add_message("系统", choice_text, "system")

                        st.rerun()
                    else:
                        add_message("系统", f"❌ 游戏启动失败: {result}", "system")
                        st.rerun()

        with col2:
            if st.button("🔗 读档", use_container_width=True):
                st.info("读档功能将在后续版本实现。")

    else:
        # 角色卡
        cd = st.session_state.character_data
        if cd:
            st.markdown(f"### {cd.get('name', '英雄')}")
            st.markdown(f"**{cd.get('race_name', '')} {cd.get('class_name', '')}** · Lv.{cd.get('level', 1)}")

            # 生命值
            render_health_bar(cd.get("current_hp", 0), cd.get("max_hp", 1))
            st.markdown(f"<div class='xp-bar' style='width:{min(100, cd.get('xp', 0) / max(1, cd.get('xp_to_next', 300)) * 100)}%'></div>", unsafe_allow_html=True)
            st.caption(f"EXP: {cd.get('xp', 0)} / {cd.get('xp_to_next', 'MAX')}")

            st.markdown("---")
            st.markdown("#### 属性")
            stats = cd.get("stats", {})
            mods = cd.get("modifiers", {})

            stat_names_cn = {
                "strength": "力量", "dexterity": "敏捷", "constitution": "体质",
                "intelligence": "智力", "wisdom": "感知", "charisma": "魅力",
            }

            cols = st.columns(3)
            for i, (stat_key, stat_val) in enumerate(stats.items()):
                with cols[i % 3]:
                    st.markdown(render_stat_bar(
                        stat_names_cn.get(stat_key, stat_key),
                        stat_val,
                        mods.get(stat_key, 0),
                    ), unsafe_allow_html=True)

            st.markdown("---")
            st.markdown(f"**⚔️ 攻击加值:** +{cd.get('attack_bonus', 0)}")
            st.markdown(f"**🛡️ 护甲等级:** {cd.get('armor_class', 10)}")

            # 背包
            inv = cd.get("inventory", {})
            if inv.get("items"):
                st.markdown("---")
                st.markdown("#### 🎒 背包")
                for item in inv["items"]:
                    st.markdown(f"- {item.get('name', '?')} x{item.get('quantity', 1)}")
            st.markdown(f"💰 **金币:** {inv.get('gold', 0)}")

    st.markdown("---")
    st.caption("🎲 AI 文本跑团游戏引擎 v1.0")


# ---------------------------------------------------------------------------
# Main — Chat Area
# ---------------------------------------------------------------------------

col_main, col_right = st.columns([2.5, 1])

with col_main:
    st.markdown("## 📜 故事")
    st.markdown("---")

    # Chat messages
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages[-30:]:
            msg_type = msg.get("type", "dm")
            css_class = f"chat-message {msg_type}-message"
            st.markdown(f"""<div class="{css_class}">{msg['content']}</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # 战斗提示
    if st.session_state.in_combat:
        st.markdown("<div class='combat-badge'>⚔️ 战斗中!</div>", unsafe_allow_html=True)

    # 快捷操作按钮
    if st.session_state.game_started and not st.session_state.in_combat:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if st.button("⬆️ 前进", use_container_width=True):
                _process_interaction("前进")
        with col2:
            if st.button("🗺️ 地图", use_container_width=True):
                _process_interaction("地图")
        with col3:
            if st.button("🎒 背包", use_container_width=True):
                _process_interaction("查看背包")
        with col4:
            if st.button("💤 休息", use_container_width=True):
                _process_interaction("休息")
        with col5:
            if st.button("🔍 探索", use_container_width=True):
                _process_interaction("探索")

    # 战斗快捷键
    if st.session_state.in_combat:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("⚔️ 攻击", use_container_width=True, type="primary"):
                _process_combat_action("attack")
        with col2:
            if st.button("🛡️ 防御", use_container_width=True):
                _process_combat_action("dodge")
        with col3:
            if st.button("🏃 逃离", use_container_width=True):
                _process_combat_action("flee")
        with col4:
            if st.button("💚 治疗药水", use_container_width=True):
                _process_combat_action("use", item_id="healing_potion")

    # 故事选项
    if st.session_state.get("current_choices"):
        st.markdown("#### 📋 选项")
        for i, choice in enumerate(st.session_state.current_choices):
            if st.button(f"{i+1}. {choice.get('text', '')}", use_container_width=True):
                _process_interaction(f"choice_{i}")

    # 自由输入
    user_input = st.chat_input("输入你的行动... (比如：前进、攻击哥布林、检视房间)")
    if user_input:
        if st.session_state.in_combat:
            _process_combat_action(user_input)
        else:
            _process_interaction(user_input)


# ---------------------------------------------------------------------------
# Right Panel — Combat / Map / Info
# ---------------------------------------------------------------------------

with col_right:
    st.markdown("## 📊 信息面板")
    st.markdown("---")

    # 环境信息
    if st.session_state.game_started and st.session_state.gm:
        session = st.session_state.gm.get_session(st.session_state.session_id)
        if session:
            env = session.world.get_environment()
            st.markdown(f"**⏰ {env['time']['formatted']}**")
            st.markdown(f"**🌤️ {env['weather']['type']}** ({env['weather']['temperature']})")
            st.markdown(f"**☀️ 光照:** {env['light_level']}")

    st.markdown("---")

    # 战斗面板
    if st.session_state.in_combat and st.session_state.get("enemies"):
        st.markdown("### ⚔️ 敌人")
        for enemy in st.session_state.enemies:
            if enemy.get("is_alive"):
                hp_pct = max(0, enemy.get("current_hp", 0) / max(1, enemy.get("max_hp", 1)) * 100)
                st.markdown(f"""
                <div style="background: rgba(60,20,20,0.6); border-radius: 0.3rem; padding: 0.5rem; margin: 0.25rem 0;">
                    <div style="font-weight: bold;">{enemy.get('name', '?')}</div>
                    <div style="background: #333; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: #ef5350; width: {hp_pct}%; height: 100%;"></div>
                    </div>
                    <div style="font-size: 0.7rem; color: #aaa;">
                        HP: {enemy.get('current_hp', 0)}/{enemy.get('max_hp', 0)} | AC: {enemy.get('armor_class', 10)}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # 地图
    if st.session_state.game_started:
        st.markdown("---")
        st.markdown("### 🗺️ 区域")
        session = st.session_state.gm.get_session(st.session_state.session_id) if st.session_state.gm else None
        if session:
            for area in session.world.areas.values():
                progress = area.get_discovery_progress()
                st.markdown(f"**{area.name}** ({area.area_type.value})")
                st.markdown(f"<div style='background: #333; height: 4px; border-radius: 2px; overflow: hidden;'>"
                           f"<div style='background: #66bb6a; width: {progress * 100}%; height: 100%;'></div></div>",
                           unsafe_allow_html=True)

    # 任务
    if st.session_state.game_started and hasattr(st.session_state, 'gm') and st.session_state.gm:
        session = st.session_state.gm.get_session(st.session_state.session_id)
        if session:
            active_quests = session.story.quest_manager.get_active_quests()
            if active_quests:
                st.markdown("---")
                st.markdown("### 📜 任务")
                for quest in active_quests:
                    st.markdown(f"**{quest.name}**")
                    for obj in quest.objectives:
                        st.markdown(f"- {'✅' if obj.is_completed else '⬜'} {obj.description}")

    st.markdown("---")
    st.caption("🔗 [GitHub](https://github.com/c50346867/ai-text-rpg)")


# ---------------------------------------------------------------------------
# Action Processing Functions
# ---------------------------------------------------------------------------

def _process_interaction(action: str):
    """处理探索交互。"""
    if not st.session_state.gm or not st.session_state.session_id:
        return

    # 如果选择了故事选项
    if action.startswith("choice_"):
        pass  # 直接发送

    add_message("玩家", f"> {action}", "player")

    result = st.session_state.gm.process_action(st.session_state.session_id, action)
    _handle_action_result(result)


def _process_combat_action(action: str, **kwargs):
    """处理战斗交互。"""
    if not st.session_state.gm or not st.session_state.session_id:
        return

    add_message("玩��", f"> ⚔️ {action}", "player")

    result = st.session_state.gm.process_action(st.session_state.session_id, action, **kwargs)
    _handle_combat_result(result)


def _handle_action_result(result: Dict[str, Any]):
    """处理行动结果。"""
    if "error" in result:
        add_message("系统", f"❌ {result['error']}", "system")
        st.rerun()
        return

    # 显示消息
    for msg in result.get("messages", []):
        add_message("DM", msg, "dm")

    # 处理战斗开始
    if result.get("combat_started"):
        st.session_state.in_combat = True
        st.session_state.enemies = result.get("enemies", [])
        st.session_state.combat_state = result.get("combat_state")
        add_message("系统", "⚔️ **战斗开始！**", "system")

    # 处理战斗胜利
    if result.get("victory"):
        st.session_state.in_combat = False
        st.session_state.enemies = None
        add_message("系统", "🎉 **战斗胜利！**", "system")

    # 更新场景
    if result.get("scene"):
        scene = result["scene"]
        st.session_state.current_scene = scene

    # 更新选项
    if result.get("choices"):
        st.session_state.current_choices = result["choices"]
    else:
        st.session_state.current_choices = None

    # 更新角色
    if result.get("character_dump"):
        st.session_state.character_data = result["character_dump"]

    # 更新队伍
    if result.get("party"):
        if st.session_state.character_data and result["party"]:
            st.session_state.character_data = result["party"][0]

    # 更新环境
    if result.get("environment"):
        pass  # side panel reads from world

    st.rerun()


def _handle_combat_result(result: Dict[str, Any]):
    """处理战斗结果。"""
    for msg in result.get("messages", []):
        add_message("战斗", msg, "combat")

    if result.get("victory"):
        st.session_state.in_combat = False
        st.session_state.enemies = None
        add_message("系统", "🎉 **战斗胜利！**", "system")

    if result.get("fled"):
        st.session_state.in_combat = False
        st.session_state.enemies = None
        add_message("系统", "🏃 你成功逃离了战斗!", "system")

    if result.get("defeat"):
        st.session_state.in_combat = False
        st.session_state.enemies = None
        add_message("系统", "💀 **队伍全灭...** 游戏结束。", "system")

    if result.get("combat_state"):
        state = result["combat_state"]
        st.session_state.combat_state = state
        st.session_state.enemies = state.get("enemies", [])
        if state.get("party"):
            st.session_state.character_data = state["party"][0]

    st.rerun()


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption("AI Text RPG — 基于 LLM 的 AI 文本跑团游戏引擎 | MIT License")
