import os
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import json

class RAGManager:
    def __init__(self, persist_directory="./chroma_db"):
        # 确保目录存在
        if not os.path.exists(persist_directory):
            os.makedirs(persist_directory)
            
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # 使用配置中的 DeepSeek API
        api_key = os.getenv("DS_API_KEY")
        api_base = os.getenv("DS_BASE_URL")
        
        # 使用默认的 embedding 训练或者 SentenceTransformer
        # 由于无法连接远程 embedding 接口，我们使用 ChromaDB 默认的（SentenceTransformer）
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # 定义集合
        self.questions_col = self.client.get_or_create_collection(
            name="questions",
            embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.answers_col = self.client.get_or_create_collection(
            name="answers",
            embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.knowledge_col = self.client.get_or_create_collection(
            name="business_knowledge",
            embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def add_question(self, question_text, metadata=None):
        if not metadata:
            metadata = {}
        
        # 查找是否存在相似度极高的问题，如果存在则增加次数
        results = self.questions_col.query(
            query_texts=[question_text],
            n_results=1
        )
        
        if results['ids'] and results['distances'] and len(results['distances'][0]) > 0 and results['distances'][0][0] < 0.05:
            # 更新已有记录的次数
            doc_id = results['ids'][0][0]
            existing_meta = results['metadatas'][0][0]
            count = existing_meta.get("count", 1) + 1
            existing_meta["count"] = count
            existing_meta["last_used"] = datetime.now().isoformat()
            self.questions_col.update(
                ids=[doc_id],
                metadatas=[existing_meta]
            )
            return doc_id
        else:
            # 新增记录
            doc_id = f"q_{int(datetime.now().timestamp() * 1000)}"
            metadata.update({
                "count": 1,
                "last_used": datetime.now().isoformat(),
                "content": question_text
            })
            self.questions_col.add(
                ids=[doc_id],
                documents=[question_text],
                metadatas=[metadata]
            )
            return doc_id

    def add_answer(self, answer_text, question_id, metadata=None):
        if not metadata:
            metadata = {}
        
        doc_id = f"a_{int(datetime.now().timestamp() * 1000)}"
        metadata.update({
            "question_id": question_id,
            "count": 1,
            "last_used": datetime.now().isoformat(),
            "content": answer_text
        })
        self.answers_col.add(
            ids=[doc_id],
            documents=[answer_text],
            metadatas=[metadata]
        )
        return doc_id

    def search_questions(self, query_text, limit=5):
        results = self.questions_col.query(
            query_texts=[query_text],
            n_results=limit
        )
        
        combined_results = []
        if results['ids'] and len(results['ids']) > 0:
            for i in range(len(results['ids'][0])):
                combined_results.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i]
                })
        
        # 权重排序：次数多的优先，相似度高的优先
        combined_results.sort(key=lambda x: (-x['metadata'].get('count', 0), x['distance']))
        return combined_results

    def search_answers_by_question_id(self, question_id):
        # 简单实现，根据 question_id 查找
        results = self.answers_col.get(
            where={"question_id": question_id}
        )
        return results

    def search_knowledge(self, query_text, limit=5):
        results = self.knowledge_col.query(
            query_texts=[query_text],
            n_results=limit
        )
        return results

    def get_top_questions(self, limit=5):
        """获取全站提问频次最高的 Top N 问题"""
        try:
            results = self.questions_col.get()
            if not results['ids'] or len(results['ids']) == 0:
                return []

            combined = []
            for i in range(len(results['ids'])):
                # 处理 bytes -> str
                doc = results['documents'][i]
                if isinstance(doc, bytes):
                    doc = doc.decode("utf-8")
                elif doc is None:
                    continue

                meta = results['metadatas'][i] if results['metadatas'] else {}
                count = meta.get("count", 1)
                if isinstance(count, bytes):
                    count = int(count.decode("utf-8"))
                elif isinstance(count, str):
                    count = int(count)

                combined.append({
                    "document": doc,
                    "count": count
                })

            # 按次数降序排序
            combined.sort(key=lambda x: x['count'], reverse=True)
            return combined[:limit]
        except Exception as e:
            print(f"获取 Top 问题失败: {e}")
            return []

    def import_json_knowledge(self, json_path):
        if not os.path.exists(json_path):
            return
        
        with open(json_path, "r", encoding="utf-8") as f:
            knowledge_base = json.load(f)
        
        for item in knowledge_base:
            doc_id = f"k_{item['name']}"
            doc_content = f"业务定义: {item['name']}\n涉及表: {item['table']}\n业务逻辑: {item['logic']}\n参考SQL: {item.get('sql_snippet', '')}"
            
            existing = self.knowledge_col.get(ids=[doc_id])
            if not existing['ids']:
                self.knowledge_col.add(
                    ids=[doc_id],
                    documents=[doc_content],
                    metadatas={"name": item['name'], "table": item['table']}
                )
