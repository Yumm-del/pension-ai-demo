"""工银智养仓 · B端运营工作台 v4.0；仅使用模拟客户与会话内任务。"""
import random
import streamlit as st
from workbench import (
    render_dashboard, render_classification, render_strategy, render_batch,
    render_library, render_compliance, render_tax,
)

st.set_page_config(page_title="工银智养仓 · B端运营工作台", page_icon="工", layout="wide")
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
            "contact_allowed": True,
        })
    # 精选情景是显式模拟证据，其他客户不按收入或年龄臆测动机。
    examples = [
        {"name": "陈女士", "age": 32, "stated_concern": "规则认知不足", "concern_evidence": "不清楚缴存和领取条件"},
        {"name": "张先生", "age": 38, "stated_concern": "资金锁定顾虑", "concern_evidence": "半年内计划购房，担心资金无法使用"},
        {"name": "王女士", "age": 35, "stated_concern": "当前现金流受限", "concern_evidence": "近期还贷和日常支出较多，暂不安排缴存"},
        {"name": "李先生", "age": 45, "stated_concern": "参与流程受阻", "concern_evidence": "想了解办理步骤，但找不到入口"},
        {"name": "赵女士", "age": 42, "knowledge": 4, "stated_concern": "", "concern_evidence": "尚未确认"},
        {"name": "刘女士", "age": 67, "stated_concern": "规则认知不足", "concern_evidence": "希望由客户经理逐项解释规则"},
    ]
    for customer, example in zip(pool, examples):
        customer.update(example)
        customer["days_inactive"] = 240
    return pool


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
[data-testid="stMetricLabel"] { color:#4b5563!important; }
/* 说明文字加深：原 #6b7280 在白底上偏浅，评委/客户经理反映看不清 */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color:#4b5563!important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color:#262626!important; }
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

if "_nav_target" in st.session_state:
    st.session_state["nav"] = st.session_state.pop("_nav_target")

with st.sidebar:
    st.markdown("## 工银智养仓")
    st.caption("个人养老金 · 客户经理工作台")
    st.divider()
    page = st.radio("功能导航", [
        "📊 运营看板", "🔍 客户分型", "🤖 AI策略工场", "批量任务",
        "📈 A/B试验台", "客户库", "🔒 合规中心", "🧮 税优计算器",
    ], key="nav", label_visibility="collapsed")
    st.divider()
    with st.expander("演示设置"):
        st.caption("LLM仅接收固定规则模板正文，不发送客户身份信息或回访记录。留空可完成全部流程。")
        api_key = st.text_input("DeepSeek API Key（可选）", type="password", key="demo_api_key")
        st.caption("生成的候选正文仍需规则预检和模拟人工审核。")
        st.checkbox("预置上一轮服务记录", value=True, key="seed_demo",
                    help="开启后工作台自带一批已服务客户，状态分布贴近真实工作日；"
                         "关闭则从空白开始，演示完整流程。")
    st.caption("模拟数据 · 未连接真实触达渠道")
    st.caption("任务在本次会话内保留，刷新或会话结束可能丢失；合规中心可导出留痕。")
    st.caption("吕滢滢 · 广东金融学院 · 第17届工行杯参赛作品")

if "customer_pool" not in st.session_state:
    random.seed(20260901)
    st.session_state.customer_pool = generate_customer_pool(200)
if "tasks" not in st.session_state:
    st.session_state.tasks = []
pool = st.session_state.customer_pool
tasks = st.session_state.tasks

# ============================================================
# 演示初始态：预置上一轮的服务记录
# ------------------------------------------------------------
# 目的：让看板的状态分布贴近真实工作日，而不是"200 户全部待联系"。
# 预置数据全部通过 operations 的真实接口生成（new_task → approve →
# send_simulated → save_feedback），字段与正常操作完全一致，非手工构造。
# 可通过侧边栏「演示设置」里的开关关闭，从空白状态演示完整流程。
# ============================================================
if "seeded" not in st.session_state:
    st.session_state.seeded = True
    if st.session_state.get("seed_demo", True) and len(tasks) == 0:
        from operations import new_task, approve, send_simulated, save_feedback

        # 上一轮已服务客户：(客户序号, 服务渠道, 回访结果, 客户反馈原因, 反馈依据)
        seeded = [
            (6,  "企微",   "已完成缴存",     "规则认知不足",   "客户理解规则后自主完成首次缴存"),
            (7,  "短信",   "已完成缴存",     "当前现金流受限", "先按小额缴存，后续视资金情况调整"),
            (8,  "企微",   "已联系",         "规则认知不足",   "客户表示已了解领取规则"),
            (9,  "电话",   "未接通",         "原因待确认",     "两次拨打未接通，转入低频队列"),
            (10, "APP推送", "希望稍后联系",   "资金锁定顾虑",   "客户希望在与家人商议后再决定"),
            (11, "企微",   "需要规则解释",   "规则认知不足",   "客户希望了解税收扣除的办理方式"),
            (12, "短信",   "暂不参与",       "资金锁定顾虑",   "客户明确表示暂不考虑长期锁定"),
            (13, "企微",   "已联系",         "原因待确认",     "客户暂未说明具体原因"),
        ]
        for idx, (ci, channel, outcome, ftype, freason) in enumerate(seeded):
            if ci >= len(pool):
                break
            c = pool[ci]
            c["contact_allowed"] = True
            t = new_task(c, idx + 1, channel)
            approve(t, "演示审核员")
            send_simulated(t, c)
            if outcome != "未接通" and outcome != "希望稍后联系":
                save_feedback(t, c, outcome, ftype, freason)
            elif outcome == "希望稍后联系":
                from datetime import date as _date, timedelta as _td
                save_feedback(t, c, outcome, ftype, freason,
                              (_date.today() + _td(days=7)).isoformat())
            tasks.append(t)

        # 另有 1 笔待人工审核、1 笔已发送待回访（演示"手上还有活"的状态）
        for ci, channel in [(14, "企微"), (15, "电话")]:
            if ci >= len(pool):
                break
            c = pool[ci]
            c["contact_allowed"] = True
            tasks.append(new_task(c, len(tasks) + 1, channel))
        if len(tasks) >= 2 and len(pool) > 15:
            # 倒数第二笔走完审核并发送（留在"待回访"）；最后一笔保持"待审核"
            approve(tasks[-2], "演示审核员")
            send_simulated(tasks[-2], pool[14])

if page == "📊 运营看板":
    render_dashboard(pool, tasks)
elif page == "🔍 客户分型":
    render_classification(pool, tasks)
elif page == "🤖 AI策略工场":
    render_strategy(pool, tasks, api_key)
elif page == "批量任务":
    render_batch(pool, tasks)
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


elif page == "客户库":
    render_library(pool, tasks)
elif page == "🔒 合规中心":
    render_compliance(tasks)
else:
    render_tax()

st.divider()
st.markdown(
    '<div style="background:#f2f4f7;border-left:3px solid #c7000b;padding:.7rem 1rem;'
    'border-radius:3px;color:#3f4652;font-size:.86rem;line-height:1.6;">'
    '<b>原型能力边界</b>：已实现规则分型、任务审核、模拟发送、回访留痕、税优简算；'
    '待接入 CRM、真实权限、生产归档与触达渠道。A/B 经营效果待真实试点验证。</div>',
    unsafe_allow_html=True)
