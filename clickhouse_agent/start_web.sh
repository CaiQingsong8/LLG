#!/bin/bash
# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 设置 PYTHONPATH 包含当前目录以便导入 db.py
export PYTHONPATH=$PYTHONPATH:$SCRIPT_DIR
# 切换到脚本所在目录运行，确保相对路径正确
cd "$SCRIPT_DIR"
# 启动 Streamlit
streamlit run main.py
