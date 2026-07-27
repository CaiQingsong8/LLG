import numpy as np
import sys
import json
import os
import warnings
from typing import Dict, List, Optional
from db import ckread  # 你的数据库连接
from tabulate import tabulate
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

load_dotenv(find_dotenv())
warnings.filterwarnings("ignore")

# ==================== 1. 封装的分析逻辑 ====================

class SalesAnalyzer:
    """销售数据分析工具类"""

    def __init__(self):
        self.default_start = '2025-01'
        self.default_end = '2026-01'

    def fetch_data(self, start_month: str, end_month: str):
        """从数据库获取指定区间的月度销量数据"""
        sql = f"""
        SELECT 
            month_dt,
            SUM(f_sale_num) AS total_qty
        FROM alphafeed.dwd_so_saleorder
        WHERE client_class_flag = '0'
          AND month_dt BETWEEN '{start_month}' AND '{end_month}'
        GROUP BY month_dt
        ORDER BY month_dt
        """
        rows = ckread.query(sql).result_rows
        if not rows:
            return [], np.array([])
        months = [row[0] for row in rows]
        qtys = np.array([float(row[1]) for row in rows])
        return months, qtys

    def get_monthly_data(self, start_month: str = None, end_month: str = None) -> Dict:
        """获取月度销量数据、环比、同比"""
        start = start_month or self.default_start
        end = end_month or self.default_end
        months, qtys = self.fetch_data(start, end)

        if len(qtys) == 0:
            return {"error": f"在 {start} 到 {end} 期间未找到数据"}

        # 环比
        if len(qtys) > 1:
            mom = np.diff(qtys) / qtys[:-1] * 100
            mom = [None] + list(mom)
        else:
            mom = [None]

        # 同比（需要至少13个月）
        if len(qtys) >= 13:
            yoy = (qtys[12:] - qtys[:-12]) / qtys[:-12] * 100
            yoy = [None] * 12 + list(yoy)
        else:
            yoy = [None] * len(qtys)

        return {
            'months': months,
            'qtys': qtys.tolist(),
            'mom': mom,
            'yoy': yoy,
            'total': sum(qtys),
            'avg': float(np.mean(qtys)),
            'max': float(np.max(qtys)),
            'max_month': months[np.argmax(qtys)],
            'min': float(np.min(qtys)),
            'min_month': months[np.argmin(qtys)]
        }

analyzer = SalesAnalyzer()

# ==================== 2. 定义工具 (Tools) ====================

@tool
def get_sales_summary(start_month: str = None, end_month: str = None) -> str:
    """获取销量汇总信息，包括总销量、月均销量、最高最低月份等。参数格式 YYYY-MM。"""
    data = analyzer.get_monthly_data(start_month, end_month)
    if "error" in data: return data["error"]
    
    summary = f"""
数据周期：{data['months'][0]} 至 {data['months'][-1]}
总销量：{data['total']:,.0f} 件
月均销量：{data['avg']:.0f} 件
最高销量月份：{data['max_month']}（{data['max']:,.0f} 件）
最低销量月份：{data['min_month']}（{data['min']:,.0f} 件）
    """
    return summary.strip()

@tool
def get_sales_table(start_month: str = None, end_month: str = None) -> str:
    """获取月度销量明细表格，包含每月销量、环比、同比。参数格式 YYYY-MM。"""
    data = analyzer.get_monthly_data(start_month, end_month)
    if "error" in data: return data["error"]

    table_data = []
    for i, m in enumerate(data['months']):
        row = [
            m,
            f"{data['qtys'][i]:,.0f}",
            f"{data['mom'][i]:+.1f}%" if data['mom'][i] is not None else '-',
            f"{data['yoy'][i]:+.1f}%" if data['yoy'][i] is not None else '-'
        ]
        table_data.append(row)
    headers = ["月份", "销量", "环比", "同比"]
    return tabulate(table_data, headers=headers, tablefmt="grid")

@tool
def get_trend_analysis(start_month: str = None, end_month: str = None) -> str:
    """分析销售趋势，返回增长或下降的描述。参数格式 YYYY-MM。"""
    data = analyzer.get_monthly_data(start_month, end_month)
    if "error" in data: return data["error"]
    
    months = data['months']
    qtys = data['qtys']
    if len(qtys) < 2:
        return "数据不足，无法分析趋势。"

    first = qtys[0]
    last = qtys[-1]
    change = last - first
    pct = (change / first) * 100 if first != 0 else 0
    
    if pct > 10: trend = "显著上升"
    elif pct > 0: trend = "温和上升"
    elif pct > -10: trend = "基本持平"
    else: trend = "显著下降"

    recent_avg = np.mean(qtys[-3:]) if len(qtys) >= 3 else last
    overall_avg = np.mean(qtys)
    diff_pct = (recent_avg / overall_avg - 1) * 100 if overall_avg != 0 else 0

    result = f"整体趋势：{trend}（从{months[0]}的{first:,.0f}件到{months[-1]}的{last:,.0f}件，变化{pct:+.1f}%）\n"
    if len(qtys) >= 3:
        result += f"近三个月平均销量{recent_avg:.0f}件，相比整体均值{overall_avg:.0f}件，{('高出' if diff_pct > 0 else '低于')}{abs(diff_pct):.1f}%"
    return result

# ==================== 3. 构建 Agent ====================

# 配置模型
llm = ChatOpenAI(
    model=os.getenv("DS_MODEL", "deepseek-chat"),
    api_key=os.getenv("DS_API_KEY"),
    base_url=os.getenv("DS_BASE_URL"),
    temperature=0.1
)

# 系统提示词
system_prompt = """你是一个专业的销售数据分析助手。
你可以使用工具来获取 ClickHouse 数据库中的销量数据。
默认查询范围是 2025-01 到 2026-01。
如果用户提问涉及时间，请准确提取并传递给工具。
回答要专业、客观，多使用数据支持你的观点。"""

# 创建 ReAct Agent
agent_executor = create_react_agent(
    model=llm,
    tools=[get_sales_summary, get_sales_table, get_trend_analysis],
    prompt=system_prompt
)

if __name__ == "__main__":
    print("🚀 销售数据智能助手已启动")
    print("（可提问：销售趋势、月度明细、汇总统计等）")
    print("输入 '退出' 结束对话\n")

    while True:
        user_input = input("👤 你：")
        if user_input.lower() in ['退出', 'exit', 'quit']:
            print("👋 再见！")
            break
        
        print("\n🤖 助手：")
        inputs = {"messages": [("user", user_input)]}
        for chunk in agent_executor.stream(inputs, stream_mode="values"):
            message = chunk["messages"][-1]
            if message.type == "ai" and message.content:
                print(message.content)
            elif message.type == "ai" and message.tool_calls:
                for tool_call in message.tool_calls:
                    print(f"🛠️  正在查询数据库: {tool_call['name']}...")
        print()