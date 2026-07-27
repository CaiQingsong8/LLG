import warnings
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 过滤 LangGraph 的弃用警告
warnings.filterwarnings("ignore", message=".*create_react_agent has been moved to.*")


@tool(description="查询天气，传入城市名称字符串，返回字符串天气信息")
def get_weather(city: str) -> str:
    return f"{city}天气：晴天"


# 注意：在 LangGraph / create_react_agent 中，传统的 middleware 装饰器（如 @before_agent）已不再适用。
# 下面通过在工具调用和模型交互前后的打印来模拟中间件行为。

def model_call_with_log(model):
    def wrapped_model(messages):
        print("[before_model] 模型即将调用")
        res = model.invoke(messages)
        print("[after_model] 模型调用结束")
        return res
    return wrapped_model


# 使用 create_react_agent 构建智能体
agent = create_react_agent(
    model=ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat")),
    tools=[get_weather],
    prompt="你是一个聊天助手，可以回答用户问题。"
)

print("[before agent] agent 启动")
res = agent.invoke({"messages": [{"role": "user", "content": "深圳今天的天气如何呀，如何穿衣"}]})
print("[after agent] agent 结束")

print("**********\n最终回答：", res["messages"][-1].content)
