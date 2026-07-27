"""Streamlit UI 组件。"""
import uuid
import re
import logging
from datetime import datetime

import streamlit as st

logger = logging.getLogger("ui")

# ---------- 问候模式检测 ----------
_GREETING_PATTERNS = re.compile(
    r"^(你好|嗨|hi|hello|hey|早上好|下午好|晚上好|在吗|你好吗|谢谢|thanks|"
    r"再见|拜拜|bye|嗯|好的|可以|ok|okay|好了|没了|没有问题了|先这样)$",
    re.IGNORECASE,
)


def is_greeting(text: str) -> bool:
    """判断是否问候/闲聊。仅匹配明确的问候模式，不依赖长度猜测。"""
    t = text.strip().rstrip(".!?。！？")
    if _GREETING_PATTERNS.match(t):
        return True
    # 叠词问候：哈哈哈，嘿嘿嘿
    if re.fullmatch(r"([哈哈嗨嘿嘿嗯好哦噢])\1{1,3}", t):
        return True
    return False


# ---------- 用户身份 ----------

def render_user_login() -> str | None:
    """渲染登录面板，返回 user_id 或 None。"""
    query_params = st.query_params
    url_user = query_params.get("user", "")

    if "user_id" in st.session_state:
        return st.session_state.user_id

    with st.sidebar:
        st.title("👤 登录")
        input_uid = st.text_input("用户名", value=url_user or "", placeholder="例如: zhangsan")
        if input_uid and st.button("确认", use_container_width=True):
            if re.fullmatch(r"[A-Za-z0-9_\-]{1,50}", input_uid):
                st.session_state.user_id = input_uid
                st.query_params["user"] = input_uid
                st.rerun()
            else:
                st.error("用户名: 字母/数字/下划线/短横线，1-50 位")
        return None


# ---------- 侧边栏 ----------

def render_sidebar(
    hierarchy: dict,
    corp_id_map: dict,
    mat_hierarchy: dict,
    all_mats: list,
    mat_id_map: dict,
    user_id: str,
    conversations: list,
    load_conv_callback,
    delete_conv_callback,
    ck_ok: bool,
    client_ids: list | None = None,
    client_map: dict | None = None,
):
    """渲染完整的侧边栏: 用户信息 → 筛选 → 展示维度 → 历史会话。"""
    with st.sidebar:
        st.markdown(f"**👤 {user_id}**")
        if st.button("➕ 新建对话", use_container_width=True, type="primary"):
            st.session_state.conversation_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.subheader("🎯 筛选条件")

        # 公司
        all_corp_ids = [str(c[0]) for c in hierarchy.get("all", [])]
        # Flatten hierarchy
        flat_corps = []
        for region, corps in hierarchy.items():
            flat_corps.extend(corps)
        flat_corps = sorted(set(flat_corps), key=lambda x: x[1])
        all_corp_ids = [str(c[0]) for c in flat_corps]

        st.multiselect(
            "🏢 公司",
            options=all_corp_ids,
            format_func=lambda x: corp_id_map.get(x, x),
            key="selected_corps",
            placeholder="点击选择...",
        )
        st.checkbox("显示未营业/已停用", key="_show_inactive_corps",
                     help="勾选后显示已停业的公司")

        # 日期
        if "selected_date" not in st.session_state:
            st.session_state.selected_date = datetime.now()
        st.date_input("📅 日期", key="selected_date")

        # 客户
        # (实际渲染时从 database 获取联动客户列表)
        st.multiselect(
            "👥 客户",
            options=client_ids,
            format_func=lambda x: client_map.get(x, x),
            key="selected_clients",
            placeholder="公司联动后可选...",
        )
        st.checkbox("显示未启用/冻结", key="_show_inactive_clients",
                     help="勾选后显示未启用或已冻结的客户")

        # 物料
        with st.expander("📦 物料筛选"):
            st.checkbox("显示已停用物料", key="_show_inactive_mats",
                         help="勾选后显示已停用的物料")
            _sel = st.session_state.get("selected_mats", [])
            
            # 已选物料标签
            if _sel:
                _tags = [mat_id_map.get(m, m) for m in _sel[:5]]
                st.markdown("✅ " + " ∙ ".join(_tags))
                if len(_sel) > 5:
                    st.caption(f"...{len(_sel)}项")
                if st.button("✕ 清空", key="clr_mats", use_container_width=True):
                    st.session_state.selected_mats = []
                    st.rerun()

            # 构建一次树路径索引，缓存在 session_state
            if "_mat_tree" not in st.session_state:
                _idx = {}
                for _c1, _c2d in mat_hierarchy.items():
                    for _c2, _its in _c2d.items():
                        for _mid, _nm, _cd in _its:
                            _idx[_mid] = (_c1, _c2, f"{_c1} > {_c2} > {_nm} ({_cd})")
                st.session_state._mat_tree = _idx

            _tree = st.session_state._mat_tree
            _tab1, _tab2 = st.tabs(["🔍 搜索", "📂 浏览"])
            
            with _tab1:
                _q = st.text_input("", placeholder="输入名称或编码...", key="_mq", label_visibility="collapsed")
                if _q:
                    _t = _q.lower()
                    _matched = []
                    for _mid, (_c1, _c2, _path) in _tree.items():
                        if _t in _path.lower():
                            _matched.append((_mid, _path))
                            if len(_matched) >= 40:
                                break
                    if _matched:
                        _opts = [m[0] for m in _matched]
                        _new = st.multiselect("结果", options=_opts, default=[m for m in _sel if m in _opts],
                                              format_func=lambda x: _tree.get(x, (None,None,x))[2],
                                              key="_ms_s", label_visibility="collapsed")
                        if _new != _sel:
                            st.session_state.selected_mats = _new
                            st.rerun()
                    else:
                        st.caption("无匹配")

            with _tab2:
                # 自定义排序：商品 / 配方 / 其余字母序
                _sort_pri = {"库存商品": 0, "配方半成品": 1, "配方回粉": 2}
                _c1_list = sorted(mat_hierarchy.keys(), key=lambda k: (_sort_pri.get(k, 9), k))
                _c1 = st.selectbox("大类", [""] + _c1_list, key="_mc1")
                if _c1:
                    _c2_list = sorted(mat_hierarchy[_c1].keys())
                    _c2 = st.selectbox("子类", [""] + _c2_list, key="_mc2")
                    if _c2:
                        _items = mat_hierarchy[_c1][_c2]
                        _opts = [m[0] for m in _items]
                        _new = st.multiselect("选择物料", options=_opts,
                                              default=[m for m in _sel if m in _opts],
                                              format_func=lambda x: f"{_tree.get(x, (None,None,x))[2].split(' > ')[-1]}",
                                              key="_ms_b", label_visibility="collapsed")
                        if _new != _sel:
                            st.session_state.selected_mats = _new
                            st.rerun()
        st.subheader("📜 历史会话")
        for conv_id, started_at, first_msg in conversations[:3]:
            label = f"{started_at[:16] if started_at else ''} | {first_msg}"
            if st.button(label, key=f"conv_{conv_id}", use_container_width=True):
                load_conv_callback(conv_id)

        if len(conversations) > 3:
            with st.expander(f"📂 更多 ({len(conversations) - 3})"):
                for conv_id, started_at, first_msg in conversations[3:]:
                    label = f"{started_at[:16] if started_at else ''} | {first_msg}"
                    if st.button(label, key=f"conv_more_{conv_id}", use_container_width=True):
                        load_conv_callback(conv_id)

        st.divider()
        st.caption("⚙️ " + ("🟢 数据库已连接" if ck_ok else "🔴 数据库未连接"))
        if st.button("🗑️ 清空当前对话", use_container_width=True):
            delete_conv_callback()
            st.rerun()


def render_filter_tags(corp_id_map: dict, mat_id_map: dict):
    """在聊天区域顶部显示当前筛选条件标签。"""
    tags = []
    if st.session_state.get("selected_corps"):
        names = [corp_id_map.get(c, c) for c in st.session_state.selected_corps]
        tags.append(f"🏢 {', '.join(names[:3])}{'...' if len(names) > 3 else ''}")
    if st.session_state.get("selected_date"):
        tags.append(f"📅 {st.session_state.selected_date.strftime('%Y-%m-%d')}")
    if st.session_state.get("selected_mats"):
        names = [mat_id_map.get(m, m) for m in st.session_state.selected_mats]
        tags.append(f"📦 {', '.join(names[:2])}{'...' if len(names) > 2 else ''}")
    if tags:
        st.markdown(">>> " + " | ".join(tags))


# ---------- 智能建议 ----------

def render_suggestions(top_questions: list[str], recent_questions: list[str]):
    """渲染"猜你想问"智能建议（动态生成，非硬编码）。"""
    suggestions = []
    if top_questions:
        suggestions.extend([("🔥 热门", q) for q in top_questions[:4]])
    if recent_questions:
        suggestions.extend([("📋 历史", q) for q in recent_questions[:3]])

    if not suggestions:
        suggestions = [
            ("💡", "查一下上个月的饲料销量"),
            ("💡", "列出今年新开户的客户"),
            ("💡", "帮我查一下 dwd_so_saleorder 表的结构"),
        ]

    st.markdown("---")
    st.markdown("💡 **猜你想问**")
    cols = st.columns(3)
    for i, (label, q) in enumerate(suggestions[:6]):
        btn_label = f"{label} {q[:20]}{'...' if len(q) > 20 else ''}"
        with cols[i % 3]:
            if st.button(btn_label, key=f"sug_{i}", use_container_width=True):
                st.session_state._pending_suggestion = q
                st.rerun()
