"""
アプリケーション設定モジュール。
環境変数および .env ファイルから設定値を読み込む。
"""

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """アプリケーション全体の設定クラス。"""

    # AWS Bedrock
    BEDROCK_REGION: str = "ap-northeast-1"
    BEDROCK_MODEL_ID: str = "jp.anthropic.claude-sonnet-4-6"
    BEDROCK_EMBED_MODEL_ID: str = "cohere.embed-multilingual-v3"
    BEDROCK_RERANK_MODEL_ID: str = "cohere.rerank-v3-5:0"

    # Oracle DB
    ORACLE_DSN: str = ""
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_ENABLED: bool = True
    ORACLE_POOL_MIN: int = 2
    ORACLE_POOL_MAX: int = 10
    ORACLE_QUERY_TIMEOUT: int = 30
    ORACLE_ROW_LIMIT: int = 500

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_COLLECTION: str = "documents"
    QDRANT_MASTER_COLLECTION: str = "master_data"

    # SQLite
    SQLITE_DB_PATH: str = "/app/data/ragphantom.db"

    # ファイルアップロード
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    MAX_BATCH_UPLOAD_FILES: int = 20
    MAX_BATCH_UPLOAD_SIZE: int = 200 * 1024 * 1024  # 200MB
    ALLOWED_EXTENSIONS: list[str] = [
        "md",
        "txt",
        "csv",
        "json",
        "pdf",
        "pptx",
        "xlsx",
        "docx",
        "png",
        "jpeg",
        "jpg",
        "html",
    ]
    UPLOAD_DIR: str = "/app/uploads"

    # マスターデータ
    MASTER_MD_PATH: str = "/app/data/master-flat-with-place-aliases.md"

    # RAG
    RELEVANCE_THRESHOLD: float = 0.3
    QUERY_EXPANSION_COUNT: int = 3

    # セキュリティ
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://10.168.124.32:3000",
        "https://10.168.124.32:3443",
    ]

    # 外部 API キー
    API_KEYS: list[str] = ["the-rag-default-key"]

    # エラーリトライ
    MAX_RETRY_COUNT: int = 3

    # エージェンティック検索
    AGENTIC_MAX_ITERATIONS: int = 10
    AGENTIC_LOOP_TIMEOUT: int = 120  # 秒

    # Gitea 連携（GitHub API レート制限回避用のセカンダリソース）
    # 例: GITEA_BASE_URL="https://gitea.example.com"
    GITEA_BASE_URL: str = ""
    GITEA_TOKEN: str = ""

    # フォルダソース
    FOLDER_SOURCE_MAX_FILES: int = 100

    # ソフトデリート
    SOFT_DELETE_RETENTION_DAYS: int = 30

    model_config = {"env_file": ".env"}


# アプリケーション全体で使用するシングルトン設定インスタンス
config = Config()
