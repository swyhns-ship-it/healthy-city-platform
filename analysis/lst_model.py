# -*- coding: utf-8 -*-
"""
上海 100m: 绿地 -> 地表温度(LST) 模型 + 剂量-反应函数。

目标:从实测数据拟合"绿地指标变化 -> ΔLST",支撑 HIA demo。
- 清洗无效像元(LST 范围、剔水体)
- 随机森林拟合 LST ~ 绿地 + 建成 + 地形
- 空间分块交叉验证(把上海切成网格块,整块留出),给出诚实的泛化 R²
- 导出剂量-反应:固定建成背景,扫 NDVI -> 预测 LST 曲线
- 给出 predict_delta_lst():某地块 NDVI 从 a 升到 b 的预测降温
"""
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error

CSV = r"C:\Users\Administrator\Downloads\SH_HIA_100m_full.csv"
OUT = r"E:\projects\hia_demo\analysis\out"
import os
os.makedirs(OUT, exist_ok=True)

FEATURES = ["NDVI", "dw_trees", "dw_built", "bldg_height", "FAR_proxy",
            "ntl", "elevation", "slope", "lat", "lon"]
GREEN = ["NDVI", "dw_trees"]


def load_clean():
    df = pd.read_csv(CSV)
    n0 = len(df)
    df = df[(df["LST"] >= 20) & (df["LST"] <= 60)]
    df = df[(df["worldcover"] != 80) & (df["worldcover"] != 90) & (df["NDVI"] > 0.1)]
    df = df.dropna(subset=FEATURES + ["LST"]).reset_index(drop=True)
    print("清洗: %d -> %d 陆地像元 (%.1f%%)" % (n0, len(df), 100 * len(df) / n0))
    return df


def spatial_block_cv(df, n_blocks=6):
    """把研究区按经纬度切成 n_blocks×n_blocks 个块,做留块交叉验证。"""
    df = df.copy()
    df["bx"] = pd.qcut(df["lon"], n_blocks, labels=False, duplicates="drop")
    df["by"] = pd.qcut(df["lat"], n_blocks, labels=False, duplicates="drop")
    df["block"] = df["bx"].astype(str) + "_" + df["by"].astype(str)
    blocks = df["block"].unique()
    print("\n空间分块 CV: %d 个块" % len(blocks))

    r2s, maes = [], []
    # 随机但确定的分组(5 折块)
    order = sorted(blocks)
    folds = [order[i::5] for i in range(5)]
    for k, test_blocks in enumerate(folds):
        te = df[df["block"].isin(test_blocks)]
        tr = df[~df["block"].isin(test_blocks)]
        m = RandomForestRegressor(n_estimators=80, max_depth=18,
                                  min_samples_leaf=20, n_jobs=-1, random_state=0)
        m.fit(tr[FEATURES], tr["LST"])
        p = m.predict(te[FEATURES])
        r2 = r2_score(te["LST"], p); mae = mean_absolute_error(te["LST"], p)
        r2s.append(r2); maes.append(mae)
        print("  fold %d: 测试块=%2d  R2=%.3f  MAE=%.2f°C  (n_test=%d)" %
              (k, len(test_blocks), r2, mae, len(te)))
    print("  空间CV 平均: R2=%.3f±%.3f  MAE=%.2f°C" %
          (np.mean(r2s), np.std(r2s), np.mean(maes)))
    return np.mean(r2s), np.mean(maes)


def fit_full(df):
    m = RandomForestRegressor(n_estimators=120, max_depth=20,
                              min_samples_leaf=15, n_jobs=-1, random_state=0)
    m.fit(df[FEATURES], df["LST"])
    imp = pd.Series(m.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\n全样本模型 训练 R2=%.3f" % m.score(df[FEATURES], df["LST"]))
    print("特征重要性:\n" + imp.round(3).to_string())
    return m, imp


def dose_response(m, df):
    """固定建成背景为典型建成区中位数,扫 NDVI 看预测 LST。"""
    base = df[df["dw_built"] > 0.4]  # 典型建成片区
    bg = base[FEATURES].median()
    ndvi_grid = np.round(np.arange(0.15, 0.85, 0.05), 2)
    rows = []
    for nd in ndvi_grid:
        x = bg.copy(); x["NDVI"] = nd
        # dw_trees 随 NDVI 协同上升(经验线性近似)
        x["dw_trees"] = float(np.clip(0.02 + 0.5 * (nd - 0.15), 0.02, 0.5))
        rows.append((nd, float(m.predict([x[FEATURES].values])[0])))
    dr = pd.DataFrame(rows, columns=["NDVI", "pred_LST"])
    dr["dLST_vs_min"] = (dr["pred_LST"] - dr["pred_LST"].iloc[0]).round(2)
    print("\n=== 剂量-反应曲线(建成区背景, NDVI 扫描) ===")
    print(dr.round(2).to_string(index=False))
    dr.to_csv(os.path.join(OUT, "dose_response.csv"), index=False, encoding="utf-8-sig")
    return dr


def calibrate_cases(m, df):
    """给 3 个 demo 案例算数据驱动的 ΔLST。
    干预 = 地块 NDVI 从'前'升/降到'后',其它背景取该街道附近中位。"""
    base = df[df["dw_built"] > 0.4]
    bg = base[FEATURES].median()

    def predict_lst(ndvi, trees=None):
        x = bg.copy(); x["NDVI"] = ndvi
        x["dw_trees"] = trees if trees is not None else float(np.clip(0.02 + 0.5 * (ndvi - 0.15), 0.02, 0.5))
        return float(m.predict([x[FEATURES].values])[0])

    # 案例典型 NDVI 前后(停车场/建地~0.2;社区公园~0.6;大型郊野公园~0.7)
    scen = {
        "case_1_停车场转0.5ha社区公园": (0.20, 0.60),
        "case_2_1.2ha绿地拆除建地铁口": (0.62, 0.22),
        "case_3_85ha大型郊野公园新建": (0.25, 0.72),
    }
    print("\n=== 案例 ΔLST 标定(数据驱动 vs 现硬编码) ===")
    hard = {"case_1_停车场转0.5ha社区公园": -1.5,
            "case_2_1.2ha绿地拆除建地铁口": 1.4,
            "case_3_85ha大型郊野公园新建": -3.0}
    res = {}
    for k, (a, b) in scen.items():
        d = predict_lst(b) - predict_lst(a)
        res[k] = round(d, 2)
        print("  %-32s NDVI %.2f->%.2f  全转ΔLST=%+.2f°C  现值=%+.1f" %
              (k, a, b, d, hard[k]))
    print("\n  注:上为'整像元完全转换'的上界;实际地块小、周边稀释,"
          "demo 用值应取其一定折减(见说明)。")
    json.dump(res, open(os.path.join(OUT, "case_dLST.json"), "w"), ensure_ascii=False, indent=2)
    return res


if __name__ == "__main__":
    df = load_clean()
    spatial_block_cv(df)
    m, imp = fit_full(df)
    dose_response(m, df)
    calibrate_cases(m, df)
    print("\n输出已存到", OUT)
