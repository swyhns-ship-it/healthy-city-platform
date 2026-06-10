# -*- coding: utf-8 -*-
"""智能助手引擎 —— 调 DeepSeek,把用户对话转成「回复 + 选项 + 动作」结构化响应。

DeepSeek 为 OpenAI 兼容接口(api.deepseek.com),用 JSON 模式稳定产出协议。
助手只引导/推荐/给选项/请用户在地图操作,真正计算仍在各模块页完成(引导+预填跳转)。
知识底座见 platform_manual.py;被 views/assistant.py 调用。
"""
import json

import requests

import platform_manual as pm

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

_PROTOCOL = """你必须只输出一个 JSON 对象(不要任何额外文字、不要 markdown 代码块),字段:
{
  "reply": "给用户看的简明中文回复",
  "options": [{"label":"按钮上的字","value":"用户点它后等价于说的话"}],
  "action": {"type":"navigate|need_map|none", "page":"模块key(navigate时必填)",
             "prefill":{"session键":"值"}, "map_mode":"click或draw(need_map时必填)"}
}
说明:options 用于让用户点选而非打字(没有就给空数组[]);action 没有就用 {"type":"none"}。"""

_RULES = """你是「健康城市规划与智能评估平台」的智能助手。用户多为规划/管理/研究人员,**不一定懂技术术语**,你要把他们当第一次用平台的人来引导。

语气与说明(很重要):
- 多用**通俗、友好、完整**的说明文字。把功能"能帮你做什么、为什么有用、大概几步操作"讲清楚,别只甩名词。每次回复尽量写 2–4 句话,不要过于简短。
- **任何专业词或参数都要用一句大白话解释**(例:"MCLP 选址"="自动帮你算新增设施放哪几处覆盖最多人";"容积率"="地块上盖了多少建筑面积";"重点改造N格"="只挑潜力最大的少数地块来改")。
- 给 options 时,**选项文字本身要让外行一看就懂**——不要只写"重点改造N格",要写成"只重点改造潜力最大的少数地块";不要只写术语缩写。

流程(尽量短,别逐个参数盘问):
1. 先理解用户想解决什么问题,匹配最合适的 1–2 个功能,用一段话解释这个功能能帮他做什么、原理大意。
2. 功能若需要地点/起终点/范围,用 action.need_map(map_mode=click 点一个点 / draw 圈一个范围)请他在地图上操作。
3. **关键参数能用默认值就用默认值,不要让用户在对话里连续选一堆陌生参数**。最多给 1 个最重要、且你已解释清楚的选择;其余告诉他"进入功能页后可随时调整"。
4. 拿到必要信息后,用 action.navigate 带他进功能页(page=清单里的 key),并在 reply 里说明:进去后会看到什么、默认已设了什么、他可以怎么调。

5. **每一轮都必须给用户一个明确的下一步**:要么给 options 让他点选,要么用 need_map 让他点/圈,要么用 navigate 给跳转按钮,要么问一个具体问题并配 options。**绝不能只回一句话却不给任何下一步**(那样用户会卡住)。
6. **需要多个地点的功能(例如清凉路径规划需要"起点+终点")不要在对话里逐个收集坐标**,直接用 action.navigate 让用户进入该功能页,在页面地图上点选起终点(reply 里说明进去后怎么点)。need_map 只用于"单个点"或"单个范围"。
7. **只浏览/筛选类功能(如中暑风险地图)不需要让用户点地图**,直接 navigate 进页面即可。need_map 只在功能确实要"一个具体地点"或"一个范围"作为计算输入时才用(如急救反应时间要事发点、骑行/绿地要范围)。用户进页面后提出的筛选/调参问题(如"只看重症"),用文字告诉他在页面里哪个控件怎么调,并可再次 navigate。
8. **带用户去功能页一律用 action.navigate(系统会显示一个跳转按钮)**,不要把"进入XX页"写成 options 选项。也**不要假称用户"已进入/已打开页面"**——用户必须点了跳转按钮才会进入;你应说"点下方按钮即可进入"。
9. 回复尽量充分但**别过度冗长**(一般 2–4 句即可),避免太长。用户已经在某功能流程中又问该功能的参数/模式(如"我想用重点改造N格模式")时,直接用文字解释这个模式是什么、在页面哪里选,并配 navigate 按钮带他去;**不要回避或说"没理解"**。

硬性要求:reply 必须是非空、有信息量的中文,且必须配一个明确的下一步(options/need_map/navigate 三选一,除非确实是纯闲聊);只能推荐清单里存在的功能,page 用清单里的 key;options 可空,但只要给就要自解释;action 没有就 {"type":"none"}。一次不要堆太多功能。"""


def _system_prompt():
    return f"{_RULES}\n\n平台功能清单(key 用于跳转):\n{pm.manual_text()}\n\n{_PROTOCOL}"


def _extract_json(content):
    """从模型文本里稳健提取 JSON 对象(去掉 markdown 代码围栏、取第一个 {...})。"""
    s = (content or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s[:4].lower() == "json":
            s = s[4:].strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _call_once(msgs, api_key, timeout, temperature):
    """单次调用(json_object 模式 + 稳健提取),返回 (reply, options, action)。"""
    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": msgs, "temperature": temperature,
              "response_format": {"type": "json_object"}, "max_tokens": 1500},
        timeout=timeout)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"] or ""
    data = _extract_json(content)
    reply = str(data.get("reply", "") or "").strip()
    opts = [o for o in (data.get("options") or []) if isinstance(o, dict) and o.get("label")]
    act = data.get("action") if isinstance(data.get("action"), dict) else {"type": "none"}
    act.setdefault("type", "none")
    return reply, opts, act


def chat(history, api_key, timeout=60):
    """history -> dict(reply, options, action)。
    DeepSeek json_object 偶发对固定输入确定性地只吐空白 → 退化时给"扰动提示"并升温重试,打破确定性。"""
    base = [{"role": "system", "content": _system_prompt()}]
    base += [{"role": m["role"], "content": m["content"]} for m in history]
    attempts = [
        (base, 0.3),
        (base + [{"role": "user", "content": "请严格按系统要求,只输出一个 JSON 对象,reply 字段必须非空。"}], 0.8),
        (base + [{"role": "user", "content": "用 JSON 回复我,包含非空 reply 和明确的下一步(options 或 action)。"}], 1.2),
    ]
    reply, opts, act = "", [], {"type": "none"}
    for msgs, temp in attempts:
        try:
            reply, opts, act = _call_once(msgs, api_key, timeout, temp)
        except Exception:
            continue
        if reply or opts or act.get("type") != "none":
            break
    data = {"reply": reply, "options": opts, "action": act}
    # 兜底:回复为空 且 没有任何下一步 → 给有方向的引导,绝不出现死胡同
    if not str(data["reply"]).strip():
        if data["options"] or act.get("type") != "none":
            data["reply"] = "好的,请看下面。"
        else:
            data["reply"] = ("抱歉,我刚没太理解你的意思。你可以换个说法,或者直接告诉我你想做什么——"
                             "比如:看中暑风险分布、评估某地急救多快到、规划凉爽路线、分析骑行潜力、"
                             "算规划方案的健康影响。")
            data["options"] = [
                {"label": "看中暑风险分布", "value": "我想看上海中暑病例的空间分布"},
                {"label": "评估急救可达性", "value": "我想知道某个地点救护车多久能到"},
                {"label": "规划凉爽路线", "value": "我想规划一条凉快的出行路线"},
                {"label": "算规划方案健康影响", "value": "我想定量算规划方案对健康的影响"},
            ]
    return data
