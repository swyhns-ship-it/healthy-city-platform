# -*- coding: utf-8 -*-
"""健康影响评估:AI 辅助 HIA(定性初筛)。

对标《健康影响评估初筛表》:上传评估对象文档(PDF/Word)→ AI 对 10 个重点问题逐条
给出「是/不知道/否」研判草案 + 影响路径 + 原文依据 + 证据缺口 → 单专家逐条复核改判 →
生成填好的初筛表 docx。AI 仅辅助,判定与签字以专家为准。引擎 hia_screen.py。
"""
from datetime import date

import streamlit as st

import hia_screen as hs
from theme import page_header

ANSWERS = hs.ANSWERS                      # ("是", "不知道", "否")
_BADGE = {"是": "#C62828", "不知道": "#B07A00", "否": "#1B6B3A"}


def _get_key():
    try:
        return st.secrets.get("deepseek_api_key", "") or ""
    except Exception:
        return ""


def _clear_review_state():
    for k in list(st.session_state.keys()):
        if k.startswith("hs_ans_") or k.startswith("hs_note_"):
            del st.session_state[k]


def page_hia_screen():
    page_header(
        "健康影响评估 · AI 辅助 HIA",
        "对标《健康影响评估初筛表》:上传**评估对象文档(PDF / Word)**,AI 针对 10 个重点问题"
        "逐条给出「是 / 不知道 / 否」研判草案、影响路径与**原文依据**,供专家逐条复核改判,"
        "再导出填好的初筛表。**AI 仅辅助研判,不替代专家判定与签字。**")

    # ===== ① 评估对象文档 =====
    st.markdown("##### ① 评估对象文档")
    up = st.file_uploader("上传 PDF 或 Word(.docx)", type=["pdf", "docx"], key="hs_file")

    # ===== ② 初筛表表头 =====
    st.markdown("##### ② 初筛表信息")
    c1, c2 = st.columns(2)
    name = c1.text_input("评估对象名称", value=(up.name.rsplit(".", 1)[0] if up else ""), key="hs_name")
    category = c2.selectbox("发布/实施类别",
                            ["政府发布/实施", "部门发布/实施"], key="hs_cat")
    c3, c4, c5 = st.columns(3)
    dept = c3.text_input("起草/提交部门", key="hs_dept")
    submitter = c4.text_input("提交人", key="hs_submitter")
    phone = c5.text_input("电话", key="hs_phone")
    c6, c7 = st.columns(2)
    screen_date = c6.date_input("初筛日期", value=date.today(), key="hs_date")
    related_dept = c7.text_input("涉及的相关部门", key="hs_related")
    method = st.text_input("初筛方法",
                           value="AI 辅助专家研判(DeepSeek 文档研判 + 专家核定)", key="hs_method")

    # ===== ③ 密钥 + 生成 =====
    key = _get_key()
    if not key:
        key = st.text_input("DeepSeek API Key(未在 Secrets 配置时,可临时输入,仅本次会话)",
                            type="password", key="hs_key").strip()

    gen = st.button("🤖 AI 生成初筛草案", type="primary",
                    disabled=not (up and key), use_container_width=False)
    if not up:
        st.caption("请先上传评估对象文档。")
    elif not key:
        st.caption("需要 DeepSeek API Key(Secrets 配 `deepseek_api_key`,或上方临时输入)。")

    if gen:
        from auth import rate_limit
        ok, wait = rate_limit("hia_screen", 10, 60)
        if not ok:
            st.warning(f"⏳ 生成请求过于频繁,请约 {wait}s 后再试。")
        else:
            data = up.getvalue()
            text, info = hs.extract_text(up.name, data)
            if info.get("error"):
                st.error(info["error"])
            else:
                with st.spinner("AI 阅读文档并逐条研判中(约 10–30 秒)…"):
                    draft = hs.screen(text, key, project_name=name)
                _clear_review_state()
                st.session_state["hs_draft"] = draft
                st.session_state["hs_docinfo"] = info
                tip = f"已解析{info['kind']}" + (f"·{info['pages']}页" if info["pages"] else "")
                if info.get("truncated"):
                    tip += "(文档较长已截断前 4 万字)"
                st.success(tip + ",草案已生成,请在下方逐条复核。")

    draft = st.session_state.get("hs_draft")
    if not draft:
        return

    # ===== ④ 专家逐条复核 =====
    st.divider()
    st.markdown("##### ③ 专家逐条复核(AI 建议仅供参考,请独立研判后改判)")
    st.caption("提示:避免直接照搬 AI 判断——先看影响路径与原文依据,再决定是否改判;无依据的判断 AI 会标「不知道」。")

    items_out = []
    for it in draft["items"]:
        q = it["q"]
        with st.container(border=True):
            st.markdown(f"**{q}. {hs.QUESTIONS[q-1]}**")
            col = _BADGE.get(it["answer"], "#555")
            st.markdown(
                f"<span style='background:{col};color:#fff;padding:1px 8px;border-radius:9px;"
                f"font-size:0.82rem;'>AI 建议:{it['answer']}</span> "
                f"<span style='color:#888;font-size:0.82rem;'>把握 {it['confidence']:.0%}</span>",
                unsafe_allow_html=True)
            if it.get("pathway"):
                st.caption(f"影响路径:{it['pathway']}")
            if it.get("evidence"):
                st.caption(f"📄 原文依据:{it['evidence']}")
            if it.get("gaps"):
                st.caption(f"⚠ 证据缺口:{it['gaps']}")
            cc1, cc2 = st.columns([1, 2])
            ans = cc1.radio("专家判定", ANSWERS, index=ANSWERS.index(it["answer"]),
                            horizontal=True, key=f"hs_ans_{q}")
            note = cc2.text_input("专家备注(可选)", key=f"hs_note_{q}",
                                  placeholder="补充判断理由 / 需核实的点")
        items_out.append({**it, "answer": ans, "note": note})

    # ===== ⑤ 小结 + 结论 =====
    st.divider()
    st.markdown("##### ④ 研判小结与结论")
    if draft.get("summary"):
        st.info("AI 研判小结(参考):" + draft["summary"])

    n_yes = sum(1 for x in items_out if x["answer"] == "是")
    n_unk = sum(1 for x in items_out if x["answer"] == "不知道")
    m1, m2, m3 = st.columns(3)
    m1.metric("判「是」的维度", n_yes)
    m2.metric("判「不知道」", n_unk)
    m3.metric("判「否」", len(items_out) - n_yes - n_unk)
    yes_qs = [x["q"] for x in items_out if x["answer"] == "是"]
    if yes_qs:
        st.caption("建议进入正式评估并重点关注的维度:第 " + "、".join(map(str, yes_qs)) + " 题。")
    else:
        st.caption("各维度均未判「是」;是否进入正式评估由专家组按本地阈值规则与讨论确定。")

    lv_default = draft.get("suggest_level") or "轻度"
    level = st.radio("结论:健康影响程度", ["很小", "轻度", "重大"],
                     index=["很小", "轻度", "重大"].index(lv_default),
                     horizontal=True, key="hs_level",
                     help="AI 建议:" + (draft.get("suggest_level") or "—") + "(仅参考,以专家判定为准)")
    opinion = st.text_area("评估专家组意见", key="hs_opinion",
                           placeholder="对评估过程与结论的描述;如需进一步评估,可概述待评估的主要问题与方法。")

    # ===== ⑥ 导出 =====
    header = {"name": name, "category": category, "dept": dept, "submitter": submitter,
              "phone": phone, "screen_date": str(screen_date), "method": method,
              "related_dept": related_dept}
    docx = hs.build_screen_docx(header, items_out, level, opinion)
    st.download_button("📄 导出初筛表(Word)", data=docx,
                       file_name=f"健康影响评估初筛表_{name or '评估对象'}.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       type="primary")
    st.caption("导出的初筛表含 10 题判定、研判依据(AI 辅助·专家核定)、结论与签字栏。"
               "AI 不替代专家判定;签字与最终结论以专家为准。")
