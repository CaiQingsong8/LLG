"""用户意图分类：判断是否走 Database Agent。"""
import re

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from config import settings
from ui import is_greeting

# ── 业务关键词（命中则必然走 Agent）──────────────────────────────
_BUSINESS_WORDS = [
    # 销量 / 金额
    "销量", "销售额", "销售金额", "销售数据", "销售情况", "卖了多少",
    "毛利", "利润", "成本", "返利", "折扣", "成交额", "净销量", "净销售额",
    "订单数", "下单数", "订单",
    # 客户
    "客户", "新客户", "新开户", "开户", "外部客户", "内部客户",
    # 公司
    "公司", "集团", "大区", "区域",
    # 物料
    "物料", "原料", "成品", "产品", "品种", "配方", "bom", "BOM",
    # 表 / 数据库
    "表", "数据库", "字段", "列名", "结构", "sql", "SQL", "clickhouse", "ClickHouse",
    "dim_", "dwd_", "dws_", "alphafeed",
    # 统计
    "统计", "报表", "查询", "展示", "数据",
    # 时间相关（带业务语境）
    "销量", "本月", "上月", "本月至今", "今年", "去年", "同比", "环比",
    # 其他
    "饲料", "开票",
]

# ── 非业务关键词（命中则不走 Agent）──────────────────────────────
_GENERAL_WORDS = [
    # 天气
    "天气", "气温", "下雨", "晴天", "台风", "温度",
    # 技术 / 编程
    "python", "java", "代码", "编程", "程序", "怎么写", "怎么用",
    "算法", "函数", "debug", "bug", "git", "docker", "linux",
    # 创意 / 娱乐
    "诗", "诗歌", "故事", "小说", "电影", "音乐", "歌曲", "推荐",
    # 闲聊
    "聊聊", "聊天", "你叫什么", "你几岁", "你是谁", "你能做什么",
    "你会什么", "你是什么", "你有哪些功能",
    # 知识问答
    "什么是", "为什么", "怎么解释", "意思", "含义",
    "哲学", "历史", "科学", "数学", "物理", "化学",
    # 翻译 / 写作
    "翻译", "写一封", "写一段", "总结", "摘要", "润色",
    # 其他明显非业务
    "游戏", "新闻", "食谱", "菜谱", "旅游", "攻略",
]

_BUSINESS_PAT = re.compile("|".join(_BUSINESS_WORDS), re.IGNORECASE)
_GENERAL_PAT = re.compile("|".join(_GENERAL_WORDS), re.IGNORECASE)


def classify(query: str) -> str:
    """返回 'greeting' / 'general' / 'business'。"""
    # 1) 问候快速通道
    if is_greeting(query):
        return "greeting"

    # 2) 业务关键词 → Agent
    if _BUSINESS_PAT.search(query):
        return "business"

    # 3) 非业务关键词 → 普通聊天
    if _GENERAL_PAT.search(query):
        return "general"

    # 4) 模棱两可的走 LLM 判断
    try:
        return _llm_classify(query)
    except Exception:
        # LLM 不可用时，默认走普通聊天（避免用户抱怨）
        return "general"


def _llm_classify(query: str) -> str:
    """用 LLM 判断剩余模糊问题。"""
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    prompt = (
        f"【用户问题】{query}\n\n"
        "判断这是业务查询还是普通聊天？\n"
        "- 业务查询：与公司内部数据直接相关，如销量、客户、配方、物料、数据库表、报表\n"
        "- 普通聊天：所有其他——天气、技术编程、创意写作、闲聊、知识问答、推荐等\n\n"
        "不确定时选「普通」。只回复两个字。"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    answer = resp.content.strip()
    return "business" if answer == "业务" or "业务查询" in answer else "general"
