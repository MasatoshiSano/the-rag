"""
マスターデータキャッシュモジュール。
サイト・ライン・工程などのマスターデータをメモリにキャッシュする。
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

from app.infrastructure.config import config
from app.services.text_normalizer import normalize_text

logger = logging.getLogger(__name__)

# フィールド抽出パターン（コンパイル済みでモジュール初期化時に一度だけ生成する）
_RE_SITE = re.compile(r"^- 拠点:\s*(.+?)\s*\((\S+)\)\s*$", re.MULTILINE)
_RE_LINE = re.compile(r"^- ライン:\s*(.+?)\s*\((\S+)\)\s*$", re.MULTILINE)
_RE_PROCESS = re.compile(r"^- 工程:\s*(.+?)\s*\((\S+)\)\s*$", re.MULTILINE)
_RE_TM = re.compile(r"^- TM区分:\s*(.+?)\s*$", re.MULTILINE)
_RE_DT = re.compile(r"^- DT区分:\s*(.+?)\s*$", re.MULTILINE)
_RE_STA1 = re.compile(r"^- ステーションNo\.1:\s*(.+?)\s*$", re.MULTILINE)
_RE_STA2 = re.compile(r"^- ステーションNo\.2:\s*(.+?)\s*$", re.MULTILINE)
_RE_STA3 = re.compile(r"^- ステーションNo\.3:\s*(.+?)\s*$", re.MULTILINE)
_RE_ALIASES = re.compile(r"^- 別名:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class SiteData:
    """製造拠点データ。"""

    code: str
    name: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class LineData:
    """製造ラインデータ。"""

    code: str
    name: str
    site_code: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class ProcessData:
    """製造工程データ。"""

    code: str
    name: str
    line_code: str
    tm_class: str | None = None
    dt_class: str | None = None
    station_no1: str | None = None
    station_no2: str | None = None
    station_no3: str | None = None


@dataclass
class MasterDataCache:
    """
    マスターデータのメモリキャッシュを表すデータクラス。

    Attributes:
        sites: サイトコードをキー、SiteData を値とする辞書。
        lines: ラインコードをキー、LineData を値とする辞書。
        processes: 工程コードをキー、ProcessData を値とする辞書。
    """

    sites: dict[str, SiteData] = field(default_factory=dict)
    lines: dict[str, LineData] = field(default_factory=dict)
    processes: dict[str, ProcessData] = field(default_factory=dict)


# モジュールレベルのキャッシュインスタンス
_cache: MasterDataCache | None = None


def _extract(pattern: re.Pattern[str], text: str) -> str | None:
    """正規表現にマッチした最初のグループを返す。マッチしなければ None。"""
    m = pattern.search(text)
    return m.group(1) if m else None


def _extract_code(pattern: re.Pattern[str], text: str) -> tuple[str, str] | None:
    """name と code の 2 グループを返すパターン用ヘルパー。"""
    m = pattern.search(text)
    if m:
        return m.group(1), m.group(2)
    return None


def _parse_aliases(raw: str) -> list[str]:
    """カンマ区切りの別名文字列をリストに変換し NFKC 正規化する。"""
    return [normalize_text(a.strip()) for a in raw.split(",") if a.strip()]


def parse_master_file(file_path: str) -> MasterDataCache:
    """
    master-flat-with-place-aliases.md を解析して MasterDataCache を返す。

    各 ## セクションから拠点・ライン・工程情報を抽出し、コードで重複排除する。
    全テキストに NFKC 正規化を適用する。

    Args:
        file_path: マスターデータ Markdown ファイルのパス。

    Returns:
        解析済みの MasterDataCache インスタンス。

    Raises:
        FileNotFoundError: 指定されたファイルが存在しない場合。
        UnicodeDecodeError: ファイルの文字コードが UTF-8 でない場合。
    """
    with open(file_path, encoding="utf-8") as fh:
        content = fh.read()

    # ファイルを ## 見出しで分割（最初の空セクションは捨てる）
    raw_sections = re.split(r"^## ", content, flags=re.MULTILINE)

    sites: dict[str, SiteData] = {}
    lines: dict[str, LineData] = {}
    processes: dict[str, ProcessData] = {}

    skipped = 0
    for raw in raw_sections:
        if not raw.strip():
            continue

        # 拠点フィールド
        site_pair = _extract_code(_RE_SITE, raw)
        if site_pair is None:
            skipped += 1
            continue
        site_name_raw, site_code_raw = site_pair
        site_code = normalize_text(site_code_raw.strip())
        site_name = normalize_text(site_name_raw.strip())

        # ライン
        line_pair = _extract_code(_RE_LINE, raw)
        if line_pair is None:
            skipped += 1
            continue
        line_name_raw, line_code_raw = line_pair
        line_code = normalize_text(line_code_raw.strip())
        line_name = normalize_text(line_name_raw.strip())

        # 工程
        process_pair = _extract_code(_RE_PROCESS, raw)
        if process_pair is None:
            skipped += 1
            continue
        process_name_raw, process_code_raw = process_pair
        process_code = normalize_text(process_code_raw.strip())
        process_name = normalize_text(process_name_raw.strip())

        # 別名（サイト・ライン両方で共有される場合があるので各エンティティに付与）
        aliases_raw = _extract(_RE_ALIASES, raw)
        aliases: list[str] = _parse_aliases(aliases_raw) if aliases_raw else []

        # TM・DT 区分
        tm_raw = _extract(_RE_TM, raw)
        dt_raw = _extract(_RE_DT, raw)
        tm_class = normalize_text(tm_raw.strip()) if tm_raw else None
        dt_class = normalize_text(dt_raw.strip()) if dt_raw else None

        # ステーション番号
        sta1_raw = _extract(_RE_STA1, raw)
        sta2_raw = _extract(_RE_STA2, raw)
        sta3_raw = _extract(_RE_STA3, raw)
        station_no1 = normalize_text(sta1_raw.strip()) if sta1_raw else None
        station_no2 = normalize_text(sta2_raw.strip()) if sta2_raw else None
        station_no3 = normalize_text(sta3_raw.strip()) if sta3_raw else None

        # --- サイト（コードで重複排除、先着優先） ---
        if site_code not in sites:
            sites[site_code] = SiteData(
                code=site_code,
                name=site_name,
                aliases=aliases,
            )

        # --- ライン（コードで重複排除） ---
        if line_code not in lines:
            lines[line_code] = LineData(
                code=line_code,
                name=line_name,
                site_code=site_code,
                aliases=aliases,
            )

        # --- 工程（コードで重複排除） ---
        if process_code not in processes:
            processes[process_code] = ProcessData(
                code=process_code,
                name=process_name,
                line_code=line_code,
                tm_class=tm_class,
                dt_class=dt_class,
                station_no1=station_no1,
                station_no2=station_no2,
                station_no3=station_no3,
            )

    if skipped:
        logger.warning(
            "parse_master_file: %d セクションをスキップしました（フィールド欠損）",
            skipped,
        )

    return MasterDataCache(sites=sites, lines=lines, processes=processes)


async def load_master_cache() -> None:
    """
    マスターデータ Markdown ファイルを読み込みモジュールレベルキャッシュに格納する。

    config.MASTER_MD_PATH で指定されたファイルを同期 I/O スレッドで解析し、
    グローバル _cache を更新する。FastAPI のスタートアップイベントから呼び出す。
    """
    global _cache
    _cache = await asyncio.to_thread(parse_master_file, config.MASTER_MD_PATH)
    logger.info(
        "マスターキャッシュを読み込みました: %d サイト / %d ライン / %d 工程",
        len(_cache.sites),
        len(_cache.lines),
        len(_cache.processes),
    )


def get_master_cache() -> MasterDataCache:
    """
    現在のマスターデータキャッシュを返す（FastAPI の Depends 注入用）。

    Returns:
        MasterDataCache インスタンス。

    Raises:
        RuntimeError: load_master_cache が呼び出される前にアクセスした場合。
    """
    if _cache is None:
        raise RuntimeError(
            "マスターキャッシュが未初期化です。load_master_cache() を先に呼び出してください。"
        )
    return _cache


async def save_to_db(db_session) -> None:
    """
    解析済みマスターデータを SQLite の MasterSite / MasterLine / MasterProcess テーブルに保存する。

    既存レコードは UPSERT（merge）で更新する。
    キャッシュが未初期化の場合は何もしない。

    Args:
        db_session: SQLAlchemy 非同期セッション。
    """
    from app.models.database import MasterLine, MasterProcess, MasterSite

    if _cache is None:
        logger.warning("save_to_db: マスターキャッシュが未初期化のためスキップします")
        return

    # --- MasterSite の UPSERT ---
    for site in _cache.sites.values():
        row = await db_session.get(MasterSite, site.code)
        if row is None:
            row = MasterSite(
                code=site.code,
                name=site.name,
                aliases=json.dumps(site.aliases, ensure_ascii=False),
            )
            db_session.add(row)
        else:
            row.name = site.name
            row.aliases = json.dumps(site.aliases, ensure_ascii=False)

    # --- MasterLine の UPSERT ---
    for line in _cache.lines.values():
        row = await db_session.get(MasterLine, line.code)
        if row is None:
            row = MasterLine(
                code=line.code,
                name=line.name,
                site_code=line.site_code,
                aliases=json.dumps(line.aliases, ensure_ascii=False),
            )
            db_session.add(row)
        else:
            row.name = line.name
            row.site_code = line.site_code
            row.aliases = json.dumps(line.aliases, ensure_ascii=False)

    # --- MasterProcess の UPSERT ---
    for process in _cache.processes.values():
        row = await db_session.get(MasterProcess, process.code)
        if row is None:
            row = MasterProcess(
                code=process.code,
                name=process.name,
                line_code=process.line_code,
                tm_class=process.tm_class,
                dt_class=process.dt_class,
                station_no1=process.station_no1,
                station_no2=process.station_no2,
                station_no3=process.station_no3,
            )
            db_session.add(row)
        else:
            row.name = process.name
            row.line_code = process.line_code
            row.tm_class = process.tm_class
            row.dt_class = process.dt_class
            row.station_no1 = process.station_no1
            row.station_no2 = process.station_no2
            row.station_no3 = process.station_no3

    await db_session.commit()
    logger.info(
        "save_to_db: %d サイト / %d ライン / %d 工程 を DB に保存しました",
        len(_cache.sites),
        len(_cache.lines),
        len(_cache.processes),
    )
