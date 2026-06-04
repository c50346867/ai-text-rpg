#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Start — AI Text RPG 快速开始示例。

演示如何快速上手 AI 文本跑团游戏引擎。

Usage:
    python examples/quick_start.py
"""

from __future__ import annotations

import sys
import time
sys.path.insert(0, ".")

from backend.engine.game_master import GameMaster, DiceRoller


def main():
    """快速开始示例。"""
    print("=" * 60)
    print("🎲 AI Text RPG — 快速开始示例")
    print("=" * 60)

    # 1. 创建 Game Master
    print("\n📦 创建 Game Master 实例...")
    gm = GameMaster(use_simulated_llm=True)

    # 2. 创建游戏会话
    print("🎮 创建游戏会话...")
    session = gm.create_session("quick_start_demo")

    # 3. 创建角色
    print("👤 创建角色...")
    char = gm.create_character("亚瑟", "human", "fighter")
    gm.join_party(session.id, char)
    print(f"   - {char.name} (Lv.{char.level} {char._class_data.get('name', '')})")
    print(f"   - HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    print(f"   - 力量: {char.stats.get(Stat.STRENGTH)} ({char.stats.modifier(Stat.STRENGTH):+d})")
    print(f"   - 敏捷: {char.stats.get(Stat.DEXTERITY)} ({char.stats.modifier(Stat.DEXTERITY):+d})")

    # 4. 开始游戏
    print("\n📖 开始游戏...")
    result = gm.start_game(session.id, "tutorial")
    if result.get("success"):
        print(f"   剧本: {result.get('scenario_name', '')}")
        print(f"   场景: {result.get('scene', {}).get('title', '')}")
        print(f"   描述: {result.get('scene', {}).get('description', '')[:80]}...")

    # 5. 演示骰子
    print("\n🎲 骰子演示:")
    for dice_expr in ["1d20", "2d6", "3d8+2", "1d100"]:
        roll = gm.roll_dice(dice_expr)
        print(f"   {dice_expr}: [{', '.join(str(r) for r in roll['results'])}] = {roll['total']}")

    # 6. 演示属性检定
    print("\n📋 属性检定演示:")
    check = gm.perform_skill_check(char, "力量", dc=12)
    print(f"   {check.get('narrative', '')}")

    check = gm.perform_skill_check(char, "感知", dc=15)
    print(f"   {check.get('narrative', '')}")

    # 7. 演示行动
    print("\n🎯 行动演示:")
    for action in ["查看角色", "天气", "地图"]:
        print(f"\n   行动: {action}")
        result = gm.process_action(session.id, action)
        for msg in result.get("messages", [])[:2]:
            print(f"   > {msg[:70]}...")

    # 8. 展示状态
    print("\n" + "=" * 60)
    print(f"📊 最终状态:")
    print(f"   角色: {char.name} (Lv.{char.level})")
    print(f"   HP: {char.current_hp}/{char.max_hp}")
    print(f"   金币: {char.inventory.gold}")
    print(f"   背包物品数: {len(char.inventory.items)}")
    print(f"   日志条数: {len(session.log)}")
    print("=" * 60)
    print("\n✅ 快速开始示例完成！")
    print("💡 运行前端: streamlit run frontend/app.py")
    print("💡 启动 API: uvicorn backend.api.main:app --reload")


if __name__ == "__main__":
    # 在模块级别导入 Stat
    from backend.engine.character import Stat
    main()
