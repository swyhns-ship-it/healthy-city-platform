# -*- coding: utf-8 -*-
"""健康影响评估:规划方案 HIA 计算器(实现专利方法)。

输入现状/规划 5D 指标 + 现状暴露(PM2.5、通勤步行),按专利"建成环境→出行→暴露→健康结果"
路径计算各疾病发病/死亡变化。引擎 hia_calc.py。
"""
import pandas as pd
import streamlit as st

import hia_calc as hc
from theme import page_header

# 降低小汽车出行的规划指标优先级(专利4.8)
_OPT_ORDER = ["路网密度", "四向交叉口百分比", "用地混合度(SHDI)",
              "工作地公交可达性", "到最近公交站距离", "人口密度"]


def page_hia_calc():
    page_header(
        "健康影响评估 · 规划方案 HIA 计算器",
        "实现专利《面向规划方案的健康结果模拟预测方法》:输入**现状与规划方案的 5D 指标**及现状暴露,"
        "按「建成环境 → 出行方式 → 风险暴露(交通PM2.5/体力活动)→ 健康结果」路径,"
        "定量预测规划方案相对现状的疾病发病/死亡变化。默认值为专利顾村案例,可改为自己的方案。")

    st.markdown("##### ① 5D 建成环境指标(现状 / 规划)")
    cur_planned = {}
    hcap = st.columns([2, 1, 1, 2])
    hcap[0].caption("指标"); hcap[1].caption("现状"); hcap[2].caption("规划"); hcap[3].caption("弹性(小汽车/步行)")
    for ind in hc.IND_ORDER:
        e = hc.ELASTICITY[ind]; d_cur, d_plan = hc.CASE_5D[ind]
        c = st.columns([2, 1, 1, 2])
        label = f"{e['zh']}" + (f"({e['unit']})" if e['unit'] else "")
        c[0].markdown(f"<div style='padding-top:6px;font-size:14px'>{label}</div>", unsafe_allow_html=True)
        cur = c[1].number_input("现状", value=float(d_cur), key=f"hc_c_{ind}",
                                label_visibility="collapsed", format="%.4g")
        plan = c[2].number_input("规划", value=float(d_plan), key=f"hc_p_{ind}",
                                 label_visibility="collapsed", format="%.4g")
        car = "—" if e["car"] is None else f"{e['car']:+.2f}"
        walk = "—" if e["walk"] is None else f"{e['walk']:+.2f}"
        c[3].markdown(f"<div style='padding-top:6px;font-size:12px;color:#888'>{car} / {walk}</div>",
                      unsafe_allow_html=True)
        cur_planned[ind] = (cur, plan)

    st.markdown("##### ② 城市与现状暴露")
    cities = hc.load_cities()
    provs = sorted(cities["省份"].unique())
    cc1, cc2, cc3 = st.columns([1.3, 1.3, 1])
    pidx = provs.index("上海市") if "上海市" in provs else 0
    prov = cc1.selectbox("省份", provs, index=pidx, key="hc_prov")
    sub = cities[cities["省份"] == prov]
    city = cc2.selectbox("城市", sorted(sub["城市"].tolist()), key="hc_city")
    row = sub[sub["城市"] == city].iloc[0]
    death_cur = float(row["死亡率"])
    pm25 = cc3.number_input("现状 PM2.5(μg/m³)", value=hc.NATIONAL_PM25, min_value=0.0,
                            help="默认全国均值 30(2023《中国生态环境状况公报》);有城市实测值可改")
    st.caption(f"**{city}** 现状全因死亡率(人口死亡率)= **{death_cur:.2f}‰**"
               f"(来源:{row['来源']},{int(row['年份'])}年)。"
               f"固定假设:小汽车贡献 PM2.5 **{hc.CASE_CAR_FRAC:.0f}%**、"
               f"通勤步行 **{hc.CASE_WALK_MIN:.1f}** 分钟/人/日(×7×{hc.WALK_MET:.0f} MET)。")

    res = hc.full_assess(cur_planned, pm25, hc.CASE_CAR_FRAC, hc.CASE_WALK_MIN,
                         outcomes=["全因死亡"], current_rates={"全因死亡": death_cur})
    tc, ed = res["travel"], res["exposure"]
    h0 = res["health"][0]
    rate_new = h0.get("rate_new", death_cur * h0["rr_c"])
    d_rate = rate_new - death_cur

    st.divider()
    st.markdown("#### 评估结果")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("步行出行量变化", f"{tc['walk_pct']:+.1f}%")
    m2.metric("小汽车出行量变化", f"{tc['car_pct']:+.1f}%")
    m3.metric("交通 PM2.5 变化", f"{ed['pm_diff']:+.2f} μg/m³")
    m4.metric("体力活动变化", f"{ed['pa_diff']:+.0f} MET·min/周")

    cL, cR = st.columns([1, 1], gap="large")
    with cL:
        st.markdown("**各 5D 指标对出行的贡献(%)**")
        rows = [{"指标": r["zh"], "变化%": round(r["pct"], 1),
                 "→小汽车%": None if r["car"] is None else round(r["car"], 2),
                 "→步行%": None if r["walk"] is None else round(r["walk"], 2)}
                for r in tc["rows"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=360)
    with cR:
        st.markdown("**全因死亡评估**")
        col = "#1B7F4B" if d_rate <= 0 else "#D7191C"
        st.markdown(
            f"<div style='background:{col}1A;border:1px solid {col};border-radius:10px;"
            f"padding:14px 16px'>"
            f"<div style='font-size:13px;color:#555'>{city} · 全因死亡率(人口死亡率)</div>"
            f"<div style='font-size:15px;margin:4px 0'>现状 <b>{death_cur:.2f}‰</b> "
            f"→ 规划方案 <b style='color:{col}'>{rate_new:.2f}‰</b></div>"
            f"<div style='font-size:26px;font-weight:800;color:{col}'>{d_rate:+.3f}‰ "
            f"({h0['change_pct']:+.2f}%)</div></div>", unsafe_allow_html=True)
        st.markdown(
            f"- 空气污染路径(交通 PM2.5)→ 死亡风险 **{(h0['rr_pm']-1)*100:+.2f}%**\n"
            f"- 体力活动路径(通勤步行)→ 死亡风险 **{(h0['rr_pa']-1)*100:+.2f}%**\n"
            f"- 综合相对风险 RR = **{h0['rr_c']:.4f}**,人群归因分数 PAF = **{h0['paf']*100:+.2f}%**")
        st.caption("负值=相对现状下降(健康改善)。综合=两条路径相对风险相乘;"
                   "预测死亡率 = 现状死亡率 × 综合RR。")

    # —— 优化建议 ——
    st.markdown("##### 规划优化建议")
    worse = [h for h in res["health"] if h["change_pct"] > 0]
    if tc["car_pct"] > 0 or any(h["has_pm"] and h["change_pct"] > 0 for h in res["health"]):
        st.warning("方案未降低小汽车出行/空气污染相关风险。建议优先调整以下指标以减少小汽车出行"
                   "(按健康效应系数大小排序):" + " → ".join(_OPT_ORDER) + "。")
    else:
        st.success(f"方案促进步行 {tc['walk_pct']:+.1f}%、降低小汽车 {tc['car_pct']:+.1f}%,"
                   "整体降低相关疾病发病/死亡风险。若需进一步提升,可继续提高用地混合度、路网密度、"
                   "四向交叉口百分比,并将产业用地向公交站点周边集中。")
    if worse:
        st.caption("注:" + "、".join(h["outcome"] for h in worse) + " 出现上升,需重点关注。")

    with st.expander("方法与参数(专利方法 + 暴露-响应函数)", expanded=False):
        st.markdown(
            "- **路径**:5D 指标变化% × 弹性量(专利表1)→ 小汽车/步行出行变化% → 暴露差值"
            "(交通PM2.5、体力活动MET)→ 暴露-响应函数 ERF(专利表2)→ 相对风险 RR → 人群归因分数 PAF → 健康结果变化。\n"
            "- **出行**:交通PM2.5 = 总PM2.5 × 小汽车贡献%;PM变化 = 小汽车出行变化% × 交通PM2.5;"
            "体力活动当量 = 步行min/日×7×4MET;PA变化 = 步行变化% × 现状当量。\n"
            "- **RR_diff = exp(ln(RR)/单位暴露 × 暴露差值)**;PAF=(RR−1)/RR;健康结果 = 现状 × 综合RR。\n"
            "- ERF 取自适用我国情景的荟萃分析(PM2.5 每 10μg/m³、体力活动每 600MET·min/周)。\n"
            "- 默认值为专利顾村案例(可复现心血管疾病约 −5.25%)。属规划阶段**辅助研判**,参数与适用性以专利为准。")
