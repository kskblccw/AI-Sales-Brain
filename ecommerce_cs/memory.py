"""
memory.py — 分层记忆系统

三层架构：
  1. 滑动窗口（Short-Term）：最近 6 条消息原样保留
  2. 摘要压缩（Summary）：超出窗口的历史 → LLM 压缩为情景摘要，拼入后续对话
  3. 用户画像（Profile）：抽取偏好/事实，< 300 tokens，含 last_active_time + weight

存储：
  - 摘要和画像存入 PostgreSQL user_profiles 表
  - 画像按 user_id（手机号 hash）隔离
  - LangGraph State 中携带 summary / profile_json 字段
"""

import json
import time
from datetime import datetime
from typing import Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import make_llm
from database import SyncSessionFactory

llm = make_llm(temperature=0.2)

# ═══════════════════════════════════════════════════════════════════════════════
# 用户画像存储
# ═══════════════════════════════════════════════════════════════════════════════
PROFILE_TOKEN_LIMIT = 300  # 用户画像上限 token


def _user_id_from_phone(phone: str) -> str:
    """手机号 → user_id（简单 hash 避免明文）"""
    import hashlib
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


def _ensure_profile_table():
    """建表（幂等）—— 延迟到首次调用时执行，避免 import 时阻塞"""
    from sqlalchemy import text
    with SyncSessionFactory() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id VARCHAR(32) PRIMARY KEY,
                preferences JSONB DEFAULT '[]',
                facts JSONB DEFAULT '{}',
                summary TEXT DEFAULT '',
                last_active_time TIMESTAMP DEFAULT NOW(),
                weight REAL DEFAULT 1.0,
                total_tokens INTEGER DEFAULT 0
            )
        """))
        db.commit()


_profile_table_ensured = False


def _ensure_profile_table_once():
    """延迟 + 幂等建表：首次调用时执行，后续跳过"""
    global _profile_table_ensured
    if not _profile_table_ensured:
        _ensure_profile_table()
        _profile_table_ensured = True


def load_profile(user_id: str) -> dict:
    """加载用户画像"""
    _ensure_profile_table_once()
    from sqlalchemy import text
    with SyncSessionFactory() as db:
        row = db.execute(
            text("SELECT preferences, facts, summary, last_active_time, weight, total_tokens "
            "FROM user_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()

    if not row:
        return {
            "preferences": [], "facts": {},
            "summary": "", "last_active_time": None, "weight": 1.0, "total_tokens": 0,
        }

    return {
        "preferences": row[0] or [],
        "facts": row[1] or {},
        "summary": row[2] or "",
        "last_active_time": row[3].isoformat() if row[3] else None,
        "weight": float(row[4] or 1.0),
        "total_tokens": int(row[5] or 0),
    }


def save_profile(user_id: str, profile: dict):
    """保存用户画像"""
    _ensure_profile_table_once()
    from sqlalchemy import text
    with SyncSessionFactory() as db:
        db.execute(text(
            """INSERT INTO user_profiles (user_id, preferences, facts, summary, last_active_time, weight, total_tokens)
               VALUES (:uid, :prefs, :facts, :summary, :active_time, :weight, :tokens)
               ON CONFLICT (user_id) DO UPDATE SET
               preferences=EXCLUDED.preferences, facts=EXCLUDED.facts,
               summary=EXCLUDED.summary, last_active_time=EXCLUDED.last_active_time,
               weight=EXCLUDED.weight, total_tokens=EXCLUDED.total_tokens"""
        ), {
            "uid": user_id,
            "prefs": json.dumps(profile.get("preferences", []), ensure_ascii=False),
            "facts": json.dumps(profile.get("facts", {}), ensure_ascii=False),
            "summary": profile.get("summary", ""),
            "active_time": profile.get("last_active_time", datetime.now()),
            "weight": profile.get("weight", 1.0),
            "tokens": profile.get("total_tokens", 0),
        })
        db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 用户画像抽取
# ═══════════════════════════════════════════════════════════════════════════════
EXTRACT_PROFILE_PROMPT = """你是用户画像分析器。从对话中提取用户信息，输出 JSON。

提取规则：
- preferences: 用户偏好列表（如"喜欢跑步""关注性价比""常用花呗"），只提取明确的
- facts: 用户事实字典（如{"城市":"北京","职业":"程序员","家庭成员":"有小孩"}），只提取明确提到的
- 保持简洁：preferences 最多 5 条，facts 最多 5 个键
- 不确定的不要编造

已有画像（更新前）：
{existing}

最近对话：
{dialog}

请输出 JSON（只输出 JSON，不要其他内容）：
{{"preferences": [...], "facts": {{...}}, "weight": 0.0~1.0}}"""


def extract_user_profile(user_id: str, conversation: list[BaseMessage]) -> dict:
    """从对话中抽取/更新用户画像"""
    existing = load_profile(user_id)
    existing_str = json.dumps({
        "preferences": existing["preferences"],
        "facts": existing["facts"],
        "weight": existing["weight"],
    }, ensure_ascii=False)

    # 只取最近的人类消息和 AI 关键回复
    dialog = "\n".join(
        f"[{'用户' if m.type == 'human' else 'AI'}] {str(m.content)[:200]}"
        for m in conversation if m.type in ("human", "ai")
    )[-1500:]

    # 用 replace 而非 format：JSON 中可能含大括号 {}
    prompt = EXTRACT_PROFILE_PROMPT.replace("{existing}", existing_str).replace("{dialog}", dialog)
    response = llm.invoke([HumanMessage(content=prompt)])

    try:
        content = response.content.strip()
        # 清理 markdown 代码块
        if "```" in content:
            parts = content.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("{"):
                    content = p
                    break
        # 只取第一个 { 到最后一个 } 之间的内容
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start:end + 1]
        result = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return existing

    # 合并：新偏好追加，旧偏好去重保留（最多 5 条），旧偏好保留但降低 weight
    old_prefs = existing.get("preferences", [])
    new_prefs = result.get("preferences", [])
    merged_prefs = list(dict.fromkeys(old_prefs[-3:] + new_prefs))[-5:]

    merged_facts = {**existing.get("facts", {}), **result.get("facts", {})}

    # 活跃用户 weight 上升，不活跃下降
    old_weight = existing.get("weight", 1.0)
    new_weight = float(result.get("weight", old_weight))

    profile = {
        "preferences": merged_prefs,
        "facts": merged_facts,
        "summary": existing.get("summary", ""),
        "last_active_time": datetime.now().isoformat(),
        "weight": round(old_weight * 0.7 + new_weight * 0.3, 3),  # EMA 平滑
        "total_tokens": existing.get("total_tokens", 0),
    }

    save_profile(user_id, profile)
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# 历史摘要压缩
# ═══════════════════════════════════════════════════════════════════════════════
COMPRESS_PROMPT = """你是对话摘要器。将以下历史对话压缩为一段情景摘要（中文，150字以内）。

要求：
- 保留关键情景：用户问了什么、做了什么操作、结果如何
- 保留重要信息：订单号、商品名、金额等具体数据
- 省略寒暄和重复内容
- 格式：一段连贯的文字，不需要编号或要点

已有摘要（如有）：
{existing_summary}

待压缩的历史对话：
{history}

请只输出压缩后的摘要文字："""


def compress_history(conversation: list[BaseMessage], existing_summary: str = "") -> str:
    """
    将超出滑动窗口的历史消息压缩为摘要

    输入: 完整的消息列表 + 已有摘要
    输出: 新的摘要文本
    """
    if not conversation:
        return existing_summary or ""

    # 只压缩 human 和 ai 消息
    history = "\n".join(
        f"[{'用户' if m.type == 'human' else 'AI'}] {str(m.content)[:300]}"
        for m in conversation if m.type in ("human", "ai")
    )

    if len(history) < 200:
        return existing_summary or history

    prompt = COMPRESS_PROMPT.replace(
        "{existing_summary}", f"（已有摘要）{existing_summary}" if existing_summary else "（无）"
    ).replace("{history}", history[-2000:])

    response = llm.invoke([HumanMessage(content=prompt)])
    new_summary = response.content.strip()
    return new_summary[:300]  # 硬截断


def compress_and_save(phone: str, messages: list[BaseMessage]) -> str:
    """
    后台异步压缩：压缩对话历史 + 抽取用户画像 → 存入 DB

    在后台线程中调用，不阻塞主流程。压缩结果存入 user_profiles 表，
    下次对话时 prepare_context_node 直接从 DB 读取。

    Args:
        phone: 用户手机号
        messages: 完整的消息列表

    Returns:
        新的摘要文本
    """
    user_id = _user_id_from_phone(phone)
    window = apply_sliding_window(messages, window_size=12)

    # 加载已有摘要
    profile = load_profile(user_id)
    old_summary = profile.get("summary", "")

    # 压缩历史
    new_summary = compress_history(window, old_summary)

    # 抽取用户画像（同时保存摘要到 DB）
    extract_user_profile(user_id, window)
    # 把摘要也持久化到 profile
    profile = load_profile(user_id)
    profile["summary"] = new_summary
    save_profile(user_id, profile)

    return new_summary


# ═══════════════════════════════════════════════════════════════════════════════
# 上下文构建器（给 Agent 的最终 context）
# ═══════════════════════════════════════════════════════════════════════════════
def build_context_injection(user_id: str, summary: str = "") -> str:
    """
    构建注入 System Prompt 的上下文块

    包含：
    - 历史摘要（优先用传入的 summary，否则从 DB 读取）
    - 用户画像（格式化为 <300 token）

    返回：拼入 prompt 的文本片段
    """
    parts = []

    # 用户画像（一次 DB 查询同时取摘要和画像）
    profile = load_profile(user_id)

    # 历史情景摘要：优先用传入的，否则从 DB 读取（后台压缩已存入）
    effective_summary = summary or profile.get("summary", "")
    if effective_summary:
        parts.append(f"【历史对话摘要】{effective_summary}")

    # 用户画像
    prefs = profile.get("preferences", [])
    facts = profile.get("facts", {})
    weight = profile.get("weight", 0)

    if prefs or facts:
        profile_lines = ["【用户画像】"]
        if prefs:
            profile_lines.append(f"偏好：{'、'.join(prefs)}")
        if facts:
            facts_str = "、".join(f"{k}:{v}" for k, v in facts.items())
            profile_lines.append(f"信息：{facts_str}")
        if weight > 0:
            profile_lines.append(f"活跃度：{weight:.2f}")
        parts.append("\n".join(profile_lines))

    injection = "\n\n".join(parts)

    # 硬截断到 ~300 token（中文约 1.5 字/token）
    if len(injection) > 450:
        injection = injection[:450] + "..."

    return injection


# ═══════════════════════════════════════════════════════════════════════════════
# 滑动窗口裁剪
# ═══════════════════════════════════════════════════════════════════════════════
def apply_sliding_window(messages: list[BaseMessage], window_size: int = 6) -> list[BaseMessage]:
    """
    滑动窗口裁剪：只保留最近 N 条 human/ai 消息

    返回裁剪后的消息列表
    """
    if len(messages) <= window_size:
        return messages
    return messages[-window_size:]
