import warnings
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 过滤 LangGraph 的弃用警告
warnings.filterwarnings("ignore", message=".*create_react_agent has been moved to.*")


@tool(description="查询天气")
def get_weather() -> str:
    return "晴天"


agent = create_react_agent(
    model=ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat")),        # 智能体的大脑LLM
    tools=[get_weather],            # 向智能体提供工具列表
    prompt="你是一个聊天助手，可以回答用户问题。",
)

res = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": "明天深圳的天气如何？"},
        ]
    }
)

for msg in res["messages"]:
    print(type(msg).__name__, msg.content)
