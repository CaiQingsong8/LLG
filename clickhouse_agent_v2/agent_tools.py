"""Agent 可调用的工具函数集合。"""
import re
import sqlparse
from datetime import datetime

from langchain_core.tools import tool
from tabulate import tabulate

from database import get_ck
from config import settings


# ==================== 0. 全局状态占位符（由 app.py 在初始化时注入）====================
# 避免循环导入：session_state 引用由调用方注入
_rag_manager = None

def inject_deps(rag_manager):
    global _rag_manager
    _rag_manager = rag_manager


# ==================== 1. 模板工具（Slot Filling）====================

@tool
def query_feed_sales(
    month: str | None = None,
    client_type: str = "外部",
    class_codes: list[str] | None = None,
    corp_ids: list[str] | None = None,
    client_ids: list[str] | None = None,
    material_ids: list[str] | None = None,
) -> str:
    """查询饲料销量（模板工具）。按月、客户类型、分类、公司/客户/物料 ID 过滤。"""
    ck = get_ck()
    if not ck:
        return "❌ 数据库未连接"

    target_month = month
    clauses = ["dr = '0'"]

    if target_month == "all":
        pass
    elif not target_month:
        now = datetime.now()
        last_month = now.replace(day=1)
        from datetime import timedelta
        last_month = last_month - timedelta(days=1)
        target_month = last_month.strftime("%Y-%m")
        clauses.append(f"month_dt = '{target_month}'")
    else:
        clauses.append(f"month_dt = '{target_month}'")

    if corp_ids:
        ids = ", ".join(f"'{c}'" for c in corp_ids)
        clauses.append(f"d_corp_id IN ({ids})")
    if client_ids:
        ids = ", ".join(f"'{c}'" for c in client_ids)
        clauses.append(f"d_client_id IN ({ids})")
    if material_ids:
        ids = ", ".join(f"'{m}'" for m in material_ids)
        clauses.append(f"d_material_id IN ({ids})")
    if class_codes:
        ids = ", ".join(f"'{c}'" for c in class_codes)
        clauses.append(f"d_class_code2 IN ({ids})")
    if client_type == "外部":
        clauses.append("client_class_flag = '0'")
    elif client_type == "内部":
        clauses.append("client_class_flag = '1'")

    sql = f"SELECT sum(f_sale_num) AS total_sales FROM alphafeed.dwd_so_saleorder WHERE {' AND '.join(clauses)}"
    try:
        result = ck.query(sql)
        val = result.result_rows[0][0] if result.result_rows else None
        if val is None:
            return f"在 {target_month or '全量'} 未找到符合条件的数据。"
        return f"【饲料销量】{target_month or '全量历史'} = {val}"
    except Exception as e:
        return f"查询出错: {e}"


@tool
def query_new_clients(year: str | None = None, client_type: str = "全部") -> str:
    """查询新客户列表（模板工具）。"""
    ck = get_ck()
    if not ck:
        return "❌ 数据库未连接"

    year = year or datetime.now().strftime("%Y")
    clauses = [f"opening_date LIKE '{year}%'"]
    if client_type == "外部":
        clauses.append("custclass_flag = 0")
    elif client_type == "内部":
        clauses.append("custclass_flag = 1")

    sql = f"SELECT d_client_id, d_client_name, opening_date FROM alphafeed.dim_client WHERE {' AND '.join(clauses)} LIMIT 100"
    try:
        result = ck.query(sql)
        rows, cols = result.result_rows, result.column_names
        if not rows:
            return f"{year} 年未找到新客户。"
        # FixedString 查出来是 bytes，转一下
        formatted = [[v.decode() if isinstance(v, bytes) else str(v) for v in row] for row in rows[:50]]
        output = tabulate(formatted, headers=cols, tablefmt="grid")
        if len(rows) > 50:
            output += f"\n(显示前 50 行, 共 {len(rows)} 行)"
        return f"【新客户】{year} 年:\n{output}"
    except Exception as e:
        return f"查询出错: {e}"


# ==================== 2. 通用工具 =====================

@tool
def get_current_time() -> str:
    """获取当前系统时间（处理相对时间时先调用）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def search_business_knowledge(query: str) -> str:
    """搜索已维护的业务定义、统计口径、历史经验。处理业务问题时必须先查。"""
    if not _rag_manager:
        return "知识库未初始化"
    result = _rag_manager.search_knowledge(query, limit=3)

    # 同时搜索历史相似问答
    q_results = _rag_manager.search_questions(query, limit=2)
    for qr in q_results:
        answer = _rag_manager.search_answers_by_question(qr["id"])
        if answer:
            result += (
                f"\n【历史相似案例（提问 {qr['count']} 次）】\n"
                f"问题: {qr['question']}\n"
                f"参考答案: {answer[:500]}\n"
            )
    return result or f"未找到 '{query}' 的相关业务知识。"


@tool
def list_tables(keyword: str | None = None, database: str = "alphafeed") -> str:
    """列出数据库中的表名及注释，支持关键词过滤。"""
    ck = get_ck()
    if not ck:
        return "❌ 数据库未连接"
    try:
        safe_kw = re.escape(keyword) if keyword else None
        if safe_kw:
            sql = (
                f"SELECT name, comment FROM system.tables "
                f"WHERE database = 'alphafeed' "
                f"AND (name ILIKE '%{safe_kw}%' OR comment ILIKE '%{safe_kw}%')"
            )
        else:
            sql = "SELECT name, comment FROM system.tables WHERE database = 'alphafeed'"
        rows = ck.query(sql).result_rows
        if not rows:
            return f"未找到匹配 '{keyword}' 的表。"
        info = [f"  {r[0]}  ({r[1]})" for r in rows]
        return f"相关表:\n" + "\n".join(info)
    except Exception as e:
        return f"列出表出错: {e}"


@tool
def describe_table(table_name: str, database: str = "alphafeed") -> str:
    """获取表的列信息（列名、类型、注释）。"""
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        return f"非法表名: {table_name}"
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        return f"非法数据库名: {database}"
    ck = get_ck()
    if not ck:
        return "❌ 数据库未连接"
    try:
        rows = ck.query(f"DESCRIBE TABLE `{database}`.`{table_name}`").result_rows
        data = [[r[0], r[1], r[4]] for r in rows]
        return tabulate(data, headers=["列名", "类型", "注释"], tablefmt="grid")
    except Exception as e:
        return f"获取表结构出错: {e}"


@tool
def execute_query(sql: str) -> str:
    """执行 SELECT 查询（仅限单条 SELECT）。自动追加 LIMIT 50。"""
    ck = get_ck()
    if not ck:
        return "❌ 数据库未连接"

    parsed = sqlparse.parse(sql)
    if len(parsed) != 1 or parsed[0].get_type() != "SELECT":
        return "错误：仅支持单条 SELECT。"
    if re.search(r"\b(DELETE|DROP|UPDATE|TRUNCATE|ALTER|INSERT|GRANT|REPLACE)\b", sql, re.IGNORECASE):
        return "错误：检测到危险关键字。"

    if "limit" not in sql.lower():
        sql = sql.rstrip(";") + " LIMIT 50"
    try:
        result = ck.query(sql)
        rows, cols = result.result_rows, result.column_names
        if not rows:
            return "查询成功，无结果。"
        output = tabulate(rows[:50], headers=cols, tablefmt="grid")
        if len(rows) > 50:
            output += f"\n(前 50 行, 共 {len(rows)} 行)"
        return output
    except Exception as e:
        return f"查询出错: {e}"
