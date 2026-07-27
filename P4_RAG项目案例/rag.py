from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory, RunnableLambda
from file_history_store import get_history
from vector_stores import VectorStoreService
import config_data as config
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
import warnings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# 过滤弃用警告
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*langchain-community.*")
warnings.filterwarnings("ignore", message=".*RunnableWithMessageHistory.*")


def print_prompt(prompt):
    print("="*20)
    print(prompt.to_string())
    print("="*20)

    return prompt


class RagService(object):
    def __init__(self):
        from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
        
        # 尝试使用 OpenAI/DashScope 嵌入模型，如果失败则回退到 FakeEmbeddings
        try:
            embedding_fn = OpenAIEmbeddings(
                model=config.embedding_model_name,
                openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
                openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            # 测试一下是否可用
            embedding_fn.embed_query("test")
        except Exception as e:
            print(f"[警告] Embedding 模型加载失败或鉴权失败，切换至 FakeEmbeddings: {e}")
            from langchain_community.embeddings import FakeEmbeddings
            embedding_fn = FakeEmbeddings(size=1536)

        self.vector_service = VectorStoreService(embedding=embedding_fn)

        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", "以我提供的已知参考资料为主，"
                 "简洁和专业的回答用户问题。参考资料:{context}。"),
                ("system", "并且我提供用户的对话历史记录，如下："),
                MessagesPlaceholder("history"),
                ("user", "请回答用户提问：{input}")
            ]
        )

        self.chat_model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))

        self.chain = self.__get_chain()

    def __get_chain(self):
        """获取最终的执行链"""
        retriever = self.vector_service.get_retriever()

        def format_document(docs: list[Document]):
            if not docs:
                return "无相关参考资料"

            formatted_str = ""
            for doc in docs:
                formatted_str += f"文档片段：{doc.page_content}\n文档元数据：{doc.metadata}\n\n"

            return formatted_str

        def format_for_retriever(value: dict) -> str:
            return value["input"]

        def format_for_prompt_template(value):
            # {input, context, history}
            new_value = {}
            new_value["input"] = value["input"]["input"]
            new_value["context"] = value["context"]
            new_value["history"] = value["input"]["history"]
            return new_value

        chain = (
            {
                "input": RunnablePassthrough(),
                "context": RunnableLambda(format_for_retriever) | retriever | format_document
            } | RunnableLambda(format_for_prompt_template) | self.prompt_template | print_prompt | self.chat_model | StrOutputParser()
        )

        conversation_chain = RunnableWithMessageHistory(
            chain,
            get_history,
            input_messages_key="input",
            history_messages_key="history",
        )

        return conversation_chain


if __name__ == '__main__':
    # session id 配置
    session_config = {
        "configurable": {
            "session_id": "user_001",
        }
    }

    res = RagService().chain.invoke({"input": "针织毛衣如何保养？"}, session_config)
    print(res)

