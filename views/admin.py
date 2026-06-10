# -*- coding: utf-8 -*-
"""模块管理面板(管理员)—— 单一全局开关:勾选开/关功能页,控制对访客的可见性。

进入方式:URL 带 ?admin(客户看不到此页) + 管理员口令(secrets 的 admin_password;
未配置则本地放行)。改动写入 module_config.json:对当前运行实例即时生效;云端长期固定
请用"导出配置"把 json 提交进仓库(见 module_config 说明)。
"""
import hmac

import streamlit as st

import module_config as mc
from theme import page_header


def _admin_ok():
    try:
        pw = (st.secrets.get("admin_password", "") or "").strip()
    except Exception:
        pw = ""
    if not pw:                       # 未配置管理员口令(本地/开发)→ 放行
        return True
    if st.session_state.get("_admin_ok"):
        return True
    st.text_input("管理员口令", type="password", key="_admin_pw")
    if st.button("进入管理"):
        if hmac.compare_digest(str(st.session_state.get("_admin_pw", "")).strip(), pw):
            st.session_state["_admin_ok"] = True
            st.rerun()
        else:
            st.error("管理员口令错误。")
    return False


def page_admin():
    page_header("模块管理 · 板块可见性",
                "勾选 = 对访客开放该板块,取消勾选 = 隐藏。改动对**当前运行实例即时生效**,"
                "访客刷新后看到新可见性。首页不可关闭。")
    if not _admin_ok():
        return

    disabled = mc.load_disabled()
    new_disabled = set(disabled)

    # 按组渲染开关
    from collections import OrderedDict
    groups = OrderedDict()
    for p in mc.PAGES:
        groups.setdefault(p["group"], []).append(p)

    for g, plist in groups.items():
        st.markdown(f"**{g}**")
        for p in plist:
            locked = p.get("locked", False)
            on = st.checkbox(
                f"{p['icon']} {p['title']}" + ("　(始终开启)" if locked else ""),
                value=(p["key"] not in disabled), disabled=locked, key=f"adm_{p['key']}")
            if not locked:
                if on:
                    new_disabled.discard(p["key"])
                else:
                    new_disabled.add(p["key"])

    # 有变化 → 保存 + 重跑(让导航按新配置重建)
    if new_disabled != disabled:
        mc.save_disabled(new_disabled)
        st.rerun()

    n_on = sum(1 for p in mc.PAGES if p["key"] not in new_disabled)
    st.success(f"当前对访客开放 {n_on} / {len(mc.PAGES)} 个板块。")

    with st.expander("⬇ 导出配置(长期固定 / 跨实例持久)"):
        st.caption("云端文件系统是临时的:实例重启/休眠后会恢复为仓库里的 module_config.json。"
                   "要长期固定,把下面内容存为项目根目录的 module_config.json 并提交进仓库。")
        st.code(mc.config_json(new_disabled), language="json")
