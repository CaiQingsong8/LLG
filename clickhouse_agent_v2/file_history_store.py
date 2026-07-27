"""聊天记录持久化：本地 JSON 文件 + ClickHouse 兜底。"""
import os
import json
import logging
import re
from datetime import datetime
from typing import Any

from database import get_ck

logger = logging.getLogger("chat_store")


def save_message(
    role: str,
    content: str,
    user_id: str,
    conversation_id: str,
    storage_dir: str,
    rag_manager=None,
):
    """保存单条消息。先写本地文件，再尝试写 ClickHouse，最后记录到 RAG。"""
    os.makedirs(storage_dir, exist_ok=True)
    fpath = os.path.join(storage_dir, f"{user_id}.json")

    # --- 本地文件 ---
    try:
        history = []
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                history = json.load(f)
        history.append({
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": datetime.now().isoformat(),
        })
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("本地保存失败: %s", e)

    # --- ClickHouse ---
    try:
        ck = get_ck()
        if ck:
            ck.insert(
                "alphafeed.agent_chat_history",
                [[f"{user_id}:{conversation_id}", role, content]],
                column_names=["session_id", "role", "content"],
            )
    except Exception as e:
        if "ACCESS_DENIED" not in str(e):
            logger.warning("CK 保存失败: %s", e)

    # --- RAG 记录（仅用户提问）---
    if role == "user" and rag_manager:
        try:
            clean = re.sub(r"【.*?】", "", content).strip()
            if clean:
                rag_manager.add_question(clean, {"user_id": user_id})
        except Exception as e:
            logger.warning("RAG 记录失败: %s", e)


def load_conversation(user_id: str, conversation_id: str, storage_dir: str) -> list[dict]:
    """从本地文件加载某会话的全部消息。"""
    fpath = os.path.join(storage_dir, f"{user_id}.json")
    try:
        if not os.path.exists(fpath):
            return []
        with open(fpath, encoding="utf-8") as f:
            history = json.load(f)
        msgs = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item.get("conversation_id") == conversation_id
        ]
        return msgs
    except Exception as e:
        logger.warning("加载会话失败: %s", e)
        return []


def list_conversations(user_id: str, storage_dir: str, max_count: int = 20) -> list[tuple]:
    """列出用户的所有历史会话 (conversation_id, started_at, first_msg)。"""
    fpath = os.path.join(storage_dir, f"{user_id}.json")
    try:
        if not os.path.exists(fpath):
            return []
        with open(fpath, encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        logger.warning("列会话失败: %s", e)
        return []

    convs: dict[str, dict] = {}
    for item in history:
        cid = item.get("conversation_id")
        if not cid:
            continue
        if cid not in convs:
            convs[cid] = {"started_at": None, "first_msg": ""}
        started = item.get("created_at")
        if started and (convs[cid]["started_at"] is None or started < convs[cid]["started_at"]):
            convs[cid]["started_at"] = started
        if item.get("role") == "user" and not convs[cid]["first_msg"]:
            msg = item.get("content", "")
            msg = re.sub(r"【.*?】", "", msg).strip()
            convs[cid]["first_msg"] = msg[:30]

    sorted_items = sorted(
        convs.items(),
        key=lambda x: x[1].get("started_at", "") or "",
        reverse=True,
    )
    return [
        (cid, v["started_at"] or "", v["first_msg"] or "(空)")
        for cid, v in sorted_items[:max_count]
    ]


def delete_conversation(user_id: str, conversation_id: str, storage_dir: str):
    """删除某条会话（本地文件 + 尝试 CK）。"""
    fpath = os.path.join(storage_dir, f"{user_id}.json")
    try:
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                history = json.load(f)
            history = [h for h in history if h.get("conversation_id") != conversation_id]
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("本地删除失败: %s", e)

    try:
        ck = get_ck()
        if ck:
            ck.command(
                f"ALTER TABLE alphafeed.agent_chat_history DELETE WHERE session_id = '{user_id}:{conversation_id}'"
            )
    except Exception:
        pass  # CK 可能无权限


# ---------- 用户偏好 ----------

def save_prefs(user_id: str, prefs: dict, storage_dir: str):
    try:
        os.makedirs(storage_dir, exist_ok=True)
        with open(os.path.join(storage_dir, f"{user_id}.json"), "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("保存偏好失败: %s", e)


def load_prefs(user_id: str, storage_dir: str) -> dict:
    try:
        fpath = os.path.join(storage_dir, f"{user_id}.json")
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("加载偏好失败: %s", e)
    return {}
