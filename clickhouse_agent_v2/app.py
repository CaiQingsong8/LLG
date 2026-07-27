"""ClickHouse Agent v2 — 入口文件。"""
import uuid
import re
import logging
from datetime import datetime

import streamlit as st

# ---- 项目模块 ----
from config import settings
from database import (
    get_ck, ck_available,
    fetch_corp_hierarchy, fetch_material_hierarchy, fetch_customers,
)
from rag import RAGManager
from agent import build_agent, TOOLS
from agent_tools import inject_deps
from file_history_store import (
    save_message, load_conversation, list_conversations, delete_conversation,
    save_prefs, load_prefs,
)
from ui import (
render_user_login, render_sidebar, render_filter_tags,
render_suggestions,
)
from intent import classify
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# ==================== 初始化 ====================

st.set_page_config(page_title="澳华数智AI助手", layout="wide")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("app")

# ---------- 启动时校验 LLM 配置 ----------
if not settings.llm_api_key:
    st.error("⚠️ 未配置 LLM API 密钥（DS_API_KEY），请检查 .env 文件。")
    st.info(f"当前配置：\n- BASE_URL: {settings.llm_base_url}\n- MODEL: {settings.llm_model}")
    st.stop()

# ---------- 缓存：RAG + Agent ----------

@st.cache_resource
def init_rag():
    rm = RAGManager(persist_directory=settings.chroma_dir)
    rm.import_json_knowledge(settings.knowledge_path)
    inject_deps(rm)
    return rm

@st.cache_resource
def init_agent():
    return build_agent()

rag_manager = init_rag()
agent_executor = init_agent()

# ---------- 缓存：维表 ----------

@st.cache_data(ttl=3600)
def get_hierarchy(show_inactive: bool = False):
    ck = get_ck()
    if not ck:
        return {}, {}
    return fetch_corp_hierarchy(ck, include_inactive=show_inactive)

@st.cache_data(ttl=3600)
def get_materials(show_inactive: bool = False):
    ck = get_ck()
    if not ck:
        return {}, [], {}
    return fetch_material_hierarchy(ck, include_inactive=show_inactive)

# ---------- Session State ----------

for key, default in [
    ("conversation_id", str(uuid.uuid4())),
    ("messages", []),
    ("selected_corps", []),
    ("selected_clients", []),
    ("selected_mats", []),
    ("selected_date", datetime.now()),
    ("selected_dimensions", []),
    ("_show_inactive_corps", False),
    ("_show_inactive_mats", False),
    ("_show_inactive_clients", False),
    ("_pending_suggestion", None),
    ("last_sql", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# 维表缓存（需在 Session State 之后）
hierarchy, corp_id_map = get_hierarchy(st.session_state._show_inactive_corps)
mat_hierarchy, all_mats, mat_id_map = get_materials(st.session_state._show_inactive_mats)

# ==================== 用户身份 ====================

user_id = render_user_login()
if not user_id:
    st.stop()

# 加载偏好
if "prefs_loaded" not in st.session_state:
    prefs = load_prefs(user_id, settings.user_prefs_dir)
    if prefs:
        for k in ["selected_corps", "selected_date", "selected_clients", "selected_mats", "selected_dimensions"]:
            if k in prefs:
                setattr(st.session_state, k, prefs[k])
        for k in ["_show_inactive_corps", "_show_inactive_mats", "_show_inactive_clients"]:
            if k in prefs:
                setattr(st.session_state, k, prefs[k])
        if isinstance(st.session_state.selected_date, str):
            try:
                st.session_state.selected_date = datetime.fromisoformat(st.session_state.selected_date)
            except (ValueError, TypeError):
                pass
    st.session_state.prefs_loaded = True

def sync_prefs():
    save_prefs(user_id, {
        "selected_corps": st.session_state.selected_corps,
        "selected_date": st.session_state.selected_date.isoformat() if hasattr(st.session_state.selected_date, "isoformat") else str(st.session_state.selected_date),
        "selected_clients": st.session_state.selected_clients,
        "selected_mats": st.session_state.selected_mats,
        "selected_dimensions": st.session_state.selected_dimensions,
        "_show_inactive_corps": st.session_state._show_inactive_corps,
        "_show_inactive_mats": st.session_state._show_inactive_mats,
        "_show_inactive_clients": st.session_state._show_inactive_clients,
    }, settings.user_prefs_dir)

# 客户联动：根据已选公司获取客户列表
relevant_clients, client_id_map = fetch_customers(
    get_ck(), st.session_state.selected_corps,
    include_inactive=st.session_state._show_inactive_clients,
)
valid_client_ids = [str(c[0]) for c in relevant_clients]
if st.session_state.selected_clients:
    st.session_state.selected_clients = [c for c in st.session_state.selected_clients if c in valid_client_ids]

# ==================== 侧边栏 ====================

ck_ok = ck_available()


def _detect_filter_suggestions(query: str, corp_map: dict, mat_map: dict, client_map: dict) -> dict:
    """扫描用户问题，识别提到的公司/物料/客户名称，返回匹配的 ID。"""
    result = {}
    q = query.lower()

    # 优先匹配最长的名称
    for cid, name in corp_map.items():
        n = name.lower()
        if n and len(n) > 1 and n in q:
            # 确保是完整词匹配
            result.setdefault("corp_ids", []).append(cid)
            result["corp_id"] = cid
            result["corp_name"] = name
            break  # 只取第一个匹配

    for mid, name in mat_map.items():
        n = name.lower().split(" (")[0]  # 去掉编码部分
        if n and len(n) > 1 and n in q:
            result.setdefault("mat_ids", []).append(mid)
            result["mat_id"] = mid
            result["mat_name"] = name
            break

    for clid, name in client_map.items():
        n = name.lower().split(" (")[0]
        if n and len(n) > 1 and n in q:
            result.setdefault("client_ids", []).append(clid)
            result["client_id"] = clid
            result["client_name"] = name
            break

    return result

def load_conv(conv_id: str):
    st.session_state.conversation_id = conv_id
    st.session_state.messages = load_conversation(user_id, conv_id, settings.chat_history_dir)

def delete_current_conv():
    delete_conversation(user_id, st.session_state.conversation_id, settings.chat_history_dir)
    st.session_state.messages = []
    st.session_state.conversation_id = str(uuid.uuid4())

conversations = list_conversations(user_id, settings.chat_history_dir)
render_sidebar(
    hierarchy, corp_id_map, mat_hierarchy, all_mats, mat_id_map,
    user_id, conversations, load_conv, delete_current_conv, ck_ok,
    client_ids=valid_client_ids, client_map=client_id_map,
)

# ==================== 主聊天区域 ====================

st.title("🚀 澳华数智AI助手")

if not st.session_state.messages:
    st.markdown(f"### 🎯 欢迎回来，{user_id}！")
    st.info("💡 筛选条件可在左侧设置，Agent 会自动识别并使用。直接问数据问题即可。")

# ---------- 显示历史消息 ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if content.count("\n") > 60:
            lines = content.split("\n")
            st.markdown("\n".join(lines[:60]))
            with st.expander(f"📖 展开全部 ({len(lines)} 行)"):
                st.markdown(content)
        else:
            st.markdown(content)

# ---------- 筛选标签 + 猜你想问 ----------
render_filter_tags(corp_id_map, mat_id_map)

try:
    top_qs = rag_manager.get_top_questions(limit=8)
    # 从当前会话的历史提取用户最近问题
    recent_qs = []
    for m in st.session_state.messages[-10:]:
        if m["role"] == "user":
            clean = re.sub(r"【.*?】", "", m["content"]).strip()
            if clean and len(clean) > 3:
                recent_qs.append(clean)
    render_suggestions(top_qs, recent_qs)
except Exception as e:
    logger.warning("建议渲染失败: %s", e)

# ---------- 处理 "猜你想问" 点击 / 用户输入 ----------
if st.session_state._pending_suggestion:
    prompt = st.session_state._pending_suggestion
    st.session_state._pending_suggestion = None
else:
    prompt = st.chat_input("请输入问题...")

if not prompt:
    st.stop()

# 保存用户消息
save_message("user", prompt, user_id, st.session_state.conversation_id,
             settings.chat_history_dir, rag_manager)
st.session_state.messages.append({"role": "user", "content": prompt})

# ==================== 意图分类 ====================

intent = classify(prompt)

# --- 问候 → 直接回复 ---
if intent == "greeting":
    greeting_responses = {
        "你好": "你好！我是澳华数智AI助手，可以帮你查询销量数据、客户信息、配方结构等。请告诉我你想了解什么？",
        "谢谢": "不客气！有其他问题随时找我。",
        "嗯": "好的，有什么需要帮助的随时说。",
    }
    reply = greeting_responses.get(prompt.strip().lower(), "你好！请问有什么可以帮你的？")
    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_message("assistant", reply, user_id, st.session_state.conversation_id,
                 settings.chat_history_dir)
    st.rerun()

# --- 普通聊天 → 直接调 LLM，不走 Agent ---
if intent == "general":
    with st.chat_message("assistant"):
        placeholder = st.empty()
        chat_llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.7,
        )
        history = []
        for m in st.session_state.messages[:-1]:
            if m["role"] == "user":
                history.append(HumanMessage(content=m["content"]))
            else:
                history.append(AIMessage(content=m["content"]))
        full = ""
        try:
            for chunk in chat_llm.stream(history + [HumanMessage(content=prompt)]):
                if hasattr(chunk, 'content') and chunk.content:
                    full += chunk.content
                    placeholder.markdown(full + "▌")
            placeholder.markdown(full)
        except Exception as e:
            full = f"抱歉，我暂时无法回复：{str(e)}"
            placeholder.error(full)
        st.session_state.messages.append({"role": "assistant", "content": full})
        save_message("assistant", full, user_id, st.session_state.conversation_id,
                     settings.chat_history_dir)
    st.rerun()


# ==================== 智能滤镜检测 ====================
# 扫描用户问题，如果提到公司/客户/物料名称，建议设为筛选

_detected_filters = _detect_filter_suggestions(
    prompt, corp_id_map, mat_id_map, client_id_map,
)

if _detected_filters:
    _suggestions = []
    _filters_to_add = {}

    if _detected_filters.get("corp_id"):
        _name = corp_id_map.get(_detected_filters["corp_id"], "")
        if _detected_filters["corp_id"] not in st.session_state.selected_corps:
            _suggestions.append(f"🏢 {_name}")
            _filters_to_add.setdefault("corps", []).append(_detected_filters["corp_id"])

    if _detected_filters.get("mat_id"):
        _name = mat_id_map.get(_detected_filters["mat_id"], "")
        if _detected_filters["mat_id"] not in st.session_state.selected_mats:
            _suggestions.append(f"📦 {_name}")
            _filters_to_add.setdefault("mats", []).append(_detected_filters["mat_id"])

    if _detected_filters.get("client_id"):
        _name = client_id_map.get(_detected_filters["client_id"], "")
        if _detected_filters["client_id"] not in st.session_state.selected_clients:
            _suggestions.append(f"👥 {_name}")
            _filters_to_add.setdefault("clients", []).append(_detected_filters["client_id"])

    if _suggestions:
        _suggestion_key = "_".join(
            str(v) for v in sum(_filters_to_add.values(), [])
        )
        st.info(f"💡 检测到你可能需要筛选：{' | '.join(_suggestions)}")
        col1, col2 = st.columns([1, 5])
        if col1.button("✅ 应用筛选", key=f"apply_flt_{_suggestion_key}", use_container_width=True):
            for k, ids in _filters_to_add.items():
                if k == "corps":
                    st.session_state.selected_corps = list(set(st.session_state.selected_corps + ids))
                elif k == "mats":
                    st.session_state.selected_mats = list(set(st.session_state.selected_mats + ids))
                elif k == "clients":
                    st.session_state.selected_clients = list(set(st.session_state.selected_clients + ids))
            sync_prefs()
            st.rerun()


# ==================== Agent 响应 (business) ====================

with st.chat_message("assistant"):
    response_placeholder = st.empty()
    full_response = ""

    # 构建上下文消息
    chat_messages = []
    for m in st.session_state.messages:
        if m["role"] == "user":
            chat_messages.append(HumanMessage(content=m["content"]))
        else:
            content = m["content"]
            if content.count("\n") > 50:
                content = "\n".join(content.split("\n")[-50:]) + "\n\n...(截断)"
            chat_messages.append(AIMessage(content=content))

    # 构建初始消息 = 筛选上下文（不作为用户消息注入，而是作为系统上下文）
    selected_corps = st.session_state.selected_corps
    selected_date = st.session_state.selected_date
    selected_clients = st.session_state.selected_clients
    selected_mats = st.session_state.selected_mats
    selected_dims = st.session_state.selected_dimensions

    filter_context = f"""【当前筛选条件】
公司 ID: {selected_corps or '无'}
公司名称: {[corp_id_map.get(c, c) for c in selected_corps] if selected_corps else '无'}
日期: {selected_date.strftime('%Y-%m-%d')}
客户 ID: {selected_clients or '无'}
物料 ID: {selected_mats or '无'}
展示维度: {selected_dims or '默认'}

编写 SQL 时优先使用 ID 过滤。如果用户问题与筛选条件冲突，以用户问题为准。"""

    chat_messages.insert(0, HumanMessage(content=filter_context))

    try:
        for chunk in agent_executor.stream({"messages": chat_messages}, stream_mode="values"):
            if "messages" not in chunk or not chunk["messages"]:
                continue
            message = chunk["messages"][-1]

            if isinstance(message, AIMessage):
                if message.content:
                    full_response = message.content
                    response_placeholder.markdown(full_response)
                elif message.tool_calls:
                    for tc in message.tool_calls:
                        import json
                        try:
                            with st.status(f"🛠️ {tc['name']}...", expanded=False):
                                st.code(json.dumps(tc['args'], ensure_ascii=False, indent=2))
                                if "sql" in tc.get("args", {}):
                                    st.session_state.last_sql = tc["args"]["sql"]
                        except Exception:
                            pass
            elif isinstance(message, ToolMessage):
                try:
                    with st.status(f"✅ {message.name}", expanded=False):
                        st.code(message.content[:300])
                except Exception:
                    pass

        if full_response:
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_message("assistant", full_response, user_id, st.session_state.conversation_id,
                         settings.chat_history_dir)

            # SQL 查看（受密码保护）
            if st.session_state.last_sql:
                with st.expander("🔍 查看 SQL"):
                    pwd = st.text_input("输入复制密码", type="password", key=f"sqlpwd_{st.session_state.conversation_id}")
                    if pwd == "Aohua1688":
                        st.code(st.session_state.last_sql, language="sql")

            # 人工验证按钮
            if st.button("👍 采纳为经验", key=f"verify_{st.session_state.conversation_id}"):
                # 将最后一条 assistant 回答存入 RAG
                try:
                    rag_manager.add_answer(full_response, st.session_state.conversation_id, {"user_id": user_id})
                    st.success("已存入经验库")
                except Exception as e:
                    st.error(f"保存失败: {e}")

            st.rerun()
        else:
            # Agent 未产生文本响应 → 给出兜底提示
            fallback_msg = (
                "抱歉，我没有生成有效的回答。"
                "请重新描述你的问题，或检查左侧筛选条件是否设置正确。"
            )
            response_placeholder.info(fallback_msg)
            st.session_state.messages.append({"role": "assistant", "content": fallback_msg})
            save_message("assistant", fallback_msg, user_id, st.session_state.conversation_id,
                         settings.chat_history_dir)
            st.rerun()

    except Exception as e:
        error_msg = f"❌ 运行出错: {str(e)}"
        st.error(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.rerun()
