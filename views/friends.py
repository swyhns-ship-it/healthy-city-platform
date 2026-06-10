# -*- coding: utf-8 -*-
"""友情链接:集成合作学者的研究工具与交互式成果(外部作者开发,经授权嵌入)。

新增一个合作工具:往 FRIENDS 加一项即可。
- type="embed":嵌入仓库内 friends/ 下的自包含 HTML(如 Mapbox/Leaflet 仪表盘)。
- type="url":  外链按钮(打开作者托管的页面)。
"""
import os

import streamlit as st
import streamlit.components.v1 as components

from theme import page_header

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRIENDS = [
    {
        "title": "纽约市 犯罪 × 夜间照明 叠加分析仪表盘",
        "author": "rxy",
        "affil": "",
        "desc": "基于 Mapbox 的交互式仪表盘:在 100m 网格上叠加分析纽约市的犯罪量与夜间灯光,"
                "识别「高犯罪—低照明(HCLL)」网格;可用滑块按百分位筛选照明/犯罪阈值,"
                "并叠加 NTA/警区边界、商业改进区、土地利用、311 投诉、交通事故致死等参考图层。",
        "type": "embed",
        "file": "nyc_crime_light.html",
        "height": 720,
    },
]


def _render_embed(fr):
    path = os.path.join(_ROOT, "friends", fr["file"])
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        components.html(html, height=fr.get("height", 700), scrolling=False)
    except Exception as e:
        st.error(f"嵌入加载失败:{e}")


def page_friends():
    page_header(
        "友情链接 · 合作学者工具",
        "集成合作学者开发的研究工具与交互式成果。以下内容由外部作者开发、经授权在本平台嵌入展示,"
        "**版权与解释权归原作者所有**,仅供学术交流。")

    for i, fr in enumerate(FRIENDS):
        st.markdown(f"#### {fr['title']}")
        meta = "作者:" + fr["author"] + (f" · {fr['affil']}" if fr.get("affil") else "")
        st.caption(meta)
        st.markdown(fr["desc"])
        if fr["type"] == "embed":
            _render_embed(fr)
        elif fr["type"] == "url":
            st.link_button("🔗 打开工具", fr["url"], use_container_width=False)
        if i < len(FRIENDS) - 1:
            st.divider()
