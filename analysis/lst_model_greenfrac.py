# -*- coding: utf-8 -*-
"""
上海 100m: 用【绿地占比 greenfrac】(不是 NDVI) 作绿地预测因子的 LST 模型。
理由:demo 里用户画的是新增/减少绿地的多边形,落入网格 greenfrac 现状->目标,
预测因子必须与"这块地变绿了多少"对应。

- 把 SH_greenfrac_100m.tif / SH_green_100m.tif 按经纬度采样 join 进 CSV
- 清洗(LST 范围、剔水体)
- 随机森林 LST ~ greenfrac + 建成/地形(默认不含 lat/lon,避免地理坐标吸收绿地效应)
- 空间分块交叉验证给诚实泛化精度
- 剂量-反应:固定建成背景,扫 greenfrac -> 预测 LST(这就是"画多边形"对应的曲线)
- 案例标定:greenfrac 现状->目标 的预测 ΔLST
"""
import os, json
import numpy as np
import pandas as pd
from osgeo import gdal
from pyproj import Transformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error

CSV = r"C:\Users\Administrator\Downloads\SH_HIA_100m_full.csv"
TIF_FRAC = r"C:\Users\Administrator\Downloads\SH_greenfrac_100m.tif"
TIF_BIN = r"C:\Users\Administrator\Downloads\SH_green_100m.tif"
OUT = r"E:\projects\hia_demo\analysis\out"
os.makedirs(OUT, exist_ok=True)
CACHE = os.path.join(OUT, "joined.pkl")

# 不含 lat/lon:让 greenfrac 承载绿地降温,而非被地理坐标吸收
FEATURES = ["greenfrac", "dw_built", "bldg_height", "FAR_proxy", "ntl",
            "elevation", "slope"]


def sample_tif(path, lon, lat):
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    arr = ds.GetRasterBand(1).ReadAsArray()
    ny, nx = arr.shape
    tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    x, y = tr.transform(lon, lat)
    col = ((x - gt[0]) / gt[1]).astype(int)
    row = ((y - gt[3]) / gt[5]).astype(int)
    ok = (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
    out = np.full(len(lon), np.nan, dtype=float)
    out[ok] = arr[row[ok], col[ok]]
    return out, ok


def build_joined():
    df = pd.read_csv(CSV)
    lon = df["lon"].values; lat = df["lat"].values
    gf, ok1 = sample_tif(TIF_FRAC, lon, lat)
    gb, ok2 = sample_tif(TIF_BIN, lon, lat)
    df["greenfrac"] = gf
    df["green_bin"] = gb
    print("greenfrac 采样: 命中 %d/%d, 缺失 %d" %
          (ok1.sum(), len(df), np.isnan(gf).sum()))
    df.to_pickle(CACHE)
    return df


def load_clean():
    df = pd.read_pickle(CACHE) if os.path.exists(CACHE) else build_joined()
    n0 = len(df)
    df = df[(df["LST"] >= 20) & (df["LST"] <= 60)]
    df = df[(df["worldcover"] != 80) & (df["worldcover"] != 90)]
    df = df.dropna(subset=FEATURES + ["LST", "lat", "lon"]).reset_index(drop=True)
    print("清洗: %d -> %d (%.1f%%)" % (n0, len(df), 100 * len(df) / n0))
    print("greenfrac 分布:", df["greenfrac"].describe()[["min","25%","50%","75%","max"]].round(3).to_dict())
    return df


def corr_check(df):
    print("\n=== greenfrac 与 LST 剂量-反应(分箱) ===")
    df["gf_bin"] = pd.qcut(df["greenfrac"], 10, duplicates="drop")
    print(df.groupby("gf_bin")["LST"].agg(["mean", "count"]).round(2).to_string())
    print("\ngreenfrac vs LST 相关:", round(df[["greenfrac","LST"]].corr().iloc[0,1], 3))


def spatial_block_cv(df, n_blocks=6):
    df = df.copy()
    df["bx"] = pd.qcut(df["lon"], n_blocks, labels=False, duplicates="drop")
    df["by"] = pd.qcut(df["lat"], n_blocks, labels=False, duplicates="drop")
    df["block"] = df["bx"].astype(str) + "_" + df["by"].astype(str)
    order = sorted(df["block"].unique())
    folds = [order[i::5] for i in range(5)]
    print("\n空间分块 CV (%d 块, 5 折):" % len(order))
    r2s, maes = [], []
    for k, tb in enumerate(folds):
        te = df[df["block"].isin(tb)]; tr = df[~df["block"].isin(tb)]
        m = RandomForestRegressor(n_estimators=80, max_depth=18,
                                  min_samples_leaf=20, n_jobs=-1, random_state=0)
        m.fit(tr[FEATURES], tr["LST"])
        p = m.predict(te[FEATURES])
        r2s.append(r2_score(te["LST"], p)); maes.append(mean_absolute_error(te["LST"], p))
        print("  fold %d: R2=%.3f MAE=%.2f (n=%d)" % (k, r2s[-1], maes[-1], len(te)))
    print("  平均: R2=%.3f±%.3f MAE=%.2f°C" % (np.mean(r2s), np.std(r2s), np.mean(maes)))


def fit_full(df):
    m = RandomForestRegressor(n_estimators=120, max_depth=20,
                              min_samples_leaf=15, n_jobs=-1, random_state=0)
    m.fit(df[FEATURES], df["LST"])
    imp = pd.Series(m.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\n全样本 R2=%.3f  特征重要性:\n%s" % (m.score(df[FEATURES], df["LST"]),
                                            imp.round(3).to_string()))
    return m


def dose_response(m, df):
    bg = df[df["dw_built"] > 0.4][FEATURES].median()
    grid = np.round(np.arange(0.0, 1.01, 0.1), 2)
    rows = []
    for gf in grid:
        x = bg.copy(); x["greenfrac"] = gf
        rows.append((gf, float(m.predict([x[FEATURES].values])[0])))
    dr = pd.DataFrame(rows, columns=["greenfrac", "pred_LST"])
    dr["dLST"] = (dr["pred_LST"] - dr["pred_LST"].iloc[0]).round(2)
    print("\n=== 剂量-反应:建成区背景, greenfrac 0->1 ===")
    print(dr.round(2).to_string(index=False))
    dr.to_csv(os.path.join(OUT, "dose_response_greenfrac.csv"),
              index=False, encoding="utf-8-sig")
    return dr


def calibrate_cases(m, df):
    bg = df[df["dw_built"] > 0.4][FEATURES].median()

    def pred(gf):
        x = bg.copy(); x["greenfrac"] = gf
        return float(m.predict([x[FEATURES].values])[0])

    # greenfrac 前->后:停车场/建地~0.05;社区公园~0.85;大型公园~0.95
    scen = {
        "case_1 停车场->0.5ha社区公园": (0.05, 0.85, -1.5),
        "case_2 拆1.2ha绿地建地铁口":   (0.80, 0.05, 1.4),
        "case_3 新建85ha郊野公园":      (0.10, 0.95, -3.0),
    }
    print("\n=== 案例 ΔLST 标定(greenfrac 口径) ===")
    res = {}
    for k, (a, b, hard) in scen.items():
        d = round(pred(b) - pred(a), 2)
        res[k] = d
        print("  %-26s gf %.2f->%.2f  ΔLST=%+.2f°C  现值=%+.1f" % (k, a, b, d, hard))
    json.dump(res, open(os.path.join(OUT, "case_dLST_greenfrac.json"), "w"),
              ensure_ascii=False, indent=2)
    return res


if __name__ == "__main__":
    df = load_clean()
    corr_check(df)
    spatial_block_cv(df)
    m = fit_full(df)
    dose_response(m, df)
    calibrate_cases(m, df)
    print("\n输出 ->", OUT)
