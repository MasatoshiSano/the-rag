"""
ORM データベースモデルモジュール。
SQLAlchemy 2.0 スタイルの宣言型マッピングを使用して全テーブルを定義する。

datetime フィールドは ISO 8601 文字列として TEXT 型で格納する。
JSON フィールドは JSON 文字列として TEXT 型で格納する。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import REAL, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db import Base


class User(Base):
    """ユーザー設定・プロファイルモデル。id は localStorage の UUID を使用する。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    nickname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rerank_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hybrid_search_enabled: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    retrieval_count: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    response_mode: Mapped[str] = mapped_column(Text, default="detailed", nullable=False)
    search_mode: Mapped[str] = mapped_column(Text, default="agentic", nullable=False)
    agentic_max_iterations: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    user_behavior: Mapped[Optional[UserBehavior]] = relationship(
        "UserBehavior",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_memories: Mapped[list[UserMemory]] = relationship(
        "UserMemory", back_populates="user", cascade="all, delete-orphan"
    )
    knowledge_bases: Mapped[list[KnowledgeBase]] = relationship(
        "KnowledgeBase",
        back_populates="creator",
        foreign_keys="KnowledgeBase.created_by",
    )
    knowledge_base_favorites: Mapped[list[KnowledgeBaseFavorite]] = relationship(
        "KnowledgeBaseFavorite", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    uploaded_documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="uploader", foreign_keys="Document.uploaded_by"
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, nickname={self.nickname!r})"


class UserBehavior(Base):
    """ユーザー行動ログモデル。user_id はユニーク（1ユーザー1レコード）。"""

    __tablename__ = "user_behaviors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id"), unique=True, nullable=False
    )
    frequent_lines: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    frequent_categories: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON
    recent_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="user_behavior")

    def __repr__(self) -> str:
        return f"UserBehavior(id={self.id!r}, user_id={self.user_id!r})"


class UserMemory(Base):
    """ユーザーメモリモデル。Gemini の「自分について」のように自由テキストで保存する。

    source が "manual" の場合はユーザーが手動で追加したメモリ、
    "auto" の場合は会話履歴から自動生成されたメモリを表す。
    """

    __tablename__ = "user_memories"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, default="manual", nullable=False
    )  # 'manual' | 'auto'
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="user_memories")

    def __repr__(self) -> str:
        return f"UserMemory(id={self.id!r}, content={self.content[:30]!r})"


class KnowledgeBase(Base):
    """ナレッジベースモデル。複数のドキュメントをグループ化する。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(Text, default="#6366f1", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    creator: Mapped[Optional[User]] = relationship(
        "User", back_populates="knowledge_bases", foreign_keys=[created_by]
    )
    favorites: Mapped[list[KnowledgeBaseFavorite]] = relationship(
        "KnowledgeBaseFavorite",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[Session]] = relationship(
        "Session", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    github_sources: Mapped[list[GitHubSource]] = relationship(
        "GitHubSource", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    gitea_sources: Mapped[list[GiteaSource]] = relationship(
        "GiteaSource", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    folder_sources: Mapped[list[FolderSource]] = relationship(
        "FolderSource", back_populates="knowledge_base", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"KnowledgeBase(id={self.id!r}, name={self.name!r})"


class KnowledgeBaseFavorite(Base):
    """ナレッジベースお気に入りモデル。user_id と knowledge_base_id の組み合わせはユニーク。"""

    __tablename__ = "knowledge_base_favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "knowledge_base_id",
            name="uq_kb_favorites_user_id_knowledge_base_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="knowledge_base_favorites")
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="favorites"
    )

    def __repr__(self) -> str:
        return f"KnowledgeBaseFavorite(id={self.id!r}, user_id={self.user_id!r}, knowledge_base_id={self.knowledge_base_id!r})"


class Session(Base):
    """チャットセッションモデル。ユーザーとナレッジベースを紐付ける。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("users.id"), nullable=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    user: Mapped[Optional[User]] = relationship("User", back_populates="sessions")
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="sessions"
    )
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Session(id={self.id!r}, title={self.title!r})"


class Message(Base):
    """チャットメッセージモデル。FTS5 仮想テーブルと同期される。"""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("sessions.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    input_type: Mapped[str] = mapped_column(
        Text, default="text", nullable=False
    )  # 'text' | 'voice'
    response_mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_cancelled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    session: Mapped[Optional[Session]] = relationship(
        "Session", back_populates="messages"
    )
    chat_output: Mapped[Optional[ChatOutput]] = relationship(
        "ChatOutput",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Message(id={self.id!r}, role={self.role!r})"


class Document(Base):
    """ドキュメントモデル。RAG パイプラインの処理状態を管理する。"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    converted_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_document_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("documents.id"), nullable=True
    )
    # status enum values:
    # processing / converting / converted / tagging / tagged / confirmed
    # chunking / chunked / indexing / indexed
    # convert_failed / tag_failed / index_failed / permanent_failed / cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="documents"
    )
    uploader: Mapped[Optional[User]] = relationship(
        "User", back_populates="uploaded_documents", foreign_keys=[uploaded_by]
    )
    parent_document: Mapped[Optional[Document]] = relationship(
        "Document", back_populates="child_documents", remote_side="Document.id"
    )
    child_documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="parent_document"
    )
    tags: Mapped[list[DocumentTag]] = relationship(
        "DocumentTag", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Document(id={self.id!r}, filename={self.filename!r}, status={self.status!r})"


class DocumentTag(Base):
    """ドキュメントタグモデル。AI によるタグ付け結果を格納する。"""

    __tablename__ = "document_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("documents.id"), nullable=False
    )
    tag_key: Mapped[str] = mapped_column(Text, nullable=False)
    tag_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, default=0.0, nullable=False)
    ai_suggested: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="tags")

    def __repr__(self) -> str:
        return f"DocumentTag(id={self.id!r}, tag_key={self.tag_key!r}, tag_value={self.tag_value!r})"


class ChatOutput(Base):
    """チャット出力モデル。テーブル・チャートなどの構造化出力を格納する。"""

    __tablename__ = "chat_outputs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    message_id: Mapped[str] = mapped_column(
        Text, ForeignKey("messages.id"), nullable=False
    )
    output_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # 'table' | 'chart' | 'both'
    table_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    chart_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    sql_executed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    message: Mapped[Message] = relationship("Message", back_populates="chat_output")

    def __repr__(self) -> str:
        return f"ChatOutput(id={self.id!r}, output_type={self.output_type!r})"


class OracleQueryTemplate(Base):
    """Oracle クエリテンプレートモデル。再利用可能な SQL テンプレートを格納する。"""

    __tablename__ = "oracle_query_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    def __repr__(self) -> str:
        return f"OracleQueryTemplate(id={self.id!r}, name={self.name!r})"


class MasterSite(Base):
    """マスタサイトモデル。製造拠点の正規表現と別名を管理する。"""

    __tablename__ = "master_sites"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    # Relationships
    lines: Mapped[list[MasterLine]] = relationship(
        "MasterLine", back_populates="site", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"MasterSite(code={self.code!r}, name={self.name!r})"


class MasterLine(Base):
    """マスタラインモデル。製造ラインの正規表現と別名を管理する。"""

    __tablename__ = "master_lines"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    site_code: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("master_sites.code"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    # Relationships
    site: Mapped[Optional[MasterSite]] = relationship(
        "MasterSite", back_populates="lines"
    )
    processes: Mapped[list[MasterProcess]] = relationship(
        "MasterProcess", back_populates="line", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"MasterLine(code={self.code!r}, name={self.name!r})"


class MasterProcess(Base):
    """マスタプロセスモデル。製造工程の詳細情報を管理する。"""

    __tablename__ = "master_processes"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    line_code: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("master_lines.code"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tm_class: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dt_class: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    station_no1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    station_no2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    station_no3: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    line: Mapped[Optional[MasterLine]] = relationship(
        "MasterLine", back_populates="processes"
    )

    def __repr__(self) -> str:
        return f"MasterProcess(code={self.code!r}, name={self.name!r})"


class GitHubSource(Base):
    """GitHub 同期設定モデル。ナレッジベースに同期済みのリポジトリ情報を管理する。"""

    __tablename__ = "github_sources"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "repository_url",
            "path",
            "branch",
            name="uq_github_sources_kb_repo_path_branch",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    repository_url: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    branch: Mapped[str] = mapped_column(Text, default="main", nullable=False)
    synced_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="github_sources"
    )

    def __repr__(self) -> str:
        return f"GitHubSource(id={self.id!r}, repository_url={self.repository_url!r})"


class GiteaSource(Base):
    """Gitea 同期設定モデル。ナレッジベースに同期済みの Gitea リポジトリ情報を管理する。"""

    __tablename__ = "gitea_sources"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "repository_url",
            "path",
            "branch",
            name="uq_gitea_sources_kb_repo_path_branch",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    repository_url: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    branch: Mapped[str] = mapped_column(Text, default="main", nullable=False)
    synced_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="gitea_sources"
    )

    def __repr__(self) -> str:
        return f"GiteaSource(id={self.id!r}, repository_url={self.repository_url!r})"


class FolderSource(Base):
    """ローカルフォルダソースモデル。Windows フォルダパスを KB に紐付け、深掘り検索で直接読み取る。"""

    __tablename__ = "folder_sources"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "folder_path",
            name="uq_folder_sources_kb_folder_path",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        Text, ForeignKey("knowledge_bases.id"), nullable=False
    )
    folder_path: Mapped[str] = mapped_column(Text, nullable=False)
    container_path: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(Text, default="document", nullable=False)
    registered_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase", back_populates="folder_sources"
    )

    def __repr__(self) -> str:
        return f"FolderSource(id={self.id!r}, folder_path={self.folder_path!r})"
