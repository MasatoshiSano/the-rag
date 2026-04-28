"""
テキスト正規化サービスモジュール。
全角・半角統一などのテキスト前処理機能を提供する。
"""

import unicodedata


def normalize_text(text: str) -> str:
    """
    テキストを NFKC 正規化する。
    全角英数字の半角化、カタカナの正規化などを行う。
    RAG の検索精度向上のために使用する。

    Args:
        text: 正規化対象のテキスト文字列。

    Returns:
        NFKC 正規化されたテキスト文字列。
    """
    return unicodedata.normalize("NFKC", text)


def normalize_query(query: str) -> str:
    """
    検索クエリを正規化する。
    NFKC 正規化に加えて、前後の空白を除去し、連続空白を単一スペースに統一する。

    Args:
        query: 正規化対象のクエリ文字列。

    Returns:
        正規化されたクエリ文字列。
    """
    normalized = normalize_text(query)
    # 前後の空白を除去し、連続した空白を単一スペースに統一する
    return " ".join(normalized.split())
