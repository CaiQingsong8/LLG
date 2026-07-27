# from langchain_community.llms.tongyi import Tongyi
#
# model = Tongyi(model="qwen-max")
#
# # 通过stream方法获得流式输出
# res = model.stream(input="你是谁呀能做什么？")
#
# for chunk in res:
#     print(chunk, end="", flush=True)

# from langchain_ollama import OllamaLLM
#
# model = OllamaLLM(model="qwen3:4b")
#
# res = model.stream(input="你是谁呀能做什么？")
#
# for chunk in res:
#     print(chunk, end="", flush=True)



# # langchain_community
# from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
# import os
# from langchain_openai import ChatOpenAI
#
# # 不用qwen3-max，因为qwen3-max是聊天模型，qwen-max是大语言模型
#
# # 不用qwen3-max，因为qwen3-max是聊天模型，qwen-max是大语言模型
# model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))
# # 通过stream方法获得流式输出
# res = model.stream(input="你是谁呀能做什么？")
#
# for chunk in res:
#     print(chunk.content, end="", flush=True)


from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="deepseek-chat")

res = model.stream(input="你是谁呀能做什么？")

for chunk in res:
    print(chunk.content, end="", flush=True)