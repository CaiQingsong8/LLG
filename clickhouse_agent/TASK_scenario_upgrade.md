# 任务：升级 ClickHouse Text2SQL Agent

## 背景
现有文件 main.py 是一个基于 LangGraph create_react_agent 的 Streamlit 应用，
已有工具：get_current_time, search_business_knowledge, list_tables, describe_table, execute_query。
已有 business_knowledge.json 存自然语言业务规则。

## 需要新增/修改的内容

### 1. 新增结构化查询工具（Slot Filling 模式）
为 business_knowledge.json 里的每条高频场景，生成对应的 Pydantic 参数类 + 
build_xxx_sql() 拼接函数 + @tool 包装。参考模式：

```python
class FeedSaleQueryParams(BaseModel):
    month: str = Field(None, description="查询月份，格式为 'YYYY-MM'。如果不提供，默认查上月。")
    client_type: str = Field("外部", description="客户类型，可选值：'外部'、'内部'、'全部'。默认为'外部'。")
    class_codes: List[str] = Field(["21", "22"], description="分类代码列表。默认为饲料分类 ['21', '22']。")

@tool
def query_feed_sales(params: FeedSaleQueryParams) -> str:
    # 逻辑实现...
```

请先读 business_knowledge.json 里现有条目，按同样模式为每条生成对应工具，
硬约束条件（dr='0'、内外部客户过滤等）必须写死在 build_xxx_sql 里，不能作为可选参数。

### 2. 安全修复
- execute_query: 用 `len(parsed) != 1` 替换现有的单语句判断（当前有多语句注入风险）
- user_id: 新增 validate_user_id()，正则 `^[A-Za-z0-9_\-]{1,50}$`，入口处立即校验

### 3. system_prompt 更新
在业务逻辑检索步骤之后，新增一条：如果问题匹配已有结构化工具（工具名+docstring 里列出的场景），
必须优先调用该工具，不允许自己拼 SQL。

### 4. 新增 eval.py
维护一份测试用例列表（question + must_contain_sql 关键字断言），
跑一遍所有工具，输出通过/失败清单，用于每次改动后回归验证。

## 约束
- ClickHouse 连接复用现有 db.py 的 ckread
- 不引入 Vanna、semantic-router 等新依赖，只用现有 langchain/langgraph/pydantic
- 每个新工具函数附带完整 docstring，说明命中场景和参数含义
