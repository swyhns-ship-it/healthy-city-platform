# -*- coding: utf-8 -*-
"""绿荫凉爽路径引擎:在街景路网上做多目标最短路(距离 / 低温 LST / 绿荫 S_veget 加权)。

数据 roadnet.npz 由 analysis/build_roadnet_data.py 离线生成(中心城区 74k 节点 / 95k 边,
每条边带 length、S_veget(绿视率)、采样 LST、折线几何)。运行时只用 numpy/scipy。

边权 = length × (1 + w_heat·heat_norm + w_shade·(1−S_veget)):
  w=0 → 最短路;w_heat 大 → 避开高温;w_shade 大 → 偏好绿荫。
被 views/roadnet_route.py 调用。
"""
import os

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

_DIR = os.path.dirname(os.path.abspath(__file__))
_S = None
_KX = float(np.cos(np.radians(31.24)))
SHADE_VEG = 0.25          # 绿视率 ≥ 此值算“有荫路段”


def _state():
    global _S
    if _S is None:
        d = np.load(os.path.join(_DIR, "roadnet.npz"))
        s = {k: d[k] for k in d.files}
        s["N"] = int(len(s["node_lng"]))
        s["tree"] = cKDTree(np.column_stack([s["node_lng"] * _KX, s["node_lat"]]))
        em = {}
        eu, ev = s["eu"], s["ev"]
        for i in range(len(eu)):
            a, b = int(eu[i]), int(ev[i])
            em[(a, b)] = i; em[(b, a)] = i
        s["emap"] = em
        s["lst_lo"] = float(s["lst_lo"]); s["lst_hi"] = float(s["lst_hi"])
        # 无向图拓扑(两向),路由时只换边权 data
        s["row"] = np.concatenate([eu, ev]); s["col"] = np.concatenate([ev, eu])
        _S = s
    return _S


def meta():
    s = _state()
    return {"n_node": s["N"], "n_edge": int(len(s["eu"])),
            "bbox": (float(s["node_lng"].min()), float(s["node_lat"].min()),
                     float(s["node_lng"].max()), float(s["node_lat"].max())),
            "veg_median": float(np.median(s["eveg"]))}


def snap(lng, lat):
    """最近节点 (索引, 距离米)。"""
    s = _state()
    dd, i = s["tree"].query([lng * _KX, lat])
    return int(i), float(dd) * 111000.0


def in_network(lng, lat, max_m=500):
    return snap(lng, lat)[1] <= max_m


def _edge_cost(w_heat, w_shade):
    s = _state()
    heat = np.clip((s["elst"] - s["lst_lo"]) / (s["lst_hi"] - s["lst_lo"] + 1e-9), 0, 1)
    shade_pen = 1.0 - np.clip(s["eveg"], 0, 1)
    return s["elen"] * (1.0 + w_heat * heat + w_shade * shade_pen)


def route(o, d, w_heat=0.0, w_shade=0.0):
    """求一条路径。o/d=(lng,lat)。返回几何 + 指标,或 None(不可达)。"""
    s = _state()
    src = snap(*o)[0]; dst = snap(*d)[0]
    if src == dst:
        return None
    c = _edge_cost(w_heat, w_shade)
    data = np.concatenate([c, c])
    G = csr_matrix((data, (s["row"], s["col"])), shape=(s["N"], s["N"]))
    dist, pred = dijkstra(G, indices=src, return_predecessors=True)
    if not np.isfinite(dist[dst]):
        return None
    nodes = []; cur = dst
    while cur != src and cur >= 0:
        nodes.append(cur); cur = int(pred[cur])
    nodes.append(src); nodes.reverse()

    gx, goff, em = s["geom_xy"], s["geom_off"], s["emap"]
    coords = []; tot = 0.0; lst_w = 0.0; veg_w = 0.0; shade_len = 0.0
    for a, b in zip(nodes[:-1], nodes[1:]):
        i = em.get((a, b))
        if i is None:
            continue
        seg = gx[goff[i]:goff[i + 1]]
        na = (s["node_lng"][a], s["node_lat"][a])
        if (abs(seg[0, 0] - na[0]) + abs(seg[0, 1] - na[1])) > \
           (abs(seg[-1, 0] - na[0]) + abs(seg[-1, 1] - na[1])):
            seg = seg[::-1]
        seg = seg[1:] if coords else seg
        coords.extend((float(x), float(y)) for x, y in seg)
        L = float(s["elen"][i]); tot += L
        lst_w += float(s["elst"][i]) * L; veg_w += float(s["eveg"][i]) * L
        if s["eveg"][i] >= SHADE_VEG:
            shade_len += L
    return {"coords": coords, "length_m": tot,
            "mean_lst": lst_w / max(tot, 1e-9), "mean_veg": veg_w / max(tot, 1e-9),
            "shade_ratio": shade_len / max(tot, 1e-9)}


# 预设方案:(标签, w_heat, w_shade)
PRESETS = [("最短", 0.0, 0.0), ("最凉", 3.0, 0.0), ("最荫", 0.0, 3.0)]
