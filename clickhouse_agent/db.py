import clickhouse_connect
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
load_dotenv('.env')
load_dotenv('../.env')

# 连接数据库 - 必须通过环境变量或 .env 配置
# 连接失败时不崩模块导入，留 ckread=None 让调用方判定
CK_HOST = os.getenv('CK_HOST', '')
CK_PORT = int(os.getenv('CK_PORT', '8123'))
CK_USER = os.getenv('CK_USER', 'ckread')
CK_PASSWORD = os.getenv('CK_PASSWORD', '')

if CK_HOST and CK_PASSWORD:
    try:
        ckread = clickhouse_connect.get_client(
            host=CK_HOST,
            port=CK_PORT,
            username=CK_USER,
            password=CK_PASSWORD,
            connect_timeout=5
        )
    except Exception as e:
        import warnings
        warnings.warn(f'ClickHouse 连接失败，将以离线模式运行: {e}')
        ckread = None
else:
    import warnings
    warnings.warn('未配置 CK_HOST 或 CK_PASSWORD，将以离线模式运行')
    ckread = None
