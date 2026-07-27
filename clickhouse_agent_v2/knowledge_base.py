"""知识库更新服务：导入业务知识 JSON、增量更新、文件上传。"""
import os
import json
import logging
from typing import Any

from vector_stores import ChromaStore

logger = logging.getLogger("knowledge_base")


def import_json(store: ChromaStore, json_path: str):
    """导入 JSON 业务知识文件到向量库（幂等）。"""
    store.import_json_knowledge(json_path)


def import_json_direct(persist_directory: str, json_path: str):
    """便捷函数：直接初始化 ChromaStore 并导入知识。"""
    store = ChromaStore(persist_directory)
    import_json(store, json_path)
    return store


def list_knowledge_items(store: ChromaStore) -> list[dict[str, Any]]:
    """列出知识库中全部条目（名称 + 涉及表）。"""
    results = store.col_knowledge.get()
    items = []
    if results["ids"]:
        for i in range(len(results["ids"])):
            meta = (results["metadatas"][i] or {}) if results.get("metadatas") else {}
            items.append({
                "id": results["ids"][i],
                "name": meta.get("name", "未知"),
                "table": meta.get("table", ""),
            })
    return items
