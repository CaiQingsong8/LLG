from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI
# zero-shot
prompt_template = PromptTemplate.from_template(
    "我的邻居姓{lastname}, 刚生了{gender}, 你帮我起个名字，简单回答。"
)
model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))
# 调用.format方法注入信息即可
# prompt_text = prompt_template.format(lastname="张", gender="女儿")
#
# model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))
# res = model.invoke(input=prompt_text)
# print(res)

chain = prompt_template | model

res = chain.invoke(input={"lastname": "张", "gender": "女儿"})
print(res)
