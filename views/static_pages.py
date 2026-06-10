# -*- coding: utf-8 -*-
"""简单静态页:平台首页 / 健康行为(占位)/ 关于平台。"""
import streamlit as st

from theme import page_header, md_bold

# 「健康风险—资源—行为」空间干预梯度模型示意(据王兰 2023 重绘,矢量自绘,非原图)
_LADDER_SVG = """
<svg viewBox="0 0 1000 400" width="100%" xmlns="http://www.w3.org/2000/svg"
     style="max-width:780px; display:block; margin:0.4rem auto 0.2rem;">
  <rect x="0" y="30" width="1000" height="110" fill="#EEF5DE"/>
  <rect x="0" y="140" width="1000" height="110" fill="#E2F0E8"/>
  <rect x="0" y="250" width="1000" height="110" fill="#E4EEF7"/>
  <polygon points="430,30 513,140 347,140" fill="#8CBF4F"/>
  <polygon points="347,140 513,140 597,250 263,250" fill="#4FA07C"/>
  <polygon points="263,250 597,250 680,360 180,360" fill="#3479B0"/>
  <line x1="513" y1="140" x2="980" y2="140" stroke="#B9C8B0" stroke-dasharray="6 5"/>
  <line x1="597" y1="250" x2="980" y2="250" stroke="#A9C0CE" stroke-dasharray="6 5"/>
  <text x="430" y="80" text-anchor="middle" fill="#fff" font-size="19" font-weight="700">健康</text>
  <text x="430" y="106" text-anchor="middle" fill="#fff" font-size="19" font-weight="700">行为</text>
  <text x="430" y="206" text-anchor="middle" fill="#fff" font-size="22" font-weight="700">健康资源</text>
  <text x="430" y="316" text-anchor="middle" fill="#fff" font-size="22" font-weight="700">健康风险</text>
  <text x="700" y="84" fill="#3B6B1F" font-size="23" font-weight="700">路径3:干预促进</text>
  <text x="700" y="114" fill="#555" font-size="17">促进体力活动和交往</text>
  <text x="700" y="194" fill="#1F6B4E" font-size="23" font-weight="700">路径2:支撑保障</text>
  <text x="700" y="224" fill="#555" font-size="17">提供可获得的健康设施</text>
  <text x="700" y="304" fill="#1C4E78" font-size="23" font-weight="700">路径1:基线控制</text>
  <text x="700" y="334" fill="#555" font-size="17">减少外界病源及人体暴露风险</text>
  <polygon points="40,98 110,98 75,46" fill="#2E6FA8"/>
  <rect x="55" y="98" width="40" height="262" fill="#2E6FA8"/>
  <text x="75" y="140" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">空</text>
  <text x="75" y="175" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">间</text>
  <text x="75" y="210" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">健</text>
  <text x="75" y="245" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">康</text>
  <text x="75" y="280" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">性</text>
  <text x="75" y="315" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">能</text>
  <text x="124" y="118" fill="#2E6FA8" font-size="26" font-weight="700">+</text>
  <text x="126" y="352" fill="#2E6FA8" font-size="30" font-weight="700">−</text>
  <line x1="133" y1="132" x2="133" y2="332" stroke="#2E6FA8" stroke-dasharray="3 4"/>
</svg>
"""


def page_home():
    page_header(
        "平台概览",
        "围绕健康城市研究的多个维度,提供基于上海实测数据与机器学习模型的交互式分析工具,"
        "支撑规划方案的健康影响研判与调控。从左侧导航按维度进入各工具。")

    # —— 四维度卡片(随实际功能更新)——
    cards = [
        ("🌡️ 健康风险",
         "**中暑风险地图**(2013–2025 实测病例空间分布)、**热相关重症风险诊断与规划调控**"
         "(建成环境→地表温度→重症化风险,可局部改造模拟)、**清凉路径规划**(沿路实测热暴露/绿荫路由)。"),
        ("🚑 健康资源",
         "**急救反应时间预测**(任意点→最近急救站→驾车路径→反应时间)、**急救站布局模拟**"
         "(重症风险底图上落站 what-if)、**设施配置优化**(纳凉/EMS 设施 MCLP 选址 + 街道公平性)。"),
        ("🚶 健康行为",
         "**骑行潜力与建成环境优化**:机器学习预测共享单车骑行量,圈定范围反向优化建成环境杠杆,"
         "估算骑行(体力活动)提升潜力。"),
        ("🌳 健康影响评估",
         "**绿地规划健康影响评估**(自定义地块绿地干预的热暴露健康影响)、**规划方案 HIA 计算器**"
         "(5D 指标→出行→暴露→疾病发病/死亡变化,内置城市死亡率库)。"),
    ]
    cols = st.columns(2)
    for i, (t, d) in enumerate(cards):
        with cols[i % 2]:
            st.markdown(
                f"<div class='home-card'><div class='home-card-title'>{t}</div>"
                f"<div class='home-card-desc'>{md_bold(d)}</div></div>",
                unsafe_allow_html=True)


def page_behavior():
    page_header("健康行为")
    st.info("本维度正在建设中,敬请期待。")
    st.markdown("**规划纳入**:居民体力活动、绿地使用、出行方式与暴露、高温避险行为等,"
                "及其与建成环境、气候的关系分析。如有相关数据(如手机信令、问卷、可穿戴),可接入本维度建模。")


def page_about():
    page_header("关于平台")
    tab_intro, tab_read = st.tabs(["平台说明", "延伸阅读"])

    with tab_intro:
        st.markdown("##### 免责声明")
        st.markdown(
            "本平台为**研究与规划辅助研判工具**。所载机器学习模型、情景模拟与预测结果基于上海实测数据"
            "及公开文献参数,属**关联性 / 情景分析**,存在不确定性,**不构成正式的环境健康风险评估、"
            "医学诊断或规划决策依据**,亦不替代法定评估程序。使用者据此作出的任何判断与决策,其后果自行承担。")
        st.markdown("##### 版权声明")
        st.markdown(
            "© 同济大学建筑与城市规划学院 · 健康城市实验室。本平台的模型、代码、数据集与界面设计之知识产权"
            "归开发团队及相关权利人所有。未经书面许可,不得用于商业用途或对外再分发;学术引用请注明来源。")

    with tab_read:
        _extended_reading()


def _extended_reading():
    st.markdown("##### 团队相关论文")
    st.caption("本平台依托同济大学建筑与城市规划学院 · 健康城市实验室(王兰团队)的系列研究。")
    papers = [
        "王兰. 健康城市科学与规划循证实践[J]. 城市规划学刊, 2023(06): 27-31.",
        "孙文尧, 王兰, 任祖华, 等. 面向复杂场景的健康城市规划理论、关键技术及应用[J]. 世界建筑, 2025(06): 31-36.",
        "王兰, 孙文尧, 陶佳, 等. 城市规划健康影响评估理论框架构建[J]. 西部人居环境学刊, 2024, 39(2): 177-182.",
        "王兰, 贾颖慧, 孙文尧, 蒋放芳. 面向城市规划方案的定量健康影响评估研究[J]. 规划师, 2021, 37(19): 72-77.",
    ]
    for p in papers:
        st.markdown(f"- {p}")

    st.divider()
    st.markdown("##### 重点导读 · 王兰《健康城市科学与规划循证实践》(2023)")
    st.info("这篇论文是本平台的**理论母体**:平台导航的「健康风险—资源—行为—影响评估」四维度,"
            "正源自文中提出的空间干预梯度模型与循证实践工作流。以下为编辑梳理的要点导读(非原文)。")

    st.markdown("**一、两个核心概念**")
    st.markdown(
        "- **健康城市科学**:以促进人类全生命周期的空间健康为目标,研究城市空间要素对身心健康的"
        "短期与累积影响机制;关键科学问题是「如何测度城乡空间要素对身心健康的短期与累积效应」。\n"
        "- **健康城市规划**:将健康因素系统融入各尺度、各类型的空间规划,即「为健康而规划」。")

    st.markdown("**二、理论模型:「健康风险—资源—行为」空间干预梯度**")
    st.markdown(_LADDER_SVG, unsafe_allow_html=True)
    st.caption("图:「健康风险—资源—行为」空间干预梯度模型(据王兰 2023 重绘)。"
               "三条路径自下而上递进——基线控制(健康风险)→ 支撑保障(健康资源)→ 干预促进(健康行为),"
               "共同提升空间健康性能。")
    st.markdown(
        "由作者此前提出的「四要素三路径」模型进阶而来,被世界卫生组织(WHO)与联合国人居署"
        "联合发布的《健康城市与区域规划指南》采纳为核心理论依据。\n"
        "- **四类可调控空间要素**:土地使用、空间形态、道路交通、绿地与公共开放空间。\n"
        "- **三条递进路径**(从基线控制到干预促进):\n"
        "    - **健康风险(基线控制)**:减少污染源及人体暴露——在功能布局、选址与路网上,"
        "确保人群与污染源/病原(空气污染、噪声、病毒等)的空间距离。\n"
        "    - **健康资源(支撑保障)**:提供可获得、可达的健康设施与服务。\n"
        "    - **健康行为(干预促进)**:以建成环境促进体力活动与社会交往。")

    st.markdown("**三路径 → 本平台对应功能**")
    st.table({
        "理论路径": ["健康风险", "健康资源", "健康行为", "方案评估"],
        "本平台对应维度": [
            "中暑风险地图 / 热相关重症风险诊断 / 清凉路径规划",
            "急救反应时间预测 / 急救站布局模拟 / 设施配置优化",
            "骑行潜力与建成环境优化",
            "绿地规划 HIA / 规划方案 HIA 计算器 / AI 辅助 HIA",
        ],
    })

    st.markdown("**三、循证实践工作流:诊断—编制—评估**")
    st.markdown(
        "- **诊断**:风险诊断(污染源/热岛/疾病高发区的空间叠加,识别高风险地段)、"
        "资源诊断(健康设施服务与不同人群时空需求的匹配、平急结合)、"
        "行为诊断(街道可步行性/骑行性测度)。\n"
        "- **编制**:依干预路径对各类空间要素提出健康促进的编制引导,例如优化 120 急救设施布局以"
        "缩短院前急救反应时间(对标国际 8 分钟)、在社区生活圈设公共健康单元。\n"
        "- **评估**:方案健康效应评估——定性(专家打分/居民访谈)与定量(基于实证模型参数测算"
        "健康中介效益如体力活动当量、健康结果如期望寿命);方案实施后再做实地观测验证。")

    st.markdown("**四、未来框架:认知—干预两个扇面**")
    st.markdown(
        "- **认知扇面**:从以横截面相关分析为主,迈向加入时间维度的「多要素多时空演进模型」,"
        "更深入揭示空间要素、人类行为与健康结果之间的因果路径与关键阈值。\n"
        "- **干预扇面**:空间创造(硬件)+ 空间治理(软件),研发多维健康目标协同、"
        "健康性能可量化的规划调控方法与技术。\n"
        "- 并倡导以城乡规划为核心的跨学科融合创新与全链条育人,构建「健康城市科学与规划」"
        "产学研联动体系。")

    st.markdown("**与本平台的关系**")
    st.markdown(
        "本平台是上述理论的工程化落地:把「诊断—编制—评估」工作流嵌入上海 100m 实测数据与"
        "机器学习模型,沿「健康风险—资源—行为」三路径提供可量化的循证规划研判工具,"
        "并以「健康影响评估」维度支撑方案的定性初筛与定量测算。")
