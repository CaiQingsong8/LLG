#!/bin/bash

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

echo "正在启动 ClickHouse 智能查询助手..."
echo "脚本目录: $SCRIPT_DIR"
echo "项目根目录: $PROJECT_ROOT"

# 设置 PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$SCRIPT_DIR

# 切换到项目根目录，以便 load_dotenv 能找到 .env
cd "$PROJECT_ROOT"

# 运行 Streamlit
streamlit run p6/streamlit_db_agent.py
