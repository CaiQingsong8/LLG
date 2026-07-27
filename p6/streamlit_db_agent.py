import streamlit as st
import os
import warnings
from datetime import datetime
from typing import List, Dict, Any, Annotated
from db import ckread
from tabulate import tabulate
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# 加载配置
load_dotenv(find_dotenv())

# 确保环境变量加载成功，如果没有加载到，尝试在当前目录及其父目录寻找 .env
if not os.getenv("DS_API_KEY"):
    load_dotenv(".env")
if not os.getenv("DS_API_KEY"):
    load_dotenv("../.env")

warnings.filterwarnings("ignore")

# ==================== 1. 定义数据库记录与工具 ====================

def save_chat_to_db(role: str, content: str):
    """将聊天记录保存到 ClickHouse。"""
    try:
        # 使用 streamlit 的 session_id 作为标识
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        session_id = ctx.session_id if ctx else "default"
        
        sql = "INSERT INTO alphafeed.agent_chat_history (session_id, role, content) VALUES"
        data = [(session_id, role, content)]
        ckread.insert(sql, data)
    except Exception as e:
        print(f"保存记录出错: {e}")

def load_chat_from_db():
    """从数据库加载最近的聊天记录。"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        session_id = ctx.session_id if ctx else "default"
        
        sql = f"SELECT role, content FROM alphafeed.agent_chat_history WHERE session_id = '{session_id}' ORDER BY created_at ASC"
        rows = ckread.query(sql).result_rows
        return [{"role": row[0], "content": row[1]} for row in rows]
    except:
        return []

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
        sql = f"DESCRIBE TABLE {database}.{table_name}"
        rows = ckread.query(sql).result_rows
        headers = ["列名", "类型", "注释"]
        table_data = [[row[0], row[1], row[4]] for row in rows]
        return f"表 {table_name} 的结构如下：\n" + tabulate(table_data, headers=headers, tablefmt="grid")
    except Exception as e:
        return f"获取表结构时出错: {str(e)}"

@tool
def execute_query(sql: str) -> str:
    """执行 SQL 查询语句并返回结果。仅限 SELECT 语句。"""
    try:
        if not sql.strip().lower().startswith("select"):
            return "错误：仅支持 SELECT 查询。"
        
        result = ckread.query(sql)
        rows = result.result_rows
        cols = result.column_names
        
        if not rows:
            return "查询成功，但没有返回结果。"
        
        max_rows = 50
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
   - **核心要求**：如果搜索结果中存在多个类似的表（例如：dwd_sales 和 ads_sales），请不要盲目猜测。你应该先通过 `describe_table` 查看它们的注释/结构，然后停止进一步的 SQL 编写，直接向用户展示这些表的信息，并明确询问：“我发现了以下几张相关的表，请问您指的是哪一张？”，并等待用户回复。
3. **结构确认**：在用户明确选择表后，使用 `describe_table` 查看其字段定义。
4. **执行查询**：根据字段定义编写 SQL，并使用 `execute_query` 获取数据。
5. **回答**：最后根据查询结果回答用户的问题。

注意事项：
- 数据库默认是 `alphafeed`。
- 编写 SQL 时要确保语法符合 ClickHouse 规范。
- **绝对安全**：如果语意不明确或有多张候选表，必须向用户确认，绝不能自行决定。
"""

agent_executor = create_react_agent(
    model=llm,
    tools=[get_current_time, list_tables, describe_table, execute_query],
    prompt=system_prompt
)

# ==================== 3. Streamlit UI ====================

st.set_page_config(page_title="ClickHouse 智能查询助手", layout="wide")

st.title("🚀 ClickHouse 智能数据库助手")
st.markdown("""
本助手可以帮助你通过自然语言查询 ClickHouse 数据库。
1. 它会自动寻找相关的表。
2. 如果有多张类似的表，它会请你先做选择。
3. 自动生成并执行 SQL。
""")

if "messages" not in st.session_state:
    st.session_state.messages = load_chat_from_db()

# 显示历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 用户输入
if prompt := st.chat_input("请输入您的问题..."):
    # 添加用户消息到历史并保存
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_chat_to_db("user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    # Agent 响应
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        inputs = {"messages": [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in st.session_state.messages]}
        
        try:
            # 检查 API KEY
            if not os.getenv("DS_API_KEY"):
                st.error("未找到 DS_API_KEY，请检查 .env 文件。")
                st.stop()
                
            # 使用流式输出显示工具调用过程
            for chunk in agent_executor.stream(inputs, stream_mode="values"):
                message = chunk["messages"][-1]
                
                if isinstance(message, AIMessage):
                    if message.content:
                        full_response = message.content
                        response_placeholder.markdown(full_response)
                    elif message.tool_calls:
                        for tool_call in message.tool_calls:
                            with st.status(f"🛠️ 正在执行工具: {tool_call['name']}...", expanded=False):
                                st.write(f"参数: {tool_call['args']}")
                elif isinstance(message, ToolMessage):
                     with st.status(f"✅ 工具 {message.name} 执行完成", expanded=False):
                         st.code(message.content)

            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_chat_to_db("assistant", full_response)
            
        except Exception as e:
            error_msg = f"❌ 运行出错: {str(e)}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

# 侧边栏
with st.sidebar:
    st.header("系统状态")
    if ckread:
        st.success("数据库已连接")
    else:
        st.error("数据库连接失败")
    
    if st.button("清空聊天记录"):
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            ctx = get_script_run_ctx()
            session_id = ctx.session_id if ctx else "default"
            ckread.command(f"ALTER TABLE alphafeed.agent_chat_history DELETE WHERE session_id = '{session_id}'")
        except:
            pass
        st.session_state.messages = []
        st.rerun()
