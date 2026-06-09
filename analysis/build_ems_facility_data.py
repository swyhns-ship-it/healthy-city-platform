# -*- coding: utf-8 -*-
"""EMS 急救设施配置优化 —— 离线数据瘦身(只在有原始图层的机器跑一次)。

需求端:外环内 256,269 栋建筑的 ART 预测(WM358 4 档时间)聚合到 ~200m 格网;
        每格附 总人口/老年人口(Pop 栅格)、ART 欠服务分数、所属街道。
供给端:202 个现状急救站(heat_ems_points.npz)。
街道:cooling_jiedao.geojson(与纳凉共用,做公平性 choropleth)。

输出 ems_facility.npz,运行时由 ems_facility.py 用 scipy+pulp 求解 MCLP(不依赖 geopandas)。
"""
import os
import json

import numpy as np
import geopandas as gpd
import rasterio
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

RAW = os.environ.get("EMS_RAW", r"E:\projects\_ems_raw\120data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_SHP = os.path.join(RAW, r"外环内建筑ART预测结果_字段WM358是4类时间\外环内建筑ART预测结果.shp")
POP_TIF = os.path.join(RAW, r"Pop_200米缓冲区\total.tif")
AGE_TIF = os.path.join(RAW, r"Pop_200米缓冲区\aging.tif")
JD_GEOJSON = os.path.join(ROOT, "cooling_jiedao.geojson")

STEP = 0.002                       # 格网边长(度)≈ 200m
ART_ORD = {"4min": 0, "8min": 1, "12min": 2, "Delay": 3}


def main():
    # ---------- 1. 建筑 ART → 格网聚合 ----------
    print("[1/5] 读取建筑 ART…")
    g = gpd.read_file(ART_SHP, columns=["WM358", "Floor", "Shape_Area"])
    cen = g.geometry.representative_point()
    lon = cen.x.values; lat = cen.y.values
    ordv = g["WM358"].map(ART_ORD).fillna(1).values.astype(float)
    floor = np.clip(g["Floor"].fillna(1).values.astype(float), 1, None)
    farea = np.clip(g["Shape_Area"].fillna(0).values.astype(float), 0, None)
    fa_wt = floor * farea + 1e-12          # 楼面面积(相对权重,作占用近似)

    lon0 = np.floor(lon.min() / STEP) * STEP
    lat0 = np.floor(lat.min() / STEP) * STEP
    col = ((lon - lon0) / STEP).astype(int)
    row = ((lat - lat0) / STEP).astype(int)
    key = row.astype(np.int64) * 100000 + col

    # 每格:楼面加权 ART 均值(欠服务分数)、建筑数
    from collections import defaultdict
    sum_w = defaultdict(float); sum_wart = defaultdict(float); cnt = defaultdict(int)
    for k, a, w in zip(key, ordv, fa_wt):
        sum_w[k] += w; sum_wart[k] += a * w; cnt[k] += 1
    cells = sorted(sum_w.keys())
    art_score = {k: sum_wart[k] / sum_w[k] for k in cells}
    print(f"      建筑 {len(g):,} → 有建筑格网 {len(cells):,}")

    # 格中心经纬度
    crow = np.array([k // 100000 for k in cells]); ccol = np.array([k % 100000 for k in cells])
    clon = lon0 + (ccol + 0.5) * STEP; clat = lat0 + (crow + 0.5) * STEP
    cidx = {k: i for i, k in enumerate(cells)}
    art = np.array([art_score[k] for k in cells])

    # ---------- 2. 人口/老年 栅格 → 同格网求和 ----------
    print("[2/5] 叠加人口/老年栅格…")
    def sum_raster_to_cells(tif):
        with rasterio.open(tif) as ds:
            arr = ds.read(1).astype(float); nod = ds.nodata; T = ds.transform
            ny, nx = arr.shape
        jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
        plon = T.c + (jj + 0.5) * T.a; plat = T.f + (ii + 0.5) * T.e
        val = arr.ravel(); plon = plon.ravel(); plat = plat.ravel()
        m = np.isfinite(val) & (val != (nod if nod is not None else np.nan)) & (val > 0)
        val, plon, plat = val[m], plon[m], plat[m]
        pc = ((plon - lon0) / STEP).astype(int); pr = ((plat - lat0) / STEP).astype(int)
        pk = pr.astype(np.int64) * 100000 + pc
        out = np.zeros(len(cells))
        for k, v in zip(pk, val):
            i = cidx.get(k)
            if i is not None:
                out[i] += v
        return out
    pop = sum_raster_to_cells(POP_TIF)
    elderly = sum_raster_to_cells(AGE_TIF)
    print(f"      总人口 {pop.sum():,.0f},老年 {elderly.sum():,.0f}")

    # ---------- 3. 街道归属(格中心 point-in-polygon) ----------
    print("[3/5] 街道归属…")
    with open(JD_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    polys, names = [], []
    for ft in gj["features"]:
        polys.append(shape(ft["geometry"])); names.append(ft["properties"]["NAME"])
    tree = STRtree(polys)
    dem_jd = np.full(len(cells), -1, int)
    for i in range(len(cells)):
        p = Point(clon[i], clat[i])
        for j in tree.query(p):
            if polys[int(j)].contains(p):
                dem_jd[i] = int(j); break
    keep_jd = sorted(set(int(x) for x in dem_jd if x >= 0))
    remap = {old: new for new, old in enumerate(keep_jd)}
    dem_jd = np.array([remap.get(int(x), -1) for x in dem_jd])
    jd_names = [names[old] for old in keep_jd]
    jd_ll = np.array([[polys[old].representative_point().x,
                       polys[old].representative_point().y] for old in keep_jd])
    # 丢掉不在任何街道内的格(极少)
    inb = dem_jd >= 0
    clon, clat, art, pop, elderly, dem_jd = clon[inb], clat[inb], art[inb], pop[inb], elderly[inb], dem_jd[inb]
    print(f"      街道 {len(jd_names)} 个,有效需求格 {inb.sum():,}")

    # ---------- 4. 等距圆柱投影到局部米制 ----------
    cx, cy = float(np.mean(clon)), float(np.mean(clat))
    mlon = 111320.0 * np.cos(np.radians(cy)); mlat = 110540.0
    def to_m(lo, la):
        return np.column_stack([(np.asarray(lo) - cx) * mlon, (np.asarray(la) - cy) * mlat])
    dem_xy = to_m(clon, clat); dem_ll = np.column_stack([clon, clat])
    jd_xy = to_m(jd_ll[:, 0], jd_ll[:, 1])

    E = np.load(os.path.join(ROOT, "heat_ems_points.npz"))
    ems_ll = np.column_stack([E["lon"], E["lat"]])
    ems_xy = to_m(E["lon"], E["lat"])

    # ---------- 5. 存盘 ----------
    out = os.path.join(ROOT, "ems_facility.npz")
    np.savez_compressed(
        out,
        dem_xy=dem_xy.astype("float32"), dem_ll=dem_ll.astype("float32"),
        pop=pop.astype("float32"), elderly=elderly.astype("float32"),
        art=art.astype("float32"), dem_jd=dem_jd.astype("int32"),
        ems_xy=ems_xy.astype("float32"), ems_ll=ems_ll.astype("float32"),
        jd_xy=jd_xy.astype("float32"), jd_ll=jd_ll.astype("float32"),
        jd_names=np.array(jd_names, dtype=object),
        center=np.array([cx, cy], float),
    )
    print(f"[done] {out}  {os.path.getsize(out)/1e6:.2f} MB  "
          f"需求格 {len(dem_xy):,} | ART均值 {art.mean():.2f} | "
          f"欠服务(≥1.5)格占比 {(art>=1.5).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
