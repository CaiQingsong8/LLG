import os
import warnings
from datetime import datetime
from typing import List, Dict, Any
from db import ckread
from tabulate import tabulate
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# 加载配置
load_dotenv(find_dotenv())
warnings.filterwarnings("ignore")

# ==================== 1. 定义数据库探索工具 ====================

@tool
def get_current_time() -> str:
    """获取当前的系统时间。在处理‘上月’、‘本周’等相对时间词时，必须先调用此工具。"""
    return f"当前时间是：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@tool
def list_tables(keyword: str = None, database: str = "alphafeed") -> str:
    """列出指定数据库中的表名。支持通过关键词过滤表名。"""
    try:
        if keyword:
            sql = f"SHOW TABLES FROM {database} LIKE '%{keyword}%'"
        else:
            sql = f"SHOW TABLES FROM {database}"
        
        rows = ckread.query(sql).result_rows
        tables = [row[0] for row in rows]
        
        if not tables:
            return f"在数据库 {database} 中没找到匹配 '{keyword}' 的表。"
        
        return f"数据库 {database} 中的相关表有：\n" + ", ".join(tables)
    except Exception as e:
        return f"列出表时出错: {str(e)}"

@tool
def describe_table(table_name: str, database: str = "alphafeed") -> str:
    """获取指定表的列信息，包括列名、类型和注释（如果有）。"""
    try:
        # ClickHouse 使用 DESCRIBE TABLE
        sql = f"DESCRIBE TABLE {database}.{table_name}"
        rows = ckread.query(sql).result_rows
        # rows 结构通常是: (name, type, default_type, default_expression, comment, codec_expression, ttl_expression)
        headers = ["列名", "类型", "注释"]
        table_data = [[row[0], row[1], row[4]] for row in rows]
        return f"表 {table_name} 的结构如下：\n" + tabulate(table_data, headers=headers, tablefmt="grid")
    except Exception as e:
        return f"获取表结构时出错: {str(e)}"

@tool
def execute_query(sql: str) -> str:
    """执行 SQL 查询语句并返回结果。仅限 SELECT 语句。"""
    try:
        # 简单的安全检查
        if not sql.strip().lower().startswith("select"):
            return "错误：仅支持 SELECT 查询。"
        
        result = ckread.query(sql)
        rows = result.result_rows
        cols = result.column_names
        
        if not rows:
            return "查询成功，但没有返回结果。"
        
        # 限制返回行数，防止过大
        max_rows = 20
        display_rows = rows[:max_rows]
        
        output = tabulate(display_rows, headers=cols, tablefmt="grid")
        if len(rows) > max_rows:
            output += f"\n(仅显示前 {max_rows} 行，总计 {len(rows)} 行)"
        return output
    except Exception as e:
        return f"执行查询时出错: {str(e)}"

# ==================== 2. 构建 Agent ====================

llm = ChatOpenAI(
    model=os.getenv("DS_MODEL", "deepseek-chat"),
    api_key=os.getenv("DS_API_KEY"),
    base_url=os.getenv("DS_BASE_URL"),
    temperature=0.1
)

system_prompt = """你是一个专业的 ClickHouse 数据库助手。
你可以根据用户的提问，动态地探索数据库、查看表结构并编写 SQL 查询。

你的操作流程通常应该是：
1. **时间确认**：如果用户提到“上月”、“去年”、“本周”等相对时间词，请务必先调用 `get_current_time` 确认当前时间。
2. **表探索**：
   - 如果不确定有哪些表，使用 `list_tables`（可以带关键字）搜索相关的表。
   - **重要**：如果搜索结果中存在多个类似的表（例如：dwd_sales 和 ads_sales），请不要盲目猜测。你应该先通过 `describe_table` 查看它们的注释/结构，或者直接询问用户：“我发现了以下几张相关的表，请问您指的是哪一张？”，并把表的注释信息展示给用户供其选择。
3. **结构确认**：找到相关的表后，使用 `describe_table` 查看其字段定义。
4. **执行查询**：根据字段定义编写 SQL，并使用 `execute_query` 获取数据。
5. **回答**：最后根据查询结果回答用户的问题。

注意事项：
- 数据库默认是 `alphafeed`。
- 编写 SQL 时要确保语法符合 ClickHouse 规范。
- 即使你知道表名，也建议先 `describe_table` 以确保字段名准确。
- **准确度优先**：如果语意不明确，必须向用户确认，不要生成错误的 SQL。
"""

agent_executor = create_react_agent(
    model=llm,
    tools=[get_current_time, list_tables, describe_table, execute_query],
    prompt=system_prompt
)

if __name__ == "__main__":
    print("🚀 动态数据库智能助手已启动")
    print("你可以问我关于数据库中的任何数据，我会自动寻找表和字段。")
    print("输入 '退出' 结束对话\n")

    while True:
        user_input = input("👤 你：")
        if user_input.lower() in ['退出', 'exit', 'quit']:
            print("👋 再见！")
            break
        
        print("\n🤖 助手：")
        inputs = {"messages": [("user", user_input)]}
        try:
            for chunk in agent_executor.stream(inputs, stream_mode="values"):
                message = chunk["messages"][-1]
                if message.type == "ai" and message.content:
                    print(message.content)
                elif message.type == "ai" and message.tool_calls:
                    for tool_call in message.tool_calls:
                        print(f"🛠️  正在执行工具: {tool_call['name']} (参数: {tool_call['args']})...")
        except Exception as e:
            print(f"❌ 运行出错: {e}")
        print()
