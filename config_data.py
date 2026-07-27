import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----- 向量数据库配置 -----
collection_name = "rag"                          # Chroma 集合名
persist_directory = "./chroma_db"                 # 向量数据库持久化路径

# ----- 文本分割配置 -----
chunk_size = 1000                                # 分割的最大长度
chunk_overlap = 100                              # 相邻片段重叠字符数
separators = ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]  # 分割符
max_split_char_number = 1                        # 超过此长度才分割
similarity_threshold = 1                         # 检索返回的文档数量

# ----- 模型配置 -----
embedding_model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-v1")
chat_model_name = os.getenv("OPENAI_MODEL", "deepseek-chat")

# ----- MD5 文件去重配置 -----
md5_path = os.path.join(BASE_DIR, 'md5.text')

# ----- 会话配置 -----
session_config = {"configurable": {"session_id": "user_001"}}
