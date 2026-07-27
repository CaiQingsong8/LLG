import warnings
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 过滤 LangGraph 的弃用警告
warnings.filterwarnings("ignore", message=".*create_react_agent has been moved to.*")


@tool(description="获取股价，传入股票名称，返回字符串信息")
def get_price(name: str) -> str:
    return f"股票{name}的价格是20元"


@tool(description="获取股票信息，传入股票名称，返回字符串信息")
def get_info(name: str) -> str:
    return f"股票{name}，是一家A股上市公司，专注于IT职业教育。"


agent = create_react_agent(
    model=ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat")),
    tools=[get_price, get_info],
    prompt="你是一个智能助手，可以回答股票相关问题，记住请告知我思考过程，让我知道你为什么调用某个工具"
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "传智教育股价多少，并介绍一下"}]},
    stream_mode="values"
):
    latest_message = chunk['messages'][-1]

    if latest_message.content:
        print(type(latest_message).__name__, latest_message.content)

    if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
        print(f"工具调用： { [tc['name'] for tc in latest_message.tool_calls]  }")
