"""向量存储服务：封装 ChromaDB 的连接、集合管理、向量搜索。"""
import os
import logging
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("vector_stores")


class ChromaStore:
    """管理 ChromaDB 持久化客户端及三个业务集合。"""

    def __init__(self, persist_directory: str):
        os.makedirs(persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()

        self.col_knowledge = self.client.get_or_create_collection(
            name="business_knowledge", embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.col_questions = self.client.get_or_create_collection(
            name="questions", embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.col_answers = self.client.get_or_create_collection(
            name="answers", embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------- 业务知识查询 ----------

    def search_knowledge(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """向量搜索业务知识，返回原始结果列表。"""
        try:
            results = self.col_knowledge.query(query_texts=[query], n_results=limit)
            if not results.get("ids") or not results["ids"][0]:
                return []
            out = []
            for i in range(len(results["ids"][0])):
                doc = results["documents"][0][i]
                doc = doc.decode() if isinstance(doc, bytes) else str(doc)
                out.append({
                    "id": results["ids"][0][i],
                    "content": doc,
                    "distance": results["distances"][0][i],
                    "metadata": (results["metadatas"][0][i] or {}) if results.get("metadatas") else {},
                })
            return out
        except Exception as e:
            logger.warning("search_knowledge 出错: %s", e)
            return []

    # ---------- 知识导入 ----------

    def import_json_knowledge(self, json_path: str):
        """从 JSON 文件导入业务知识（幂等）。"""
        if not os.path.exists(json_path):
            logger.warning("知识文件不存在: %s", json_path)
            return
        import json
        with open(json_path, encoding="utf-8") as f:
            items = json.load(f)
        count = 0
        for item in items:
            doc_id = f"k_{item['name']}"
            existing = self.col_knowledge.get(ids=[doc_id])
            if existing["ids"]:
                continue
            content = (
                f"业务定义: {item['name']}\n"
                f"涉及表: {item['table']}\n"
                f"业务逻辑: {item['logic']}\n"
                f"参考SQL: {item.get('sql_snippet', '')}"
            )
            self.col_knowledge.add(
                ids=[doc_id], documents=[content],
                metadatas={"name": item["name"], "table": item["table"]},
            )
            count += 1
        logger.info("已导入 %d 条业务知识（跳过 %d 条已存在的）", count, len(items) - count)

    # ---------- 问题频次 ----------

    def add_question(self, question: str, metadata: dict | None = None) -> str:
        """记录用户问题；若已有相似度极高的问题则累加频次。"""
        from datetime import datetime
        meta = metadata or {}
        results = self.col_questions.query(query_texts=[question], n_results=1)
        if results["ids"] and results["distances"] and results["distances"][0]:
            dist = results["distances"][0][0]
            if dist < 0.05:
                doc_id = results["ids"][0][0]
                m = dict(results["metadatas"][0][0])
                m["count"] = m.get("count", 1) + 1
                m["last_used"] = datetime.now().isoformat()
                self.col_questions.update(ids=[doc_id], metadatas=[m])
                return doc_id

        doc_id = f"q_{int(datetime.now().timestamp() * 1000000)}"
        meta.update(count=1, last_used=datetime.now().isoformat(), content=question)
        self.col_questions.add(ids=[doc_id], documents=[question], metadatas=[meta])
        return doc_id

    def add_answer(self, answer: str, question_id: str, metadata: dict | None = None) -> str:
        """保存人工验证过的答案。"""
        from datetime import datetime
        doc_id = f"a_{int(datetime.now().timestamp() * 1000000)}"
        meta = {"question_id": question_id, "verified": True, **(metadata or {})}
        self.col_answers.add(ids=[doc_id], documents=[answer], metadatas=[meta])
        return doc_id

    def search_questions(self, query: str, limit: int = 5) -> list[dict]:
        """搜索历史问题，按 (频次降序, 相似度升序) 排序。"""
        results = self.col_questions.query(query_texts=[query], n_results=limit)
        rows = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                doc = results["documents"][0][i]
                doc = doc.decode() if isinstance(doc, bytes) else str(doc)
                meta = results["metadatas"][0][i] or {}
                rows.append({
                    "id": results["ids"][0][i],
                    "question": doc,
                    "count": int(meta.get("count", 1)),
                    "distance": results["distances"][0][i],
                })
        rows.sort(key=lambda r: (-r["count"], r["distance"]))
        return rows

    def search_answers_by_question(self, question_id: str) -> str:
        """查找某个问题的历史参考答案。"""
        results = self.col_answers.get(where={"question_id": question_id})
        if results["ids"]:
            doc = results["documents"][0]
            return doc.decode() if isinstance(doc, bytes) else str(doc)
        return ""

    def get_top_questions(self, limit: int = 8) -> list[str]:
        """获取全站提问频次最高的 Top N 问题文本。"""
        try:
            results = self.col_questions.get()
            if not results["ids"]:
                return []
            pairs = []
            for i in range(len(results["ids"])):
                doc = results["documents"][i]
                if doc is None:
                    continue
                doc = doc.decode() if isinstance(doc, bytes) else str(doc)
                meta = results["metadatas"][i] or {}
                cnt = int(meta.get("count", 1))
                pairs.append((cnt, doc))
            pairs.sort(key=lambda x: -x[0])
            return [q for _, q in pairs[:limit]]
        except Exception as e:
            logger.warning("get_top_questions 出错: %s", e)
            return []
