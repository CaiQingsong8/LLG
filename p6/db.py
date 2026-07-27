
import clickhouse_connect
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

CK_HOST = os.getenv("CK_HOST", "")
CK_PORT = int(os.getenv("CK_PORT", "8123"))
CK_USER = os.getenv("CK_USER", "ckread")
CK_PASSWORD = os.getenv("CK_PASSWORD", "")

if not CK_HOST or not CK_PASSWORD:
    raise RuntimeError("❌ 请配置 CK_HOST 和 CK_PASSWORD（可在 .env 中设置）")

# 连接数据库
ckread = clickhouse_connect.get_client(
    host=CK_HOST,
    port=CK_PORT,
    username=CK_USER,
    password=CK_PASSWORD
)