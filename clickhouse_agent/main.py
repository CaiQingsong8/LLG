import streamlit as st
import uuid
import sqlparse
import re
import os
import json
import logging
import warnings
import pandas as pd
import duckdb
from datetime import datetime
from typing import List, Dict, Any, Annotated
from pathlib import Path
from db import ckread
from tabulate import tabulate
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from rag_manager import RAGManager

# 配置日志替换 print
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("agent")

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 加载配置
load_dotenv(find_dotenv())

# 确保环境变量加载成功，如果没有加载到，尝试在当前目录及其父目录寻找 .env
if not os.getenv("DS_API_KEY"):
   load_dotenv(".env")
if not os.getenv("DS_API_KEY"):
   load_dotenv("../.env")

warnings.filterwarnings("ignore")

from pydantic import BaseModel, Field

# ==================== 0. 线下数据集管理 ====================
STORAGE_DIR = "/mnt/group_share/ai_agent_datasets"
# 如果共享盘不可用，先用本地目录兜底
if not os.path.exists("/mnt/group_share"):
   STORAGE_DIR = "./offline_datasets"
os.makedirs(STORAGE_DIR, exist_ok=True)

def register_offline_dataset(name: str, df: pd.DataFrame, uploaded_by: str):
   dataset_id = f"{name}_{uuid.uuid4().hex[:8]}"
   storage_path = os.path.join(STORAGE_DIR, f"{dataset_id}.parquet")
   df.to_parquet(storage_path)

   try:
       ckread.command(f"""
           INSERT INTO alphafeed.agent_offline_datasets
           (dataset_id, dataset_name, storage_path, uploaded_by, row_count)
           VALUES ('{dataset_id}', '{name}', '{storage_path}', '{uploaded_by}', {len(df)})
       """)
   except Exception as e:
       if "ACCESS_DENIED" in str(e) or "UNKNOWN_TABLE" in str(e):
           logger.info(f"[CATALOG] 写入 ClickHouse 目录表失败 (权限不足或表不存在): {e}")
       else:
           logger.warning(f"写入 ClickHouse 目录失败: {e}")
       # 如果 ClickHouse 写入失败，这里我们目前没有更好的持久化目录方案，只能依赖缓存
   
   get_offline_catalog.clear()
   return dataset_id

@st.cache_resource(ttl=300)
def get_offline_catalog() -> dict:
   try:
       # 如果 ClickHouse 访问受限，这里会抛出异常，我们将使用内存缓存或空目录
       sql = "SELECT dataset_id, dataset_name, storage_path, row_count FROM alphafeed.agent_offline_datasets"
       rows = ckread.query(sql).result_rows
       return {
           did.decode() if isinstance(did, bytes) else str(did): {
               "name": name.decode() if isinstance(name, bytes) else str(name),
               "path": path.decode() if isinstance(path, bytes) else str(path),
               "row_count": cnt
           }
           for did, name, path, cnt in rows
       }
   except Exception as e:
       e_str = str(e)
       # 如果表不存在或无权限，打印错误并返回空，避免崩溃
       if "UNKNOWN_TABLE" in e_str or "ACCESS_DENIED" in e_str:
           # 简化日志，避免干扰用户
           logger.info(f"[CATALOG] 数据库目录不可用 (表不存在或无权限)。")
       else:
           logger.warning(f"获取线下数据集目录失败: {e_str[:100]}...")
       return {}

@tool
def list_offline_datasets() -> str:
   """列出已上传的线下补充数据集，涉及非数据库数据的问题应优先检查这里。"""
   catalog = get_offline_catalog()
   if not catalog:
       return "当前没有已上传的线下数据。"
   return "\n".join(f"{info['name']} ({info['row_count']}行)" for info in catalog.values())

@tool
def describe_offline_dataset(dataset_name: str) -> str:
   """查看指定线下数据集的字段结构。"""
   catalog = get_offline_catalog()
   match = next((v for v in catalog.values() if v["name"] == dataset_name), None)
   if not match:
       return f"未找到数据集 {dataset_name}。"
   df = pd.read_parquet(match["path"])
   return f"字段: {list(df.columns)}\n示例数据:\n{df.head(3).to_string()}"

@tool
def query_offline_data(dataset_name: str, sql: str) -> str:
   """对指定线下数据集执行 SQL 查询，表名固定写作 df。仅限 SELECT。"""
   parsed = sqlparse.parse(sql)
   if len(parsed) != 1 or parsed[0].get_type() != "SELECT":
       return "错误：仅支持单条 SELECT 查询。"
   if re.search(r"\b(DELETE|DROP|UPDATE|TRUNCATE|ALTER|INSERT|GRANT|REPLACE)\b", sql, re.IGNORECASE):
       return "错误：检测到危险关键字。"

   catalog = get_offline_catalog()
   match = next((v for v in catalog.values() if v["name"] == dataset_name), None)
   if not match:
       return f"未找到数据集 {dataset_name}。"

   df = pd.read_parquet(match["path"])
   try:
       result = duckdb.query_df(df, "df", sql).to_df()
       if result.empty:
           return "查询成功，但没有返回结果。"
       return tabulate(result.head(50).values, headers=result.columns, tablefmt="grid")
   except Exception as e:
       return f"查询出错: {e}"

# ==================== 1. 定义数据库记录与工具 ====================

class FeedSaleQueryParams(BaseModel):
   month: str = Field(None, description="查询月份，格式为 'YYYY-MM'。如果不提供，默认查上月。如果要查询全量或不分月份，请传 'all'。")
   client_type: str = Field("外部", description="客户类型，可选值：'外部'、'内部'、'全部'。默认为'外部'。")
   class_codes: List[str] = Field(["21", "22"], description="分类代码列表。默认为饲料分类 ['21', '22']。")
   corp_ids: List[str] = Field(None, description="公司ID列表 (d_corp_id)，用于精确过滤。")
   client_ids: List[str] = Field(None, description="客户ID列表 (d_client_id)，用于精确过滤。")
   material_ids: List[str] = Field(None, description="物料ID列表 (d_material_id)，用于精确过滤。")

@tool
def query_feed_sales(params: FeedSaleQueryParams) -> str:
   """专门用于查询饲料销量的模板化工具。支持按月份、客户类型、分类、公司ID、客户ID和物料ID过滤。命中此场景时优先使用。"""
   try:
       # 1. 自动处理月份 (Slot Filling 默认值逻辑)
       target_month = params.month
       where_clauses = ["dr = '0'"]
       
       if target_month == "all":
           # 如果是查询全量，不添加月份过滤
           pass
       elif not target_month:
           # 默认使用侧边栏选中的日期月份
           if 'selected_date_sync' in st.session_state:
               target_month = st.session_state.selected_date_sync.strftime("%Y-%m")
           else:
               from datetime import datetime, timedelta
               now = datetime.now()
               first_day_of_current_month = now.replace(day=1)
               last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
               target_month = last_day_of_last_month.strftime("%Y-%m")
           where_clauses.append(f"month_dt = '{target_month}'")
       else:
           where_clauses.append(f"month_dt = '{target_month}'")
       
       # 公司过滤 (ID)
       if params.corp_ids:
           ids_str = ", ".join([f"'{cid}'" for cid in params.corp_ids])
           where_clauses.append(f"d_corp_id IN ({ids_str})")
           
       # 客户过滤 (ID)
       if params.client_ids:
           clients_str = ", ".join([f"'{cid}'" for cid in params.client_ids])
           where_clauses.append(f"d_client_id IN ({clients_str})")

       # 物料过滤 (ID)
       if params.material_ids:
           mats_str = ", ".join([f"'{mid}'" for mid in params.material_ids])
           where_clauses.append(f"d_material_id IN ({mats_str})")
       
       # 分类过滤
       if params.class_codes:
           codes_str = ", ".join([f"'{c}'" for c in params.class_codes])
           where_clauses.append(f"d_class_code2 IN ({codes_str})")
       
       # 客户类型过滤 (修正字段名为 client_class_flag)
       if params.client_type == "外部":
           where_clauses.append("client_class_flag = '0'")
       elif params.client_type == "内部":
           where_clauses.append("client_class_flag = '1'")
           
       sql = f"SELECT sum(f_sale_num) as total_sales FROM alphafeed.dwd_so_saleorder WHERE {' AND '.join(where_clauses)}"
       
       logger.info(f"[ROUTER] 命中模板: query_feed_sales, 参数: {params}")
       
       # 执行查询
       result = ckread.query(sql)
       if not result.result_rows or result.result_rows[0][0] is None:
           return f"查询成功，但在 {target_month} 未找到符合条件的销量数据。"
       
       val = result.result_rows[0][0]
       display_month = "全量历史" if target_month == "all" else target_month
       return f"【模板查询结果】{display_month} 的饲料销量统计为：{val}。 (查询条件: {params})"
   except Exception as e:
       return f"执行模板查询时出错: {str(e)}"

class NewClientQueryParams(BaseModel):
   year: str = Field(None, description="查询年份，格式为 'YYYY'。如果不提供，默认查今年。")
   client_type: str = Field("全部", description="客户类型，可选值：'外部'、'内部'、'全部'。默认为'全部'。")

@tool
def query_new_clients(params: NewClientQueryParams) -> str:
   """专门用于查询新客户的模板化工具。支持按年份和客户类型过滤。命中新客户场景时优先使用。"""
   try:
       target_year = params.year
       if not target_year:
            if 'selected_date_sync' in st.session_state:
                target_year = st.session_state.selected_date_sync.strftime("%Y")
            else:
                target_year = datetime.now().strftime("%Y")
       
       where_clauses = [f"toYear(open) = {target_year}"] # 假设 open 是日期字段
       
       if params.client_type == "外部":
           where_clauses.append("is_internal_client = 0")
       elif params.client_type == "内部":
           where_clauses.append("is_internal_client = 1")
           
       sql = f"SELECT client_id, name, open FROM alphafeed.DIM_CLIENT WHERE {' AND '.join(where_clauses)} LIMIT 100"
       
       logger.info(f"[ROUTER] 命中模板: query_new_clients, 参数: {params}")
       
       result = ckread.query(sql)
       rows, cols = result.result_rows, result.column_names
       
       if not rows:
           return f"查询成功，但在 {target_year} 未找到符合条件的新客户。"
           
       output = tabulate(rows[:50], headers=cols, tablefmt="grid")
       if len(rows) > 50:
           output += f"\n(仅显示前 50 行，总计 {len(rows)} 行)"
       return f"【模板查询结果】{target_year} 的新客户列表：\n{output}"
   except Exception as e:
       return f"执行模板查询时出错: {str(e)}"

@st.cache_resource
def get_rag_manager():
   rm = RAGManager(persist_directory="./chroma_db")
   rm.import_json_knowledge("business_knowledge.json")
   return rm

rag_manager = get_rag_manager()

# ==================== 1.1 获取维表数据 (带缓存) ====================

@st.cache_data(ttl=3600)
def get_corp_hierarchy():
   try:
       sql = "SELECT DISTINCT d_region_name, d_corp_id, d_corp_name FROM alphafeed.dim_unit WHERE d_corp_name != '' AND d_corp_id IS NOT NULL ORDER BY d_region_name, d_corp_name"
       rows = ckread.query(sql).result_rows
       hierarchy = {}
       corp_id_map = {}
       for region, corp_id, corp_name in rows:
           region = region.decode() if isinstance(region, bytes) else str(region) if region and region != '无' else '其他'
           corp_id = corp_id.decode() if isinstance(corp_id, bytes) else str(corp_id) # 兼容 bytes 类型并转字符串
           corp_name = corp_name.decode() if isinstance(corp_name, bytes) else str(corp_name)
           if region not in hierarchy:
               hierarchy[region] = []
           if (corp_id, corp_name) not in hierarchy[region]:
               hierarchy[region].append((corp_id, corp_name))
           corp_id_map[corp_id] = corp_name
       return hierarchy, corp_id_map
   except Exception as e:
       logger.warning(f"获取公司架构出错: {e}")
       return {}, {}

@st.cache_data(ttl=3600)
def get_material_hierarchy():
   """获取物料架构，并构建搜索索引"""
   try:
       # 获取 ID, 名称, 编码
       sql = "SELECT DISTINCT d_class_name1, d_class_name2, d_material_id, d_material_name, d_material_code FROM alphafeed.dim_material WHERE d_material_name != '' AND d_material_name NOT LIKE '%(停用)%' ORDER BY d_class_name1, d_class_name2, d_material_name"
       rows = ckread.query(sql).result_rows
       hierarchy = {}
       all_materials = [] # 存储 (id, name, code)
       mat_id_map = {}
       for c1, c2, mid, name, code in rows:
           c1 = c1.decode() if isinstance(c1, bytes) else str(c1) if c1 else '未分类'
           c2 = c2.decode() if isinstance(c2, bytes) else str(c2) if c2 else '通用'
           mid = mid.decode() if isinstance(mid, bytes) else str(mid) # 兼容 bytes 类型并转字符串
           name = name.decode() if isinstance(name, bytes) else str(name)
           code = code.decode() if isinstance(code, bytes) else str(code)
           if c1 not in hierarchy:
               hierarchy[c1] = {}
           if c2 not in hierarchy[c1]:
               hierarchy[c1][c2] = []
           
           mat_tuple = (mid, name, code)
           hierarchy[c1][c2].append(mat_tuple)
           all_materials.append(mat_tuple)
           mat_id_map[mid] = f"{name} ({code})"
           
       return hierarchy, sorted(list(set(all_materials)), key=lambda x: x[1]), mat_id_map
   except Exception as e:
       logger.warning(f"获取物料架构出错: {e}")
       return {}, [], {}

@st.cache_data(ttl=3600)
def get_customers(corp_ids: List[str] = None):
   try:
       where_clauses = ["d_client_name != ''", "d_client_id IS NOT NULL"]
       if corp_ids:
           ids_str = ", ".join([f"'{cid}'" for cid in corp_ids])
           where_clauses.append(f"d_corp_id IN ({ids_str})")
       
       where_str = " AND ".join(where_clauses)
       # 获取 ID, 名称, 编码
       sql = f"SELECT DISTINCT d_client_id, d_client_name, d_client_code FROM alphafeed.dim_client WHERE {where_str} ORDER BY d_client_name"
       rows = ckread.query(sql).result_rows
       
       clients = []
       client_id_map = {}
       for cid, name, code in rows:
           cid = cid.decode() if isinstance(cid, bytes) else str(cid) # 兼容 bytes 类型并转字符串
           name = name.decode() if isinstance(name, bytes) else str(name) if name else ""
           code = code.decode() if isinstance(code, bytes) else str(code) if code else ""
           clients.append((cid, name, code))
           client_id_map[cid] = f"{name} ({code})"
           
       return clients, client_id_map
   except Exception as e:
       logger.warning(f"获取客户列表出错: {e}")
       return [], {}

def save_user_preferences(user_id: str, prefs: dict):
   """保存用户偏好设置到本地文件。"""
   try:
       local_dir = "user_preferences"
       os.makedirs(local_dir, exist_ok=True)
       local_file = os.path.join(local_dir, f"{user_id}.json")
       with open(local_file, "w", encoding="utf-8") as f:
           json.dump(prefs, f, ensure_ascii=False, indent=2)
   except Exception as e:
       logger.info(f"[PREFS] 保存偏好失败: {e}")

def load_user_preferences(user_id: str) -> dict:
   """从本地文件加载用户偏好设置。"""
   try:
       local_file = os.path.join("user_preferences", f"{user_id}.json")
       if os.path.exists(local_file):
           with open(local_file, "r", encoding="utf-8") as f:
               return json.load(f)
   except Exception as e:
       logger.info(f"[PREFS] 加载偏好失败: {e}")
   return {}

def validate_user_id(uid: str) -> str:
   """校验用户名格式，防止 SQL 注入。"""
   if not uid:
       return ""
   if not re.fullmatch(r"^[A-Za-z0-9_\-]{1,50}$", uid):
       st.error("用户名只能包含字母、数字、下划线、短横线，长度 1-50。")
       st.stop()
   return uid

def save_conversation_filters(user_id: str, conversation_id: str, filters: dict):
   """保存会话对应的筛选条件快照，切换会话时可自动恢复。"""
   try:
       conv_file = os.path.join("user_preferences", f"{user_id}_conv_filters.json")
       conv_filters = {}
       if os.path.exists(conv_file):
           with open(conv_file, "r", encoding="utf-8") as f:
               conv_filters = json.load(f)
       conv_filters[conversation_id] = filters
       with open(conv_file, "w", encoding="utf-8") as f:
           json.dump(conv_filters, f, ensure_ascii=False, indent=2)
   except Exception as e:
       logger.info(f"[CONV_FILTERS] 保存会话筛选条件失败: {e}")

def load_conversation_filters(user_id: str, conversation_id: str) -> dict:
   """加载会话保存的筛选条件。"""
   try:
       conv_file = os.path.join("user_preferences", f"{user_id}_conv_filters.json")
       if os.path.exists(conv_file):
           with open(conv_file, "r", encoding="utf-8") as f:
               conv_filters = json.load(f)
           return conv_filters.get(conversation_id, {})
   except Exception as e:
       logger.info(f"[CONV_FILTERS] 加载会话筛选条件失败: {e}")
   return {}

def apply_conversation_filters(conv_filters: dict):
   """将保存的筛选条件应用到当前 session_state。"""
   if not conv_filters:
       return
   if conv_filters.get("corps_ids") is not None:
       st.session_state.selected_corps_ms = conv_filters["corps_ids"]
   if conv_filters.get("date"):
       try:
           st.session_state.selected_date_sync = datetime.strptime(conv_filters["date"], "%Y-%m-%d")
       except (ValueError, TypeError):
           pass
   if conv_filters.get("client_ids") is not None:
       st.session_state.selected_clients = conv_filters["client_ids"]
   if conv_filters.get("material_ids") is not None:
       st.session_state.selected_mats = conv_filters["material_ids"]
   if conv_filters.get("dimensions") is not None:
       st.session_state.selected_dimensions = conv_filters["dimensions"]
   sync_user_prefs()

def condense_conversation(messages: list) -> dict:
   """调用 LLM 将当前对话压缩为结构化 QA 摘要。"""
   try:
       llm = ChatOpenAI(
           model=os.getenv("DS_MODEL", "deepseek-chat"),
           api_key=os.getenv("DS_API_KEY"),
           base_url=os.getenv("DS_BASE_URL"),
           temperature=0.3
       )
       # 提取 Q&A 对
       qa_pairs = []
       i = 0
       while i < len(messages):
           if messages[i]["role"] == "user":
               q = messages[i]["content"]
               q_clean = re.sub(r"【筛选条件：.*?】", "", q).strip()
               q_clean = re.sub(r"【系统硬约束.*?】", "", q_clean).strip()
               a = ""
               for j in range(i + 1, min(i + 3, len(messages))):
                   if messages[j]["role"] == "assistant":
                       a = messages[j]["content"][:300]
                       break
               if q_clean:
                   qa_pairs.append({"q": q_clean, "a": a})
           i += 1

       if not qa_pairs:
           return {"qa_pairs": [], "summary": "对话内容过短，无法浓缩。"}

       qa_text = "\n".join([f"Q: {p['q']}\nA: {p['a'][:200]}" for p in qa_pairs])
       prompt_text = f"请为以下对话生成结构化摘要，格式：\n- 核心主题：一句话概括\n- Q&A：每个问题一行\n\n对话：\n{qa_text}"
       resp = llm.invoke([HumanMessage(content=prompt_text)])
       summary = resp.content if hasattr(resp, 'content') else str(resp)

       return {"qa_pairs": qa_pairs, "summary": summary}
   except Exception as e:
       logger.info(f"[CONDENSE] 浓缩对话失败: {e}")
       return {"qa_pairs": [], "summary": f"浓缩失败: {e}"}

def save_condensed_history(user_id: str, conversation_id: str, data: dict):
   """保存浓缩后的历史记录到本地文件。"""
   try:
       cond_file = os.path.join("user_preferences", f"{user_id}_condensed.json")
       histories = []
       if os.path.exists(cond_file):
           with open(cond_file, "r", encoding="utf-8") as f:
               histories = json.load(f)
       histories.append({
           "conversation_id": conversation_id,
           "condensed_at": datetime.now().isoformat(),
           "qa_pairs": data.get("qa_pairs", []),
           "summary": data.get("summary", "")
       })
       histories = histories[-20:]
       with open(cond_file, "w", encoding="utf-8") as f:
           json.dump(histories, f, ensure_ascii=False, indent=2)
   except Exception as e:
       logger.info(f"[CONDENSE] 保存浓缩历史失败: {e}")

def load_condensed_histories(user_id: str) -> list:
   """加载用户的所有浓缩历史记录。"""
   try:
       cond_file = os.path.join("user_preferences", f"{user_id}_condensed.json")
       if os.path.exists(cond_file):
           with open(cond_file, "r", encoding="utf-8") as f:
               return json.load(f)
   except Exception as e:
       logger.info(f"[CONDENSE] 加载浓缩历史失败: {e}")
   return []

def save_chat_to_db(role: str, content: str, user_id: str, conversation_id: str):
    """将聊天记录保存到本地文件 + ClickHouse，并同步到向量库。"""
    # 确保内容不是 bytes
    content = content.decode() if isinstance(content, bytes) else str(content)
    
    # 0. 保存到本地文件 (彻底解决数据库权限导致的丢失问题)
    try:
        local_dir = "chat_history"
        os.makedirs(local_dir, exist_ok=True)
        local_file = os.path.join(local_dir, f"{user_id}.json")
        
        history_data = []
        if os.path.exists(local_file):
            with open(local_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        
        history_data.append({
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": datetime.now().isoformat()
        })
        
        with open(local_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存聊天记录到 {local_file}")
    except Exception as local_e:
        logger.warning(f"保存本地聊天记录失败: {local_e}")

    # 1. 保存到 ClickHouse (如果权限允许)
    try:
        combined_id = f"{user_id}:{conversation_id}"
        data = [[combined_id, role, content]]
        ckread.insert("alphafeed.agent_chat_history", data, column_names=['session_id', 'role', 'content'])
    except Exception as db_e:
        db_e_str = str(db_e)
        if "ACCESS_DENIED" in db_e_str or "read-only" in db_e_str.lower():
            pass  # 已有本地备份，此处可忽略
        else:
            logger.warning(f"保存聊天记录出错: {db_e_str[:100]}...")
    
    # 审计日志
    logger.info(f"User: {user_id}, Conv: {conversation_id}, Role: {role}, Content: {content[:50]}...")
    
    # 2. 如果是用户提问，记录到向量库并统计频次（独立 try，不受主流程失败影响）
    if role == 'user':
        try:
            clean_content = re.sub(r"【筛选条件：.*?】", "", content).strip()
            clean_content = re.sub(r"【系统硬约束.*?】", "", clean_content).strip()
            if clean_content:
                q_id = rag_manager.add_question(clean_content, {"user_id": user_id})
                st.session_state.last_question_id = q_id
        except Exception as rag_e:
            logger.warning(f"记录问题到向量库失败: {rag_e}")

def load_chat_from_db(user_id: str, conversation_id: str):
   """优先从本地加载聊天记录，本地没有则尝试数据库。"""
   # 1. 尝试从本地加载
   try:
       local_file = os.path.join("chat_history", f"{user_id}.json")
       if os.path.exists(local_file):
           with open(local_file, "r", encoding="utf-8") as f:
               history_data = json.load(f)
           # 过滤出当前会话的记录
           conv_messages = [
               {"role": item["role"], "content": item["content"]}
               for item in history_data if item.get("conversation_id") == conversation_id
           ]
           if conv_messages:
               return conv_messages
   except Exception as e:
       logger.info(f"[LOCAL] 加载本地记录失败: {e}")

   # 2. 尝试从数据库加载 (兜底)
   try:
       combined_id = f"{user_id}:{conversation_id}"
       sql = f"SELECT role, content FROM alphafeed.agent_chat_history WHERE session_id = '{combined_id}' ORDER BY created_at ASC"
       result = ckread.query(sql)
       return [{"role": row[0], "content": row[1]} for row in result.result_rows]
   except Exception as e:
       if "ACCESS_DENIED" not in str(e):
           logger.info(f"加载数据库记录失败: {str(e)[:100]}...")
       return []

def list_conversations(user_id: str, max_count: int = 50):
   """列出用户的所有历史会话，优先读取本地。返回最多 max_count 条。"""
   convs = {} # key: conv_id, value: {started_at, first_msg}

   # 1. 从本地加载
   try:
       local_file = os.path.join("chat_history", f"{user_id}.json")
       if os.path.exists(local_file):
           with open(local_file, "r", encoding="utf-8") as f:
               history_data = json.load(f)

           for item in history_data:
               cid = item.get("conversation_id")
               if not cid: continue

               # 记录该会话的第一条消息和开始时间
               if cid not in convs:
                   if item["role"] == "user":
                       # 去除筛选上下文
                       clean_content = re.sub(r"【筛选条件：.*?】", "", item["content"]).strip()
                       clean_content = re.sub(r"【系统硬约束.*?】", "", clean_content).strip()
                       convs[cid] = {
                           "started_at": datetime.fromisoformat(item["created_at"]),
                           "first_msg": clean_content
                       }
   except Exception as e:
       logger.info(f"[LOCAL] 获取线下数据集目录失败: {e}")

   # 2. 从数据库加载 (合并)
   try:
       sql = f"""
           SELECT
               splitByChar(':', session_id)[2] as conv_id,
               min(created_at) as started_at,
               any(content) as first_msg
           FROM alphafeed.agent_chat_history
           WHERE session_id LIKE '{user_id}:%' AND role = 'user'
           GROUP BY conv_id
           ORDER BY started_at DESC
           LIMIT {max_count}
       """
       result = ckread.query(sql)
       for row in result.result_rows:
           cid, started, msg = row[0], row[1], row[2]
           if cid not in convs:
               clean_msg = re.sub(r"【筛选条件：.*?】", "", msg).strip()
               clean_msg = re.sub(r"【系统硬约束.*?】", "", clean_msg).strip()
               convs[cid] = {"started_at": started, "first_msg": clean_msg}
   except Exception as e:
       if "ACCESS_DENIED" not in str(e):
           logger.warning(f"获取数据库会话列表失败: {str(e)[:100]}...")

   # 排序并返回
   sorted_convs = sorted(
       [(cid, v["started_at"], v["first_msg"]) for cid, v in convs.items()],
       key=lambda x: x[1],
       reverse=True
   )
   return sorted_convs[:max_count]

@tool
def search_business_knowledge(query: str) -> str:
   """搜索已维护的业务定义、统计口径、专业术语以及历史相似问题的答案。在处理业务概念或重复问题时，必须先查阅。"""
   try:
       # 1. 搜索业务知识库集合
       kb_results = rag_manager.search_knowledge(query, limit=3)
           
       # 2. 搜索历史高频问题及答案
       q_results = rag_manager.search_questions(query, limit=2)
           
       result = ""
       if kb_results['ids'] and len(kb_results['ids'][0]) > 0:
           result += "【查找到相关业务逻辑】：\n"
           for i in range(len(kb_results['ids'][0])):
               doc = kb_results['documents'][0][i]
               doc = doc.decode() if isinstance(doc, bytes) else str(doc)
               result += f"- {doc}\n"
           
       if q_results:
           history_info = ""
           for q in q_results:
               # 寻找该问题的答案
               a_results = rag_manager.search_answers_by_question_id(q['id'])
               if a_results['ids']:
                   history_info += f"--- 历史相似问题 (提问次数: {q['metadata'].get('count', 0)}) ---\n"
                   q_doc = q['document']
                   q_doc = q_doc.decode() if isinstance(q_doc, bytes) else str(q_doc)
                   history_info += f"问题: {q_doc}\n"
                   a_doc = a_results['documents'][0]
                   a_doc = a_doc.decode() if isinstance(a_doc, bytes) else str(a_doc)
                   history_info += f"历史优化参考答案: {a_doc}\n"
           
           if history_info:
               result += "\n【查找到历史相似案例与自我优化建议】：\n" + history_info
       
       if not result:
           return f"没有找到关于 '{query}' 的业务定义或历史经验。"
       
       return result
   except Exception as e:
       return f"检索 RAG 知识库时出错: {str(e)}"

@tool
def get_current_time() -> str:
   """获取当前的系统时间。在处理‘上月’、‘本周’等相对时间词时，必须先调用此工具。"""
   return f"当前时间是：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@tool
def list_tables(keyword: str = None, database: str = "alphafeed") -> str:
    """列出指定数据库中的表名及其注释。支持通过关键词过滤表名。"""
    try:
        # 防止 SQL 注入：对 keyword 做转义
        safe_keyword = re.escape(keyword) if keyword else None
        if safe_keyword:
            sql = f"""
                SELECT name, comment 
                FROM system.tables 
                WHERE database = 'alphafeed' AND (name ILIKE '%{safe_keyword}%' OR comment ILIKE '%{safe_keyword}%')
            """
        else:
            sql = "SELECT name, comment FROM system.tables WHERE database = 'alphafeed'"

        rows = ckread.query(sql).result_rows

        if not rows:
            return f"在数据库 {database} 中没找到匹配 '{keyword}' 的表。"

        table_info = [f"表名: {row[0]} (注释: {row[1]})" for row in rows]
        return f"数据库 {database} 中的相关表有：\n" + "\n".join(table_info)
    except Exception as e:
        return f"列出表时出错: {str(e)}"

@tool
def describe_table(table_name: str, database: str = "alphafeed") -> str:
    """获取指定表的列信息，包括列名、类型和注释（如果有）。"""
    try:
        # 防止 SQL 注入：只允许字母数字下划线
        if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
            return f"错误：非法的表名 '{table_name}'。"
        if not re.fullmatch(r"[A-Za-z0-9_]+", database):
            return f"错误：非法的数据库名 '{database}'。"
        sql = f"DESCRIBE TABLE `{database}`.`{table_name}`"
        rows = ckread.query(sql).result_rows
        headers = ["列名", "类型", "注释"]
        table_data = [[row[0], row[1], row[4]] for row in rows]
        return f"表 {table_name} 的结构如下：\n" + tabulate(table_data, headers=headers, tablefmt="grid")
    except Exception as e:
        return f"获取公司架构出错: {str(e)}"

@tool
def execute_query(sql: str) -> str:
   """执行 SQL 查询语句并返回结果。仅限 SELECT 语句。"""
   try:
       # 安全检查
       parsed = sqlparse.parse(sql)
       # 必须确保只有一条语句，且类型为 SELECT
       if len(parsed) != 1 or parsed[0].get_type() != "SELECT":
           return "错误：仅支持单条 SELECT 查询。请勿包含多条语句或非 SELECT 语句。"
       
       # 检查危险关键字（作为辅助防护）
       danger_pattern = r"\b(DELETE|DROP|UPDATE|TRUNCATE|ALTER|INSERT|GRANT|REPLACE)\b"
       if re.search(danger_pattern, sql, re.IGNORECASE):
           return "错误：检测到危险关键字，操作被拦截。"
       
       # 强制 LIMIT
       if "limit" not in sql.lower():
           sql = sql.rstrip(";") + " LIMIT 50"
       
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

def _load_system_prompt() -> str:
    """从文件加载系统提示词，文件不存在时使用内联兜底。"""
    prompt_path = PROJECT_ROOT / "prompts" / "agent_system.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"读取提示词文件失败（{e}），使用内联兜底")
        return """你是一个具备自我进化能力的 ClickHouse 数据库助手。
你能够精准地使用维表主键 ID 进行过滤，确保查询效率和结果的唯一性。
你的操作流程必须严格遵守以下步骤：
1. 上下文感知，主键 ID 优先过滤。2. 检索 RAG 业务知识。3. 意图路由匹配模板工具。
4. 时间感知（涉及时间先调用 get_current_time）。5. 编写并执行 SQL。6. 给出回答。"""

system_prompt = _load_system_prompt()

@st.cache_resource
def get_agent_executor():
   llm_internal = ChatOpenAI(
       model=os.getenv("DS_MODEL", "deepseek-chat"),
       api_key=os.getenv("DS_API_KEY"),
       base_url=os.getenv("DS_BASE_URL"),
       temperature=0.1
   )
   return create_react_agent(
       model=llm_internal,
       tools=[
           get_current_time, query_feed_sales, query_new_clients, search_business_knowledge, 
           list_tables, describe_table, execute_query,
           list_offline_datasets, describe_offline_dataset, query_offline_data
       ],
       prompt=system_prompt
   )

agent_executor = get_agent_executor()

# ==================== 3. Streamlit UI ====================

st.set_page_config(page_title="澳华数智AI助手", layout="wide")

# 获取维表基础数据
hierarchy, corp_id_map = get_corp_hierarchy()
all_corps_options = []
for region, corps in hierarchy.items():
   all_corps_options.extend(corps)
# 按名称排序
all_corps_options = sorted(list(set(all_corps_options)), key=lambda x: x[1])

mat_hierarchy, all_mats, mat_id_map = get_material_hierarchy()

# 初始化 Session State 变量
if "selected_corps_ms" not in st.session_state:
   st.session_state.selected_corps_ms = []

if "conversation_id" not in st.session_state:
   st.session_state.conversation_id = str(uuid.uuid4())

if "messages" not in st.session_state:
   st.session_state.messages = []

if "last_question_id" not in st.session_state:
   st.session_state.last_question_id = None

if "temp_prompt" not in st.session_state:
   st.session_state.temp_prompt = None

if "selected_mats" not in st.session_state:
   st.session_state.selected_mats = []

if "selected_clients" not in st.session_state:
   st.session_state.selected_clients = []

if "selected_dimensions" not in st.session_state:
   st.session_state.selected_dimensions = []

if "filter_context" not in st.session_state:
   st.session_state.filter_context = ""

if "last_sql" not in st.session_state:
   st.session_state.last_sql = None

if "selected_date_sync" not in st.session_state:
   st.session_state.selected_date_sync = datetime.now()

# 统一获取当前筛选状态
selected_corps = st.session_state.selected_corps_ms
selected_date = st.session_state.selected_date_sync
final_selected_mats = st.session_state.selected_mats
final_selected_clients = st.session_state.selected_clients
final_selected_dims = st.session_state.selected_dimensions

# ==================== 用户身份识别 ====================
query_params = st.query_params
url_user = query_params.get("user")

# 如果 URL 中没有 user，但在 Session State 中有（比如之前输入过），则维持
if "persistent_user_id" not in st.session_state:
   st.session_state.persistent_user_id = validate_user_id(url_user)

user_id = st.session_state.persistent_user_id

if not user_id:
   with st.sidebar:
       st.info("👋 欢迎！请输入用户名以开始使用。")
       input_uid = st.text_input("用户名", placeholder="例如: zhansan", key="user_id_input")
       if input_uid:
           user_id = validate_user_id(input_uid)
           st.session_state.persistent_user_id = user_id
           # 将 user_id 写入 URL 参数，以便刷新后维持
           st.query_params["user"] = user_id
           st.rerun()
       else:
           st.stop()
else:
   # 确保 URL 参数与当前 user_id 一致
   if url_user != user_id:
       st.query_params["user"] = user_id

# 加载用户偏好设置 (核心逻辑)
if user_id and "prefs_loaded" not in st.session_state:
   prefs = load_user_preferences(user_id)
   if prefs:
       if "selected_corps_ms" in prefs:
           st.session_state.selected_corps_ms = prefs["selected_corps_ms"]
       if "selected_date_sync" in prefs:
           try:
               st.session_state.selected_date_sync = datetime.fromisoformat(prefs["selected_date_sync"])
           except:
               pass
       if "selected_clients" in prefs:
           st.session_state.selected_clients = prefs["selected_clients"]
       if "selected_mats" in prefs:
           st.session_state.selected_mats = prefs["selected_mats"]
       if "selected_dimensions" in prefs:
           st.session_state.selected_dimensions = prefs["selected_dimensions"]
   st.session_state.prefs_loaded = True

def sync_user_prefs():
   """将当前的筛选状态保存到用户偏好中。"""
   if not user_id:
       return
   prefs = {
       "selected_corps_ms": st.session_state.selected_corps_ms,
       "selected_date_sync": st.session_state.selected_date_sync.isoformat() if hasattr(st.session_state.selected_date_sync, "isoformat") else str(st.session_state.selected_date_sync),
       "selected_clients": st.session_state.selected_clients,
       "selected_mats": st.session_state.selected_mats,
       "selected_dimensions": st.session_state.selected_dimensions
   }
   save_user_preferences(user_id, prefs)

# 在侧边栏渲染前应用待处理的会话筛选条件（必须在 widget 创建前执行）
if "_pending_conv_filters" in st.session_state:
   pending = st.session_state._pending_conv_filters
   del st.session_state._pending_conv_filters
   apply_conversation_filters(pending)

# 侧边栏：核心筛选与历史管理
with st.sidebar:
   st.header(f"👤 用户: {user_id}")
   if st.button("➕ 新建对话", use_container_width=True):
       st.session_state.conversation_id = str(uuid.uuid4())
       st.session_state.messages = []
       st.session_state.last_sql = None
       st.rerun()
   
   st.divider()
   st.subheader("🎯 核心筛选")
   
   # 公司筛选
   all_corp_ids = [str(c[0]) for c in all_corps_options]
   st.multiselect("🏢 选择公司范围 (可选)", 
                  options=all_corp_ids, 
                  format_func=lambda x: corp_id_map.get(x, x),
                  key="selected_corps_ms", 
                  placeholder="点击选择公司...",
                  on_change=sync_user_prefs)
                  
   # 日期筛选
   st.date_input("📅 选择日期", value=st.session_state.selected_date_sync, 
                 key="selected_date_sync",
                 on_change=sync_user_prefs)
                 
   # 客户筛选 (与公司联动)
   relevant_clients, client_id_map = get_customers(st.session_state.selected_corps_ms)
   valid_client_ids = [str(c[0]) for c in relevant_clients]
   
   # 联动保护：如果已选客户不在当前公司可选范围内，则自动剔除
   if not all(cid in valid_client_ids for cid in st.session_state.selected_clients):
       st.session_state.selected_clients = [cid for cid in st.session_state.selected_clients if cid in valid_client_ids]
       sync_user_prefs()
       st.rerun()

   st.multiselect("👥 选择客户 (可选)", 
                  options=valid_client_ids,
                  format_func=lambda x: client_id_map.get(x, x),
                  key="selected_clients",
                  placeholder="全选或指定公司后联动...",
                  on_change=sync_user_prefs)

   # 物料筛选
   with st.expander("📦 物料筛选 (可选)"):
       mat_search = st.text_input("快速搜索物料", placeholder="名称或编码...", key="side_mat_search")
       if mat_search:
           search_term = str(mat_search).lower()
           search_results = [m for m in all_mats if search_term in str(m[1]).lower() or search_term in str(m[2]).lower()][:100]
           if search_results:
               # 这里的 m[0] 已经是字符串
               search_results_ids = [str(m[0]) for m in search_results]
               all_options_ids = list(set(search_results_ids + [str(mid) for mid in st.session_state.selected_mats]))
               selected_from_search_ids = st.multiselect(f"搜索结果 ({len(search_results)}+)", 
                                                        options=all_options_ids, 
                                                        format_func=lambda x: mat_id_map.get(x, x),
                                                        default=[str(mid) for mid in st.session_state.selected_mats if str(mid) in all_options_ids],
                                                        key="side_mat_ms")
               if set(selected_from_search_ids) != set(st.session_state.selected_mats):
                   st.session_state.selected_mats = selected_from_search_ids
                   sync_user_prefs()
                   st.rerun()

       if st.checkbox("按分类浏览", value=False, key="side_mat_browse"):
           for c1_name, c2_dict in mat_hierarchy.items():
               with st.expander(f"📦 {c1_name}"):
                   for c2_name, mats in c2_dict.items():
                       c2_label = f"∟ {c2_name}" if c2_name != '通用' else "∟ 其他"
                       current_selected_ids = [m[0] for m in mats if m[0] in st.session_state.selected_mats]
                       new_selected_c2_ids = st.multiselect(c2_label, 
                                                            options=[m[0] for m in mats], 
                                                            format_func=lambda x: mat_id_map.get(x, x),
                                                            default=current_selected_ids, 
                                                            key=f"side_ms_{c1_name}_{c2_name}")
                       if set(new_selected_c2_ids) != set(current_selected_ids):
                           removed = [m_id for m_id in current_selected_ids if m_id not in new_selected_c2_ids]
                           added = [m_id for m_id in new_selected_c2_ids if m_id not in current_selected_ids]
                           updated_list = [m_id for m_id in st.session_state.selected_mats if m_id not in removed]
                           updated_list.extend(added)
                           st.session_state.selected_mats = list(set(updated_list))
                           sync_user_prefs()
                           st.rerun()

   # 自动更新上下文描述 (用于 UI 显示和 Prompt 注入)
   temp_filters = []
   if st.session_state.selected_corps_ms:
       selected_corp_names = [corp_id_map.get(cid, cid) for cid in st.session_state.selected_corps_ms]
       if len(selected_corp_names) > 2:
           temp_filters.append(f"公司: {selected_corp_names[0]}等{len(selected_corp_names)}家")
       else:
           temp_filters.append(f"公司: {','.join(selected_corp_names)}")
           
   temp_filters.append(f"日期: {st.session_state.selected_date_sync.strftime('%Y-%m-%d')}")
   
   if st.session_state.selected_clients:
       _, c_id_map = get_customers(st.session_state.selected_corps_ms)
       selected_client_names = [c_id_map.get(cid, cid) for cid in st.session_state.selected_clients]
       if len(selected_client_names) > 2:
            temp_filters.append(f"客户: {selected_client_names[0]}等{len(selected_client_names)}人")
       else:
           temp_filters.append(f"客户: {','.join(selected_client_names)}")
           
   if st.session_state.selected_mats:
       selected_mat_names = [mat_id_map.get(mid, mid) for mid in st.session_state.selected_mats]
       if len(selected_mat_names) > 2:
           temp_filters.append(f"物料: {selected_mat_names[0]}等{len(selected_mat_names)}项")
       else:
           temp_filters.append(f"物料: {','.join(selected_mat_names)}")
           
   if st.session_state.selected_dimensions:
       temp_filters.append(f"维度: {','.join(st.session_state.selected_dimensions)}")
   
   st.session_state.filter_context = " | ".join(temp_filters)

   st.divider()
   st.subheader("📊 数据展示维度")
   st.multiselect("选择展示维度 (可选)", 
                  options=[
                      "大区/集团/公司", "客户", 
                      "物料编码", "产品系列", "物料6位", "物料4位", "物料2位", "物料1位",
                      "时间(日)", "时间(月)", "时间(年)", "时间(范围)"
                  ],
                  key="selected_dimensions",
                  placeholder="点击设置展示偏好...",
                  on_change=sync_user_prefs)

   st.divider()
   st.subheader("📜 历史会话")
   conversations = list_conversations(user_id, max_count=20)
   # 显示最近 3 条为按钮
   for conv_id, started_at, first_msg in conversations[:3]:
       # 格式化显示标签
       time_str = started_at.strftime("%m-%d %H:%M")
       preview = (first_msg[:15] + "...") if len(first_msg) > 15 else first_msg
       label = f"{time_str} | {preview}"

       if st.button(label, key=conv_id, use_container_width=True):
           st.session_state.conversation_id = conv_id
           st.session_state.messages = load_chat_from_db(user_id, conv_id)
           st.session_state._pending_conv_filters = load_conversation_filters(user_id, conv_id)
           st.rerun()

   # 剩余历史放在可展开区域
   if len(conversations) > 3:
       with st.expander(f"📂 更多历史会话 ({len(conversations) - 3}条)"):
           for conv_id, started_at, first_msg in conversations[3:]:
               time_str = started_at.strftime("%m-%d %H:%M")
               preview = (first_msg[:20] + "...") if len(first_msg) > 20 else first_msg
               label = f"{time_str} | {preview}"
               if st.button(label, key=f"more_{conv_id}", use_container_width=True):
                   st.session_state.conversation_id = conv_id
                   st.session_state.messages = load_chat_from_db(user_id, conv_id)
                   st.session_state._pending_conv_filters = load_conversation_filters(user_id, conv_id)
                   st.rerun()

   st.divider()
   # 一键浓缩历史记录
   if len(st.session_state.messages) >= 4:
       if st.button("📝 一键浓缩本对话", use_container_width=True):
           with st.spinner("正在浓缩对话内容..."):
               condensed = condense_conversation(st.session_state.messages)
               save_condensed_history(user_id, st.session_state.conversation_id, condensed)
               if condensed["qa_pairs"]:
                   q_count = len(condensed["qa_pairs"])
                   st.success(f"✅ 浓缩完成！共 {q_count} 轮问答，已保存到历史经验库，新会话将自动带入。")
               else:
                   st.info(condensed.get("summary", "浓缩完成。"))
               st.rerun()

   st.divider()
   with st.expander("📤 上传线下补充数据"):
       uploaded_file = st.file_uploader("上传 Excel/CSV", type=["xlsx", "csv"])
       ds_name_input = st.text_input("数据集名称（英文/拼音）", key="offline_ds_name")
       if uploaded_file and ds_name_input:
           if not re.fullmatch(r"[A-Za-z0-9_]{1,50}", ds_name_input):
               st.error("数据集名称只能包含字母、数字、下划线")
           elif st.button("✅ 上传并共享给所有人"):
               try:
                   df_uploaded = (pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv")
                         else pd.read_excel(uploaded_file))
                   register_offline_dataset(ds_name_input, df_uploaded, user_id)
                   st.success(f"已上传 {len(df_uploaded)} 行，其他用户提问命中即可共享查询。")
               except Exception as e:
                   st.error(f"上传失败: {e}")

   st.divider()
   with st.expander("🛠️ 业务知识库"):
       try:
           with open("business_knowledge.json", "r", encoding="utf-8") as f:
               kb = json.load(f)
               for item in kb:
                   with st.expander(item["name"]):
                       st.write(f"**表:** `{item['table']}`")
                       st.write(f"**逻辑:** {item['logic']}")
                       
                       # 添加模版提问
                       suggested_query = st.text_area(f"模版提问 ({item['name']})", value=f"帮我查一下{item['name']}", key=f"tpl_{item['name']}")
                       if st.button(f"🚀 发送提问", key=f"btn_{item['name']}", use_container_width=True):
                           st.session_state.temp_prompt = suggested_query
                           st.rerun()
       except:
           st.info("暂无业务知识库内容")

# 处理点击模版后的自动发送
if st.session_state.temp_prompt:
   prompt = st.session_state.temp_prompt
   st.session_state.temp_prompt = None # 清除标记
   
   # 自动附加筛选上下文 (模板点击也要加)
   if st.session_state.filter_context:
       prompt = f"【筛选条件：{st.session_state.filter_context}】 {prompt}"
       logger.info(f"[UI] 模板点击 - 自动注入筛选上下文: {st.session_state.filter_context}")
   
   # 模拟用户输入逻辑 (复制自 st.chat_input 后的处理)
   st.session_state.messages.append({"role": "user", "content": prompt})
   save_chat_to_db("user", prompt, user_id, st.session_state.conversation_id)
   # 保存当前筛选条件快照，切换会话时可恢复
   save_conversation_filters(user_id, st.session_state.conversation_id, {
       "corps_ids": st.session_state.selected_corps_ms or None,
       "date": st.session_state.selected_date_sync.strftime('%Y-%m-%d'),
       "client_ids": st.session_state.selected_clients or None,
       "material_ids": st.session_state.selected_mats or None,
       "dimensions": st.session_state.selected_dimensions or None
   })
   # 此处不需要 st.chat_message("user")，因为 rerun 后会统一渲染
   st.rerun()

# 初始化当前会话的数据（如果为空）
if not st.session_state.messages:
   st.session_state.messages = load_chat_from_db(user_id, st.session_state.conversation_id)

st.title("🚀 澳华数智AI助手")

if not st.session_state.messages:
   # 首次进入，显示欢迎语
   st.markdown(f"### 🎯 欢迎回来，{user_id}！")
   st.info(f"💡 当前筛选：{st.session_state.filter_context if st.session_state.filter_context else '全量数据'}。可在侧边栏随时调整。")

   st.divider()

# 自定义 CSS 优化移动端体验
st.markdown("""
   <style>
   .stChatMessage {
       padding: 0.5rem;
       border-radius: 0.5rem;
   }
   @media (max-width: 640px) {
       .stChatMessage {
           font-size: 0.9rem;
       }
       .stButton button {
           padding: 0.2rem 0.5rem;
       }
   }
   </style>
""", unsafe_allow_html=True)

# 显示历史消息
for message in st.session_state.messages:
   with st.chat_message(message["role"]):
       content = message["content"]
       if message["role"] == "assistant" and content.count('\n') > 50:
           lines = content.split('\n')
           st.markdown('\n'.join(lines[:50]))
           with st.expander(f"📖 展开全部 ({len(lines)} 行)"):
               st.markdown(content)
       else:
           st.markdown(content)

# --- 猜你想问 (按分类展示) ---
st.write("💡 **猜你想问**")

# 1. 准备分类问题
categories = {
   "💰 销售查询": [
       "查询最近一个月的饲料总销量",
       "按公司统计今年的销售金额",
       "查询外部客户的折扣与返利金额",
       "分析本月的销售毛利情况"
   ],
   "🧪 配方查询": [
       "查询指定产品的配方BOM结构",
       "查看某原料在哪些成品配方中使用",
       "对比不同版本的配方差异",
       "查询成品的配方组成及比例"
   ],
   "🆕 新客户查询": [
       "列出今年新开户的所有客户",
       "统计各区域的新客户增长情况",
       "查询本月新增的外部客户列表"
   ],
   "📦 物料查询": [
       "查询指定分类下的物料编码与名称",
       "检索物料的层级结构（1-6位）",
       "查找特定编码的物料详细信息"
   ]
}

# 2. 获取历史高频提问 (作为补充)
try:
   top_qs = rag_manager.get_top_questions(limit=5)
   if top_qs:
       # 确保文档内容是字符串，处理 bytes 类型
       high_freq_questions = []
       for q in top_qs:
           doc = q["document"]
           if isinstance(doc, bytes):
               doc = doc.decode("utf-8")
           high_freq_questions.append(doc)
       categories["🔥 历史高频"] = high_freq_questions
except Exception as e:
   logger.info(f"[高频问题] 获取线下数据集目录失败: {e}")

# 3. 从浓缩历史中提取话题（基于用户的真实历史问答）
try:
   condensed_list = load_condensed_histories(user_id)
   history_questions = []
   for item in condensed_list[-5:]:  # 最近5次浓缩
       for qa in item.get('qa_pairs', [])[:2]:  # 每次取前2个QA
           q_text = qa.get('q', '').strip()
           if q_text and len(q_text) > 3:
               history_questions.append(q_text)
   if history_questions:
       categories["📋 历史话题"] = history_questions
   elif len(condensed_list) == 0:
       # 给新用户一个提示
       pass
except Exception as e:
   logger.info(f"[历史话题] 获取线下数据集目录失败: {e}")

# 4. 渲染分类 Tabs
cat_tabs = st.tabs(list(categories.keys()))
for i, (cat_name, qs) in enumerate(categories.items()):
   with cat_tabs[i]:
       # 每行显示 2 个按钮，适配移动端
       for j in range(0, len(qs), 2):
           cols = st.columns(2)
           for k in range(2):
               if j + k < len(qs):
                   q_text = qs[j + k]
                   if cols[k].button(q_text, key=f"btn_{i}_{j+k}", use_container_width=True):
                       st.session_state.temp_prompt = q_text
                       st.rerun()

# 用户输入
prompt = st.chat_input("请输入您的问题...")

# 如果有侧边栏筛选上下文，且用户还没输入，可以提示
if st.session_state.filter_context:
   if not prompt:
       # 这里只是一个视觉提示，或者可以自动附加
       st.info(f"💡 当前已选筛选条件：{st.session_state.filter_context}")

if prompt:
   # 自动附加筛选上下文
   if st.session_state.filter_context:
       prompt = f"【筛选条件：{st.session_state.filter_context}】 {prompt}"
       # 打印日志到终端以便调试
       logger.info(f"[UI] 自动注入筛选上下文: {st.session_state.filter_context}")
   
   # 增加调试信息：如果检测到环境异常，提示用户
   try:
       from streamlit.runtime import get_instance
       instance = get_instance()
       # 尝试获取访问的 host 头
       if hasattr(instance, "server") and hasattr(instance.server, "_manager"):
            # 这里较难直接获取端口，但可以打印一个通用提示
            pass
   except:
       pass
   
   # 始终显示端口提示（如果是 8123 则 Ok 是 ClickHouse，如果是 8501 才是本应用）
   st.caption("提示：本应用运行在 8501 端口。如果直接访问 8123 端口仅会看到 'Ok.'。")

   # 添加用户消息到历史并保存
   st.session_state.messages.append({"role": "user", "content": prompt})
   save_chat_to_db("user", prompt, user_id, st.session_state.conversation_id)
   # 保存当前筛选条件快照，切换会话时可恢复
   save_conversation_filters(user_id, st.session_state.conversation_id, {
       "corps_ids": st.session_state.selected_corps_ms or None,
       "date": st.session_state.selected_date_sync.strftime('%Y-%m-%d'),
       "client_ids": st.session_state.selected_clients or None,
       "material_ids": st.session_state.selected_mats or None,
       "dimensions": st.session_state.selected_dimensions or None
   })
   st.rerun() # 统一 rerun 处理

# 检查是否需要 Agent 响应 (最后一条消息是 user)
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_prompt = st.session_state.messages[-1]["content"]

    # Agent 响应
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        # 构建 Agent 上下文，对超长的 assistant 消息截断尾部保留最新分析
        chat_messages = []
        for m in st.session_state.messages:
                if m["role"] == "user":
                    chat_messages.append(HumanMessage(content=m["content"]))
                else:
                    content = m["content"]
                    if content.count('\n') > 50:
                        lines = content.split('\n')
                        content = '\n'.join(lines[-50:]) + '\n\n...(截断，完整内容见历史记录)'
                    chat_messages.append(AIMessage(content=content))

        inputs = {"messages": chat_messages}

        # 4. 架构优化：注入 UI 结构化筛选条件作为额外上下文 (Slot Filling)
        # --- 问题记录兜底：防止 save_chat_to_db 异常导致 last_question_id 为 None ---
        if st.session_state.last_question_id is None:
            try:
                    clean_q = re.sub(r"【筛选条件：.*?】", "", last_user_prompt).strip()
                    clean_q = re.sub(r"【系统硬约束.*?】", "", clean_q).strip()
                    if clean_q:
                        q_id = rag_manager.add_question(clean_q, {"user_id": user_id})
                        st.session_state.last_question_id = q_id
                        logger.info(f"兜底记录问题到向量库: {clean_q[:50]}...")
            except Exception as rag_e:
                    logger.warning(f"兜底记录问题失败: {rag_e}")
                    # 4. 架构优化：注入 UI 结构化筛选条件作为额外上下文 (Slot Filling)
        # 获取最新的 ID 到 名称的映射，用于显示/记录
        relevant_clients_current, client_id_map_current = get_customers(selected_corps)

        current_filters = {
                "corps_ids": selected_corps if selected_corps else None,
                "corps_names": [corp_id_map.get(cid, cid) for cid in selected_corps] if selected_corps else None,
                "date": selected_date.strftime('%Y-%m-%d'),
                "client_ids": final_selected_clients if final_selected_clients else None,
                "client_names": [client_id_map_current.get(cid, cid) for cid in final_selected_clients] if final_selected_clients else None,
                "material_ids": final_selected_mats if final_selected_mats else None,
                "material_names": [mat_id_map.get(mid, mid) for mid in final_selected_mats] if final_selected_mats else None,
                "dimensions": final_selected_dims if final_selected_dims else None
        }

        # 将结构化信息放入第一条消息的 context 中
        filter_instr = (
                f"【系统硬约束(结构化输入)】：\n"
                f"- 公司过滤：d_corp_id IN {current_filters['corps_ids']}\n"
                f"- 客户过滤：d_client_id IN {current_filters['client_ids']}\n"
                f"- 物料过滤：d_material_id IN {current_filters['material_ids']}\n"
                f"- 日期范围：{current_filters['date']}\n"
                f"- 期望展示维度：{current_filters['dimensions']}\n"
                f"调用工具或编写 SQL 时，**必须优先使用主键 ID (d_corp_id, d_client_id, d_material_id)**。"
        )
        chat_messages.insert(0, HumanMessage(content=filter_instr))

        # 5. 注入历史浓缩经验（如果有）
        condensed_histories = load_condensed_histories(user_id)
        if condensed_histories:
                history_summaries = []
                for item in condensed_histories[-3:]:  # 最近3条
                    summary = item.get("summary", "")
                    if summary and len(summary) > 10:
                        # 截断过长的摘要
                        if len(summary) > 200:
                                summary = summary[:200] + "..."
                        history_summaries.append(f"- {summary}")
                if history_summaries:
                    condensed_context = "【你的历史经验摘要（源自之前的对话浓缩）】\n" + "\n".join(history_summaries)
                    chat_messages.insert(0, HumanMessage(content=condensed_context))

        try:
                # 检查 API KEY
                if not os.getenv("DS_API_KEY"):
                    st.error("未找到 DS_API_KEY，请检查 .env 文件。")
                    st.stop()

                # 使用流式输出显示工具调用过程
                for chunk in agent_executor.stream(inputs, stream_mode="values"):
                    if "messages" not in chunk or not chunk["messages"]:
                        continue
                    message = chunk["messages"][-1]

                    if isinstance(message, AIMessage):
                        if message.content:
                                full_response = message.content
                                response_placeholder.markdown(full_response)
                        elif message.tool_calls:
                                for tool_call in message.tool_calls:
                                    # 注意: 此处在线程中，st.status 可能会触发警告
                                    # 但由于这是在 agent_executor.stream 中（由 Streamlit 主线程驱动），通常是安全的
                                    try:
                                        with st.status(f"🛠️ 正在执行工具: {tool_call['name']}...", expanded=False):
                                                st.write(f"参数: {tool_call['args']}")
                                                # 捕获 SQL
                                                if "sql" in tool_call['args']:
                                                    st.session_state.last_sql = tool_call['args']['sql']
                                    except Exception:
                                        # 如果 st.status 失败（由于 ScriptRunContext），降级为 print
                                        logger.info(f"[AGENT] 执行工具: {tool_call['name']}, 参数: {tool_call['args']}")
                    elif isinstance(message, ToolMessage):
                        try:
                                with st.status(f"✅ 工具 {message.name} 执行完成", expanded=False):
                                    st.code(message.content)
                        except Exception:
                                logger.info(f"[AGENT] 工具 {message.name} 执行完成")

                if full_response:
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                    save_chat_to_db("assistant", full_response, user_id, st.session_state.conversation_id)

                    # --- SQL 查看与保护逻辑 ---
                    if st.session_state.last_sql:
                        with st.expander("🔍 查看 SQL 查询语句"):
                                pwd = st.text_input("此操作受保护，请输入复制密码", type="password", key=f"pwd_{st.session_state.conversation_id}")
                                if pwd == "Aohua1688":
                                    st.code(st.session_state.last_sql, language="sql")
                                    st.button("📋 已显示，请手动复制", disabled=True)
                                elif pwd:
                                    st.error("密码错误")

                    # 5. RAG 自进化：添加人工审核按钮
                    if st.button("👍 采纳为业务经验", key=f"verify_{st.session_state.last_question_id}"):
                        rag_manager.add_answer(full_response, st.session_state.last_question_id, {"user_id": user_id, "verified": True})
                        st.success("已存入业务经验库！")

                    st.rerun() # 完成回复后 rerun，回到显示模式

        except Exception as e:
                error_msg = f"❌ 运行出错: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

# 侧边栏系统状态
with st.sidebar:
   st.divider()
   st.header("⚙️ 系统设置")
   if ckread:
       st.success("数据库已连接")
   else:
       st.error("数据库连接失败")
   
   if st.button("🗑️ 清空当前对话历史"):
       try:
           # 1. 清空本地记录中该会话的消息
           local_file = os.path.join("chat_history", f"{user_id}.json")
           if os.path.exists(local_file):
               with open(local_file, "r", encoding="utf-8") as f:
                   history_data = json.load(f)
               
               new_history = [item for item in history_data if item.get("conversation_id") != st.session_state.conversation_id]
               
               with open(local_file, "w", encoding="utf-8") as f:
                   json.dump(new_history, f, ensure_ascii=False, indent=2)

           # 2. 尝试清空数据库记录
           combined_id = f"{user_id}:{st.session_state.conversation_id}"
           # 注意：ckread 账号可能没有 DELETE 权限，如果报错则仅清空内存
           ckread.command(f"ALTER TABLE alphafeed.agent_chat_history DELETE WHERE session_id = '{combined_id}'")
       except Exception as e:
           # 简化日志
           if "ACCESS_DENIED" not in str(e):
               logger.warning(f"删除聊天记录失败: {str(e)[:100]}...")
           st.warning("由于数据库权限限制，已仅清空本地显示与备份。")
       st.session_state.messages = []
       st.rerun()
