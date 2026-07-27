import json
import os
import re
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from main import agent_executor

def run_eval():
    cases_file = "eval_cases.json"
    if not os.path.exists(cases_file):
        print(f"Error: {cases_file} not found.")
        return

    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    print(f"开始执行评估，共 {len(cases)} 个用例...\n")

    for i, case in enumerate(cases):
        question = case["question"]
        print(f"[{i+1}/{len(cases)}] 测试问题: {question}")
        
        # 调用 agent
        inputs = {"messages": [HumanMessage(content=question)]}
        generated_sql = ""
        
        try:
            # 我们需要获取 agent 调用的工具和参数
            # 在 create_react_agent 中，工具调用记录在 AIMessage 中
            tool_calls_info = []
            for chunk in agent_executor.stream(inputs, stream_mode="values"):
                messages = chunk["messages"]
                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            # 记录工具名和所有参数的字符串，用于匹配校验
                            call_summary = f"{tool_call['name']}({json.dumps(tool_call['args'], ensure_ascii=False)})"
                            if call_summary not in tool_calls_info:
                                tool_calls_info.append(call_summary)
                            
                            # 兼容旧逻辑：如果是 execute_query，提取其 sql 字段
                            if tool_call["name"] == "execute_query":
                                generated_sql = tool_call["args"].get("sql", "")
            
            # 将所有工具调用合并为一个字符串用于片段匹配
            full_context = " ".join(tool_calls_info) + " " + generated_sql
            
            # 验证结果
            passed = True
            missing_fragments = []
            if not tool_calls_info and not generated_sql:
                passed = False
                missing_fragments = ["(未检测到任何工具调用或 SQL 生成)"]
            else:
                for fragment in case["must_contain_sql"]:
                    if fragment.lower() not in full_context.lower():
                        passed = False
                        missing_fragments.append(fragment)

            status = "✅ 通过" if passed else "❌ 失败"
            print(f"结果: {status}")
            if not passed:
                print(f"  缺失片段: {missing_fragments}")
                print(f"  工具调用: {tool_calls_info}")
                print(f"  生成的 SQL: {generated_sql}")
            print("-" * 40)

            results.append({
                "question": question,
                "passed": passed,
                "tool_calls": tool_calls_info,
                "generated_sql": generated_sql,
                "missing_fragments": missing_fragments
            })
        except Exception as e:
            print(f"❌ 执行出错: {e}")
            results.append({
                "question": question,
                "passed": False,
                "error": str(e)
            })

    # 汇总
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    print(f"\n评估完成!")
    print(f"总计: {total}, 通过: {passed_count}, 失败: {total - passed_count}")
    print(f"通过率: {(passed_count/total)*100:.2f}%")

if __name__ == "__main__":
    run_eval()
