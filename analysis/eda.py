# -*- coding: utf-8 -*-
"""快速 EDA:摸清 LST 与绿地各指标的关系。仅用 pandas/numpy/sklearn。"""
import numpy as np
import pandas as pd

CSV = r"C:\Users\Administrator\Downloads\SH_HIA_100m_full.csv"

df = pd.read_csv(CSV)
print("形状:", df.shape)
print("\n列:", list(df.columns))

# 关心的变量
num_cols = ["LST", "NDVI", "dw_trees", "dw_built", "bldg_height",
            "FAR_proxy", "bldg_volume", "ntl", "pop", "elevation", "slope",
            "lat", "lon", "worldcover"]
num_cols = [c for c in num_cols if c in df.columns]

print("\n=== 缺失率 ===")
print((df[num_cols].isna().mean() * 100).round(2))

print("\n=== 描述统计 ===")
print(df[num_cols].describe().T[["mean", "std", "min", "25%", "50%", "75%", "max"]].round(3))

# LST 有效性
lst = df["LST"]
print("\nLST 范围: %.2f ~ %.2f, 中位 %.2f" % (lst.min(), lst.max(), lst.median()))

print("\n=== 与 LST 的相关系数(Pearson) ===")
corr = df[num_cols].corr()["LST"].drop("LST").sort_values()
print(corr.round(3))

# 绿地剂量-反应:NDVI 分箱看 LST 均值
print("\n=== LST vs NDVI 分箱(10 分位) ===")
dd = df.dropna(subset=["LST", "NDVI"]).copy()
dd["ndvi_bin"] = pd.qcut(dd["NDVI"], 10, duplicates="drop")
print(dd.groupby("ndvi_bin")["LST"].agg(["mean", "count"]).round(3))

# worldcover 分类的 LST
print("\n=== 各 worldcover 类别的 LST 均值 ===")
wc_map = {10: "树", 20: "灌", 30: "草", 40: "农", 50: "建成", 60: "裸", 80: "水", 90: "湿"}
g = df.groupby("worldcover")["LST"].agg(["mean", "count"]).round(2)
g.index = [f"{int(i)}-{wc_map.get(int(i), '?')}" for i in g.index]
print(g)

# 简单线性:LST ~ NDVI(单变量斜率,即每 +0.1 NDVI 降温多少)
from sklearn.linear_model import LinearRegression
m = LinearRegression().fit(dd[["NDVI"]], dd["LST"])
print("\n单变量 LST~NDVI 斜率: %.3f °C / 单位NDVI (即 +0.1 NDVI → %.3f°C)" %
      (m.coef_[0], m.coef_[0] * 0.1))
