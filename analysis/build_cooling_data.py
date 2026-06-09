# -*- coding: utf-8 -*-
"""离线预处理:把 MCLP 三个 shapefile(UTM 51N / EPSG:32651)瘦身成运行时数据。

产物(提交进仓库,运行时 app 用):
  - cooling_mclp.npz      纳凉点/小区质心/街道质心 的坐标(UTM 米 + WGS84 经纬度)
                          + 小区 Pop/LST/Health + 小区所属街道索引 + 街道名
  - cooling_jiedao.geojson 简化后的街道边界(choropleth 用,WGS84)

只需在有原始 shp 的机器上跑一次。运行时(app / cooling_mclp.py)不依赖本脚本,
也不依赖 geopandas/GDAL —— 这里用 pyshp + shapely + pyproj。

用法(venv):
  .venv/Scripts/python.exe analysis/build_cooling_data.py
"""
import json
import os

import numpy as np
import shapefile  # pyshp
from shapely.geometry import shape, mapping
from shapely.strtree import STRtree
from shapely.ops import transform as shp_transform
from pyproj import Transformer

RAW = r"D:/projects/_mclp_raw"            # 解压后的原始 shp 目录(仓库外)
OUT = r"D:/projects/healthy-city-platform"
JD_NAME_FIELD = "F"                        # jiedao.shp 中的街道名字段

_to_wgs = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)


def _tf(x, y, z=None):
    lon, lat = _to_wgs.transform(x, y)
    return (lon, lat)


def _to_ll(xy):
    lon, lat = _to_wgs.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([lon, lat])


print("▶ 读取 cool.shp(只读几何,跳过 50MB dbf)...")
rc = shapefile.Reader(os.path.join(RAW, "cool.shp"))
cool_g = [shape(s.__geo_interface__) for s in rc.shapes()]
cool_xy = np.array([[g.x, g.y] for g in cool_g], float)
print(f"  现状纳凉点:{len(cool_xy):,}")

print("▶ 读取 residence1.shp(小区面 → 质心 + Pop/LST/Health)...")
rr = shapefile.Reader(os.path.join(RAW, "residence1.shp"))
res_flds = [f[0] for f in rr.fields[1:]]
res_cent, pop, lst, health = [], [], [], []
for sr in rr.shapeRecords():
    res_cent.append(shape(sr.shape.__geo_interface__).centroid)
    d = dict(zip(res_flds, sr.record))
    pop.append(d.get("Pop", 0)); lst.append(d.get("LST", 0)); health.append(d.get("Health", 0))
res_xy = np.array([[c.x, c.y] for c in res_cent], float)
pop = np.array(pop, float); lst = np.array(lst, float); health = np.array(health, float)
print(f"  小区数:{len(res_xy):,} | 字段:{res_flds}")

print("▶ 读取 jiedao.shp(街道面 → 名称 + 质心)...")
rj = shapefile.Reader(os.path.join(RAW, "jiedao.shp"))
jd_flds = [f[0] for f in rj.fields[1:]]
jd_g, jd_names = [], []
for i, sr in enumerate(rj.shapeRecords()):
    jd_g.append(shape(sr.shape.__geo_interface__))
    d = dict(zip(jd_flds, sr.record))
    jd_names.append(str(d.get(JD_NAME_FIELD, f"街道{i}")).strip())
jd_xy = np.array([[g.centroid.x, g.centroid.y] for g in jd_g], float)
print(f"  街道数:{len(jd_g)} | 名称字段:{JD_NAME_FIELD}")

print("▶ 小区 → 街道 归属(点在面内,STRtree 加速)...")
tree = STRtree(jd_g)
res_jd = np.full(len(res_cent), -1, int)
for i, c in enumerate(res_cent):
    for j in tree.query(c):
        if jd_g[int(j)].contains(c):
            res_jd[i] = int(j)
            break
n_unknown = int((res_jd < 0).sum())
print(f"  已归属:{len(res_jd) - n_unknown:,} | 未落入任何街道:{n_unknown:,}")

print("▶ 投影到 WGS84(显示用)...")
cool_ll = _to_ll(cool_xy)
res_ll = _to_ll(res_xy)
jd_ll = _to_ll(jd_xy)

out_npz = os.path.join(OUT, "cooling_mclp.npz")
np.savez_compressed(
    out_npz,
    cool_xy=cool_xy.astype(np.float32), cool_ll=cool_ll.astype(np.float32),
    res_xy=res_xy.astype(np.float32), res_ll=res_ll.astype(np.float32),
    pop=pop.astype(np.float32), lst=lst.astype(np.float32), health=health.astype(np.float32),
    res_jd=res_jd.astype(np.int16),
    jd_xy=jd_xy.astype(np.float32), jd_ll=jd_ll.astype(np.float32),
    jd_names=np.array(jd_names, dtype="<U40"),
)
print(f"  ✓ 写出 {out_npz}  ({os.path.getsize(out_npz)/1e6:.2f} MB)")

print("▶ 生成简化街道边界 GeoJSON(choropleth)...")
feats = []
for i, g in enumerate(jd_g):
    gw = shp_transform(_tf, g).simplify(0.0006, preserve_topology=True)
    feats.append({"type": "Feature",
                  "properties": {"NAME": jd_names[i], "idx": i},
                  "geometry": mapping(gw)})
gj = {"type": "FeatureCollection", "features": feats}
out_gj = os.path.join(OUT, "cooling_jiedao.geojson")
with open(out_gj, "w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False)
print(f"  ✓ 写出 {out_gj}  ({os.path.getsize(out_gj)/1e6:.2f} MB)")

print("\n✅ 完成。运行时数据已就绪:cooling_mclp.npz + cooling_jiedao.geojson")
