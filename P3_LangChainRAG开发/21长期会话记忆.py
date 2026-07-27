import os, json
from typing import Sequence
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv())
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.memory import MemorySaver


model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "deepseek-chat"))

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你需要根据会话历史回应用户问题。对话历史："),
        MessagesPlaceholder("chat_history"),
        ("human", "请回答如下问题：{input}")
    ]
)


def call_model(state):
    """LangGraph 的模型调用节点"""
    # state["messages"] 是当前会话所有消息
    chat_history = state["messages"][:-1]           # 历史消息（除了最后一条）
    user_input = state["messages"][-1].content      # 最后一条是用户输入

    # 格式化提示词（和原来一样打印出来）
    full_prompt = prompt.format_prompt(
        chat_history=chat_history,
        input=user_input
    )
    print("="*20, full_prompt.to_string(), "="*20)

    # 调用模型
    response = model.invoke(full_prompt)
    return {"messages": [AIMessage(content=response.content)]}


# 构建 LangGraph
workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.add_edge(START, "model")

# 持久化：LangGraph 自动管理消息历史
# MemorySaver 在内存中保存（程序重启后丢失）
# 如需文件持久化可使用 SqliteSaver
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)


if __name__ == '__main__':
    # thread_id 相当于原来 session_id
    session_config = {"configurable": {"thread_id": "user_001"}}

    res = graph.invoke({"messages": [HumanMessage(content="小明有2个猫")]}, session_config)
    print("第1次执行：", res["messages"][-1].content)

    res = graph.invoke({"messages": [HumanMessage(content="小刚有1只狗")]}, session_config)
    print("第2次执行：", res["messages"][-1].content)

    res = graph.invoke({"messages": [HumanMessage(content="总共有几个宠物")]}, session_config)
    print("第3次执行：", res["messages"][-1].content)
