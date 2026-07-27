from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI

parser = StrOutputParser()
model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))
prompt = PromptTemplate.from_template(
    "我邻居姓：{lastname}，刚生了{gender}，请起名，仅告知我名字无需其它内容。"
)

chain = prompt | model | parser | model | parser

res: str = chain.invoke({"lastname": "张", "gender": "女儿"})
print(res)
print(type(res))
