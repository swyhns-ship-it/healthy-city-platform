# -*- coding: utf-8 -*-
"""建模方法说明页(LST 模型数据 / 验证 / 剂量-反应 / 预测流程)。"""
import numpy as np
import pandas as pd
import streamlit as st

import green_lst
from theme import page_header


FEAT_ZH = {
    "bldg_height": "建筑高度 (GHSL)", "ntl": "夜间灯光 (VIIRS·人为热代理)",
    "dw_built": "建成概率 (Dynamic World)", "FAR_proxy": "容积率代理",
    "elevation": "高程", "slope": "坡度",
    "greenfrac": "本格绿地占比", "g300": "300m 邻域绿地占比",
    "g900": "900m 邻域绿地占比", "dist_green_m": "到最近绿地距离",
}


@st.cache_data(show_spinner=False)
def _feature_importance():
    rf = green_lst._state()["rf"]
    feats = green_lst.OWN + green_lst.GREEN_FEATS
    s = pd.Series(rf.feature_importances_, index=[FEAT_ZH[f] for f in feats])
    return s.sort_values(ascending=False)


@st.cache_data(show_spinner=False)
def _dose_response():
    """代表性建成背景下,周边绿地占比 0→1 的预测地表温度(剂量–反应曲线)。"""
    S = green_lst._state()
    own = S["own"]; gf = S["gf"]; wc = S["wc"]
    built = np.isfinite(own[0]) & (own[0] > 0.4) & (wc != 80) & (wc != 90)
    bg = [float(np.nanmedian(own[i][built])) for i in range(len(green_lst.OWN))]
    levels = np.round(np.arange(0, 1.001, 0.1), 2)
    rows = []
    for g in levels:
        dist = 0.0 if g >= green_lst.GREEN_THRESH else 300.0
        rows.append(bg + [g, g, g, dist])   # greenfrac, g300, g900, dist_green_m
    pred = S["rf"].predict(np.array(rows, dtype=float))
    d = pred - pred[0]
    return pd.DataFrame({"绿地占比": levels, "预测地表温度变化 ΔLST (°C)": np.round(d, 2)}
                        ).set_index("绿地占比")


def render_methodology():
    """LST 变化建模方法的专门说明页。"""
    S = green_lst._state()
    page_header(
        "地表温度变化建模方法 · 技术说明",
        "本页说明 demo 中「绿地干预 → 地表温度(LST)变化」的数据、模型、验证与预测流程,供方法学审阅。")

    st.markdown("### 1　总体思路")
    st.markdown(
        "在地图上绘制一块新增/拆除绿地的多边形后,系统用一个基于上海全市 100m 实测数据训练的"
        "**机器学习地表温度模型**,预测该地块**及其周边**逐格的夏季地表温度变化 ΔLST(含空间外溢),"
        "再据此做逐格健康影响评估(HIA)。核心特征里包含**邻域绿地占比与到最近绿地的距离**,"
        "因此「绿地对周边的降温外溢」是由模型内生预测的,而非人为叠加的衰减假设。")

    st.markdown("### 2　数据源")
    st.markdown(
        "- **训练数据**:上海全市 100m 网格(EPSG:32651 / UTM 51N),约 **60.7 万**个有效网格,"
        "GEE 多年夏季(6–9 月)中位合成,有效 LST 覆盖率 ~100%(每格含 `LST_count` 有效影像数,中位 16)。\n"
        "- **地表温度 LST**:Landsat 8/9 热红外反演,多年合成以抑制云污染与单期噪声。\n"
        "- **绿地**:ESA WorldCover / Dynamic World 衍生的 100m 绿地占比(greenfrac)与二值绿地。\n"
        "- **协变量**:建筑高度/体积(GHSL)、建成概率(Dynamic World)、容积率代理、"
        "夜间灯光(VIIRS,人为热代理)、高程与坡度(Copernicus DEM)、人口(WorldPop 2020)。")

    st.markdown("### 3　自变量(特征)")
    st.markdown("分两类:**绿地相关特征**(干预会改变)与**建成/地形背景特征**(干预时保持不变)。")
    feat_rows = [
        {"类别": "绿地(可干预)", "特征": "本格绿地占比 greenfrac", "说明": "100m 网格内绿地面积比例,干预直接改变"},
        {"类别": "绿地(可干预)", "特征": "300m / 900m 邻域绿地占比", "说明": "周边窗口内绿地均值——绿地降温外溢的关键通道"},
        {"类别": "绿地(可干预)", "特征": "到最近绿地距离", "说明": "离最近成片绿地的距离,刻画可达性"},
        {"类别": "建成/地形(背景)", "特征": "建筑高度、建成概率、容积率代理", "说明": "城市形态——热岛主要驱动"},
        {"类别": "建成/地形(背景)", "特征": "夜间灯光", "说明": "人为热排放代理"},
        {"类别": "建成/地形(背景)", "特征": "高程、坡度", "说明": "地形背景"},
    ]
    st.table(feat_rows)
    st.caption("注:经纬度未直接入模,以免地理坐标吸收绿地效应;空间趋势由邻域绿地与建成形态承载。")

    st.markdown("### 4　模型与精度验证")
    c1, c2, c3 = st.columns(3)
    c1.metric("模型", "随机森林")
    c2.metric("空间分块 CV · R²", f"{S['cv_r2']:.2f}")
    c3.metric("空间分块 CV · MAE", f"{S['cv_mae']:.1f} °C")
    st.markdown(
        "- 采用**随机森林回归**(300 棵树)。\n"
        "- 因地表温度存在强**空间自相关**,普通随机交叉验证会高估精度;故用 **6×6 空间分块"
        "交叉验证**(整块留出、5 折),给出诚实的泛化精度:**R²≈{:.2f}、MAE≈{:.1f}°C**。\n"
        "- 下图为特征重要性:城市形态(建筑高度、夜间灯光、建成概率)主导地表温度水平,"
        "绿地类特征是**次级调节项**——这与城市热岛物理一致;绿地的价值体现在"
        "「相对降温幅度」与「空间外溢」上。".format(S["cv_r2"], S["cv_mae"]))
    st.bar_chart(_feature_importance(), height=300)

    st.markdown("### 5　绿地降温的剂量–反应关系")
    st.markdown("固定典型建成区背景,把(本格及邻域)绿地占比从 0 提到 1,模型预测的地表温度变化:")
    st.line_chart(_dose_response(), height=300)
    st.caption("曲线为说明性剂量–反应:绿地占比越高、降温越强,且呈现边际递减。"
               "实际每个地块的降温幅度还取决于其建筑高度、人为热等背景。")

    st.markdown("### 6　绘制多边形后的预测流程")
    st.markdown(
        "1. **设定干预**:多边形内网格的绿地占比设为目标值(新增→0.9,拆除→0.05)。\n"
        "2. **重算绿地特征**:在影响范围内重新计算邻域绿地占比(300m/900m)与到最近绿地距离"
        "——这使周边网格的特征也随之改变,从而预测出**外溢降温**。\n"
        "3. **逐格预测**:用模型预测干预后地表温度,ΔLST = 干预后预测 − 现状基线预测。\n"
        "4. **单调约束**:新增绿地只计降温、拆除只计升温,抑制模型在个别格上的反向噪声。\n"
        "5. **空间平滑**:对 ΔLST 场做掩膜感知高斯平滑(等效热扩散),消除随机森林阶梯差值的斑驳,"
        "得到连续降温场。\n"
        "6. **影响半径自适应**:影响范围随地块大小缩放(等效半径 √(N/π)+余量,约 200–900m),"
        "小地块小范围、大公园大范围,符合公园冷岛(PCI)尺度规律。")

    st.markdown("### 7　从地表温度到健康影响")
    st.markdown(
        "- **ΔLST → 近地气温 ΔT_air**:按经验系数 0.7 折减(地表温度变化大于气温变化)。\n"
        "- **逐格 HIA**:对每个 100m 网格,用其**自身的 ΔT_air × 该格 100m 人口 × 城市基线死亡率 × "
        "热归因比例 ×(1 − RR^ΔT)** 计算可避免/额外病例,再全场求和——而非"
        "「单一温度 × 总人口」的粗略口径。ERF 采用 Liu 2022(主分析)与 Lingyan 2017(敏感性)。")

    st.markdown("### 8　局限与说明")
    st.markdown(
        "- 模型为**观测数据的统计关系**(相关性),非因果实验;迁移到具体新建项目存在不确定性。\n"
        "- 绿地类特征重要性偏低,绝对降温幅度对绿地的敏感度有限;大尺度公园的区域性降温可能被低估。\n"
        "- 「平滑栅格」为展示层的空间插值,使热力图连续;底层 HIA 计算仍用真实 100m 逐格 ΔLST。\n"
        "- 数据为 100m 分辨率,**最小可分辨干预为 1 格(1 公顷)**;更小地块按 1 格处理。\n"
        "- 卫星底图(高德)为 GCJ-02 坐标系,叠加层已做坐标变换对齐;ΔLST→气温、热归因比例等为经验设定。\n"
        "- 本系统用于规划阶段的健康影响**辅助研判**,不替代正式环境健康风险评估。")
    st.caption(f"模型:随机森林 · 空间分块CV R²={S['cv_r2']:.2f} / MAE={S['cv_mae']:.1f}°C · "
               "训练数据:上海 100m 多年夏季合成(约 60.7 万网格)")
