"""知识库上传与更新（Streamlit）。"""
import os
import json
import logging
from datetime import datetime

import streamlit as st

from config import settings
from vector_stores import ChromaStore

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("app_file_upload")

st.set_page_config(page_title="知识库管理", layout="wide")
st.title("📚 知识库管理")

store = ChromaStore(settings.chroma_dir)

tab_upload, tab_browse, tab_stats = st.tabs(["📤 上传知识", "📖 浏览条目", "📊 状态"])

with tab_upload:
    st.subheader("上传 JSON 业务知识文件")
    st.info("JSON 格式：列表，每项含 name/table/logic/sql_snippet 字段")
    uploaded = st.file_uploader("选择 JSON 文件", type=["json"])
    if uploaded is not None:
        try:
            items = json.loads(uploaded.read().decode("utf-8"))
            count = 0
            for item in items:
                doc_id = f"k_{item['name']}"
                existing = store.col_knowledge.get(ids=[doc_id])
                if existing["ids"]:
                    continue
                content = (
                    f"业务定义: {item['name']}\n"
                    f"涉及表: {item['table']}\n"
                    f"业务逻辑: {item['logic']}\n"
                    f"参考SQL: {item.get('sql_snippet', '')}"
                )
                store.col_knowledge.add(
                    ids=[doc_id], documents=[content],
                    metadatas={"name": item["name"], "table": item["table"]},
                )
                count += 1
            st.success(f"✅ 导入完成：新增 {count} 条，跳过 {len(items) - count} 条已存在的。")
        except Exception as e:
            st.error(f"❌ 导入失败：{e}")

    st.divider()
    st.subheader("上传纯文本知识")
    txt_file = st.file_uploader("选择文本文件（.txt）", type=["txt"], key="txt")
    if txt_file is not None:
        try:
            content = txt_file.read().decode("utf-8")
            name = os.path.splitext(txt_file.name)[0]
            doc_id = f"k_upload_{name}_{int(datetime.now().timestamp())}"
            store.col_knowledge.add(
                ids=[doc_id], documents=[content],
                metadatas={"name": name, "table": "user_upload", "source": txt_file.name},
            )
            st.success(f"✅ 已存入知识库：{txt_file.name}（{len(content)} 字符）")
        except Exception as e:
            st.error(f"❌ 导入失败：{e}")

with tab_browse:
    st.subheader("当前知识条目")
    results = store.col_knowledge.get()
    if results["ids"]:
        for i in range(len(results["ids"])):
            meta = (results["metadatas"][i] or {}) if results.get("metadatas") else {}
            name = meta.get("name", "未知")
            table = meta.get("table", "")
            doc = results["documents"][i]
            doc = doc.decode() if isinstance(doc, bytes) else str(doc)
            with st.expander(f"📌 {name}  ({table})"):
                st.text(doc[:1000])
                if st.button("🗑️ 删除", key=f"del_{results['ids'][i]}"):
                    store.col_knowledge.delete(ids=[results["ids"][i]])
                    st.rerun()
    else:
        st.info("知识库为空")

with tab_stats:
    st.subheader("向量库状态")
    k_count = store.col_knowledge.count()
    q_count = store.col_questions.count()
    a_count = store.col_answers.count()
    st.metric("业务知识条目", k_count)
    st.metric("历史问题", q_count)
    st.metric("参考答案", a_count)
    st.caption(f"存储路径：{settings.chroma_dir}")

st.caption("💡 上传后的知识会在下次使用 Agent 时自动生效（search_business_knowledge 工具会检索到）。")
