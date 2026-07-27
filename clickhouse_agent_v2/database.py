"""数据库连接与维表缓存。"""
import logging
import warnings
from typing import Any

import clickhouse_connect
from config import settings

logger = logging.getLogger("db")

# ---------- ClickHouse 连接（优雅降级）----------
_ckread: Any = None

def get_ck() -> Any:
    global _ckread
    if _ckread is not None:
        return _ckread
    try:
        _ckread = clickhouse_connect.get_client(
            host=settings.ck_host,
            port=settings.ck_port,
            username=settings.ck_user,
            password=settings.ck_password,
            connect_timeout=settings.ck_connect_timeout,
        )
        logger.info("ClickHouse 已连接: %s:%s", settings.ck_host, settings.ck_port)
    except Exception as e:
        warnings.warn(f"ClickHouse 连接失败: {e}")
        _ckread = None
    return _ckread


def ck_available() -> bool:
    return get_ck() is not None


# ---------- 维表缓存（Streamlit st.cache_data 由调用方注入）----------
# 这些函数返回纯数据，不依赖 Streamlit

def fetch_corp_hierarchy(ck, include_inactive: bool = False) -> tuple[dict, dict]:
    """(hierarchy, corp_id_map)"""
    include_inactive = False
    try:
        where_clauses = ["d_corp_name != ''", "d_corp_id IS NOT NULL"]
        if not include_inactive:
            where_clauses.append("d_corp_busi_status = 'Y'")
        where_sql = " AND ".join(where_clauses)
        sql = (
            f"SELECT DISTINCT d_region_name, d_corp_id, d_corp_name "
            f"FROM alphafeed.dim_unit "
            f"WHERE {where_sql} "
            f"ORDER BY d_region_name, d_corp_name"
        )
        rows = ck.query(sql).result_rows
    except Exception as e:
        logger.warning("获取公司架构出错: %s", e)
        return {}, {}

    hierarchy: dict[str, list] = {}
    corp_map: dict[str, str] = {}
    for region, cid, name in rows:
        region = _s(region) or "其他"
        cid = _s(cid)
        name = _s(name)
        hierarchy.setdefault(region, []).append((cid, name))
        corp_map[cid] = name
    # 去重
    for k in hierarchy:
        hierarchy[k] = list(set(hierarchy[k]))
    return hierarchy, corp_map


def fetch_material_hierarchy(ck, include_inactive: bool = False) -> tuple[dict, list, dict]:
    """(hierarchy, all_materials, mat_id_map)"""
    try:
        where_clauses = ["d_material_name != ''"]
        if not include_inactive:
            where_clauses.append("d_material_name NOT LIKE '%(停用)%'")
        where_sql = " AND ".join(where_clauses)
        sql = (
            f"SELECT DISTINCT d_class_name1, d_class_name2, d_material_id, "
            f"       d_material_name, d_material_code "
            f"FROM alphafeed.dim_material "
            f"WHERE {where_sql} "
            f"ORDER BY d_class_name1, d_class_name2, d_material_name"
        )
        rows = ck.query(sql).result_rows
    except Exception as e:
        logger.warning("获取物料架构出错: %s", e)
        return {}, [], {}

    hierarchy: dict = {}
    all_mats: list[tuple] = []
    mat_map: dict[str, str] = {}
    for c1, c2, mid, name, code in rows:
        c1 = _s(c1) or "未分类"
        c2 = _s(c2) or "通用"
        mid = _s(mid)
        name = _s(name)
        code = _s(code)
        hierarchy.setdefault(c1, {}).setdefault(c2, []).append((mid, name, code))
        all_mats.append((mid, name, code))
        mat_map[mid] = f"{name} ({code})"
    all_mats = sorted(set(all_mats), key=lambda x: x[1])
    return hierarchy, all_mats, mat_map


def fetch_customers(ck, corp_ids: list[str] | None = None, include_inactive: bool = False) -> tuple[list, dict]:
    """(clients, client_id_map)"""
    try:
        where = ["d_client_name != ''", "d_client_id IS NOT NULL"]
        if not include_inactive:
            where.append("start_status = 2")
            where.append("frozen_flag = 0")
        if corp_ids:
            ids = ", ".join(f"'{_s(c)}'" for c in corp_ids)
            where.append(f"d_corp_id IN ({ids})")
        sql = (
            f"SELECT DISTINCT d_client_id, d_client_name, d_client_code "
            f"FROM alphafeed.dim_client WHERE {' AND '.join(where)} ORDER BY d_client_name"
        )
        rows = ck.query(sql).result_rows
    except Exception as e:
        logger.warning("获取客户列表出错: %s", e)
        return [], {}

    clients: list[tuple] = []
    client_map: dict[str, str] = {}
    for cid, name, code in rows:
        cid = _s(cid)
        name = _s(name) or ""
        code = _s(code) or ""
        clients.append((cid, name, code))
        client_map[cid] = f"{name} ({code})"
    return clients, client_map


def _s(v: Any) -> str:
    """统一转 str，处理 bytes 类型。"""
    if isinstance(v, bytes):
        return v.decode()
    return str(v) if v is not None else ""
