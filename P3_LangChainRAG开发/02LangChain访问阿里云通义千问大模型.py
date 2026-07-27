# langchain_community
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI

# 不用qwen3-max，因为qwen3-max是聊天模型，qwen-max是大语言模型
model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))

# 调用invoke向模型提问
res = model.invoke(input="你是谁呀能做什么？")

print(res)
