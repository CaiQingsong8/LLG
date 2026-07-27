from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI

chat_prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个边塞诗人，可以作诗。"),
        MessagesPlaceholder("history"),
        ("human", "请再来一首唐诗"),
    ]
)

history_data = [
    ("human", "你来写一个唐诗"),
    ("ai", "床前明月光，疑是地上霜，举头望明月，低头思故乡"),
    ("human", "好诗再来一个"),
    ("ai", "锄禾日当午，汗滴禾下锄，谁知盘中餐，粒粒皆辛苦"),
]

# StringPromptValue    to_string()
prompt_text = chat_prompt_template.invoke({"history": history_data}).to_string()

model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))

res = model.invoke(prompt_text)

print(res.content, type(res))

