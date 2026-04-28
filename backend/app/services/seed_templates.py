"""Oracle SQL テンプレート初期データ投入モジュール。"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import OracleQueryTemplate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template definitions
# Each entry maps directly to OracleQueryTemplate columns:
#   name        : UNIQUE identifier (TEXT)
#   description : human-readable Japanese label (TEXT)
#   sql_template: Oracle SQL with named bind variables prefixed by ":" (TEXT)
#   parameters  : JSON string describing each bind variable (TEXT)
# ---------------------------------------------------------------------------

TEMPLATES: list[dict[str, str]] = [
    # ------------------------------------------------------------------
    # 1. 生産トレーサビリティ検索
    # Table: HF1R6M01
    # ------------------------------------------------------------------
    {
        "name": "production_traceability",
        "description": "生産トレーサビリティ検索 - 拠点・ライン・期間を指定して製造実績を取得する",
        "sql_template": (
            "SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, M_SERIAL, INSP_ITEMNAME, MEASURE\n"
            "FROM HF1R6M01\n"
            "WHERE STA_NO1 = :site_code AND STA_NO2 = :line_code\n"
            "  AND MK_DATE BETWEEN :start_date AND :end_date\n"
            "ORDER BY MK_DATE DESC\n"
            "FETCH FIRST 500 ROWS ONLY"
        ),
        "parameters": (
            "["
            '{"name": "site_code", "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code", "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 2. 工程別不良率
    # Table: HF1REM01  (EXCEPT_FLAG IN (0, 1) 必須)
    # ------------------------------------------------------------------
    {
        "name": "defect_rate_by_process",
        "description": "工程別不良率 - 拠点・ライン・期間ごとに工程単位の不良率を集計する",
        "sql_template": (
            "SELECT STA_NO3 AS process_code,\n"
            "       COUNT(*) AS total_count,\n"
            "       SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) AS ng_count,\n"
            "       ROUND(SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS defect_rate\n"
            "FROM HF1REM01\n"
            "WHERE STA_NO1 = :site_code AND STA_NO2 = :line_code\n"
            "  AND MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND EXCEPT_FLAG IN (0, 1)\n"
            "GROUP BY STA_NO3\n"
            "ORDER BY defect_rate DESC"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code",  "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 3. 不良内容別集計
    # Tables: HF1REM01 LEFT JOIN HF1SGM01  (EXCEPT_FLAG IN (0, 1) 必須)
    # ------------------------------------------------------------------
    {
        "name": "defect_detail_by_ng_code",
        "description": "不良内容別集計 - NGコードごとにトラブル種別名と件数を集計する",
        "sql_template": (
            "SELECT NVL(s.TROUBLE_NG_INFO, '未分類') AS defect_type,\n"
            "       COUNT(*) AS ng_count\n"
            "FROM HF1REM01 r\n"
            "LEFT JOIN HF1SGM01 s ON r.NG_CODE = s.CODE_NO\n"
            "WHERE r.OPEFIN_RESULT = 2\n"
            "  AND r.STA_NO1 = :site_code AND r.STA_NO2 = :line_code\n"
            "  AND r.MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND r.EXCEPT_FLAG IN (0, 1)\n"
            "GROUP BY NVL(s.TROUBLE_NG_INFO, '未分類')\n"
            "ORDER BY ng_count DESC"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code",  "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 4. ライン別トラブル発生件数
    # Tables: HF1RFM01 JOIN HF1SGM01  (EXCEPT_FLAG IN (0, 1) 必須)
    # ------------------------------------------------------------------
    {
        "name": "trouble_count_by_line",
        "description": "ライン別トラブル発生件数 - 拠点内の各ラインにおけるトラブル種別ごとの発生件数を集計する",
        "sql_template": (
            "SELECT r.STA_NO2 AS line_code,\n"
            "       s.TROUBLE_NG_INFO AS trouble_type,\n"
            "       COUNT(*) AS trouble_count\n"
            "FROM HF1RFM01 r\n"
            "JOIN HF1SGM01 s ON r.CODE_NO = s.CODE_NO\n"
            "WHERE r.STA_NO1 = :site_code\n"
            "  AND r.T4_UPDATE_CHECK = 4\n"
            "  AND r.MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND r.EXCEPT_FLAG IN (0, 1)\n"
            "GROUP BY r.STA_NO2, s.TROUBLE_NG_INFO\n"
            "ORDER BY trouble_count DESC"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 5. トラブル時系列推移
    # Tables: HF1RFM01 JOIN HF1SGM01  (EXCEPT_FLAG IN (0, 1) 必須)
    # ------------------------------------------------------------------
    {
        "name": "trouble_timeline",
        "description": "トラブル時系列推移 - 拠点・ライン・期間ごとにトラブル種別の日次発生件数を時系列で集計する",
        "sql_template": (
            "SELECT SUBSTR(r.MK_DATE, 1, 8) AS date_str,\n"
            "       s.TROUBLE_NG_INFO AS trouble_type,\n"
            "       COUNT(*) AS daily_count\n"
            "FROM HF1RFM01 r\n"
            "JOIN HF1SGM01 s ON r.CODE_NO = s.CODE_NO\n"
            "WHERE r.STA_NO1 = :site_code AND r.STA_NO2 = :line_code\n"
            "  AND r.T4_UPDATE_CHECK = 4\n"
            "  AND r.MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND r.EXCEPT_FLAG IN (0, 1)\n"
            "GROUP BY SUBSTR(r.MK_DATE, 1, 8), s.TROUBLE_NG_INFO\n"
            "ORDER BY date_str"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code",  "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 6. トラブル時間算出（クロステーブル）
    # Tables: HF1RFM01 JOIN HF1SGM01, correlated subquery -> HF1REM01
    #         両テーブルで EXCEPT_FLAG IN (0, 1) 必須
    # ------------------------------------------------------------------
    {
        "name": "trouble_duration",
        "description": "トラブル時間算出 - トラブル発生時刻と次回生産再開時刻の差分からダウンタイム（分）を算出する",
        "sql_template": (
            "SELECT rf.MK_DATE AS trouble_start,\n"
            "       sg.TROUBLE_NG_INFO AS trouble_type,\n"
            "       rf.STA_NO1, rf.STA_NO2, rf.STA_NO3,\n"
            "       (SELECT MIN(re.MK_DATE)\n"
            "        FROM HF1REM01 re\n"
            "        WHERE re.STA_NO1 = rf.STA_NO1\n"
            "          AND re.STA_NO2 = rf.STA_NO2\n"
            "          AND re.STA_NO3 = rf.STA_NO3\n"
            "          AND re.MK_DATE > rf.MK_DATE\n"
            "          AND re.EXCEPT_FLAG IN (0, 1)) AS next_production,\n"
            "       ROUND(\n"
            "         (TO_DATE(\n"
            "           (SELECT MIN(re.MK_DATE)\n"
            "            FROM HF1REM01 re\n"
            "            WHERE re.STA_NO1 = rf.STA_NO1\n"
            "              AND re.STA_NO2 = rf.STA_NO2\n"
            "              AND re.STA_NO3 = rf.STA_NO3\n"
            "              AND re.MK_DATE > rf.MK_DATE\n"
            "              AND re.EXCEPT_FLAG IN (0, 1)),\n"
            "           'YYYYMMDDHH24MISS')\n"
            "         - TO_DATE(rf.MK_DATE, 'YYYYMMDDHH24MISS')) * 24 * 60, 1) AS downtime_minutes\n"
            "FROM HF1RFM01 rf\n"
            "JOIN HF1SGM01 sg ON rf.CODE_NO = sg.CODE_NO\n"
            "WHERE rf.STA_NO1 = :site_code AND rf.STA_NO2 = :line_code\n"
            "  AND rf.T4_UPDATE_CHECK = 4\n"
            "  AND rf.MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND rf.EXCEPT_FLAG IN (0, 1)\n"
            "ORDER BY rf.MK_DATE DESC\n"
            "FETCH FIRST 100 ROWS ONLY"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code",  "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
    # ------------------------------------------------------------------
    # 7. 部品別品質結果
    # Tables: HF1REM01 LEFT JOIN HF1SKM01  (EXCEPT_FLAG IN (0, 1) 必須)
    # ------------------------------------------------------------------
    {
        "name": "parts_quality",
        "description": "部品別品質結果 - 部品ごとに検査件数・不良件数・不良率を集計する",
        "sql_template": (
            "SELECT sk.MAIN_PARTS_NAME AS parts_name,\n"
            "       r.PARTS_NO,\n"
            "       COUNT(*) AS total_count,\n"
            "       SUM(CASE WHEN r.OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) AS ng_count,\n"
            "       ROUND(SUM(CASE WHEN r.OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS defect_rate\n"
            "FROM HF1REM01 r\n"
            "LEFT JOIN HF1SKM01 sk ON r.PARTS_NO = sk.PARTS_NO\n"
            "WHERE r.STA_NO1 = :site_code AND r.STA_NO2 = :line_code\n"
            "  AND r.MK_DATE BETWEEN :start_date AND :end_date\n"
            "  AND r.EXCEPT_FLAG IN (0, 1)\n"
            "GROUP BY sk.MAIN_PARTS_NAME, r.PARTS_NO\n"
            "ORDER BY defect_rate DESC"
        ),
        "parameters": (
            "["
            '{"name": "site_code",  "type": "string", "description": "拠点コード (STA_NO1)"},'
            '{"name": "line_code",  "type": "string", "description": "ラインコード (STA_NO2)"},'
            '{"name": "start_date", "type": "string", "description": "開始日時 YYYYMMDDHHmmss"},'
            '{"name": "end_date",   "type": "string", "description": "終了日時 YYYYMMDDHHmmss"}'
            "]"
        ),
    },
]


async def seed_oracle_templates(db: AsyncSession) -> int:
    """Oracle SQL テンプレートを初期データとして投入する。

    name カラムは UNIQUE 制約があるため、既存レコードは上書きせずにスキップする。

    Args:
        db: 非同期 SQLAlchemy セッション。

    Returns:
        新規投入したテンプレートの件数。
    """
    inserted = 0
    for tmpl in TEMPLATES:
        result = await db.execute(
            select(OracleQueryTemplate).where(OracleQueryTemplate.name == tmpl["name"])
        )
        if result.scalar_one_or_none() is None:
            db.add(OracleQueryTemplate(**tmpl))
            inserted += 1

    await db.commit()
    logger.info("Seeded %d oracle query templates", inserted)
    return inserted
