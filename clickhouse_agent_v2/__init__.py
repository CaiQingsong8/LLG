"""
# ClickHouse Agent v2 — 模块化重构版

按 PPT 课程「03RAG项目」的模块划分：

┌─ app_qa.py ─────────── 主对话页面（Streamlit 入口）
├─ app_file_upload.py ── 知识库上传与更新（Streamlit 入口）
├─ config.py ─────────── 配置管理（对应 PPT config_data.py）
├─ file_history_store.py  会话记忆存储（对应 PPT file_history_store.py）
├─ vector_stores.py ──── 向量存储服务（对应 PPT vector_stores.py）
├─ knowledge_base.py ─── 知识库更新服务（对应 PPT knowledge_base.py）
├─ rag.py ────────────── RAG 编排层
├─ database.py ───────── ClickHouse 数据库连接与维表查询
├─ agent_tools.py ────── Agent 工具函数
├─ agent.py ──────────── LangGraph Agent 构建
├─ intent.py ─────────── 用户意图分类
├─ ui.py ─────────────── Streamlit UI 组件
└─ prompts/ ──────────── 系统提示词
"""
