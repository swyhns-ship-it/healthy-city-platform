# -*- coding: utf-8 -*-
"""
离线导出:把 RF 模型蒸馏成 demo 运行时用的纯 numpy 网格资产。

对每个 100m 网格,预存它在若干 greenfrac 锚点下的 RF 预测 LST。
demo 运行时不需要 sklearn/GDAL,只用 numpy 在锚点间插值即可得到
"该格 greenfrac 从现状改到目标值"的 ΔLST,且保留每格自身的建成背景。

输出: E:\projects\hia_demo\green_lst_grid.npz
"""
import os, json
import numpy as np
import pandas as pd
from osgeo import gdal
from sklearn.ensemble import RandomForestRegressor

OUT_DIR = r"E:\projects\hia_demo\analysis\out"
NPZ = r"E:\projects\hia_demo\green_lst_grid.npz"
TIF_FRAC = r"C:\Users\Administrator\Downloads\SH_greenfrac_100m.tif"
CACHE = os.path.join(OUT_DIR, "joined.pkl")

FEATURES = ["greenfrac", "dw_built", "bldg_height", "FAR_proxy", "ntl",
            "elevation", "slope"]
ANCHORS = [0.0, 0.25, 0.5, 0.75, 1.0]

# 网格几何(来自 tif)
ds = gdal.Open(TIF_FRAC)
GT = ds.GetGeoTransform()           # (x0,100,0,y0,0,-100)
NX, NY = ds.RasterXSize, ds.RasterYSize  # 973 x 1388

df = pd.read_pickle(CACHE)

# ---- 训练(陆地、有效 LST)----
train = df[(df["LST"] >= 20) & (df["LST"] <= 60)]
train = train[(train["worldcover"] != 80) & (train["worldcover"] != 90)]
train = train.dropna(subset=FEATURES + ["LST"])
print("训练样本:", len(train))
rf = RandomForestRegressor(n_estimators=120, max_depth=20, min_samples_leaf=15,
                           n_jobs=-1, random_state=0)
rf.fit(train[FEATURES], train["LST"])
print("训练 R2=%.3f" % rf.score(train[FEATURES], train["LST"]))

# ---- 把每行 CSV 映射到网格 (row,col) ----
# CSV 经纬度 -> UTM(用 tif 同投影)。greenfrac 已采样过,这里用其行列。
from pyproj import Transformer
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
x, y = tr.transform(df["lon"].values, df["lat"].values)
col = ((x - GT[0]) / GT[1]).astype(int)
row = ((y - GT[3]) / GT[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)

# ---- 预测每格在各 greenfrac 锚点下的 LST(仅可预测格)----
predictable = inb & df[FEATURES].notna().all(axis=1).values
sub = df.loc[predictable].copy()
sub_row = row[predictable]; sub_col = col[predictable]

# 用于预测的特征矩阵(land 限定可不做,这里对所有有特征的格预测以便整图展示)
base_feat = sub[FEATURES].copy()
pred_anchor = np.full((len(ANCHORS), NY, NX), np.nan, dtype=np.float32)
for ai, g in enumerate(ANCHORS):
    f = base_feat.copy(); f["greenfrac"] = g
    p = rf.predict(f[FEATURES].values).astype(np.float32)
    pred_anchor[ai, sub_row, sub_col] = p
    print("  锚点 greenfrac=%.2f 预测完成" % g)

# ---- 网格层:观测 LST、现状 greenfrac、人口、land 掩膜 ----
def to_grid(colname, dtype=np.float32):
    arr = np.full((NY, NX), np.nan, dtype=dtype)
    arr[row[inb], col[inb]] = df.loc[inb, colname].values.astype(dtype)
    return arr

obs_lst = to_grid("LST")
greenfrac_cur = to_grid("greenfrac")
pop = to_grid("pop")
worldcover = np.full((NY, NX), -1, dtype=np.int16)
worldcover[row[inb], col[inb]] = df.loc[inb, "worldcover"].values.astype(np.int16)

# land 掩膜:有预测且非水/湿、LST 有效
land_mask = (~np.isnan(pred_anchor[0])) & (worldcover != 80) & (worldcover != 90)

# 全网格每格中心经纬度(运行时点-多边形判断用,免投影)
cc = (np.arange(NX) + 0.5) * GT[1] + GT[0]          # 各列中心 X(UTM)
cr = (np.arange(NY) + 0.5) * GT[5] + GT[3]          # 各行中心 Y(UTM)
gx, gy = np.meshgrid(cc, cr)
inv = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
glon, glat = inv.transform(gx.ravel(), gy.ravel())
lon_grid = np.asarray(glon, dtype=np.float32).reshape(NY, NX)
lat_grid = np.asarray(glat, dtype=np.float32).reshape(NY, NX)

np.savez_compressed(
    NPZ,
    anchors=np.array(ANCHORS, dtype=np.float32),
    pred_anchor=pred_anchor,            # (5, NY, NX) 各锚点预测 LST
    obs_lst=obs_lst,                    # 观测地表温度(展示"现状")
    greenfrac_cur=greenfrac_cur,        # 现状绿地占比
    pop=pop,
    worldcover=worldcover,
    land_mask=land_mask,
    lon_grid=lon_grid,
    lat_grid=lat_grid,
    gt=np.array(GT, dtype=np.float64),
    nx=NX, ny=NY,
    features=np.array(FEATURES),
)
meta = {"features": FEATURES, "anchors": ANCHORS, "gt": list(GT),
        "nx": NX, "ny": NY, "crs": "EPSG:32651",
        "train_r2": round(float(rf.score(train[FEATURES], train["LST"])), 3),
        "n_train": int(len(train))}
json.dump(meta, open(os.path.join(OUT_DIR, "grid_meta.json"), "w"),
          ensure_ascii=False, indent=2)
sz = os.path.getsize(NPZ) / 1e6
print("\n导出 %s (%.1f MB)" % (NPZ, sz))
print("可预测格:", int(predictable.sum()), " land 格:", int(land_mask.sum()))
