
from openai import OpenAI
#1获取client openai 对象
client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
#2调用模型
response=client.chat.completions.create(
    model="qwen3-max",
    messages=[
        {"role":"system","content":"你是一个python编程专家，并且不说废话简单回答"}, #尽量少说废话节省token
        {"role": "assistant", "content": "好的，我是一个python编程专家，并且不说废话，你要问什么"},
        {"role": "user", "content": "输出1-10的数字，使用python代码"}
    ],
    stream=True #开启了流式输出
)
#3处理结果
#print(response.choices[0].message.content)
for chunk in response:
    print(
        chunk.choices[0].delta.content,
        end=" ", #每一段之间以空格分隔
        flush=True #立刻刷新缓冲区
    )