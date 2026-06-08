# -*- coding: utf-8 -*-
"""清洗后再看绿地-LST关系:去无效LST、剔水体,再算相关与剂量反应。"""
import numpy as np
import pandas as pd

CSV = r"C:\Users\Administrator\Downloads\SH_HIA_100m_full.csv"
df = pd.read_csv(CSV)
n0 = len(df)

# 1) 清洗:夏季合理地表温度范围,去无效像元
df = df[(df["LST"] >= 20) & (df["LST"] <= 60)].copy()
n1 = len(df)
# 2) 水体单独剔除(worldcover 80=水, 90=湿地);NDVI<0.1 多为水/无效
land = df[(df["worldcover"] != 80) & (df["worldcover"] != 90) & (df["NDVI"] > 0.1)].copy()
n2 = len(land)

print("原始 %d → LST在[20,60] %d (%.1f%%) → 陆地像元 %d (%.1f%%)" %
      (n0, n1, 100 * n1 / n0, n2, 100 * n2 / n0))
print("\n清洗后 LST: 中位 %.2f, 均值 %.2f, std %.2f" %
      (land["LST"].median(), land["LST"].mean(), land["LST"].std()))

cols = ["NDVI", "dw_trees", "dw_built", "bldg_height", "FAR_proxy",
        "bldg_volume", "ntl", "pop", "elevation", "lat", "lon"]
print("\n=== 清洗后与 LST 相关系数 ===")
print(land[cols + ["LST"]].corr()["LST"].drop("LST").sort_values().round(3))

print("\n=== 清洗后 LST vs NDVI 分箱 ===")
land["ndvi_bin"] = pd.qcut(land["NDVI"], 10, duplicates="drop")
print(land.groupby("ndvi_bin")["LST"].agg(["mean", "count"]).round(2))

print("\n=== 清洗后 LST vs dw_trees 分箱 ===")
land["tree_bin"] = pd.qcut(land["dw_trees"], 10, duplicates="drop")
print(land.groupby("tree_bin")["LST"].agg(["mean", "count"]).round(2))

# 多元线性:控制建成/高程/纬度后,绿地净效应
from sklearn.linear_model import LinearRegression
X = land[["NDVI", "dw_built", "bldg_height", "elevation", "lat"]].values
y = land["LST"].values
m = LinearRegression().fit(X, y)
print("\n=== 多元线性回归(控制建成密度等) ===")
for name, c in zip(["NDVI", "dw_built", "bldg_height", "elevation", "lat"], m.coef_):
    print("  %-12s 系数 %+.3f" % (name, c))
print("  R^2 = %.3f" % m.score(X, y))
print("\n  → 控制混杂后, NDVI 系数 %.2f °C/单位 → +0.1 NDVI 约 %+.2f°C" %
      (m.coef_[0], m.coef_[0] * 0.1))
