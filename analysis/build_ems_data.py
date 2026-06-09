# -*- coding: utf-8 -*-
"""
EMS 急救反应时间模块 —— 离线建模/数据瘦身脚本(只在有原始图层的机器跑一次)。

输入(原始图层,不进仓库,默认在 E:\\projects\\_ems_raw\\120data):
  - 道路__20米缓冲区\\上海市_其它道路.shp      支路(funcclass=5),WGS84
  - Pop_200米缓冲区\\total.tif                   人口栅格(人/像元),WGS84 0.001°
  - BUILT_V_FAR要除以3_200米缓冲区\\GHS_BUILT_V...tif  建筑体积 m³/像元,ESRI:54009
  - medicalPOI_200米缓冲区\\medicalPOI.shp        医疗 POI 点,WGS84
  - 120data_demo.csv                              训练表(5 自变量 + 因变量)

输出(进仓库,运行时用,纯 numpy/scipy/shapely 即可加载):
  - ems_layers.npz   人口密度栅格 + FAR 栅格 + 支路坐标 + 医疗POI坐标 + 校准系数 + 投影中心
  - ems_model.joblib LST 风格:回归(ART_s)+ 分类(ART_4type)双模型 + 元数据

变量定义(与 120data_demo.csv 对齐):
  Distance_m       行驶距离 = 路径几何长度(米)
  Road4_Length_m   路径 20m 缓冲区内支路总长(米)
  POPDEN_phm2      路径 200m 缓冲区人口密度均值(校准到训练分布)
  FAR              路径 200m 缓冲区容积率均值(校准到训练分布)
  MediPOIDen_nhm2  路径 200m 缓冲区医疗POI密度(个/公顷)
"""
import os
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.warp import reproject, Resampling
import joblib

RAW = os.environ.get("EMS_RAW", r"E:\projects\_ems_raw\120data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "120data_demo.csv")
if not os.path.exists(CSV):
    CSV = r"C:\Users\Administrator\AppData\Local\Temp\120data_demo.csv"

ROAD_SHP = os.path.join(RAW, r"道路__20米缓冲区\上海市_其它道路.shp")
POP_TIF = os.path.join(RAW, r"Pop_200米缓冲区\total.tif")
BUILTV_TIF = os.path.join(RAW, r"BUILT_V_FAR要除以3_200米缓冲区",
                          "GHS_BUILT_V_E2020_GLOBE_R2023A_54009_100_V1_0_R6_C30.tif")
POI_SHP = os.path.join(RAW, r"medicalPOI_200米缓冲区\medicalPOI.shp")

FEATS = ["Distance_m", "Road4_Length_m", "POPDEN_phm2", "FAR", "MediPOIDen_nhm2"]


def cell_area_m2(lat_deg, dlon_deg, dlat_deg):
    """WGS84 像元近似面积(m²),按纬度修正经度方向。"""
    m_per_deg_lat = 110540.0
    m_per_deg_lon = 111320.0 * np.cos(np.radians(lat_deg))
    return abs(dlon_deg * m_per_deg_lon) * abs(dlat_deg * m_per_deg_lat)


def fit_linear_calibration(raw_samples, target_series):
    """把 raw 分布线性映射到 target 分布:匹配均值/标准差。返回 (a, b),使 a*raw+b 对齐。"""
    raw = np.asarray(raw_samples, float)
    raw = raw[np.isfinite(raw)]
    tgt = np.asarray(target_series, float)
    tgt = tgt[np.isfinite(tgt)]
    a = tgt.std() / (raw.std() + 1e-9)
    b = tgt.mean() - a * raw.mean()
    return float(a), float(b)


def main():
    print(f"[paths] RAW={RAW}\n        CSV={CSV}")
    train = pd.read_csv(CSV)
    print(f"[train] {train.shape}  因变量分布:\n{train['ART_4type'].value_counts().to_dict()}")

    # ---------- 1. 人口密度栅格 ----------
    with rasterio.open(POP_TIF) as ds:
        pop = ds.read(1).astype("float64")
        nod = ds.nodata
        T = ds.transform
        nx, ny = ds.width, ds.height
        lon0, lat0_top = T.c, T.f          # 左上角
        dlon, dlat = T.a, T.e              # dlat<0
        bounds = ds.bounds
    valid = np.ones_like(pop, bool)
    if nod is not None:
        valid &= pop != nod
    valid &= np.isfinite(pop)
    pop[~valid] = np.nan
    # 每像元中心纬度(用于面积修正)
    rows = np.arange(ny)
    lat_centers = lat0_top + (rows + 0.5) * dlat            # (ny,)
    area_m2_row = cell_area_m2(lat_centers, dlon, dlat)     # (ny,)
    pop_dens = pop / (area_m2_row[:, None] / 10000.0)       # 人/公顷
    print(f"[pop] grid {nx}x{ny} 像元≈{area_m2_row.mean():.0f}m² "
          f"原始密度 mean={np.nanmean(pop_dens):.1f} max={np.nanmax(pop_dens):.1f}")

    # ---------- 2. FAR 栅格(把 built_v 重投影到人口栅格) ----------
    builtv_on_pop = np.full((ny, nx), np.nan, dtype="float64")
    with rasterio.open(BUILTV_TIF) as bs:
        src = bs.read(1).astype("float64")
        src_nod = bs.nodata
        dst = np.zeros((ny, nx), dtype="float64")
        reproject(
            source=src, destination=dst,
            src_transform=bs.transform, src_crs=bs.crs,
            dst_transform=T, dst_crs="EPSG:4326",
            src_nodata=src_nod, dst_nodata=np.nan,
            resampling=Resampling.average,
        )
    builtv_on_pop = dst
    # FAR = (建筑体积/3 层高=楼面面积) / 像元面积
    far = (builtv_on_pop / 3.0) / area_m2_row[:, None]
    far[~np.isfinite(far)] = np.nan
    print(f"[far] 原始 mean={np.nanmean(far):.3f} max={np.nanmax(far):.2f}")

    # ---------- 3. 支路 + 医疗POI(裁剪到人口栅格范围 + 余量) ----------
    margin = 0.01  # ~1km
    minx, miny, maxx, maxy = bounds.left - margin, bounds.bottom - margin, \
        bounds.right + margin, bounds.top + margin
    roads = gpd.read_file(ROAD_SHP, bbox=(minx, miny, maxx, maxy))
    roads = roads[roads.geometry.type == "LineString"]
    print(f"[roads] 裁剪后支路 {len(roads)} 条")
    # 展平为 coords + offsets
    coords_list, offs = [], [0]
    for geom in roads.geometry:
        xy = np.asarray(geom.coords, dtype="float64")
        coords_list.append(xy)
        offs.append(offs[-1] + len(xy))
    road_xy = np.vstack(coords_list).astype("float32")
    road_off = np.asarray(offs, dtype="int32")

    poi = gpd.read_file(POI_SHP, bbox=(minx, miny, maxx, maxy))
    poi = poi[poi.geometry.type == "Point"]
    poi_xy = np.array([[g.x, g.y] for g in poi.geometry], dtype="float32")
    print(f"[poi] 裁剪后医疗POI {len(poi_xy)} 个")

    # ---------- 4. 校准系数(POPDEN/FAR):在支路顶点处采样原始栅格 -> 对齐训练分布 ----------
    # 路径都沿支路走,用支路顶点处的栅格值近似"路径缓冲区会遇到的值分布"
    def sample_grid(grid, xs, ys):
        cols = ((xs - lon0) / dlon).astype(int)
        rws = ((ys - lat0_top) / dlat).astype(int)
        ok = (cols >= 0) & (cols < nx) & (rws >= 0) & (rws < ny)
        out = np.full(xs.shape, np.nan)
        out[ok] = grid[rws[ok], cols[ok]]
        return out

    sx, sy = road_xy[:, 0].astype(float), road_xy[:, 1].astype(float)
    pop_raw_samp = sample_grid(pop_dens, sx, sy)
    far_raw_samp = sample_grid(far, sx, sy)
    pop_a, pop_b = fit_linear_calibration(pop_raw_samp, train["POPDEN_phm2"])
    far_a, far_b = fit_linear_calibration(far_raw_samp, train["FAR"])
    print(f"[calib] POPDEN: a={pop_a:.4f} b={pop_b:.2f}  "
          f"(校准后采样 mean={np.nanmean(pop_a*pop_raw_samp+pop_b):.1f} vs 训练 {train['POPDEN_phm2'].mean():.1f})")
    print(f"[calib] FAR:    a={far_a:.4f} b={far_b:.3f}  "
          f"(校准后采样 mean={np.nanmean(far_a*far_raw_samp+far_b):.3f} vs 训练 {train['FAR'].mean():.3f})")

    # ---------- 5. 存运行时图层 ----------
    out_npz = os.path.join(ROOT, "ems_layers.npz")
    np.savez_compressed(
        out_npz,
        pop_dens=pop_dens.astype("float32"),
        far=far.astype("float32"),
        grid_meta=np.array([lon0, lat0_top, dlon, dlat, nx, ny], dtype="float64"),
        calib=np.array([pop_a, pop_b, far_a, far_b], dtype="float64"),
        road_xy=road_xy, road_off=road_off,
        poi_xy=poi_xy,
        center=np.array([(minx + maxx) / 2, (miny + maxy) / 2], dtype="float64"),
    )
    print(f"[save] {out_npz}  {os.path.getsize(out_npz)/1e6:.1f} MB")

    # ---------- 6. 训练模型(回归 ART_s + 分类 ART_4type) ----------
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    X = train[FEATS].values
    reg = RandomForestRegressor(n_estimators=400, min_samples_leaf=5,
                                random_state=42, n_jobs=-1).fit(X, train["ART_s"].values)
    clf = RandomForestClassifier(n_estimators=400, min_samples_leaf=5,
                                 class_weight="balanced_subsample",
                                 random_state=42, n_jobs=-1).fit(X, train["ART_4type"].values)
    bundle = {
        "reg": reg, "clf": clf, "feats": FEATS,
        "bins": [240, 480, 720], "bin_labels": ["4min", "8min", "12min", "Delay"],
        "feat_ranges": {f: [float(train[f].min()), float(train[f].max())] for f in FEATS},
    }
    out_model = os.path.join(ROOT, "ems_model.joblib")
    joblib.dump(bundle, out_model, compress=3)
    print(f"[save] {out_model}  {os.path.getsize(out_model)/1e6:.1f} MB")
    print("[done]")


if __name__ == "__main__":
    main()
