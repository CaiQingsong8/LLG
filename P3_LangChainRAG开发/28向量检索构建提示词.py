"""
提示词：用户的提问 + 向量库中检索到的参考资料
"""
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def print_prompt(prompt):
    print(prompt.to_string())
    print("=" * 20)
    return prompt


model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "以我提供的已知参考资料为主，简洁和专业的回答用户问题。参考资料:{context}。"),
        ("user", "用户提问：{input}")
    ]
)

vector_store = InMemoryVectorStore(embedding=OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")))

# 准备一下资料（向量库的数据）
# add_texts 传入一个 list[str]
vector_store.add_texts(
    ["减肥就是要少吃多练", "在减脂期间吃东西很重要,清淡少油控制卡路里摄入并运动起来", "跑步是很好的运动哦"])

input_text = "怎么减肥？"

# 检索向量库
result = vector_store.similarity_search(input_text, 2)
reference_text = "["
for doc in result:
    reference_text += doc.page_content
reference_text += "]"

chain = prompt | print_prompt | model | StrOutputParser()

res = chain.invoke({"input": input_text, "context": reference_text})
print(res)
