
import os
from openai import OpenAI
from dotenv import load_dotenv; load_dotenv()
client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY"))
#2调用模型
response=client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role":"system","content":"你是AI助理，回答很简洁"}, #尽量少说废话节省token
        {"role": "user", "content": "小明有两条宠物狗"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "小红有三只宠物狗"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "总共有几个宠物？"}
    ],
    stream=True #开启了流式输出
)
#3处理结果
#print(response.choices[0].message.content)
for chunk in response:
    content = chunk.choices[0].delta.content
    if content:
        print(
            content,
            end="", 
            flush=True #立刻刷新缓冲
        )