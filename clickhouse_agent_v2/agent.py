"""LangGraph Agent 构建。"""
import logging
from pathlib import Path

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from config import settings
from agent_tools import (
    get_current_time, query_feed_sales, query_new_clients,
    search_business_knowledge, list_tables, describe_table, execute_query,
)

logger = logging.getLogger("agent")

TOOLS = [
    get_current_time,
    query_feed_sales,
    query_new_clients,
    search_business_knowledge,
    list_tables,
    describe_table,
    execute_query,
]


def _load_system_prompt() -> str:
    """从文件加载 system prompt，失败时使用内联兜底。"""
    path = Path(settings.prompts_dir) / "system.txt"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取 system prompt 失败: %s，使用内联兜底", e)
        return (
            "你是一个 ClickHouse 数据库助手。\n"
            "1. 先查业务知识  2. 匹配模板工具  3. 编写 SQL  4. 返回结果\n"
            "禁止危险操作，默认排除预算表。"
        )


_system_prompt = _load_system_prompt()


def build_agent():
    """构建并返回 LangGraph ReAct Agent（兼容多个 langgraph 版本）。"""
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
    )

    # 兼容 create_react_agent 的参数命名变化
    # langgraph >= 0.2.61: prompt=
    # langgraph < 0.2.x:   system_message=
    try:
        agent = create_react_agent(
            model=llm,
            tools=TOOLS,
            prompt=_system_prompt,
        )
    except TypeError as e:
        if "unexpected keyword argument 'prompt'" in str(e):
            logger.warning("当前 langgraph 版本不支持 prompt= 参数，尝试使用 system_message=")
            try:
                from langchain_core.messages import SystemMessage
                agent = create_react_agent(
                    model=llm,
                    tools=TOOLS,
                    system_message=SystemMessage(content=_system_prompt),
                )
            except (TypeError, ImportError) as e2:
                logger.warning("system_message= 也失败: %s，降级为无 system prompt", e2)
                agent = create_react_agent(model=llm, tools=TOOLS)
        else:
            logger.warning("create_react_agent 调用失败: %s，降级为无 system prompt", e)
            agent = create_react_agent(model=llm, tools=TOOLS)
    except Exception as e:
        logger.error("构建 Agent 异常: %s", e)
        raise

    logger.info("Agent 已构建，提示词 %d 字符", len(_system_prompt))
    return agent
