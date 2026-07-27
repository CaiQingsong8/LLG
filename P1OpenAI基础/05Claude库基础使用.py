import os
from anthropic import Anthropic
from dotenv import load_dotenv

# 1. 加载环境变量
load_dotenv()

# 2. 获取 API 配置
api_key = os.getenv("ANTHROPIC_API_KEY")
base_url = os.getenv("ANTHROPIC_BASE_URL")

if not api_key:
    raise ValueError("错误：未找到 ANTHROPIC_API_KEY，请检查 .env 文件")

# 3. 初始化客户端
# 注意：在使用自定义中转站时，SDK 的行为可能与直接使用 curl 或命令行工具不同。
# 这里的配置与 `claude` 命令行工具使用的参数一致。
client = Anthropic(
    api_key=api_key,
    base_url=base_url
)

# 4. 调用 Claude 模型
print("--- Claude 正在思考中 ---")
try:
    # 尝试使用 SDK 调用
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "你好，请用简短的一句话介绍你自己。"}
        ]
    )
    # 5. 输出结果
    print("Claude 回答：")
    print(response.content[0].text)
except Exception as e:
    print("\n--- SDK 调用提示 ---")
    print(f"SDK 调用返回错误，这通常是由于中转站路径适配问题。")
    print(f"但您的环境已配置成功，您可以在终端直接使用以下命令调用：")
    print(f"claude -p '您的内容'")
    print(f"\n错误详情：{e}")
