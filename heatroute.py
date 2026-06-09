# -*- coding: utf-8 -*-
"""凉爽路径规划引擎:百度 directionlite 路线 + 沿路 LST 热暴露评估。

- LST 面:直接取自 green_lst._state()['lst'](1388×973 100m 实测栅格,WGS84 逐格 lon/lat),
  用 cKDTree 建空间索引(运行时缓存一次),按经纬度快速查 LST。
- 路线:百度 directionlite(步行/骑行/驾车),输入 WGS84(coord_type=wgs84),
  返回路径默认 BD09,转回 WGS84 与 LST 网格对齐。
- 热暴露:把路径加密到 ~50m,沿线采样 LST,算 长度加权均温 / 最高温 / 累计暴露(°C·m)/ 高温路段长度。

被 views/heatroute.py 调用。百度 AK 走 st.secrets['baidu_ak'](不入库)。
"""
import math

import numpy as np
from scipy.spatial import cKDTree

import green_lst
import geo

_LAT0 = 31.2
_KX = math.cos(math.radians(_LAT0))     # 经度方向缩放,使最近邻在度空间近似各向同性
_SAMPLER = None
HOT_THRESHOLD = 45.0                      # 高温路段判定阈值(°C 地表温度)


def _sampler():
    global _SAMPLER
    if _SAMPLER is None:
        S = green_lst._state()
        lon, lat, lst = S["lon"], S["lat"], S["lst"]
        v = np.isfinite(lst) & np.isfinite(lon) & np.isfinite(lat)
        pts = np.column_stack([lon[v].astype(float) * _KX, lat[v].astype(float)])
        _SAMPLER = {"tree": cKDTree(pts), "lst": lst[v].astype(float)}
    return _SAMPLER


def sample_lst(lngs, lats):
    """按经纬度数组查最近有效格的 LST;离网格过远(>~450m)返回 NaN。"""
    s = _sampler()
    q = np.column_stack([np.asarray(lngs, float) * _KX, np.asarray(lats, float)])
    d, idx = s["tree"].query(q)
    out = s["lst"][idx]
    return np.where(d > 0.004, np.nan, out)   # 0.004° ≈ 450m


def _haversine(lng1, lat1, lng2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def densify(path, step_m=50.0):
    """把折线按 step_m 加密(线性插值)。path: [(lng,lat),...]。"""
    if len(path) < 2:
        return list(path)
    out = []
    for i in range(len(path) - 1):
        x1, y1 = path[i]; x2, y2 = path[i + 1]
        d = _haversine(x1, y1, x2, y2)
        n = max(1, int(d / step_m))
        for k in range(n):
            t = k / n
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    out.append(path[-1])
    return out


def route_heat(path, step_m=50.0):
    """沿路径计算热暴露指标。返回 mean/max LST、累计暴露(°C·m)、高温路段长度、逐点采样。"""
    dense = densify(path, step_m)
    lngs = np.array([p[0] for p in dense]); lats = np.array([p[1] for p in dense])
    lst = sample_lst(lngs, lats)
    seglen = np.array([_haversine(dense[i][0], dense[i][1], dense[i + 1][0], dense[i + 1][1])
                       for i in range(len(dense) - 1)])
    cumdist = np.concatenate([[0.0], np.cumsum(seglen)])      # 各采样点累计里程(m)
    seg_lst = (lst[:-1] + lst[1:]) / 2.0
    m = np.isfinite(seg_lst)
    if not m.any():
        return {"mean_lst": float("nan"), "max_lst": float("nan"), "exposure": float("nan"),
                "length_m": float(seglen.sum()), "hot_len_m": 0.0, "samples": [],
                "dist": cumdist.tolist(), "cover": 0.0}
    mean_lst = float(np.average(seg_lst[m], weights=seglen[m]))
    exposure = float((seg_lst[m] * seglen[m]).sum())
    hot = m & (seg_lst > HOT_THRESHOLD)
    hot_len = float(seglen[hot].sum())
    samples = [(float(x), float(y), (float(z) if np.isfinite(z) else None))
               for x, y, z in zip(lngs, lats, lst)]
    return {"mean_lst": mean_lst, "max_lst": float(np.nanmax(lst)), "exposure": exposure,
            "length_m": float(seglen.sum()), "hot_len_m": hot_len, "samples": samples,
            "dist": cumdist.tolist(),
            "cover": float(seglen[m].sum() / max(seglen.sum(), 1e-9))}


# ───────────────────────── 百度 directionlite ─────────────────────────
_MODES = {"步行": "walking", "骑行": "riding", "驾车": "driving"}


def _extract_path(rt):
    """从一条 route 的 steps 拼接路径点(BD09 lng,lat)。"""
    pts = []
    for step in rt.get("steps", []):
        p = step.get("path") or ""
        for pair in p.split(";"):
            if not pair:
                continue
            xy = pair.split(",")
            if len(xy) >= 2:
                pts.append((float(xy[0]), float(xy[1])))   # lng,lat (BD09)
    return pts


def plan_routes(o_wgs, d_wgs, mode_zh="步行", ak=None, timeout=8):
    """调百度 directionlite,返回路线列表(路径已转 WGS84)。
    o_wgs/d_wgs: (lng, lat) WGS84。需要 ak。"""
    import requests
    if not ak:
        raise RuntimeError("缺少百度 AK")
    mode = _MODES.get(mode_zh, "walking")
    url = f"https://api.map.baidu.com/directionlite/v1/{mode}"
    params = {
        "origin": f"{o_wgs[1]:.6f},{o_wgs[0]:.6f}",          # 百度用 纬度,经度
        "destination": f"{d_wgs[1]:.6f},{d_wgs[0]:.6f}",
        "coord_type": "wgs84", "ak": ak,
    }
    r = requests.get(url, params=params, timeout=timeout)
    js = r.json()
    if js.get("status") != 0:
        raise RuntimeError(f"百度API status={js.get('status')}:{js.get('message')}")
    routes = []
    for rt in js.get("result", {}).get("routes", []):
        bd = _extract_path(rt)
        path_wgs = [geo.bd09_to_wgs(x, y) for x, y in bd]
        if len(path_wgs) < 2:
            continue
        routes.append({"path": path_wgs,
                       "distance": rt.get("distance"), "duration": rt.get("duration")})
    return routes


def geocode(address, ak, city="上海", timeout=8, return_raw=False):
    """地址/地标 → (lng, lat) WGS84。

    用百度【地点检索 Place API】而非 geocoding API:后者只适合结构化地址,拿地标/POI 名
    (如“上海火车站”)会错配到几公里外。Place API 返回 GCJ02(ret_coordtype=gcj02ll),
    经 gcj2wgs 转 WGS84(与路线 bd09_to_wgs 输出一致、对齐底图)。
    return_raw=True 时额外返回匹配到的名称/地址(供确认)。"""
    import requests
    if not ak:
        raise RuntimeError("缺少百度 AK")
    r = requests.get("https://api.map.baidu.com/place/v2/search",
                     params={"query": address, "region": city, "city_limit": "true",
                             "output": "json", "ret_coordtype": "gcj02ll",
                             "page_size": 1, "ak": ak}, timeout=timeout)
    js = r.json()
    if js.get("status") != 0:
        raise RuntimeError(f"地点检索失败 status={js.get('status')}:{js.get('message')}")
    results = js.get("results") or []
    if not results:
        raise RuntimeError(f"未找到「{address}」,请换更具体的名称或完整地址")
    r0 = results[0]; loc = r0["location"]
    wgs = geo.gcj2wgs(loc["lng"], loc["lat"])      # GCJ02 -> WGS84
    if return_raw:
        return wgs[0], wgs[1], {"name": r0.get("name", ""), "address": r0.get("address", "")}
    return wgs


def _bearing(o, d):
    lon1, lat1 = math.radians(o[0]), math.radians(o[1])
    lon2, lat2 = math.radians(d[0]), math.radians(d[1])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x))


def _offset_point(lng, lat, bearing_deg, dist_m):
    R = 6371000.0
    br = math.radians(bearing_deg); dr = dist_m / R
    lat1, lon1 = math.radians(lat), math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(dr) + math.cos(lat1) * math.sin(dr) * math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(lat1),
                             math.cos(dr) - math.sin(lat1) * math.sin(lat2))
    return (math.degrees(lon2), math.degrees(lat2))


def _cool_waypoints(o, d, n=2, offsets=(400, 700, 1000)):
    """在 O-D 走廊垂直两侧采样 LST,挑出比走廊更凉的若干途经点。"""
    brg = _bearing(o, d)
    cands = []
    for frac in (0.4, 0.5, 0.6):
        plng = o[0] + (d[0] - o[0]) * frac; plat = o[1] + (d[1] - o[1]) * frac
        for side in (90, -90):
            for off in offsets:
                cands.append(_offset_point(plng, plat, brg + side, off))
    base = float(np.nanmean(sample_lst(
        [o[0] + (d[0] - o[0]) * t for t in (0.4, 0.5, 0.6)],
        [o[1] + (d[1] - o[1]) * t for t in (0.4, 0.5, 0.6)])))
    lst = sample_lst([c[0] for c in cands], [c[1] for c in cands])
    scored = [(c, float(l)) for c, l in zip(cands, lst)
              if np.isfinite(l) and (not np.isfinite(base) or l < base - 0.3)]
    scored.sort(key=lambda x: x[1])
    # 去掉彼此太近的途经点(>300m 才算不同)
    out = []
    for c, _l in scored:
        if all(_haversine(c[0], c[1], w[0], w[1]) > 300 for w in out):
            out.append(c)
        if len(out) >= n:
            break
    return out


def _detour_waypoints(o, d, direct_path, n=2):
    """针对直达路线**最热的位置**,朝凉的方向横向避让,生成途经点。
    比在直线中点撒点更对症(直接绕开热点)。"""
    h = route_heat(direct_path)
    samp = [(s[0], s[1], s[2]) for s in h["samples"] if s[2] is not None]
    if not samp:
        return _cool_waypoints(o, d, n)
    hot = max(samp, key=lambda s: s[2])         # 路线最热点
    brg = _bearing(o, d)
    cands = []
    for side in (90, -90):
        for off in (300, 550, 850):
            cands.append(_offset_point(hot[0], hot[1], brg + side, off))
    lst = sample_lst([c[0] for c in cands], [c[1] for c in cands])
    scored = sorted([(c, float(l)) for c, l in zip(cands, lst) if np.isfinite(l)],
                    key=lambda x: x[1])
    out = []
    for c, _l in scored:
        if all(_haversine(c[0], c[1], w[0], w[1]) > 300 for w in out):
            out.append(c)
        if len(out) >= n:
            break
    return out


def plan_cool_routes(o, d, mode_zh="步行", ak=None, add_detours=True, n_detours=2):
    """直达路线 + (可选)绕开直达路线最热段的绕行备选。返回带 kind/via 标记的路线列表。"""
    routes = plan_routes(o, d, mode_zh, ak)
    for r in routes:
        r["kind"] = "直达"; r["via"] = None
    if add_detours and routes:
        for w in _detour_waypoints(o, d, routes[0]["path"], n_detours):
            try:
                l1 = plan_routes(o, w, mode_zh, ak)
                l2 = plan_routes(w, d, mode_zh, ak)
            except Exception:
                continue
            if l1 and l2:
                routes.append({
                    "path": l1[0]["path"] + l2[0]["path"],
                    "distance": (l1[0]["distance"] or 0) + (l2[0]["distance"] or 0),
                    "duration": (l1[0]["duration"] or 0) + (l2[0]["duration"] or 0),
                    "kind": "绕行", "via": w})
    return routes
