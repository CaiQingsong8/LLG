import warnings
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 过滤 LangGraph 的弃用警告
warnings.filterwarnings("ignore", message=".*create_react_agent has been moved to.*")


@tool(description="获取体重，返回值是整数，单位千克")
def get_weight() -> int:
    return 90


@tool(description="获取身高，返回值是整数，单位厘米")
def get_height() -> int:
    return 172


agent = create_react_agent(
    model=ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat")),
    tools=[get_weight, get_height],
    prompt="""你是严格遵循ReAct框架的智能体，必须按「思考→行动→观察→再思考」的流程解决问题，
    且**每轮仅能思考并调用1个工具**，禁止单次调用多个工具。
    并告知我你的思考过程，工具的调用原因，按思考、行动、观察三个结构告知我""",
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "计算我的BMI"}]},
    stream_mode="values"
):
    latest_message = chunk['messages'][-1]

    if latest_message.content:
        print(type(latest_message).__name__, latest_message.content)

    if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
        print(f"工具调用： { [tc['name'] for tc in latest_message.tool_calls]  }")
