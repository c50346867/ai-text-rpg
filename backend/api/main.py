# -*- coding: utf-8 -*-
"""
FastAPI REST API — AI 文本跑团游戏后端 API。

提供游戏会话管理、角色操作、行动处理、战斗交互等 RESTful 接口。

Usage:
    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.engine.game_master import GameMaster, GameSession
from backend.engine.character import Character, Stats


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Text RPG API",
    description="AI 驱动的文本跑团游戏引擎 REST API",
    version="1.0.0",
)

# CORS — 允许 Streamlit 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Game Master 全局实例
gm = GameMaster(use_simulated_llm=True)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    session_id: Optional[str] = None


class CreateCharacterRequest(BaseModel):
    name: str = "英雄"
    race_id: str = "human"
    class_id: str = "fighter"


class StartGameRequest(BaseModel):
    session_id: str
    scenario_id: str = "tutorial"


class ActionRequest(BaseModel):
    session_id: str
    action: str
    target: Optional[str] = None
    skill: Optional[str] = None
    dc: Optional[int] = 12
    spell_name: Optional[str] = None
    item_id: Optional[str] = None


class RollDiceRequest(BaseModel):
    dice: str = "1d20"


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    """API 根路径 — 健康检查。"""
    return {
        "name": "AI Text RPG Engine",
        "version": "1.0.0",
        "status": "running",
        "sessions": len(gm.sessions),
    }


@app.get("/health")
def health_check():
    """健康检查端点。"""
    return {"status": "healthy", "message": "AI Text RPG 引擎运行正常"}


# ---------------------------------------------------------------------------
# Routes — Sessions
# ---------------------------------------------------------------------------

@app.post("/sessions")
def create_session(req: CreateSessionRequest):
    """创建新游戏会话。"""
    session = gm.create_session(req.session_id)
    return {
        "success": True,
        "session_id": session.id,
        "message": f"会话 {session.id} 已创建",
    }


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """获取会话状态。"""
    session = gm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.to_dict()


@app.get("/sessions")
def list_sessions():
    """列出所有会话。"""
    return {
        "sessions": list(gm.sessions.keys()),
        "total": len(gm.sessions),
    }


# ---------------------------------------------------------------------------
# Routes — Characters
# ---------------------------------------------------------------------------

@app.post("/characters")
def create_character(req: CreateCharacterRequest):
    """创建游戏角色。"""
    char = gm.create_character(req.name, req.race_id, req.class_id)
    return {"success": True, "character": char.to_dict()}


@app.post("/sessions/{session_id}/join")
def join_party(session_id: str, req: CreateCharacterRequest):
    """加入队伍。"""
    session = gm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    char = gm.create_character(req.name, req.race_id, req.class_id)
    gm.join_party(session_id, char)
    return {
        "success": True,
        "message": f"{char.name} 加入了队伍",
        "character": char.to_dict(),
        "party_size": len(session.characters),
    }


# ---------------------------------------------------------------------------
# Routes — Game Actions
# ---------------------------------------------------------------------------

@app.post("/game/start")
def start_game(req: StartGameRequest):
    """开始游戏。"""
    session = gm.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not session.characters:
        raise HTTPException(status_code=400, detail="队伍中还没有角色，请先加入角色")

    result = gm.start_game(req.session_id, req.scenario_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/game/action")
def process_action(req: ActionRequest):
    """处理玩家行动。"""
    session = gm.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    kwargs = {}
    if req.target:
        kwargs["target"] = req.target
    if req.skill:
        kwargs["skill"] = req.skill
    if req.dc:
        kwargs["dc"] = req.dc
    if req.spell_name:
        kwargs["spell_name"] = req.spell_name
    if req.item_id:
        kwargs["item_id"] = req.item_id

    result = gm.process_action(req.session_id, req.action, **kwargs)
    return result


@app.post("/game/roll")
def roll_dice(req: RollDiceRequest):
    """投掷骰子。"""
    result = gm.roll_dice(req.dice)
    return result


@app.get("/game/{session_id}/state")
def get_game_state(session_id: str):
    """获取完整游戏状态。"""
    session = gm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.to_dict()


@app.get("/game/{session_id}/log")
def get_game_log(session_id: str, count: int = 20):
    """获取游戏日志。"""
    session = gm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"log": session.get_recent_log(count)}


# ---------------------------------------------------------------------------
# Routes — Data
# ---------------------------------------------------------------------------

@app.get("/data/races")
def list_races():
    """获取所有种族定义。"""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "data" / "races.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/data/classes")
def list_classes():
    """获取所有职业定义。"""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "data" / "classes.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/data/monsters")
def list_monsters():
    """获取所有怪物定义。"""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "data" / "monsters.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/data/items")
def list_items():
    """获取所有物品定义。"""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "data" / "items.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/data/scenarios")
def list_scenarios():
    """获取可用剧本列表。"""
    from backend.engine.story_generator import ScenarioLoader
    loader = ScenarioLoader()
    return {"scenarios": loader.list_scenarios()}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
