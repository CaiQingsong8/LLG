try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
import config_data as config
import warnings

# 过滤弃用警告
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*langchain-community.*")

class VectorStoreService(object):
    def __init__(self, embedding):
        """
        :param embedding: 嵌入模型的传入
        """
        self.embedding = embedding

        self.vector_store = Chroma(
            collection_name=config.collection_name,
            embedding_function=self.embedding,
            persist_directory=config.persist_directory,
        )

    def get_retriever(self):
        """返回向量检索器，方便加入chain"""
        return self.vector_store.as_retriever(search_kwargs={"k": config.similarity_threshold})


if __name__ == '__main__':
    from langchain_openai import OpenAIEmbeddings
    from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
    import os
    
    # 尝试使用 OpenAI/DashScope 嵌入模型，如果失败则回退到 FakeEmbeddings
    try:
        embedding_fn = OpenAIEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-v1"),
            openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
            openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        # 测试一下是否可用
        embedding_fn.embed_query("test")
    except Exception as e:
        print(f"[警告] Embedding 模型加载失败或鉴权失败，切换至 FakeEmbeddings: {e}")
        from langchain_community.embeddings import FakeEmbeddings
        embedding_fn = FakeEmbeddings(size=1536)

    retriever = VectorStoreService(embedding=embedding_fn).get_retriever()

    res = retriever.invoke("我的体重180斤，尺码推荐")
    print(res)

