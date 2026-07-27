from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os

load_dotenv(find_dotenv())

# 将阿里嵌入模型替换为 DeepSeek/OpenAI 兼容模型
model = OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))

# 不用invoke stream
# embed_query、embed_documents
print(model.embed_query("我喜欢你"))
print(model.embed_documents(["我喜欢你", "我稀饭你", "晚上吃啥"]))
