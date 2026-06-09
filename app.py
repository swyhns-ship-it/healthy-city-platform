# -*- coding: utf-8 -*-
"""健康城市规划与智能评估平台 — Streamlit 多页入口。

按研究维度分组导航。页面在 views/、共享样式在 theme.py、地图/坐标工具在 geo.py、
计算引擎为根目录各 *.py(green_lst / heat_risk / cooling_mclp / hia_engine / cases / report_docx)。
详见 CLAUDE.md。
"""
import streamlit as st

st.set_page_config(
    page_title="健康城市规划与智能评估平台",
    page_icon="🌳",
    layout="wide",
)

from theme import inject_css, render_banner
from views.static_pages import page_home, page_behavior, page_about
from views.health_risk import page_health_risk
from views.heatcase_map import page_heatcase_map
from views.heatroute import page_heatroute
from views.health_resource import page_health_resource
from views.cooling import page_cooling_layout
from views.hia import page_hia_cases, render_custom_mode
from views.methodology import render_methodology

inject_css()
render_banner()

nav = st.navigation({
    "平台首页": [st.Page(page_home, title="首页", icon="🏠", default=True)],
    "健康风险": [st.Page(page_health_risk, title="热相关重症风险", icon="🌡️"),
             st.Page(page_heatcase_map, title="中暑病例风险地图", icon="🗺️"),
             st.Page(page_heatroute, title="凉爽路径规划", icon="🧭")],
    "健康资源": [st.Page(page_health_resource, title="急救站布局模拟", icon="🚑"),
             st.Page(page_cooling_layout, title="纳凉设施布局优化", icon="❄️")],
    "健康行为": [st.Page(page_behavior, title="建设中", icon="🚶")],
    "健康影响评估": [st.Page(page_hia_cases, title="绿地干预 · 示范案例", icon="🌳"),
                 st.Page(render_custom_mode, title="自定义地块评估", icon="✏️")],
    "方法与关于": [st.Page(render_methodology, title="建模方法说明", icon="📖"),
               st.Page(page_about, title="关于平台", icon="ℹ️")],
})
nav.run()
