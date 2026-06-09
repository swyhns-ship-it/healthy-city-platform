# -*- coding: utf-8 -*-
"""EMS 急救反应时间预测引擎(纯函数,被 views/ems_response.py 调用)。

思路:给定一条救护车行驶轨迹(WGS84 经纬度折线),沿轨迹缓冲区算 5 个空间自变量,
再用随机森林(回归到场秒数 + 分类 4 档)预测急救反应时间。

5 变量(与训练表 120data_demo.csv 对齐,见 analysis/build_ems_data.py):
  Distance_m       路径几何长度(米)
  Road4_Length_m   路径 20m 缓冲区内支路总长(米)
  POPDEN_phm2      路径 200m 缓冲区人口密度均值(校准到训练分布)
  FAR              路径 200m 缓冲区容积率均值(校准到训练分布)
  MediPOIDen_nhm2  路径 200m 缓冲区医疗POI密度(个/公顷)

运行时数据:ems_layers.npz(栅格+支路+POI+校准系数)、ems_model.joblib(reg+clf)、
heat_ems_points.npz(202 个现状急救站)。坐标:等距圆柱近似把 WGS84 投到局部米制
(以研究区中心为原点),buffer/求交在米制下做,纯 numpy/scipy/shapely,不依赖 geopandas。
"""
import os
import math

import numpy as np
import joblib
from scipy.spatial import cKDTree

import shapely
from shapely.geometry import LineString
from shapely.strtree import STRtree

_ROOT = os.path.dirname(os.path.abspath(__file__))
_STATE = None       # 重型预处理缓存(进程内只建一次)


def _state():
    """懒加载并缓存:栅格/支路 STRtree/POI/模型/急救站/投影常数。"""
    global _STATE
    if _STATE is not None:
        return _STATE
    L = np.load(os.path.join(_ROOT, "ems_layers.npz"))
    bundle = joblib.load(os.path.join(_ROOT, "ems_model.joblib"))

    lon0, lat0_top, dlon, dlat, nx, ny = L["grid_meta"]
    nx, ny = int(nx), int(ny)
    cx_lon, cy_lat = L["center"]
    mlat = 110540.0
    mlon = 111320.0 * np.cos(np.radians(cy_lat))

    def to_m(lon, lat):
        return ((np.asarray(lon, float) - cx_lon) * mlon,
                (np.asarray(lat, float) - cy_lat) * mlat)

    # 栅格像元中心 -> 米制(一次)
    cols = np.arange(nx); rws = np.arange(ny)
    cell_lon = lon0 + (cols + 0.5) * dlon
    cell_lat = lat0_top + (rws + 0.5) * dlat
    glon, glat = np.meshgrid(cell_lon, cell_lat)
    gx, gy = to_m(glon.ravel(), glat.ravel())

    # 支路线段 -> 米制 + STRtree
    rx, ry = to_m(L["road_xy"][:, 0], L["road_xy"][:, 1])
    off = L["road_off"]
    road_lines = [LineString(np.c_[rx[s:e], ry[s:e]])
                  for s, e in zip(off[:-1], off[1:]) if e - s >= 2]
    tree = STRtree(road_lines)

    # 医疗POI -> 米制
    px, py = to_m(L["poi_xy"][:, 0], L["poi_xy"][:, 1])

    # 现状急救站(WGS84)+ 最近邻索引(经度按纬度缩放近似各向同性)
    E = np.load(os.path.join(_ROOT, "heat_ems_points.npz"))
    st_lon, st_lat = E["lon"].astype(float), E["lat"].astype(float)
    kx = np.cos(np.radians(float(cy_lat)))
    st_tree = cKDTree(np.c_[st_lon * kx, st_lat])

    pop_a, pop_b, far_a, far_b = L["calib"]
    _STATE = {
        "to_m": to_m,
        "gx": gx, "gy": gy,
        "pop": L["pop_dens"].ravel(), "far": L["far"].ravel(),
        "calib": (pop_a, pop_b, far_a, far_b),
        "road_lines": road_lines, "tree": tree,
        "poi_m": np.c_[px, py],
        "st_lon": st_lon, "st_lat": st_lat, "st_tree": st_tree, "kx": kx,
        "bundle": bundle,
    }
    return _STATE


def stations():
    """返回现状急救站坐标 (lon[], lat[]) WGS84。"""
    s = _state()
    return s["st_lon"], s["st_lat"]


def nearest_station(lon, lat):
    """事发点最近的现状急救站(直线最近邻)。返回 (lon, lat, 直线距离米)。"""
    s = _state()
    d, i = s["st_tree"].query([lon * s["kx"], lat])
    slon, slat = float(s["st_lon"][i]), float(s["st_lat"][i])
    # 直线距离(米)
    dx = (slon - lon) * 111320.0 * s["kx"]; dy = (slat - lat) * 110540.0
    return slon, slat, float(np.hypot(dx, dy))


def compute_features(route_lonlat):
    """route_lonlat: [(lon,lat),...] WGS84 -> 5 变量 dict(已含 POPDEN/FAR 校准)。"""
    s = _state()
    lons = [p[0] for p in route_lonlat]; lats = [p[1] for p in route_lonlat]
    X, Y = s["to_m"](lons, lats)
    line = LineString(np.c_[X, Y])
    buf20 = line.buffer(20.0)
    buf200 = line.buffer(200.0)
    pop_a, pop_b, far_a, far_b = s["calib"]

    distance = float(line.length)

    # 支路长度:20m 缓冲区内候选线段求交集长度
    road_len = 0.0
    for i in np.atleast_1d(s["tree"].query(buf20)):
        road_len += buf20.intersection(s["road_lines"][int(i)]).length

    # 200m 缓冲区栅格均值(校准后)
    inb = shapely.contains_xy(buf200, s["gx"], s["gy"])
    pv = s["pop"][inb]; fv = s["far"][inb]
    pm = np.nanmean(pv) if np.isfinite(pv).any() else np.nan
    fm = np.nanmean(fv) if np.isfinite(fv).any() else np.nan
    popden = pop_a * pm + pop_b if np.isfinite(pm) else np.nan
    farv = far_a * fm + far_b if np.isfinite(fm) else np.nan

    # 医疗POI密度:200m 缓冲区内点数 / 面积(公顷)
    inpoi = shapely.contains_xy(buf200, s["poi_m"][:, 0], s["poi_m"][:, 1])
    medi = float(inpoi.sum()) / (buf200.area / 10000.0)

    return {"Distance_m": distance, "Road4_Length_m": float(road_len),
            "POPDEN_phm2": float(popden), "FAR": float(farv),
            "MediPOIDen_nhm2": float(medi)}


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


def _plan_driving_v2(o_wgs, d_wgs, ak, timeout=8):
    """百度 direction/v2/driving + alternatives:同起终点的多条真实备选路线(走不同道路)。
    输入 WGS84 (lng,lat);返回 [{path(WGS84), distance, duration}]。"""
    import requests
    import geo
    from heatroute import _extract_path
    r = requests.get("https://api.map.baidu.com/direction/v2/driving", params={
        "origin": f"{o_wgs[1]:.6f},{o_wgs[0]:.6f}",
        "destination": f"{d_wgs[1]:.6f},{d_wgs[0]:.6f}",
        "coord_type": "wgs84", "alternatives": 1, "ak": ak}, timeout=timeout).json()
    if r.get("status") != 0:
        raise RuntimeError(f"百度v2 status={r.get('status')}:{r.get('message')}")
    out = []
    for rt in r.get("result", {}).get("routes", []):
        path = [geo.bd09_to_wgs(x, y) for x, y in _extract_path(rt)]
        if len(path) >= 2:
            out.append({"path": path, "distance": rt.get("distance"),
                        "duration": rt.get("duration")})
    return out


def plan_candidate_routes(station, incident, ak, extra_offsets=(450,), timeout=8):
    """生成多条候选驾车路线:百度 v2 真实替代路线(主推+备选)+ 少量小偏移绕行补充多样性。
    station/incident: (lng,lat) WGS84。返回去重后的路线列表(每条含 path/distance/duration/kind)。
    模块只负责"生成不同的真实路线",到场时间由模型对每条独立预测后再比较取最短。"""
    import heatroute
    try:
        v2 = _plan_driving_v2(station, incident, ak, timeout)
    except Exception:
        v2 = []
    if not v2:   # v2 不可用则回退 directionlite 直达
        v2 = list(heatroute.plan_routes(station, incident, mode_zh="驾车", ak=ak, timeout=timeout))
    if not v2:
        return []
    routes = []
    for j, r in enumerate(v2):
        r = dict(r); r["kind"] = "百度主推" if j == 0 else "百度备选"; routes.append(r)

    # 走廊两侧小偏移途经点 → 强制几条不同走法补充(可能在模型下更优)
    brg = _bearing(station, incident)
    mlng = station[0] + (incident[0] - station[0]) * 0.5
    mlat = station[1] + (incident[1] - station[1]) * 0.5
    for off in extra_offsets:
        for side in (90, -90):
            wp = _offset_point(mlng, mlat, brg + side, off)
            try:
                l1 = heatroute.plan_routes(station, wp, mode_zh="驾车", ak=ak, timeout=timeout)
                l2 = heatroute.plan_routes(wp, incident, mode_zh="驾车", ak=ak, timeout=timeout)
            except Exception:
                continue
            if l1 and l2:
                routes.append({"path": l1[0]["path"] + l2[0]["path"],
                               "distance": (l1[0]["distance"] or 0) + (l2[0]["distance"] or 0),
                               "duration": (l1[0]["duration"] or 0) + (l2[0]["duration"] or 0),
                               "kind": "绕行"})
    # 去重:按百度里程 ~120m 粒度
    seen, uniq = set(), []
    for r in routes:
        key = round((r["distance"] or 0) / 120)
        if key in seen:
            continue
        seen.add(key); uniq.append(r)
    return uniq


def predict(feat):
    """5 变量 dict -> 预测结果 dict(到场秒数、分级、各档概率、特征是否越训练范围)。"""
    s = _state(); b = s["bundle"]
    feats = b["feats"]
    x = np.array([[feat[f] for f in feats]], float)
    sec = float(b["reg"].predict(x)[0])
    cls = str(b["clf"].predict(x)[0])
    proba = b["clf"].predict_proba(x)[0]
    classes = list(b["clf"].classes_)
    prob_map = {c: float(p) for c, p in zip(classes, proba)}
    # 回归秒数落到 4 档(与训练切点一致)
    edges = b["bins"]; labels = b["bin_labels"]
    sec_bin = labels[int(np.searchsorted(edges, sec))]
    oob = {f: not (b["feat_ranges"][f][0] <= feat[f] <= b["feat_ranges"][f][1])
           for f in feats}
    return {"seconds": sec, "class": cls, "sec_bin": sec_bin,
            "proba": prob_map, "classes": classes,
            "feat_ranges": b["feat_ranges"], "oob": oob, "feats": feats}
