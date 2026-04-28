"""
マスターデータルーターモジュール。
サイト・ライン・工程などのマスターデータ参照 API エンドポイントを提供する。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.infrastructure.master_cache import MasterDataCache, get_master_cache
from app.services.text_normalizer import normalize_query

router = APIRouter(prefix="/master", tags=["master"])


@router.get("/sites")
async def list_sites(
    cache: MasterDataCache = Depends(get_master_cache),
) -> dict:
    """
    全サイト一覧をマスターキャッシュから取得する。

    Returns:
        {"sites": [{"code": str, "name": str, "aliases": list[str]}, ...]}
    """
    return {
        "sites": [
            {"code": s.code, "name": s.name, "aliases": s.aliases}
            for s in cache.sites.values()
        ]
    }


@router.get("/lines")
async def list_lines(
    site_code: str | None = Query(default=None, description="フィルタするサイトコード"),
    cache: MasterDataCache = Depends(get_master_cache),
) -> dict:
    """
    ライン一覧をマスターキャッシュから取得する。
    site_code を指定した場合は該当サイトのラインのみ返す。

    Args:
        site_code: フィルタするサイトコード（省略可）。

    Returns:
        {"lines": [{"code": str, "name": str, "site_code": str, "aliases": list[str]}, ...]}
    """
    lines = cache.lines.values()
    if site_code is not None:
        normalized_site_code = normalize_query(site_code)
        lines = [ln for ln in lines if ln.site_code == normalized_site_code]

    return {
        "lines": [
            {
                "code": ln.code,
                "name": ln.name,
                "site_code": ln.site_code,
                "aliases": ln.aliases,
            }
            for ln in lines
        ]
    }


@router.get("/processes")
async def list_processes(
    line_code: str | None = Query(default=None, description="フィルタするラインコード"),
    cache: MasterDataCache = Depends(get_master_cache),
) -> dict:
    """
    工程一覧をマスターキャッシュから取得する。
    line_code を指定した場合は該当ラインの工程のみ返す。

    Args:
        line_code: フィルタするラインコード（省略可）。

    Returns:
        {"processes": [{...}, ...]}
    """
    processes = cache.processes.values()
    if line_code is not None:
        normalized_line_code = normalize_query(line_code)
        processes = [p for p in processes if p.line_code == normalized_line_code]

    return {
        "processes": [
            {
                "code": p.code,
                "name": p.name,
                "line_code": p.line_code,
                "tm_class": p.tm_class,
                "dt_class": p.dt_class,
                "station_no1": p.station_no1,
                "station_no2": p.station_no2,
                "station_no3": p.station_no3,
            }
            for p in processes
        ]
    }


@router.get("/search")
async def search_master(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    cache: MasterDataCache = Depends(get_master_cache),
) -> dict:
    """
    マスターデータをキーワード検索する。
    サイト・ライン・工程の全エンティティを横断的に検索する。
    クエリは NFKC 正規化後に name および aliases と部分一致で照合する。

    Args:
        q: 検索クエリ文字列。

    Returns:
        {"results": [{"type": str, "code": str, "name": str, "aliases": list[str]}, ...]}

    Raises:
        HTTPException 400: クエリが空文字列の場合。
    """
    normalized_q = normalize_query(q)
    if not normalized_q:
        raise HTTPException(status_code=400, detail="検索クエリが空です。")

    results: list[dict] = []

    # サイト検索
    for site in cache.sites.values():
        if normalized_q in site.name or any(
            normalized_q in alias for alias in site.aliases
        ):
            results.append(
                {
                    "type": "site",
                    "code": site.code,
                    "name": site.name,
                    "aliases": site.aliases,
                }
            )

    # ライン検索
    for line in cache.lines.values():
        if normalized_q in line.name or any(
            normalized_q in alias for alias in line.aliases
        ):
            results.append(
                {
                    "type": "line",
                    "code": line.code,
                    "name": line.name,
                    "site_code": line.site_code,
                    "aliases": line.aliases,
                }
            )

    # 工程検索（工程には別名フィールドがないため name のみ照合）
    for process in cache.processes.values():
        if normalized_q in process.name:
            results.append(
                {
                    "type": "process",
                    "code": process.code,
                    "name": process.name,
                    "line_code": process.line_code,
                    "tm_class": process.tm_class,
                    "dt_class": process.dt_class,
                }
            )

    return {"query": normalized_q, "count": len(results), "results": results}
