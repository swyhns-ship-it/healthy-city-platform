# -*- coding: utf-8 -*-
"""健康影响评估:AI 辅助 HIA(定性初筛 · 因果路径版)。

上传评估对象文档(PDF/Word)→ 3 段流水线(行动抽取→多视角路径展开→完整性批判)展开
**政策行动→健康决定因素(多级间接)→健康结果** 的因果路径网 → 可编辑因果路径图 +
路径采纳/剪枝/补充 → 代码确定性聚合到 10 题 → 专家复核改判 → 导出初筛表 docx。
AI 仅辅助;路径采纳、判定与签字以专家为准。引擎 hia_screen.py。
"""
from datetime import date

import streamlit as st

import hia_screen as hs
import hia_evidence
from theme import page_header

ANSWERS = hs.ANSWERS
LEVELS = ["很小", "轻度", "重大"]
_BADGE = {"是": "#C62828", "不知道": "#B07A00", "否": "#1B6B3A"}
_STRENGTH_C = {"强": "#C62828", "中": "#E07B39", "推测": "#9AA0A6"}


def _get_key():
    try:
        return st.secrets.get("deepseek_api_key", "") or ""
    except Exception:
        return ""


def _clear_state():
    for k in list(st.session_state.keys()):
        if k.startswith(("hs_adopt_", "hs_ans_", "hs_note_")):
            del st.session_state[k]
    st.session_state.pop("hs_custom", None)


def _all_pathways():
    """模型路径 + 专家补充路径。"""
    res = st.session_state.get("hs_res") or {}
    return list(res.get("pathways", [])) + list(st.session_state.get("hs_custom", []))


def _adopt_default(p):
    return p.get("status") != "假设待证"          # 假设待证默认不采纳,需专家勾选


def _adopted():
    return [p for p in _all_pathways()
            if st.session_state.get(f"hs_adopt_{p['id']}", _adopt_default(p))]


def page_hia_screen():
    page_header(
        "健康影响评估 · AI 辅助 HIA",
        "上传<b>评估对象文档(PDF / Word)</b>,AI 分三步展开「政策行动 → 健康决定因素(多级、间接)"
        "→ 健康结果」<b>因果路径网</b>,生成可编辑的路径图与依据;再由系统按确定性规则聚合到初筛表 10 题,"
        "供专家逐条复核。<b>AI 仅辅助研判,路径采纳、判定与签字以专家为准。</b>")

    # ===== ① 文档 + 表头 =====
    st.markdown("##### ① 评估对象文档")
    up = st.file_uploader("上传 PDF 或 Word(.docx)", type=["pdf", "docx"], key="hs_file")

    st.markdown("##### ② 初筛表信息")
    c1, c2 = st.columns(2)
    name = c1.text_input("评估对象名称", value=(up.name.rsplit(".", 1)[0] if up else ""), key="hs_name")
    category = c2.selectbox("发布/实施类别", ["政府发布/实施", "部门发布/实施"], key="hs_cat")
    c3, c4, c5 = st.columns(3)
    dept = c3.text_input("起草/提交部门", key="hs_dept")
    submitter = c4.text_input("提交人", key="hs_submitter")
    phone = c5.text_input("电话", key="hs_phone")
    c6, c7 = st.columns(2)
    screen_date = c6.date_input("初筛日期", value=date.today(), key="hs_date")
    related_dept = c7.text_input("涉及的相关部门", key="hs_related")
    method = st.text_input("初筛方法",
                           value="AI 辅助专家研判(因果路径展开 + 专家核定)", key="hs_method")

    key = _get_key()
    if not key:
        key = st.text_input("DeepSeek API Key(未在 Secrets 配置时可临时输入,仅本次会话)",
                            type="password", key="hs_key").strip()

    gen = st.button("🤖 AI 展开因果路径并生成草案", type="primary", disabled=not (up and key))
    if not up:
        st.caption("请先上传评估对象文档。")
    elif not key:
        st.caption("需要 DeepSeek API Key(Secrets 配 `deepseek_api_key`,或上方临时输入)。")

    if gen:
        from auth import rate_limit
        ok, wait = rate_limit("hia_screen", 6, 60)
        if not ok:
            st.warning(f"⏳ 生成请求过于频繁,请约 {wait}s 后再试。")
        else:
            text, info = hs.extract_text(up.name, up.getvalue())
            if info.get("error"):
                st.error(info["error"])
            else:
                with st.status("AI 因果路径分析中(约 30–60 秒,三步流水线)…", expanded=True) as status:
                    def prog(s):
                        status.write(s)
                    res = hs.analyze(text, key, project_name=name, progress=prog)
                    status.update(label="分析完成", state="complete", expanded=False)
                _clear_state()
                st.session_state["hs_res"] = res
                st.session_state["hs_docinfo"] = info
                tip = f"已解析{info['kind']}" + (f"·{info['pages']}页" if info["pages"] else "")
                if info.get("truncated"):
                    tip += "(文档较长已截断前 4 万字)"
                st.success(f"{tip};抽取行动 {len(res['actions'])} 项、展开路径 "
                           f"{len(res['pathways'])} 条。请在下方复核路径图与判定。")

    res = st.session_state.get("hs_res")
    if not res:
        return

    # ===== ② 整体小结 =====
    st.divider()
    if res.get("summary"):
        st.info("AI 研判小结(参考):" + res["summary"])
    if res.get("notes"):
        st.caption("⚠ 仍需专家补充核实:" + res["notes"])

    # ===== ③ 因果路径图(随采纳/剪枝实时重绘)=====
    st.markdown("##### ③ 因果路径图(政策行动 → 健康决定因素 → 健康结果)")
    st.caption("左=政策行动,中=健康决定因素(多级、可间接),右=初筛表 10 题。"
               "颜色:红/橙=风险(强/中),绿=效益,灰=推测;虚线=假设待证。图较宽,可在框内左右/上下拖动查看;下方可勾选采纳/剪枝。")
    # 让 graphviz 按自然尺寸渲染 + 框内滚动(否则 Streamlit 会把超宽图缩到容器宽 → 字太小、压扁)
    st.markdown(
        '<style>'
        '[data-testid="stGraphVizChart"]{overflow:auto !important; max-height:600px;'
        'border:1px solid #DCEEE3; border-radius:8px; background:#fff;}'
        '[data-testid="stGraphVizChart"] svg{width:auto !important; height:auto !important;'
        'max-width:none !important;}'
        '</style>', unsafe_allow_html=True)
    adopted = _adopted()
    if adopted:
        # 不用 use_container_width:它会把超宽图的 SVG 宽高抹成 0 → 整图不显示。
        st.graphviz_chart(hs.build_dot(res["actions"], adopted))
    else:
        st.caption("(当前没有已采纳的路径,勾选下方路径后此处显示图。)")

    # ===== ④ 路径采纳/剪枝(按结果问题分组)=====
    st.markdown("##### ④ 路径复核:采纳 / 剪枝(默认采纳有依据路径,"
                "「假设待证」需专家勾选才计入)")
    allp = _all_pathways()
    for q in range(1, len(hs.QUESTIONS) + 1):
        ps = [p for p in allp if p["outcome_q"] == q]
        if not ps:
            continue
        with st.expander(f"Q{q} {hs.SHORT_Q[q-1]} —— {len(ps)} 条路径", expanded=False):
            for p in ps:
                col = _STRENGTH_C[p["strength"]]
                chain = " → ".join(p["chain"])
                meta = (f"<span style='color:{col};font-weight:600'>[{p['strength']}]</span> "
                        f"<span style='color:#888'>{p['status']} · {p['direction']} · "
                        f"{p.get('lens','')}</span>")
                st.markdown(meta, unsafe_allow_html=True)
                st.checkbox(chain, value=_adopt_default(p), key=f"hs_adopt_{p['id']}")
                if p.get("population"):
                    st.caption("　人群:" + p["population"])
                if p.get("status") == "文档支持" and p.get("evidence"):
                    st.caption("　📄 文档依据:" + p["evidence"])
                cards = p.get("cards") or []
                if cards:
                    for c in cards:
                        st.caption("　📚 来源:" + "；".join(c["sources"])
                                   + ("　(WHO来源待补强)" if c.get("status") == "todo" else ""))
                        if c.get("note"):
                            st.caption("　　" + c["note"])
                else:
                    st.caption("　📚 机制来源:机制推断 · 待专家补证")

    # —— 专家补充自定义路径 ——
    with st.expander("➕ 补充自定义路径(专家手动添加)"):
        aopts = {a["id"]: f"{a['id']} {a['action'][:24]}" for a in res["actions"]}
        ca, cb = st.columns([1, 1])
        c_act = ca.selectbox("起始行动", list(aopts.keys()),
                             format_func=lambda x: aopts[x], key="hs_c_act")
        c_q = cb.selectbox("落到的问题", list(range(1, 11)),
                           format_func=lambda q: f"Q{q} {hs.SHORT_Q[q-1]}", key="hs_c_q")
        c_chain = st.text_input("因果链(用 → 或 ; 分隔各级节点)",
                                placeholder="如:货运增加 → 道路阻隔 → 体力活动下降 → 慢性病", key="hs_c_chain")
        cc, cd = st.columns(2)
        c_str = cc.selectbox("强度", hs.STRENGTHS, key="hs_c_str")
        c_dir = cd.selectbox("方向", ["风险", "效益"], key="hs_c_dir")
        if st.button("添加该路径"):
            steps = [s.strip() for s in c_chain.replace("；", ";").replace(";", "→").split("→") if s.strip()]
            if steps:
                st.session_state.setdefault("hs_custom", [])
                cid = f"C{len(st.session_state['hs_custom'])+1}"
                newp = {
                    "id": cid, "action_id": c_act, "chain": steps, "outcome_q": int(c_q),
                    "direction": c_dir, "population": "", "lens": "专家补充",
                    "strength": c_str, "status": "专家补充", "evidence": "(专家补充)",
                    "confidence": 0.8}
                hia_evidence.annotate([newp])      # 自动匹配 WHO/meta 证据卡片
                st.session_state["hs_custom"].append(newp)
                st.session_state[f"hs_adopt_{cid}"] = True
                st.rerun()
            else:
                st.warning("请填写因果链。")

    # ===== ⑤ 聚合判定(由已采纳路径确定性算出)+ 专家覆盖 =====
    st.divider()
    st.markdown("##### ⑤ 10 题判定(系统按已采纳路径聚合,专家可改判)")
    st.caption("聚合规则:有「强/中」且非纯假设的路径 → 是;仅「推测/假设待证」→ 不知道;无路径 → 否。"
               "专家可在每题独立改判。")
    items_live = hs.compute_items(_adopted())
    items_out = []
    for it in items_live:
        q = it["q"]
        with st.container(border=True):
            agg = it["answer"]
            col = _BADGE[agg]
            st.markdown(
                f"**{q}. {hs.QUESTIONS[q-1]}**　"
                f"<span style='background:{col};color:#fff;padding:1px 8px;border-radius:9px;"
                f"font-size:0.8rem;'>聚合判定:{agg}</span> "
                f"<span style='color:#888;font-size:0.8rem;'>支撑路径 {it['n_path']} 条</span>",
                unsafe_allow_html=True)
            if it.get("gaps"):
                st.caption("⚠ " + it["gaps"])
            cc1, cc2 = st.columns([1, 2])
            ans = cc1.radio("专家判定", ANSWERS, index=ANSWERS.index(agg),
                            horizontal=True, key=f"hs_ans_{q}")
            note = cc2.text_input("专家备注(可选)", key=f"hs_note_{q}",
                                  placeholder="补充判断理由 / 需核实点")
        items_out.append({"q": q, "answer": ans, "note": note})

    # ===== ⑥ 结论 + 导出 =====
    st.divider()
    st.markdown("##### ⑥ 结论与导出")
    n_yes = sum(1 for x in items_out if x["answer"] == "是")
    n_unk = sum(1 for x in items_out if x["answer"] == "不知道")
    m1, m2, m3 = st.columns(3)
    m1.metric("判「是」", n_yes); m2.metric("判「不知道」", n_unk)
    m3.metric("判「否」", len(items_out) - n_yes - n_unk)
    yes_qs = [x["q"] for x in items_out if x["answer"] == "是"]
    if yes_qs:
        st.caption("建议进入正式评估并重点关注:第 " + "、".join(map(str, yes_qs)) + " 题。")

    lv_default = res.get("suggest_level") or "轻度"
    level = st.radio("结论:健康影响程度", LEVELS, index=LEVELS.index(lv_default),
                     horizontal=True, key="hs_level",
                     help="AI 建议:" + (res.get("suggest_level") or "—") + "(仅参考,以专家判定为准)")
    opinion = st.text_area("评估专家组意见", key="hs_opinion",
                           placeholder="对评估过程与结论的描述;如需进一步评估,可概述待评估的主要问题与方法。")

    header = {"name": name, "category": category, "dept": dept, "submitter": submitter,
              "phone": phone, "screen_date": str(screen_date), "method": method,
              "related_dept": related_dept}
    docx = hs.build_screen_docx(header, items_out, _adopted(), level, opinion)
    st.download_button("📄 导出初筛表(Word)", data=docx,
                       file_name=f"健康影响评估初筛表_{name or '评估对象'}.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       type="primary")
    st.caption("导出的初筛表含 10 题判定、各题采纳的因果路径与依据、结论与签字栏。"
               "AI 不替代专家判定;签字与最终结论以专家为准。")
