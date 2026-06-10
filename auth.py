# -*- coding: utf-8 -*-
"""轻量访问口令门 —— 只给导师/合作方访问,顺带挡爬虫、护住付费 API 成本。

机制:口令存 st.secrets["app_password"](不进 git;云端在 Settings→Secrets 配)。
- 已通过 → 直接放行。
- 未配置口令(本地无 secrets 或没设该键)→ 不拦截,方便本机开发免输口令。
- 配置了口令但未通过 → 渲染登录框 + st.stop()。

校验用 hmac.compare_digest 做定长比较,避免计时侧信道。
被 app.py 在 render_banner() 之后、构建导航之前调用。
"""
import hmac
import time

import streamlit as st

from theme import HEALTH_GREEN, GREEN_DEEP


def rate_limit(bucket, max_calls, window_s):
    """会话级滑动窗口限流。超限 → 返回 (False, 剩余等待秒);否则记一次 → (True, 0)。

    防口令外泄后被刷爆付费 API(DeepSeek/百度)的账单。注意:基于 st.session_state,
    **仅在单会话内有效**;跨会话/分布式刷量要靠后台账单上限兜底(已在控制台配额告警)。
    """
    now = time.monotonic()
    key = f"_rl_{bucket}"
    hist = [t for t in st.session_state.get(key, []) if now - t < window_s]
    if len(hist) >= max_calls:
        st.session_state[key] = hist
        return False, int(window_s - (now - hist[0])) + 1
    hist.append(now)
    st.session_state[key] = hist
    return True, 0


def _configured_password():
    """安全读取 st.secrets["app_password"];本地无 secrets 文件时返回 None(不拦截)。"""
    try:
        pwd = st.secrets.get("app_password", None)
    except Exception:
        return None
    pwd = (pwd or "").strip()
    return pwd or None


def require_login():
    """返回 True 放行;否则渲染登录框并 st.stop()。"""
    target = _configured_password()
    if target is None:          # 未配置口令 → 开发/本地模式,不拦
        return True
    if st.session_state.get("_auth_ok"):
        return True

    def _check():
        ok = hmac.compare_digest(
            str(st.session_state.get("_pwd_input", "")).strip(), target
        )
        st.session_state["_auth_ok"] = ok
        st.session_state["_auth_tried"] = True
        if ok:
            st.session_state.pop("_pwd_input", None)   # 不在内存里留明文

    # —— 登录界面 ——
    st.markdown(
        f"""
        <div style="max-width:560px;margin:2.2rem auto 0.6rem;padding:1.4rem 1.6rem;
                    background:#F6FCF8;border:1px solid #DCEEE3;border-left:5px solid {HEALTH_GREEN};
                    border-radius:10px;">
          <div style="font-size:1.15rem;font-weight:700;color:{GREEN_DEEP};">🔒 访问受限</div>
          <div style="color:#3a3a3a;margin-top:.4rem;line-height:1.6;">
            本平台含科研数据,仅向导师与合作方开放。请输入访问口令。<br>
            <span style="color:#888;font-size:.9rem;">如需口令,请联系平台维护者(孙文尧)。</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c = st.columns([1, 2, 1])[1]
    with c:
        st.text_input("访问口令", type="password", key="_pwd_input",
                      on_change=_check, placeholder="输入后回车")
        if st.session_state.get("_auth_tried") and not st.session_state.get("_auth_ok"):
            st.error("口令错误,请重试。")
    st.stop()
