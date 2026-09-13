"""
工银智养仓 · B端运营工作台 Demo v3.0
=====================================
第17届"工行杯"参赛作品演示

核心演示流程（90秒）：
  ① 运营看板：客户数据总览 + 分型分布 + 激活趋势
  ② 客户分型：双引擎分型（规则初筛 + LLM辅助解释）
  ③ AI策略工场：基于模拟脱敏数据生成候选策略
  ④ 客户库：200位模拟脱敏客户画像（仅用于原型路演）
  ⑤ 合规中心：三层防线 + 分级锁定 + 留痕
  ⑥ 税优计算：客户沟通辅助工具

作者：吕滢滢 | 广东金融学院 · 金融科技
"""

import streamlit as st
import json
import time
import random
import pandas as pd
import altair as alt
from datetime import datetime

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(page_title="工银智养仓 · B端运营工作台", page_icon="工", layout="wide")

# ============================================================
# DeepSeek API 配置
# ============================================================
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ============================================================
# 模拟客户库（200位脱敏模拟画像，仅用于路演交互）
# ============================================================
NAMES_POOL = ["陈", "张", "王", "李", "赵", "刘", "周", "吴", "郑", "孙", "钱", "冯", "蒋", "沈", "韩"]
BEHAVIORS = ["从未浏览养老金相关内容", "浏览过但未操作", "领过立减金后无后续", "联系过客服咨询", "使用过税优计算器", "浏览产品超过3次未操作"]
HOLDINGS = ["活期存款为主", "定期存款为主", "持有理财产品", "持有基金产品", "无资产"]
RISKS = ["保守型", "稳健型", "平衡型", "进取型"]
STATUS = ["已开户未缴存", "已缴存未满额", "已开户未缴存", "已开户未缴存"]


def generate_customer_pool(n=200):
    """生成模拟客户池（演示用），保证路演时可现场随机挑选客户"""
    pool = []
    for i in range(n):
        age = random.randint(22, 62)
        salary = random.choice([5000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 60000])
        pool.append({
            "id": f"C{1000+i}",
            "name": f"{random.choice(NAMES_POOL)}{random.choice(['先生', '女士', '小姐'])}",
            "age": age,
            "salary": salary,
            "status": random.choice(STATUS),
            "risk": random.choice(RISKS),
            "holdings": random.choice(HOLDINGS),
            "behavior": random.choice(BEHAVIORS),
            "days_inactive": random.randint(30, 400),
            "last_contact": random.choice(["30天前", "2个月前", "3个月前", "半年未联系", "从未联系"]),
            # 认知分/社保依赖度：v1.1 规则特征（演示数据模拟，分布对齐访谈结论）
            "knowledge": random.choice([1, 1, 2, 2, 2, 3, 3, 4, 4, 5]),
            "pension_reliance": random.choice([1, 1, 2, 2, 3, 3, 4, 4, 5]),
        })
    return pool


# ============================================================
# 双引擎分型：规则初筛 + LLM辅助解释
# ============================================================
def rule_based_classify(c):
    """规则初筛 v1.1（2026-09 迭代版，与 engine_eval 评估版本一致）
    规则初筛：仅用于原型演示，不代表真实客群分型准确率。"""
    # 不会投：认知分低（访谈：认知不足是第一大障碍）
    if c.get("knowledge", 3) <= 2:
        return [("不会投", 0.82, "产品认知不足 决策瘫痪")]
    # 不敢投：保守型 + 有了解意愿的信号
    if c["risk"] == "保守型" and ("咨询" in c["behavior"] or "浏览" in c["behavior"]):
        return [("不敢投", 0.75, "风险厌恶 + 担忧资金锁定")]
    # 懒得投：有缴存能力但缺行动触发
    if c["salary"] >= 25000 or "立减金" in c["behavior"] or c.get("pension_reliance", 3) >= 4:
        return [("懒得投", 0.70, "有缴存能力但缺乏行动触发")]
    # 兜底：年轻→认知缺口；保守/稳健→风险顾虑；其余待确认
    if c["age"] <= 35:
        return [("不会投", 0.60, "兜底：年轻客群普遍存在认知缺口")]
    if c["risk"] in ("保守型", "稳健型"):
        return [("不敢投", 0.60, "兜底：风险偏好偏保守")]
    return [("懒得投", 0.55, "兜底：需要更多交互数据确认")]


CLASSIFY_PROMPT = """# Role
你是工银智养仓的AI客户分型引擎，服务于工商银行个人养老金业务。
你的任务：根据客户画像判断其养老金账户休眠成因。

# 三种成因定义
- 不会投：金融素养不足，不知道选什么、不敢开始（认知障碍）
- 不敢投：风险厌恶，担心亏损或资金长期锁定（信任/风险障碍）
- 懒得投：有缴存能力，但缺乏行动触发，拖延决策（行为障碍）

# 输出格式（严格JSON）
{"type": "不会投/不敢投/懒得投", "confidence": 0.0-1.0, "reason": "一句话判断依据"}

# 硬约束
只输出JSON，不要其他文字。"""


def llm_classify(customer: dict, api_key: str):
    """LLM辅助解释：仅处理模拟、脱敏行为文本，不覆盖规则结论"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE)
        user_prompt = f"""年龄：{customer['age']}岁
月薪：{customer['salary']}元
风险偏好：{customer['risk']}
在工行持有：{customer['holdings']}
近期行为：{customer['behavior']}
沉睡时长：{customer['days_inactive']}天

请判断休眠成因。"""
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFY_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1, max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        # 提取JSON
        import re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("type"), data.get("confidence", 0.7), data.get("reason", "")
    except Exception as e:
        pass
    return None


def dual_classify(customer: dict, api_key: str):
    """规则先行：LLM仅补充解释，不得覆盖规则分型结论。"""
    rule_type, rule_conf, rule_reason = rule_based_classify(customer)[0]

    if api_key:
        llm_result = llm_classify(customer, api_key)
        if llm_result and llm_result[2]:
            return {
                "type": rule_type,
                "confidence": rule_conf,
                "reason": f"{rule_reason}；AI辅助解释：{llm_result[2]}",
                "rule_type": rule_type,
                "rule_conf": rule_conf,
                "method": "规则引擎判定 + LLM辅助解释（不覆盖规则结论）",
            }

    return {
        "type": rule_type,
        "confidence": rule_conf,
        "reason": rule_reason,
        "rule_type": rule_type,
        "rule_conf": rule_conf,
        "method": "规则引擎判定（LLM未配置）",
    }


# ============================================================
# AI 策略生成
# ============================================================
SYSTEM_PROMPT = """# Role
你是工银智养仓的AI合规激活策略引擎，服务于工商银行个人养老金业务。
你的任务：根据客户画像和休眠成因，生成一条合规的个性化激活策略。

# 输出格式（严格三行）
成因：[一句话判断]
策略：[一句话激活角度，给出具体触达内容建议]
合规：[合规提醒]

# 硬约束
1. 绝对不使用：保本、稳赚、无风险、保证收益
2. 不推荐具体基金产品名称
3. 输出必须标注"不构成投资建议"
4. 客户≥55岁时提示使用大字体、高对比度和语音交互等适老化能力
5. 客户≥65岁时不生成产品推介式内容，仅输出风险提示、规则解读与转人工建议"""


def generate_strategy(customer: dict, dormancy_type: str, api_key: str) -> str:
    """调用 DeepSeek 生成策略，失败时用模板兜底"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE)
        user_prompt = f"""年龄：{customer['age']}岁
月薪：{customer['salary']}元
账户状态：{customer['status']}
风险偏好：{customer['risk']}
在工行持有：{customer['holdings']}
近期行为：{customer['behavior']}
休眠成因（系统分型）：{dormancy_type}

请生成合规激活策略。"""
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3, max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[API调用失败，使用模板策略]\n\n成因：{dormancy_type}（基于规则引擎判定）\n策略：建议通过税优计算器链接进行首次触达，辅以政策科普内容\n合规：话术需经合规词库校验后发送，不构成投资建议"


# ============================================================
# 模板策略（API不可用时的fallback）
# ============================================================
FALLBACK_STRATEGIES = {
    "不会投": """成因：对规则和产品差异了解有限，容易因信息过载而暂缓决策
策略：发送个人养老金基础规则科普与风险测评入口，先帮助客户理解制度与自身风险偏好
合规：不推荐具体产品；内容以科普和适当性提示为主，不构成投资建议""",
    "不敢投": """成因：对净值波动或资金长期性的顾虑较强，需先明确产品规则和风险边界
策略：提供不同产品类型的规则解读与风险提示，引导客户在完成风险测评后了解适配选项
合规：不承诺收益或安全性；客户达到特殊保护条件时由客户经理进一步评估""",
    "懒得投": """成因：已有一定认知，但缺少行动触发和清晰的缴存规划
策略：发送税优简化测算与年度缴存提醒，邀请客户先了解规则后自主决策
合规：不使用收益承诺；产品匹配与最终触达均须经过适当性与合规审核""",
}


# ============================================================
# 渠道版本生成：同一策略 → 四个渠道内容
# 全部按分型 + 客户画像生成；用词受合规约束（不含保本/稳赚/收益承诺）
# ============================================================
# 个人所得税综合所得级距（用于按收入估算节税金额）
TAX_BRACKETS = [
    (36000, 0.03), (144000, 0.10), (300000, 0.20), (420000, 0.25),
    (660000, 0.30), (960000, 0.35), (float('inf'), 0.45),
]
QUOTA = 12000          # 个人养老金年缴存税前扣除限额


def estimate_tax_rate(annual_taxable):
    """按年应纳税所得额估算适用税率"""
    for limit, rate in TAX_BRACKETS:
        if annual_taxable <= limit:
            return rate
    return 0.45


def estimate_saving(salary):
    """按月薪粗估顶格缴存的当年节税金额
    简化口径：年应纳税所得额 ≈ 月薪×12 − 60000（基本减除费用），
    未计入专项附加扣除与社保公积金，实际以个税 App 为准。"""
    try:
        annual_taxable = max(0.0, float(salary) * 12 - 60000)
    except (TypeError, ValueError):
        annual_taxable = 0.0
    rate = estimate_tax_rate(annual_taxable)
    if rate <= 0.03:
        return 0, rate
    return int(round(QUOTA * (rate - 0.03), -1)), rate   # 与领取时 3% 的差额


# 每个分型的沟通切入点（渠道版本共用的内容内核）
CHANNEL_CORE = {
    "不会投": {
        "hook": "个人养老金怎么参与、和自己有什么关系",
        "value": "把制度规则讲清楚：谁能参加、账户怎么用、领取条件是什么",
        "benefit": "个人养老金的三项税收优惠：缴存时税前扣除、投资期间暂不征税、"
                   "领取时按 3% 单独计税；往年在手机银行可直接办理",
        "probe": "您对个人养老金制度了解多少？",
    },
    "不敢投": {
        # 合规要点：个人养老金账户封闭运行，除六类法定情形外不得提前支取。
        # 话术只能"如实说明支取规则"，不得出现"流动性""随时可取""灵活"等暗示可提前支取的表述。
        "hook": "12000 元额度内，缴存多少就抵扣多少，钱还在您自己的账户里",
        "value": "说明账户封闭运行的规定与法定领取情形",
        "benefit": "每年最多缴存 12000 元，这部分可在个税前据实扣除；账户里的投资收益暂不征税，"
                   "将来领取时只按 3% 单独计税",
        "probe": "您主要顾虑的是资金期限，还是产品波动？",
        # 支取规则说明（五部门《关于领取个人养老金有关问题的通知》，2025.9 起实施）
        "rule": "一是达到领取基本养老金年龄；二是完全丧失劳动能力；三是出国（境）定居；"
                "四是医疗负担较重（近 12 个月自付部分超过本省上年度居民人均可支配收入）；"
                "五是领取失业保险金累计满 12 个月；六是正在领取城乡最低生活保障金",
    },
    "懒得投": {
        "hook": "今年能省多少税，一分钟算清楚",
        "value": "用税优测算展示缴存与节税的关系，降低首次行动门槛",
        "benefit": "每年缴存最多 12000 元，按您的收入测算当年可节税约 {saving} 元；"
                   "钱仍在您名下账户，将来领取时只按 3% 计税",
        "probe": "要不要我发您一个税优测算入口，先看看自己能省多少？",
    },
}


def build_channel_versions(customer: dict, dormancy_type: str) -> dict:
    """按客户画像与分型生成四个渠道版本（模板化，无 API 时也完整可用）
    返回：{'企微': 全文, '短信': ≤70字, '推送标题': 标题, '推送正文': 正文, '电话': 通话脚本}
    合规约束：不出现保本/稳赚/保证收益/限时等表述；不含产品推荐；均需人工审核后发送。
    """
    core = CHANNEL_CORE.get(dormancy_type, CHANNEL_CORE["不会投"])
    name = customer.get("name", "客户")
    age = customer.get("age", 35)
    # 称呼：拆出姓氏与称谓，拼成"王女士/王先生"（照搬全名在短信里占字数）
    raw = name.replace("先生", "|先生").replace("女士", "|女士").replace("小姐", "|小姐")
    if "|" in raw:
        surname, title = raw.split("|", 1)
        call = f"{surname}{title}"       # 如"王女士"
    else:
        call = name or "您"

    # ---------- 企微话术版（完整，一对一沟通） ----------
    saving, _rate = estimate_saving(customer.get("salary", 0))
    if saving:
        benefit_line = (f"按您目前收入测算，每年缴存 12000 元、当年可少缴个税约 {saving} 元；"
                        f"投资收益暂不征税，将来领取时只按 3% 计税")
    else:
        benefit_line = ("个人养老金缴费可在税前扣除、投资收益暂不征税、领取时按 3% 单独计税；"
                        "若您目前适用税率较低，节税空间有限，可以先了解规则再决定")

    wecom = (
        f"{call}您好，我是您的养老金服务专员。\n"
        f"想和您介绍一个和收入有关的安排——{core['hook']}。\n"
        f"{benefit_line}。\n"
        f"{core['value']}。\n"
        f"{core['probe']}"
    )

    # ---------- 短信浓缩版（≤70 字） ----------
    if saving:
        sms = f"【工行】{call}您好，个人养老金缴存可在税前扣除，按您收入测算当年约可节税{saving}元，回复1了解详情。"
    else:
        sms = f"【工行】{call}您好，个人养老金缴存可享个税抵扣、投资暂不征税、领取按3%计税，回复1了解规则。"
    if len(sms) > 70:   # 超长则进一步压缩
        sms = f"【工行】{call}您好，个人养老金缴存可享个税抵扣，回复1了解规则。"

    # ---------- APP 推送版（标题 ≤14 字，正文 ≤50 字） ----------
    push_titles = {
        "不会投": "个人养老金怎么参与",
        "不敢投": "每年可省多少税？",
        "懒得投": "今年能省多少税？",
    }
    push_bodies = {
        "不会投": "缴存可税前扣除、投资暂不征税、领取按 3% 计税，一图看懂。",
        "不敢投": (f"按您收入测算，每年缴存 12000 元约可节税 {saving} 元——看三个环节的税收优惠。"
                   if saving else "缴存税前扣除、投资暂不征税、领取按 3% 计税，看清三个环节。"),
        "懒得投": "输入月薪与缴存额，一分钟算出您的节税金额。",
    }
    title = push_titles.get(dormancy_type, "个人养老金服务")
    body = push_bodies.get(dormancy_type, "了解规则与自身适配条件，自主决策。")

    # ---------- 电话话术版（含合规提示） ----------
    phone = (
        f"【开场】{call}您好，我是工行的养老金服务专员，占用您两分钟，"
        f"关于您的个人养老金账户有个服务提醒。\n"
        f"【切入】{core['probe']}\n"
        f"【好处】{benefit_line}。\n"
        f"【说明】{core['value']}。\n"
        + (f"【支取规则】账户封闭运行，以下六种情形可以领取：{core['rule']}。\n"
           if core.get("rule") else "")
        + f"【合规提示】以上内容为规则解读，不构成投资建议；"
        f"如需了解具体产品，需先完成风险测评并由经办人员说明。\n"
        f"【收尾】我把规则解读发到您的手机银行消息里，您方便时看一下。"
    )

    return {"企微": wecom, "短信": sms, "推送标题": title, "推送正文": body, "电话": phone}

# ============================================================
# 样式
# ============================================================
st.markdown("""
<style>
/* 工行式金融工作台：白底、工行红、深灰文字，避免炫技渐变。 */
:root { --icbc-red:#c7000b; --icbc-red-dark:#9d0009; --ink:#262626; --muted:#6b7280; --line:#e5e5e5; --paper:#ffffff; --canvas:#f6f6f6; }
.stApp { background:var(--canvas); color:var(--ink); font-family:"Microsoft YaHei","PingFang SC",sans-serif; }
[data-testid="stHeader"] { background:rgba(246,246,246,.94); }
section[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
section[data-testid="stSidebar"] h2 { color:var(--icbc-red)!important; letter-spacing:.04em; }
/* 左侧导航在白底上保持完整的图标、文字和选中态。 */
section[data-testid="stSidebar"] [role="radiogroup"] label { display:flex!important; align-items:center!important; min-height:38px; padding:0 10px!important; margin:3px 0!important; border-left:3px solid transparent; border-radius:2px; color:var(--ink)!important; background:#fff!important; opacity:1!important; }
section[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#f8f1f1!important; color:var(--icbc-red)!important; }
section[data-testid="stSidebar"] [role="radiogroup"] label * { color:var(--ink)!important; opacity:1!important; font-size:.91rem!important; }
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:#fff1f2!important; border-left-color:var(--icbc-red)!important; }
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) * { color:var(--icbc-red)!important; font-weight:600!important; }
h1,h2,h3 { color:var(--ink)!important; font-weight:700!important; letter-spacing:.01em; }
h1 { border-left:4px solid var(--icbc-red); padding-left:.65rem; }
h3 { border-bottom:1px solid var(--line); padding-bottom:.45rem; margin-top:1.2rem!important; }
p,li { letter-spacing:.01em; }
/* 各类输入控件统一白底深字，防止主题继承造成文字与背景混在一起。 */
[data-baseweb="select"] > div, [data-baseweb="input"] > div, textarea, input { background:#fff!important; color:var(--ink)!important; }
[data-baseweb="select"] *, [data-baseweb="radio"] label, [data-testid="stSelectbox"] label, [data-testid="stSlider"] label { color:var(--ink)!important; }
[data-testid="stExpander"] { background:#fff; border:1px solid var(--line); border-radius:4px; }
.card { background:var(--paper); border:1px solid var(--line); border-radius:4px; padding:1.1rem; color:var(--ink); box-shadow:0 1px 2px rgba(0,0,0,.04); }
.card-blue { background:var(--icbc-red); border-radius:4px; padding:1.1rem; color:#fff; text-align:center; box-shadow:none; }
.card-gold { background:#fff7f5; border:1px solid #f0c8cb; border-radius:4px; padding:1.1rem; color:var(--icbc-red); text-align:center; }
.card-green { background:#f2f8f4; border:1px solid #b8d9c1; border-radius:4px; padding:1.1rem; color:#1e6b3a; text-align:center; }
.card-blue div, .card-blue span, .card-blue strong { color:#fff!important; }
.card-gold div, .card-gold span, .card-gold strong { color:#9d0009!important; }
.card-green div, .card-green span, .card-green strong { color:#1e6b3a!important; }
.big-num { font-size:2.05rem; font-weight:700; line-height:1.2; font-variant-numeric:tabular-nums; }
.tag { display:inline-block; padding:.16rem .55rem; border-radius:2px; font-size:.8rem; font-weight:600; }
.strategy-line { background:#fff; border-left:3px solid var(--icbc-red); border-top:1px solid var(--line); border-right:1px solid var(--line); border-bottom:1px solid var(--line); border-radius:2px; padding:.72rem 1rem; margin:.35rem 0; color:var(--ink); font-size:.9rem; line-height:1.7; }
.check-pass { background:#f2f8f4; border-left:3px solid #3f8a59; padding:.5rem .9rem; margin:.3rem 0; font-size:.88rem; color:#235e36; }
.check-warn { background:#fff8e8; border-left:3px solid #c98a17; padding:.5rem .9rem; margin:.3rem 0; font-size:.88rem; color:#7b5100; }
.check-alert { background:#fff3f3; border-left:3px solid var(--icbc-red); padding:.5rem .9rem; margin:.3rem 0; font-size:.88rem; color:#8c1219; }
.stButton>button { background:var(--icbc-red); border:1px solid var(--icbc-red); border-radius:2px; color:#fff; font-weight:600; }
.stButton>button:hover { background:var(--icbc-red-dark); border-color:var(--icbc-red-dark); color:#fff; }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:4px; padding:.7rem .8rem; }
[data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] { color:var(--muted)!important; }
[data-testid="stMetric"] [data-testid="stMetricLabel"] *, [data-testid="stMetric"] [data-testid="stMetricValue"] *, [data-testid="stMetric"] [data-testid="stMetricDelta"] * { color:var(--ink)!important; opacity:1!important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { color:var(--ink)!important; opacity:1!important; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:4px; overflow:hidden; }
.vega-embed, .vega-embed details, .vega-embed summary { background:#fff!important; }
.vega-embed svg { background:#fff!important; }
.stage-card { min-height:150px; background:#fff; border:1px solid #e5e5e5; border-top:3px solid #c7000b; padding:1rem; border-radius:3px; }
.stage-no { color:#c7000b; font-size:.8rem; font-weight:700; letter-spacing:.08em; }
.stage-title { color:#262626; font-weight:700; font-size:1rem; margin:.35rem 0; }
.stage-copy { color:#6b7280; font-size:.84rem; line-height:1.6; }
.locked-card { background:#fff3f3; border:1px solid #efc4c7; border-left:4px solid #c7000b; border-radius:3px; padding:1rem; color:#7c1d24; }
.editable-card { background:#f2f8f4; border:1px solid #b8d9c1; border-left:4px solid #3f8a59; border-radius:3px; padding:1rem; color:#235e36; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 页面指引
# ============================================================
PAGE_GUIDES = {
    "📊 运营看板": "先看模拟客户池的休眠分布，再查看规则排序形成的待联系名单。",
    "🔍 客户分型": "选择一位客户，查看规则结论、联系依据和可复核字段。",
    "🤖 AI策略工场": "选择客户后生成候选内容，查看合规对照和字段锁定规则。",
    "批量任务": "生成候选任务后，选择一位客户回填模拟触达结果，观察下一步安排。",
    "📈 A/B试验台": "查看试点应如何分组、记录指标并设置扩围决策门。",
    "客户库": "按年龄、账户状态和休眠原因筛选模拟画像。",
    "🔒 合规中心": "输入一段候选话术，查看禁用词与风险提示检查结果。",
    "🧮 税优计算器": "输入年龄、月薪和年缴存额，查看简化情景测算及边界提示。",
}

# ============================================================
# 侧边栏
# ============================================================
# 跨页跳转：按钮先写入待跳转目标，这里在导航 widget 实例化【之前】应用
if "_nav_target" in st.session_state:
    st.session_state["nav"] = st.session_state.pop("_nav_target")

with st.sidebar:
    st.markdown("""
    <div style="padding:1.1rem .3rem .9rem;border-bottom:2px solid #c7000b;">
        <div style="font-size:.75rem;color:#6b7280;letter-spacing:.12em;">ICBC · PENSION OPERATIONS</div>
        <h2 style="margin:.3rem 0 .15rem;">工银智养仓</h2>
        <p style="color:#6b7280;font-size:.8rem;margin:0;">个人养老金合规运营工作台</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    page = st.radio("功能导航", [
        "📊 运营看板",
        "🔍 客户分型",
        "🤖 AI策略工场",
        "批量任务",
        "📈 A/B试验台",
        "客户库",
        "🔒 合规中心",
        "🧮 税优计算器",
    ], label_visibility="collapsed", key="nav")

    st.divider()
    st.markdown("### 使用指引")
    st.caption(PAGE_GUIDES[page])
    st.caption("建议路演顺序：运营看板 → 客户分型 → 客户触达策略 → 批量任务 → 合规中心。")

    st.divider()

    st.markdown("### API配置")
    api_key = st.text_input("外部大模型 API Key（仅模拟脱敏数据，可选）", type="password", placeholder="sk-...",
                            help="获取: platform.deepseek.com。留空使用规则引擎+模板策略。")
    if api_key:
        st.success("已配置 · LLM仅辅助解释与候选内容生成，不覆盖规则结论")
    else:
        st.info("未配置 · 使用规则引擎")

    st.divider()
    st.caption("© 2026 工银智养仓 · 吕滢滢")
    st.caption("广东金融学院 · 金融科技")
    st.caption("第17届工行杯参赛作品")

# ============================================================
# 客户池（session 持久化，保证跨页面一致）
# ============================================================
if "customer_pool" not in st.session_state:
    random.seed(20260901)  # 固定种子：演示数据可复现（演示/录制用同一批客户）
    st.session_state.customer_pool = generate_customer_pool(200)

pool = st.session_state.customer_pool

# 精选5个演示客户（有代表性的）
FEATURED = [c for c in pool if c["days_inactive"] > 60][:5] if len(pool) >= 5 else pool[:5]


# ============================================================
# 页面1：运营看板
# ============================================================
if page == "📊 运营看板":
    st.markdown("## 客户经理运营看板")
    st.caption("本页使用模拟、脱敏客户画像，展示待试点的工作台结构。")
    st.divider()

    # 所有首页数值均从当前200位模拟客户画像实时计算，不映射真实业务规模。
    total = len(pool)
    # 沉睡定义：180 天无养老金相关操作（与卡片文案、图注口径保持一致）
    dormant_pool = [c for c in pool if c["days_inactive"] >= 180]
    dormant = len(dormant_pool)
    # 本周激活记录：按沉睡客群模拟——本周触达的沉睡客户数（演示数据）
    contacted_this_week = sum(1 for c in dormant_pool if c["last_contact"] == "30天前")
    activated_week = contacted_this_week
    # 试点转化率（模拟）：触达后完成缴存的比例，演示取值 20%
    converted = round(contacted_this_week * 0.2)
    conversion = (converted / contacted_this_week) if contacted_this_week else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="card-blue"><div class="big-num">{total:,}</div><div style="font-size:0.85rem;opacity:0.85;">模拟客户画像</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="card"><div class="big-num" style="color:#9d0009;">{dormant:,}</div><div style="font-size:0.85rem;color:#6b7280;">沉睡账户（180 天未动）</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="card-green"><div class="big-num">+{activated_week}</div><div style="font-size:0.85rem;opacity:0.85;">本周触达记录（模拟）</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="card-gold"><div class="big-num">{conversion:.0%}</div><div style="font-size:0.85rem;opacity:0.85;">触达转化率（模拟）</div></div>', unsafe_allow_html=True)

    st.caption(
        "指标口径：**沉睡账户**＝180 天无养老金相关操作；"
        "**本周触达记录**＝本周通过任一渠道联系到的沉睡客户数；"
        "**触达转化率**＝触达后完成缴存的比例。"
        "以上均为模拟脱敏数据的演示值，正式试点将按统一口径由系统日志自动取数。"
    )

    st.divider()

    # 分型分布 + 趋势
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 客户休眠原因分布")
        # 只统计沉睡客群（与上方"沉睡账户"卡片同一口径，避免总数矛盾）
        type_counts = {"不会投": 0, "不敢投": 0, "懒得投": 0}
        for c in dormant_pool:
            r = rule_based_classify(c)
            type_counts[r[0][0]] += 1

        dist_data = pd.DataFrame({
            "成因": list(type_counts.keys()),
            "客户数": list(type_counts.values()),
        })
        type_colors = {"不会投": "#c7000b", "不敢投": "#c98a17", "懒得投": "#3f8a59"}
        distribution_chart = (
            alt.Chart(dist_data)
            .mark_bar(size=26, cornerRadiusEnd=3)
            .encode(
                y=alt.Y("成因:N", sort=None, title=None, axis=alt.Axis(labelColor="#262626", labelFontSize=13)),
                x=alt.X("客户数:Q", title="模拟客户数", axis=alt.Axis(labelColor="#262626", titleColor="#4b5563", gridColor="#e5e5e5")),
                color=alt.Color("成因:N", scale=alt.Scale(domain=list(type_colors), range=list(type_colors.values())), legend=None),
                tooltip=[alt.Tooltip("成因:N", title="休眠原因"), alt.Tooltip("客户数:Q", title="模拟客户数")],
            )
            .properties(height=245)
        )
        distribution_labels = distribution_chart.mark_text(align="left", baseline="middle", dx=7, color="#262626", fontSize=12).encode(text="客户数:Q")
        st.altair_chart(distribution_chart + distribution_labels, use_container_width=True)
        st.caption(f"基于 {dormant} 位沉睡客户（180 天未动）的模拟分型分布，与上方「沉睡账户」口径一致；仅用于原型展示。")

    with col_right:
        st.markdown("#### 本周触达趋势示意（模拟）")
        trend = pd.DataFrame({
            "周一": [12], "周二": [18], "周三": [15], "周四": [22], "周五": [23], "周六": [17], "周日": [9],
        })
        trend_data = pd.DataFrame({
            "日期": list(trend.columns),
            "记录数": list(trend.iloc[0]),
        })
        trend_chart = (
            alt.Chart(trend_data)
            .mark_line(color="#c7000b", strokeWidth=3, point=alt.OverlayMarkDef(filled=True, fill="#c7000b", size=55))
            .encode(
                x=alt.X("日期:N", title=None, axis=alt.Axis(labelColor="#262626", labelFontSize=12)),
                y=alt.Y("记录数:Q", title="模拟记录数", scale=alt.Scale(zero=False), axis=alt.Axis(labelColor="#262626", titleColor="#4b5563", gridColor="#e5e5e5")),
                tooltip=[alt.Tooltip("日期:N"), alt.Tooltip("记录数:Q")],
            )
            .properties(height=245)
        )
        st.altair_chart(trend_chart, use_container_width=True)
        st.caption("趋势仅用于展示试点看板的图表结构，真实试点后按统一口径接入。")

    st.divider()

    st.markdown("### 今日优先联系（规则排序）")
    st.caption("排序参考：休眠时长、行为标签和合规边界。具体口径需在试点前确认。")

    for c in FEATURED:
        reasons = rule_based_classify(c)
        top_type, conf, desc = reasons[0]
        emoji = {"不会投": "🔵", "不敢投": "🟡", "懒得投": "🟢"}[top_type]
        color = {"不会投": "#3b82f6", "不敢投": "#f59e0b", "懒得投": "#10b981"}[top_type]

        st.markdown(f"""
        <div class="card" style="border-left:4px solid {color};margin:0.5rem 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <strong style="font-size:1rem;">{c['name']}</strong>
                    <span style="color:#6b7280;font-size:0.85rem;margin-left:0.8rem;">{c['age']}岁 · 月入{c['salary']:,} · 沉睡{c['days_inactive']}天 · {c['last_contact']}</span>
                </div>
                <span class="tag" style="background:{color}22;color:{color};">{emoji} {top_type}（置信度{conf:.0%}）</span>
            </div>
            <div style="color:#6b7280;font-size:0.85rem;margin-top:0.4rem;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

    st.caption("可在“客户分型”页查看该客户的判断依据。")

# ============================================================
# 页面2：客户分型
# ============================================================
elif page == "🔍 客户分型":
    st.markdown("## 客户休眠原因分析")
    st.caption("规则引擎完成客户分型，大模型仅辅助解释，不干预分类结果。")
    st.divider()

    # 客户选择：支持搜索
    name_options = [f"{c['name']}（{c['age']}岁 · 沉睡{c['days_inactive']}天）" for c in pool[:50]]
    selected_label = st.selectbox("选择客户（可搜索）", name_options)
    idx = name_options.index(selected_label)
    customer = pool[idx]

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### 📋 客户档案")
        st.markdown(f"""
        <div class="card">
            <table style="width:100%;color:#262626;font-size:0.9rem;">
                <tr><td style="padding:0.3rem 0;color:#6b7280;">客户编号</td><td>{customer['id']}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">年龄</td><td>{customer['age']}岁</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">月薪</td><td>¥{customer['salary']:,}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">账户状态</td><td>{customer['status']}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">风险偏好</td><td>{customer['risk']}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">在工行持有</td><td>{customer['holdings']}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">近期行为</td><td>{customer['behavior']}</td></tr>
                <tr><td style="padding:0.3rem 0;color:#6b7280;">沉睡时长</td><td>{customer['days_inactive']}天</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

    with col_r:
        st.markdown("#### 分析结果")

        result = dual_classify(customer, api_key)

        emoji = {"不会投": "🔵", "不敢投": "🟡", "懒得投": "🟢"}[result["type"]]
        color = {"不会投": "#3b82f6", "不敢投": "#f59e0b", "懒得投": "#10b981"}[result["type"]]

        st.markdown(f"""
        <div class="card" style="border-left:4px solid {color};margin:0.5rem 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span class="tag" style="background:{color}22;color:{color};font-size:0.95rem;">{emoji} {result['type']}</span>
                <span style="color:{color};font-weight:700;">置信度 {result['confidence']:.0%}</span>
            </div>
            <div style="color:#6b7280;font-size:0.88rem;margin-top:0.4rem;">{result['reason']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"**分型方法**：{result['method']}")
        if result["method"].startswith("LLM"):
            st.markdown(f"**规则引擎交叉验证**：{result['rule_type']}（置信度{result['rule_conf']:.0%}）")

        st.markdown("#### 联系依据")
        priority_reasons = [
            f"已连续 {customer['days_inactive']} 天未产生养老金相关操作，进入存量唤醒观察范围。",
            f"当前风险偏好为「{customer['risk']}」，后续内容需先通过适当性边界校验。",
        ]
        if "浏览" in customer["behavior"] or "咨询" in customer["behavior"]:
            priority_reasons.append("近期出现养老金专区浏览或咨询行为，可优先提供规则解读而非产品推介。")
        else:
            priority_reasons.append("近期无主动行为，建议低频触达并优先进行基础规则科普。")
        if customer["age"] >= 65:
            priority_reasons.append("年龄达到特殊保护阈值：仅进入风险提示、规则解读与转人工队列。")

        with st.expander("查看可复核的联系依据", expanded=True):
            for reason in priority_reasons:
                st.markdown(f"- {reason}")
            st.caption("以上为模拟、脱敏画像的原型解释。正式部署应基于经授权的数据标签，并保留规则版本与判断依据。")

        st.markdown("#### 判断依据")
        st.markdown("""
        - **规则初筛**：年龄、收入区间、产品持有、风险偏好 初始分类与置信度
        - **LLM辅助解释**：仅对模拟、脱敏行为文本补充原因说明，不覆盖规则分类
        - **持续迭代**：客户每产生一次新交互，分型画像自动更新
        """)

    st.divider()
    st.markdown("### 画像辅助指标（原型推导）")
    interest_signal = 80 if any(word in customer["behavior"] for word in ["浏览", "咨询", "计算器"]) else 25
    caution_signal = {"保守型": 85, "稳健型": 60, "平衡型": 45, "进取型": 35}[customer["risk"]]
    # 指标带简短注释（帮助客户经理一眼看懂分值含义）
    profile_data = pd.DataFrame({
        "指标全称": [
            "休眠程度｜分值越高，账户静止时间越长",
            "近期兴趣信号｜主动咨询或浏览行为的活跃度",
            "适当性关注｜风险与产品匹配的核验关注等级",
        ],
        "指标": ["休眠程度", "近期兴趣信号", "适当性关注"],
        "指数": [min(100, round(customer["days_inactive"] / 365 * 100)), interest_signal, caution_signal],
        "说明": [f"已沉睡 {customer['days_inactive']} 天", customer["behavior"], f"风险偏好：{customer['risk']}"],
        # 配色语义：红=风险告警（休眠程度），蓝=中性信息（兴趣信号），橙=需关注（适当性）
        "色": ["#c7000b", "#2E75D4", "#ED7D31"],
    })
    profile_chart = (
        alt.Chart(profile_data)
        .mark_bar(size=24, cornerRadiusEnd=3)
        .encode(
            y=alt.Y("指标全称:N", sort=None, title=None,
                    axis=alt.Axis(labelColor="#262626", labelFontSize=12,
                                  labelLimit=260, labelPadding=6)),
            x=alt.X("指数:Q", scale=alt.Scale(domain=[0, 100]), title="原型辅助指数",
                    axis=alt.Axis(labelColor="#262626", titleColor="#4b5563", gridColor="#e5e5e5")),
            color=alt.Color("指标:N", scale=alt.Scale(
                domain=["休眠程度", "近期兴趣信号", "适当性关注"],
                range=["#c7000b", "#2E75D4", "#ED7D31"]), legend=None),
            tooltip=[alt.Tooltip("指标:N", title="指标"), alt.Tooltip("指数:Q", title="分值"),
                     alt.Tooltip("说明:N", title="当前取值")],
        )
        .properties(height=200)
    )
    profile_labels = profile_chart.mark_text(align="left", baseline="middle", dx=7, color="#262626", fontSize=12).encode(text="指数:Q")
    st.altair_chart(profile_chart + profile_labels, use_container_width=True)
    st.caption("指数仅由当前模拟画像的休眠天数、行为文本与风险偏好换算，用于演示解释界面，不代表真实客户评分。")

    st.divider()
    st.markdown("#### 下一步")
    _c1, _c2 = st.columns([3, 5])
    with _c1:
        if st.button("生成个性化触达话术 →", type="primary", use_container_width=True,
                     key="goto_strategy"):
            # 记录目标客户；跳转目标写入 _nav_target，由脚本开头统一应用
            # （不能在 radio 实例化后直接改 session_state["nav"]）
            st.session_state["strategy_customer"] = f"{customer['name']}（{customer['age']}岁 · 沉睡{customer['days_inactive']}天）"
            st.session_state["_nav_target"] = "🤖 AI策略工场"
            st.rerun()
    with _c2:
        st.caption("基于当前分型结果生成四渠道合规话术（企微 / 短信 / APP推送 / 电话）")

    st.caption("也可在左侧导航直接进入「AI策略工场」查看候选内容与合规校验。")

# ============================================================
# 页面3：AI策略工场
# ============================================================
elif page == "🤖 AI策略工场":
    st.markdown("## 客户触达策略")
    st.caption("根据客户标签整理候选内容，先经合规校验，再进入人工审核。")
    st.divider()

    name_options = [f"{c['name']}（{c['age']}岁 · 沉睡{c['days_inactive']}天）" for c in pool[:50]]
    selected_label = st.selectbox("选择客户", name_options, key="strategy_customer")
    idx = name_options.index(selected_label)
    customer = pool[idx]

    result = dual_classify(customer, api_key)
    top_type = result["type"]
    # 演示参数：URL 加 ?type=不敢投 可强制指定分型（用于路演时逐个展示三类话术）
    _demo_type = st.query_params.get("type")
    if _demo_type in ("不会投", "不敢投", "懒得投"):
        top_type = _demo_type
        st.caption(f"（演示参数生效：已指定分型为「{_demo_type}」）")

    st.info(f"**分型结果：{top_type}**（置信度 {result['confidence']:.0%}）—— {customer['name']}，{customer['age']}岁，{customer['behavior']}")

    if st.button("生成候选策略", type="primary", use_container_width=True):
        with st.spinner("正在整理客户标签和规则边界……"):
            time.sleep(0.8)
            if api_key:
                strategy = generate_strategy(customer, top_type, api_key)
            else:
                strategy = FALLBACK_STRATEGIES[top_type]
                st.info("当前展示模板内容。原型只处理模拟、脱敏数据。")

            st.markdown("#### 候选触达策略")
            for line in strategy.strip().split("\n"):
                line = line.strip()
                if line:
                    st.markdown(f'<div class="strategy-line">{line}</div>', unsafe_allow_html=True)

            st.divider()
            st.markdown("#### 合规校验结果")
            checks = [
                ("✅ 话术已过禁用语词库校验（保本/稳赚/无风险）", "pass"),
                ("✅ 策略基于客户风险等级匹配", "pass"),
                ("✅ 已标注「不构成投资建议」", "pass"),
            ]
            if customer["age"] >= 55:
                checks.append(("⚠️ 客户≥55岁，建议启用适老化展示并进行适当性关怀提示", "warn"))
            if customer["age"] >= 65:
                checks.append(("🔴 客户≥65岁，禁止主动推送高风险产品，须额外风险提示", "alert"))
            if customer["risk"] == "保守型":
                checks.append(("✅ 已规避偏股型/混合型产品推荐", "pass"))

            for check, level in checks:
                cls = {"pass": "check-pass", "warn": "check-warn", "alert": "check-alert"}[level]
                st.markdown(f'<div class="{cls}">{check}</div>', unsafe_allow_html=True)

            st.divider()
            st.markdown("#### 合规红线对照（规则示例）")
            st.caption("示例展示红线表述如何被识别和替换，不进入发送队列。")
            before_col, after_col = st.columns(2)
            with before_col:
                st.error("""**修改前候选句**\n\n“这项安排比较稳，长期能有较好收益，建议您尽快办理。”\n\n命中：`较好收益`、`建议尽快办理`""")
            with after_col:
                st.success("""**合规输出候选句**\n\n“如您希望了解个人养老金规则和适配条件，可先完成风险测评；具体以产品说明及经办人员说明为准。”\n\n已替换为规则解读与适当性提示""")
            st.markdown("- **锁定字段**：风险提示、适当性结论、免责声明不可由经办人员修改。")
            st.markdown("- **可编辑字段**：称呼、问候语、预约时间等非营销核心字段；所有改动进入版本留痕。")
            st.caption("版本留痕：候选版 经办修改版 审批发送版。正式场景以行内合规制度和审批流程为准。")

            st.divider()
            st.markdown("#### 候选渠道版本")
            st.caption("同一策略按渠道特性生成四个版本，内容均由上方分型结果与客户画像生成；发送前须经人工审核。")
            versions = build_channel_versions(customer, top_type)

            vc1, vc2, vc3, vc4 = st.columns(4)
            with vc1: st.markdown('<div class="card" style="text-align:center;font-size:0.9rem;">📱 企微话术版<br><span style="color:#6b7280;font-size:0.8rem;">一键复制</span></div>', unsafe_allow_html=True)
            with vc2: st.markdown('<div class="card" style="text-align:center;font-size:0.9rem;">💬 短信浓缩版<br><span style="color:#6b7280;font-size:0.8rem;">70字内</span></div>', unsafe_allow_html=True)
            with vc3: st.markdown('<div class="card" style="text-align:center;font-size:0.9rem;">🔔 APP推送版<br><span style="color:#6b7280;font-size:0.8rem;">图文卡片</span></div>', unsafe_allow_html=True)
            with vc4: st.markdown('<div class="card" style="text-align:center;font-size:0.9rem;">📞 电话话术版<br><span style="color:#6b7280;font-size:0.8rem;">含合规提示</span></div>', unsafe_allow_html=True)

            # ---------- 企微话术版 ----------
            with st.expander("📱 企微话术版（完整版，适宜一对一沟通）", expanded=False):
                st.markdown(f'<div class="strategy-line">{versions["企微"]}</div>', unsafe_allow_html=True)
                st.caption("可编辑字段：称呼、问候语、预约时间｜锁定字段：风险提示、适当性结论、免责声明")
                st.code(versions["企微"], language=None)   # 提供一键复制区域

            # ---------- 短信浓缩版 ----------
            with st.expander("💬 短信浓缩版（70 字内）", expanded=False):
                sms = versions["短信"]
                st.markdown(f'<div class="strategy-line">{sms}</div>', unsafe_allow_html=True)
                n = len(sms)
                (st.success if n <= 70 else st.warning)(f"当前字数：{n} 字（含标点）")

            # ---------- APP 推送版（图文卡片） ----------
            with st.expander("🔔 APP 推送版（图文卡片预览）", expanded=False):
                st.markdown(f"""
                <div style="max-width:420px;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                  <div style="background:linear-gradient(135deg,#c7000b,#e23b3b);color:#fff;padding:14px 16px;">
                    <div style="font-size:1.05rem;font-weight:700;">{versions['推送标题']}</div>
                    <div style="font-size:0.78rem;opacity:0.9;margin-top:2px;">中国工商银行 · 个人养老金专区</div>
                  </div>
                  <div style="padding:14px 16px;background:#fff;">
                    <div style="font-size:0.9rem;color:#374151;line-height:1.6;">{versions['推送正文']}</div>
                    <div style="margin-top:12px;display:flex;gap:8px;">
                      <span style="background:#c7000b;color:#fff;border-radius:8px;padding:6px 16px;font-size:0.85rem;">去了解</span>
                      <span style="border:1px solid #d1d5db;color:#6b7280;border-radius:8px;padding:6px 16px;font-size:0.85rem;">暂不提醒</span>
                    </div>
                  </div>
                  <div style="background:#f9fafb;color:#9ca3af;font-size:0.72rem;padding:8px 16px;">
                    本内容为规则与政策解读，不构成投资建议
                  </div>
                </div>
                """, unsafe_allow_html=True)
                st.caption("推送卡片由策略内容自动生成：标题 ≤ 14 字，正文 ≤ 50 字，底部固定合规声明。")

            # ---------- 电话话术版 ----------
            with st.expander("📞 电话话术版（含合规提示）", expanded=False):
                for seg in versions["电话"].split("\n"):
                    if seg.strip():
                        st.markdown(f'<div class="strategy-line">{seg}</div>', unsafe_allow_html=True)
                st.warning("电话沟通须在客户已同意触达的前提下进行；客户明确拒绝时立即终止并记录，不得重复拨打。")

# ============================================================
# 页面4：批量激活任务
# ============================================================
elif page == "批量任务":
    st.markdown("## 批量任务")
    st.caption("批量整理候选内容，经过审核后进入任务流转。")
    st.divider()

    # 批量选择
    st.markdown("#### 选择目标客户（示例：沉睡超过90天）")
    batch_candidates = [c for c in pool if c["days_inactive"] > 90][:10]

    st.caption(f"原型按规则筛出 {len(batch_candidates)} 位高优先级客户（沉睡>90天）")

    # 展示批量客户卡片
    cols = st.columns(5)
    for i, c in enumerate(batch_candidates[:5]):
        r = rule_based_classify(c)
        dtype = r[0][0]
        emoji = {"不会投": "🔵", "不敢投": "🟡", "懒得投": "🟢"}[dtype]
        color = {"不会投": "#3b82f6", "不敢投": "#f59e0b", "懒得投": "#10b981"}[dtype]
        with cols[i]:
            st.markdown(f"""
            <div class="card" style="text-align:center;border-top:3px solid {color};">
                <div style="font-size:1.2rem;">{emoji}</div>
                <strong>{c['name']}</strong><br>
                <span style="color:#6b7280;font-size:0.8rem;">{c['age']}岁 · 沉睡{c['days_inactive']}天</span><br>
                <span class="tag" style="background:{color}22;color:{color};">{dtype}</span>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    if "batch_results" not in st.session_state:
        st.session_state.batch_results = []
    if "batch_feedback" not in st.session_state:
        st.session_state.batch_feedback = {}

    if st.button("生成候选策略（10位客户）", type="primary", use_container_width=True):
        results = []
        for c in batch_candidates:
            r = rule_based_classify(c)
            results.append({
                "客户": c["name"],
                "年龄": c["age"],
                "分型": r[0][0],
                "置信度": f"{r[0][1]:.0%}",
                "策略要点": {"不会投": "规则科普+风险测评", "不敢投": "规则解读+风险提示", "懒得投": "税优测算+年度提醒"}[r[0][0]],
                "合规状态": "待合规审批",
                "渠道": "企微/短信",
            })
        st.session_state.batch_results = results
        st.success("候选策略已生成，等待合规审批。")

    if st.session_state.batch_results:
        results = st.session_state.batch_results
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### 触达结果回填（模拟）")
        st.caption(
            "客户经理完成触达后，在此记录客户的反馈结果；"
            "系统按结果自动给出下一步动作建议，形成「触达 → 反馈 → 下一步」的闭环。"
        )
        feedback_customer = st.selectbox("选择需回填结果的客户", [row["客户"] for row in results], key="feedback_customer")
        next_actions = {
            "已阅读，暂未响应": "7天后进入低频规则提醒队列，不直接触发产品推介。",
            "主动咨询，转人工服务": "生成服务工单，由经办人员在适当性边界内跟进。",
            "明确暂不参与": "记录拒绝原因并降低触达频率，避免重复打扰。",
            "完成缴存，进入长期服务": "进入年度缴存提醒与账户服务队列，不纳入短期唤醒名单。",
        }
        feedback_status = st.radio(
            "模拟触达结果（选择客户本次的反馈，系统据此给出下一步动作）",
            list(next_actions.keys()),
            horizontal=True,
            key="feedback_status",
        )
        st.info(f"**{feedback_customer}** 的下一步动作：{next_actions[feedback_status]}")
        if st.button("写入模拟闭环记录", use_container_width=True):
            st.session_state.batch_feedback[feedback_customer] = {
                "触达结果": feedback_status,
                "下一步": next_actions[feedback_status],
            }
            st.success("模拟回填已保存。继续切换页面或调整选项，记录不会消失。")
        if st.session_state.batch_feedback:
            st.markdown("##### 已回填记录")
            feedback_rows = [{"客户": name, **record} for name, record in st.session_state.batch_feedback.items()]
            st.dataframe(pd.DataFrame(feedback_rows), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### 试点效果记录口径")
        st.info("本页展示候选策略、合规审核和任务流转的顺序。未展示未经试点验证的节省时长或效率倍数。")
        st.markdown("- 试点记录：单客任务准备时长、有效触达率、人工审核时长、合规拦截情况。")
        st.markdown("- 对比原则：与现行合规流程在同期、同类客群、同一统计口径下比较。")
        st.markdown("- 决策前提：数据可复算、合规可审计、客户体验不受损。")

# ============================================================
# 页面5：A/B试验设计
# ============================================================
elif page == "📈 A/B试验台":
    st.markdown("## A/B试点设计（原型）")
    st.caption("用于说明灰度试点如何分组、记录结果并做合规复盘。页面不展示未经验证的转化数据。")
    st.warning("目前为原型设计，尚无真实试点结果。样本范围、分组方式、观察周期及统计口径需由试点分行、合规与数据团队共同确认。")

    st.markdown("### 试点怎么跑")
    flow_cols = st.columns(4)
    flow_items = [
        ("01", "确定样本", "完成适当性评估并同意触达的客户，才进入试点池。"),
        ("02", "分成两组", "试验组使用本系统流程，对照组沿用现行合规流程。"),
        ("03", "统一记录", "按同一周期记录触达、审核、服务和投诉等数据。"),
        ("04", "复盘决策", "合规、体验和业务指标共同达到要求后，才考虑扩围。"),
    ]
    for column, (number, title, copy) in zip(flow_cols, flow_items):
        with column:
            st.markdown(f'<div class="stage-card"><div class="stage-no">STEP {number}</div><div class="stage-title">{title}</div><div class="stage-copy">{copy}</div></div>', unsafe_allow_html=True)

    st.markdown("### 试点状态")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("样本池", "待试点确认", "适当性通过客群")
    with c2:
        st.metric("分组方式", "待审批", "试验组 / 对照组")
    with c3:
        st.metric("结果记录", "待真实数据", "统一口径复盘")

    st.markdown("### 试点对比框架")
    trial_rows = [
        {"维度": "资金沉淀", "核心指标": "合规前提下的缴存完成率", "必备前提": "同期、同类客群、统一统计口径"},
        {"维度": "运营效率", "核心指标": "单客任务准备时长与有效触达率", "必备前提": "从任务日志自动取数"},
        {"维度": "合规质量", "核心指标": "拦截率、人工复核通过率、客户投诉", "必备前提": "合规部门审核与台账留痕"},
        {"维度": "客户体验", "核心指标": "触达接受度与咨询解决率", "必备前提": "自愿反馈与服务录音抽检"},
    ]
    st.dataframe(trial_rows, use_container_width=True, hide_index=True)

    st.markdown("### 分组与决策门")
    for step in [
        "1. 合规审批客群池：仅纳入完成适当性评估且已同意触达的客户。",
        "2. 试验组：使用分型、合规候选话术与留痕闭环。",
        "3. 对照组：继续使用现行合规运营流程，不降低服务标准。",
        "4. 复盘与决策：固化统计口径，合规、客体验与业务效果同时达标后才考虑扩围。",
    ]:
        st.markdown(f"- {step}")

    st.info("试点数据可复算、合规审核通过且客户体验不受影响后，才考虑进入下一阶段。")

# 页面6：客户库
# 页面6：客户库
# ============================================================
elif page == "客户库":
    st.markdown("## 客户库")
    st.caption("200位模拟、脱敏客户画像，仅用于原型演示。")
    st.divider()

    st.markdown("### 客户360视图（模拟）")
    library_options = [f"{c['name']}（{c['id']}）" for c in pool[:50]]
    library_customer = st.selectbox("选择一位客户查看摘要", library_options, key="library_customer")
    detail_customer = pool[library_options.index(library_customer)]
    detail_result = rule_based_classify(detail_customer)[0]
    d1, d2, d3, d4 = st.columns(4)
    with d1: st.metric("账户状态", detail_customer["status"])
    with d2: st.metric("沉睡时长", f"{detail_customer['days_inactive']} 天")
    with d3: st.metric("休眠原因", detail_result[0])
    with d4: st.metric("风险偏好", detail_customer["risk"])
    st.caption(f"最近行为：{detail_customer['behavior']}。本摘要来自模拟、脱敏客户画像，仅展示客户查询与服务准备结构。")

    # 筛选
    f1, f2, f3 = st.columns(3)
    with f1:
        age_filter = st.selectbox("年龄筛选", ["全部", "30岁以下", "30-45岁", "45-60岁", "60岁以上"])
    with f2:
        type_filter = st.selectbox("分型筛选", ["全部", "不会投", "不敢投", "懒得投"])
    with f3:
        status_filter = st.selectbox("账户状态", ["全部", "已开户未缴存", "已缴存未满额"])

    # 筛选逻辑
    filtered = pool
    if age_filter == "30岁以下":
        filtered = [c for c in filtered if c["age"] < 30]
    elif age_filter == "30-45岁":
        filtered = [c for c in filtered if 30 <= c["age"] < 45]
    elif age_filter == "45-60岁":
        filtered = [c for c in filtered if 45 <= c["age"] < 60]
    elif age_filter == "60岁以上":
        filtered = [c for c in filtered if c["age"] >= 60]

    if type_filter != "全部":
        filtered = [c for c in filtered if rule_based_classify(c)[0][0] == type_filter]

    if status_filter != "全部":
        filtered = [c for c in filtered if c["status"] == status_filter]

    st.caption(f"共 {len(filtered)} 位客户")

    # 表格展示
    table_data = []
    for c in filtered[:100]:
        r = rule_based_classify(c)
        table_data.append({
            "客户ID": c["id"],
            "姓名": c["name"],
            "年龄": c["age"],
            "月薪": c["salary"],
            "风险偏好": c["risk"],
            "持有": c["holdings"],
            "分型": r[0][0],
            "置信度": f"{r[0][1]:.0%}",
            "沉睡天数": c["days_inactive"],
            "最近联系": c["last_contact"],
        })
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, height=400)

    st.caption("本页展示客户数据管理结构。正式部署应对接行内CRM，并遵循数据授权和最小必要原则。")

# ============================================================
# 页面5：合规中心
# ============================================================
elif page == "🔒 合规中心":
    st.markdown("## 合规管控")
    st.caption("禁用词拦截、人工审核和版本留痕。")
    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:1.5rem;">🛡️</div>
            <h4 style="color:#262626;margin:0.5rem 0;">第一层 · 词库拦截</h4>
            <p style="color:#6b7280;font-size:0.85rem;">禁用语词库自动扫描<br>「保本」「稳赚」「无风险」<br>「保证收益」「最低收益」</p>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:1.5rem;">🤖</div>
            <h4 style="color:#262626;margin:0.5rem 0;">第二层 · AI自检</h4>
            <p style="color:#6b7280;font-size:0.85rem;">生成内容自动合规审查<br>识别暗示性收益承诺<br>检测夸大表述</p>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:1.5rem;">👤</div>
            <h4 style="color:#262626;margin:0.5rem 0;">第三层 · 人工抽检</h4>
            <p style="color:#6b7280;font-size:0.85rem;">合规人员定期抽检话术样本<br>分级锁定确保红线不可编辑<br>三版本留痕可追溯</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # 话术即时合规检查（复用词库逻辑，现场演示拦截效果）
    st.markdown("### 话术合规检查")
    st.caption("输入一段候选话术，系统检查禁用词和风险提示是否缺失。可输入“保本”查看拦截示例。")
    check_text = st.text_area("话术文本（演示）", height=100,
                              value="尊敬的客户，本产品保本稳赚，收益绝对有保障，推荐您立即缴存。",
                              help="此处为红线识别演示文本，不会发送给任何客户。")
    if st.button("🔍 检查合规性", type="primary", use_container_width=True):
        if not check_text.strip():
            st.warning("请输入话术文本")
        else:
            HARD_WORDS = ["保本", "稳赚", "稳赚不赔", "无风险", "零风险", "保证收益",
                          "承诺收益", "绝对收益", "刚性兑付", "本金无忧", "收益有保障",
                          "包赚", "稳赢"]
            SOFT_WORDS = ["最高收益", "最佳", "最划算", "第一", "首选", "坐享", "躺赚",
                          "高回报", "错过再等一年", "最后机会", "一定", "必然"]
            risk_triggers = ["推荐", "建议购买", "买入", "定投", "申购"]
            hints = ["不构成投资建议", "风险提示", "过往业绩不代表", "谨慎选择"]

            hard_hits = [w for w in HARD_WORDS if w in check_text]
            soft_hits = [w for w in SOFT_WORDS if w in check_text]
            missing_hint = (any(t in check_text for t in risk_triggers)
                            and not any(h in check_text for h in hints))

            if hard_hits:
                st.markdown(
                    f'<div class="check-alert" style="padding:1rem;font-size:1rem;">'
                    f'⛔ <strong>已拦截</strong>：命中 {len(hard_hits)} 个红线词（'
                    f"{'、'.join(f'「{w}」' for w in hard_hits)}）——收益承诺类表述，"
                    f'<strong>不得进入客户触达</strong>，请删除后重新检查。</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown('<div class="check-pass" style="padding:1rem;font-size:1rem;">'
                            '✅ 未命中禁用语，话术可通过</div>', unsafe_allow_html=True)
            if soft_hits:
                st.markdown(
                    f'<div class="check-warn" style="padding:0.9rem;">'
                    f'⚠️ 软提示：命中夸大/模糊表述（{"、".join(f"「{w}」" for w in soft_hits)}），'
                    f'建议人工确认后使用</div>', unsafe_allow_html=True)
            if missing_hint:
                st.markdown('<div class="check-warn" style="padding:0.9rem;">'
                            '⚠️ 软提示：含推荐/引导类表述但缺少「不构成投资建议」等风险提示语句</div>',
                            unsafe_allow_html=True)

    st.divider()

    st.markdown("### 字段锁定机制")
    st.markdown("""
    <div style="display:flex;gap:1rem;">
        <div class="locked-card" style="flex:1;">
            <strong style="font-size:1rem;">强制锁定区（不可编辑）</strong>
            <p style="font-size:0.85rem;margin-top:0.5rem;">风险提示语句<br>产品匹配依据<br>65岁以上保护声明</p>
        </div>
        <div class="editable-card" style="flex:1;">
            <strong style="font-size:1rem;">可编辑区（经办人员可修改）</strong>
            <p style="font-size:0.85rem;margin-top:0.5rem;">问候语<br>预约时间<br>非营销核心的语气调整</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown("### 话术留痕记录（模拟）")
    for i in range(5):
        c = pool[i]
        st.markdown(f"""
        <div class="card" style="padding:0.6rem 1rem;margin:0.3rem 0;">
            <span style="color:#6b7280;font-size:0.85rem;">2026-08-0{5-i} 10:2{i}  |  {c['name']}  |  AI候选版 经办修改版 待发送（模拟留痕样例）</span>
        </div>
        """, unsafe_allow_html=True)
    st.caption("本页展示三版本留痕的字段结构：候选版、经办修改版与发送版。正式部署须经合规审核并按行内制度归档。")

# ============================================================
# 页面6：税优计算器
# ============================================================
else:
    st.markdown("## 客户沟通辅助：税优测算")
    st.caption("用于沟通时展示简化的税优和账户情景测算。")
    st.divider()

    # 参数输入区（页面顶部，路演时一目了然）
    st.markdown("#### 测算参数")
    p1, p2 = st.columns(2)
    with p1:
        age = st.slider("客户年龄", 22, 60, 32)
    with p2:
        salary = st.slider("客户月薪（税前）", 5000, 100000, 25000, 1000)
    st.warning("本页为简化情景测算：未纳入社保、公积金、专项附加扣除、产品费用及市场波动等个人差异因素；结果不构成税务结论、产品建议或收益承诺。")
    st.divider()

    # 个税计算
    TAX_BRACKETS = [
        (0, 36000, 0.03), (36000, 144000, 0.10),
        (144000, 300000, 0.20), (300000, 420000, 0.25),
        (420000, 660000, 0.30), (660000, 960000, 0.35),
        (960000, float("inf"), 0.45),
    ]
    LIMIT, DEDUCTION = 12000, 5000
    SCENARIO_RATE_A, SCENARIO_RATE_B = 0.04, 0.01

    def calc_tax(taxable):
        if taxable <= 0: return 0
        tax, prev = 0, 0
        for low, high, rate in TAX_BRACKETS:
            w = min(taxable, high) - prev
            if w <= 0: break
            tax += w * rate; prev = high
            if prev >= taxable: break
        return tax

    def compound(annual, years, rate):
        total = 0.0
        for _ in range(years): total = (total + annual) * (1 + rate)
        return total

    annual = salary * 12
    # 用户自主选择用于情景演算的年缴存额，系统不提供缴存建议。
    default_deposit = min(LIMIT, max(1000, round(annual * 0.10 / 100) * 100))
    deposit = st.slider("用于情景演算的年缴存额（元）", 1000, LIMIT, int(default_deposit), 1000)
    taxable_before = max(0, annual - DEDUCTION * 12)
    tax_before = calc_tax(taxable_before)
    taxable_after = max(0, taxable_before - deposit)
    tax_after = calc_tax(taxable_after)
    saved = tax_before - tax_after
    yrs = max(1, 60 - age)

    scenario_a_fv = compound(deposit, yrs, SCENARIO_RATE_A)
    scenario_b_fv = compound(deposit, yrs, SCENARIO_RATE_B)
    diff = scenario_a_fv - scenario_b_fv
    gap = scenario_a_fv - compound(deposit, yrs - 5, SCENARIO_RATE_A) if yrs > 5 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="card-blue"><div style="font-size:0.85rem;opacity:0.85;">简化退税差额</div><div class="big-num">¥{saved:,.0f}</div><div style="font-size:0.8rem;opacity:0.8;">按当前情景缴存额</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="card" style="text-align:center;"><div style="font-size:0.85rem;color:#6b7280;">{yrs}年后退休账户</div><div class="big-num" style="color:#1e6b3a;">¥{scenario_a_fv:,.0f}</div><div style="font-size:0.8rem;color:#6b7280;">情景A：年化4%假设 · 非收益承诺</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="card" style="text-align:center;"><div style="font-size:0.85rem;color:#6b7280;">两种情景账户差额</div><div class="big-num" style="color:#9d0009;">¥{diff:,.0f}</div><div style="font-size:0.8rem;color:#6b7280;">仅比较两种统一假设</div></div>', unsafe_allow_html=True)

    st.divider()
    l, r = st.columns(2)
    with l:
        st.markdown("#### 账户情景对比")
        ys = list(range(1, yrs + 1))
        chart_data = {"年": ys,
                      "情景A（年化4%）": [compound(deposit, y, SCENARIO_RATE_A) for y in ys],
                      "情景B（年化1%）": [compound(deposit, y, SCENARIO_RATE_B) for y in ys]}
        chart_long = pd.DataFrame({
            "年": ys + ys,
            "情景": ["情景A（年化4%假设）"] * len(ys) + ["情景B（年化1%假设）"] * len(ys),
            "账户规模": chart_data["情景A（年化4%）"] + chart_data["情景B（年化1%）"],
        })
        tax_chart = (
            alt.Chart(chart_long)
            .mark_line(strokeWidth=3, point=alt.OverlayMarkDef(filled=True, size=35))
            .encode(
                x=alt.X("年:Q", title="测算年数", axis=alt.Axis(labelColor="#262626", titleColor="#4b5563", grid=False)),
                y=alt.Y("账户规模:Q", title="情景账户规模（元）", axis=alt.Axis(labelColor="#262626", titleColor="#4b5563", gridColor="#e5e5e5")),
                color=alt.Color("情景:N", scale=alt.Scale(domain=["情景A（年化4%假设）", "情景B（年化1%假设）"], range=["#c7000b", "#6b7280"]), legend=alt.Legend(title=None, labelColor="#262626")),
                tooltip=[alt.Tooltip("年:Q"), alt.Tooltip("情景:N"), alt.Tooltip("账户规模:Q", format=",.0f")],
            )
            .properties(height=285)
        )
        st.altair_chart(tax_chart, use_container_width=True)
    with r:
        st.markdown("#### 开始时间情景对比")
        if yrs > 5:
            st.markdown(f"""
            <div style="background:#fff7f5;border:1px solid #f0c8cb;border-left:4px solid #c7000b;border-radius:3px;padding:1.2rem;text-align:center;color:#7c1d24;">
                <div style="font-size:0.9rem;">如果 {age+5} 岁才开始……</div>
                <div class="big-num" style="margin:0.3rem 0;">-¥{gap:,.0f}</div>
                <div style="font-size:0.8rem;">{age}岁开始→¥{scenario_a_fv:,.0f}<br>{age+5}岁开始→¥{compound(deposit, yrs-5, SCENARIO_RATE_A):,.0f}</div>
                <div style="font-size:0.85rem;font-weight:600;margin-top:0.5rem;">💡 同一假设下，开始时点不同会形成不同账户规模</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info(f"距退休仅{yrs}年。以上为统一假设下的情景演算，不代表实际账户结果。")

    st.divider()
    st.caption("⚠️ 本页仅用于沟通时的简化情景演算；实际税务处理以税务机关核定、实际账户规则及产品表现为准。")

# ============================================================
# 页脚
# ============================================================
st.divider()
st.markdown("""
<div style="text-align:center;color:#6b7280;font-size:0.8rem;">
    工银智养仓 · B端运营工作台 Demo v3.0<br>
    吕滢滢 | 广东金融学院 · 金融科技 | 第17届工行杯参赛作品<br>
    ⚠️ 本Demo仅用于路演演示，不构成投资建议
</div>
""", unsafe_allow_html=True)


