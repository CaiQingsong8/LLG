"""RAG 核心服务：编排向量存储、知识检索、高频问题、历史答案。"""
import logging
from typing import Any

from vector_stores import ChromaStore

logger = logging.getLogger("rag")


class RAGManager:
    """RAG 编排层，向下调用 ChromaStore 的向量能力，向上提供业务接口。"""

    def __init__(self, persist_directory: str):
        self.store = ChromaStore(persist_directory)

    # ---------- 业务知识 ----------

    def search_knowledge(self, query: str, limit: int = 3) -> str:
        """模糊搜索业务定义，返回可读文本。"""
        results = self.store.search_knowledge(query, limit=limit)
        if not results:
            return ""
        chunks = [f"- {r['content']}" for r in results]
        return "【相关业务逻辑】\n" + "\n".join(chunks)

    def import_json_knowledge(self, json_path: str):
        """从 JSON 文件导入业务知识（幂等）。"""
        self.store.import_json_knowledge(json_path)

    # ---------- 问题 / 答案（自进化）----------

    def add_question(self, question: str, metadata: dict | None = None) -> str:
        return self.store.add_question(question, metadata)

    def add_answer(self, answer: str, question_id: str, metadata: dict | None = None) -> str:
        return self.store.add_answer(answer, question_id, metadata)

    def search_questions(self, query: str, limit: int = 5) -> list[dict]:
        return self.store.search_questions(query, limit)

    def search_answers_by_question(self, question_id: str) -> str:
        return self.store.search_answers_by_question(question_id)

    def get_top_questions(self, limit: int = 8) -> list[str]:
        return self.store.get_top_questions(limit)
