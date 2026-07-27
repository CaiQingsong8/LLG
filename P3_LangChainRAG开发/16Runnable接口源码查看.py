

from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI


prompt = PromptTemplate.from_template("你是一个AI助手")
model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))

chain = prompt | model | prompt | model
chain.invoke()
chain.stream()
print(type(chain))
