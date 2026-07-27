"""配置管理：从 .env / 环境变量加载所有设置。"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
load_dotenv(".env")
load_dotenv("../.env")

PROJECT_ROOT = Path(__file__).parent.resolve()
WORKSPACE_ROOT = PROJECT_ROOT.parent


@dataclass
class Settings:
    # --- LLM ---
    llm_api_key: str = field(default_factory=lambda: os.getenv("DS_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("DS_BASE_URL", "https://api.deepseek.com"))
    llm_model: str = field(default_factory=lambda: os.getenv("DS_MODEL", "deepseek-chat"))
    llm_temperature: float = 0.1

    # --- ClickHouse ---
    ck_host: str = field(default_factory=lambda: os.getenv("CK_HOST", ""))
    ck_port: int = int(os.getenv("CK_PORT", "8123"))
    ck_user: str = field(default_factory=lambda: os.getenv("CK_USER", "ckread"))
    ck_password: str = field(default_factory=lambda: os.getenv("CK_PASSWORD", ""))
    ck_database: str = "alphafeed"
    ck_connect_timeout: int = 10

    # --- 路径 ---
    chroma_dir: str = str(PROJECT_ROOT.parent / "clickhouse_agent" / "chroma_db")
    knowledge_path: str = str(PROJECT_ROOT.parent / "clickhouse_agent" / "business_knowledge.json")
    chat_history_dir: str = str(PROJECT_ROOT / "chat_history")
    user_prefs_dir: str = str(PROJECT_ROOT / "user_preferences")
    prompts_dir: str = str(PROJECT_ROOT / "prompts")

    # --- 存储 ---
    shared_storage: str = "/mnt/group_share/ai_agent_datasets"


settings = Settings()
