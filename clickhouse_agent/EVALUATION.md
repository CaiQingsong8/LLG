# ClickHouse 智能助手评估体系 (Evaluation System)

为了确保“越维护越准确”，本项目引入了自动化的评估体系。

## 1. 核心组件

- **`eval_cases.json`**: 存储标准测试用例（问答对）。
  - `question`: 用户提问。
  - `must_contain_sql`: 生成的 SQL 中必须包含的关键片段（用于验证逻辑准确性）。
  - `description`: 用例说明。
- **`eval_runner.py`**: 执行评估的脚本。
  - 它会加载 `main.py` 中的 Agent 逻辑，模拟用户提问。
  - 自动捕获 Agent 生成的 SQL 并进行断言校验。
  - 输出通过率报告。

## 2. 如何使用

在开发过程中，每当你修改了 `business_knowledge.json`（业务知识库）、更新了 `main.py` 中的 Prompt 或更换了模型配置后，请运行以下命令进行回归测试：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 eval_runner.py
```

## 3. 如何添加测试用例

当你发现 AI 对某个真实问题回答错误时，请将其修复（通过更新业务知识库或 Prompt），并将其补充到 `eval_cases.json` 中，以防止未来出现回归错误。

```json
{
    "question": "新的业务问题",
    "must_contain_sql": ["关键字段1", "关键逻辑2"],
    "description": "说明该用例验证了什么"
}
```

## 4. 评估维度
目前的评估主要基于 **SQL 关键片段匹配**。后续可以扩展：
- **结果行数校验**: 验证 `expected_row_count_min`。
- **语义相似度**: 使用模型对回答的准确性进行评分。
