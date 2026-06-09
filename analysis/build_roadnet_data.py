# -*- coding: utf-8 -*-
"""离线预处理:街景路网(含 S_veget 绿视率)→ 运行时多目标路由用的紧凑 npz。

输入:link_SVI_补充空值_type.shp(98k 路段,WGS84,字段 from_node/to_node/length/S_veget/dir…)
产物 roadnet.npz(提交进仓库):最大连通分量的节点坐标 + 边(u,v,length,S_veget,逐边采样 LST)
       + 逐边折线几何(画路线用)+ LST 归一化分位。

逐边 LST 由 green_lst 的 100m 实测栅格采样(经 heatroute.sample_lst)。
只需在有原始 shp 的机器上跑一次。运行时(roadnet.py)只用 numpy/scipy。
用法:.venv/Scripts/python.exe analysis/build_roadnet_data.py
"""
import collections
import os
import sys

import numpy as np
import shapefile
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根
import heatroute   # sample_lst(green_lst 100m LST 栅格)

RAW = r"D:/projects/_svi_raw/link"
OUT = r"D:/projects/healthy-city-platform/roadnet.npz"

print("▶ 读取路网 shp/dbf ...")
r = shapefile.Reader(RAW)
flds = [f[0] for f in r.fields[1:]]
fi = {n: i for i, n in enumerate(flds)}
recs = r.records(); shps = r.shapes()
M = len(recs)
fn = np.array([rec[fi["from_node"]] for rec in recs], np.int64)
tn = np.array([rec[fi["to_node"]] for rec in recs], np.int64)
length = np.array([rec[fi["length"]] for rec in recs], float)
veg = np.array([rec[fi["S_veget"]] for rec in recs], float)
print(f"  路段 {M:,}")

# 节点 id -> 坐标(用每条边的首/末顶点)
ncoord = {}
for k, s in enumerate(shps):
    p = s.points
    ncoord.setdefault(int(fn[k]), p[0]); ncoord.setdefault(int(tn[k]), p[-1])
ids = sorted(ncoord); idx = {n: i for i, n in enumerate(ids)}; N = len(ids)
nlng = np.array([ncoord[n][0] for n in ids], float)
nlat = np.array([ncoord[n][1] for n in ids], float)
u = np.array([idx[int(x)] for x in fn]); v = np.array([idx[int(x)] for x in tn])

print("▶ 取最大连通分量 ...")
g = coo_matrix((np.ones(M), (u, v)), shape=(N, N))
_, lab = connected_components(g, directed=False)
main = collections.Counter(lab).most_common(1)[0][0]
keep_node = (lab == main)
keep_edge = keep_node[u] & keep_node[v]
old2new = -np.ones(N, int); old2new[np.where(keep_node)[0]] = np.arange(int(keep_node.sum()))
nlng2, nlat2 = nlng[keep_node], nlat[keep_node]
ek = np.where(keep_edge)[0]
u2, v2 = old2new[u[keep_edge]], old2new[v[keep_edge]]
length2, veg2 = length[keep_edge], veg[keep_edge]
shps_keep = [shps[k] for k in ek]
print(f"  保留 节点 {len(nlng2):,} / 边 {len(u2):,}")

print("▶ 逐边采样 LST(green_lst 100m 栅格)...")
allxy = []; off = [0]
for s in shps_keep:
    allxy.extend(s.points); off.append(len(allxy))
allxy = np.array(allxy, float)
lst_all = heatroute.sample_lst(allxy[:, 0], allxy[:, 1])
edge_lst = np.array([np.nanmean(lst_all[off[i]:off[i + 1]]) for i in range(len(shps_keep))])
med = float(np.nanmedian(edge_lst))
edge_lst = np.where(np.isfinite(edge_lst), edge_lst, med)
print(f"  边 LST: {edge_lst.min():.1f}~{edge_lst.max():.1f}°C")

np.savez_compressed(
    OUT,
    node_lng=nlng2.astype(np.float32), node_lat=nlat2.astype(np.float32),
    eu=u2.astype(np.int32), ev=v2.astype(np.int32),
    elen=length2.astype(np.float32), eveg=veg2.astype(np.float32),
    elst=edge_lst.astype(np.float32),
    geom_xy=allxy.astype(np.float32), geom_off=np.array(off, np.int32),
    lst_lo=np.float32(np.nanpercentile(edge_lst, 5)),
    lst_hi=np.float32(np.nanpercentile(edge_lst, 95)),
)
print(f"  ✓ 写出 {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
print(f"\n✅ 完成。节点 {len(nlng2):,} 边 {len(u2):,} | S_veget 中位 {np.median(veg2):.3f} | "
      f"LST 归一 {np.percentile(edge_lst,5):.1f}~{np.percentile(edge_lst,95):.1f}°C")
