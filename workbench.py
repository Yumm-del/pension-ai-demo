"""客户经理工作台界面；每位客户用唯一 ID 关联任务与跨页选择。"""

from datetime import date, timedelta
import difflib
import json

import altair as alt
import pandas as pd
import streamlit as st

from operations import (
    ACTIONS, EVIDENCE_LEVELS, OUTCOMES, RULE_VERSION, TAX_SOURCE, TYPES,
    approve, calc_tax, check_content, classify, contact_block, edit_greeting,
    event, new_task, save_feedback, send_simulated, tax_saving, text_of,
)


def select_customer(pool, key):
    """将页面控件的选择同步到非控件状态，切页后不会因控件卸载丢失客户。"""
    ids = [c["id"] for c in pool]
    current = st.session_state.get("selected_customer_id", ids[0])
    if current not in ids:
        current = ids[0]
    st.session_state[key] = current
    lookup = {c["id"]: c for c in pool}
    selected = st.selectbox(
        "当前客户", ids, key=key,
        format_func=lambda cid: f"{cid} · {lookup[cid]['name']} · {lookup[cid]['age']}岁",
        on_change=lambda: st.session_state.update(selected_customer_id=st.session_state[key]),
    )
    st.session_state.selected_customer_id = selected
    return lookup[selected]


def go(page, cid):
    st.session_state.selected_customer_id = cid
    st.session_state._nav_target = page
    st.rerun()


def customer_tasks(tasks, cid):
    return [task for task in tasks if task["customer_id"] == cid]


def task_queue(customer, tasks):
    """拒绝/预约限制先于任务状态；每位客户在首页只占一行。"""
    if contact_block(customer):
        return "暂缓联系"
    own_tasks = customer_tasks(tasks, customer["id"])
    if any(t["status"] == "待回访" for t in own_tasks):
        return "待回访"
    if any(t["status"] in ("待审核", "已审核") for t in own_tasks):
        return "待审核/发送"
    if own_tasks:
        return "已回访"
    return "待联系"


def show_profile(customer):
    dtype, evidence, reason = classify(customer)
    left, right = st.columns([1, 1.35])
    with left:
        st.markdown("#### 客户档案")
        st.dataframe([
            {"字段": "客户编号", "值": customer["id"]},
            {"字段": "账户状态", "值": customer["status"]},
            {"字段": "年龄 / 风险偏好", "值": f"{customer['age']}岁 / {customer['risk']}"},
            {"字段": "最近行为", "值": customer["behavior"]},
            {"字段": "养老金未操作时长", "值": f"{customer['days_inactive']}天"},
            {"字段": "最近联系", "值": customer["last_contact"]},
            {"字段": "主动触达授权（模拟）", "值": "已同意" if customer["contact_allowed"] else "未同意/已拒绝"},
        ], hide_index=True, use_container_width=True)
    with right:
        st.markdown("#### 当前判断与下一步")
        st.info(f"**{dtype}** · {EVIDENCE_LEVELS[evidence]}")
        st.write(reason)
        st.write("**下一步：** " + (contact_block(customer) or ACTIONS[dtype]))
        st.caption(RULE_VERSION + "；证据状态不是概率，也不代表已验证准确率。")
        if customer["age"] >= 65:
            st.warning("特别服务提示：逐项解释规则、确认理解，本原型不生成产品推介内容。")


def render_dashboard(pool, tasks):
    st.markdown("## 今日工作台")
    st.caption("模拟客户 · 先处理任务，再查看运营分布。所有任务指标来自本次会话操作。")
    queues = {c["id"]: task_queue(c, tasks) for c in pool}
    columns = st.columns(4)
    for column, label in zip(columns, ["待联系", "待审核/发送", "待回访", "暂缓联系"]):
        column.metric(label, sum(value == label for value in queues.values()))

    st.markdown("### 待办清单")
    scope = st.radio("任务状态", ["待处理", "待联系", "待审核/发送", "待回访", "暂缓联系", "已回访", "全部"], horizontal=True)
    priority = {"待回访": 0, "待审核/发送": 1, "待联系": 2, "已回访": 3, "暂缓联系": 4}
    selected = sorted(pool, key=lambda c: (priority[queues[c["id"]]], -c["days_inactive"], c["id"]))
    if scope == "待处理":
        selected = [c for c in selected if queues[c["id"]] in ("待联系", "待审核/发送", "待回访")]
    elif scope != "全部":
        selected = [c for c in selected if queues[c["id"]] == scope]
    st.caption("排序：待回访 → 待审核/发送 → 待联系；同状态按未操作天数排序，不以收入推断转化潜力。")
    if not selected:
        st.info("当前筛选下没有任务。")
    for customer in selected[:8]:
        with st.container(border=True):
            summary, action = st.columns([4, 1])
            dtype = classify(customer)[0]
            summary.markdown(f"**{customer['id']} · {customer['name']}**　{queues[customer['id']]}　|　{dtype}")
            summary.write(contact_block(customer) or ACTIONS[dtype])
            summary.caption(f"最近联系：{customer['last_contact']} · 未操作 {customer['days_inactive']} 天")
            target = "🤖 AI策略工场" if customer_tasks(tasks, customer["id"]) else "🔍 客户分型"
            if action.button("处理任务 →", key=f"open_{customer['id']}", use_container_width=True):
                go(target, customer["id"])
    st.caption(f"当前筛选共 {len(selected)} 位，优先展示前8位；客户库可检索全部200位。")

    with st.expander("运营概览与分型分布"):
        dormant = [c for c in pool if c["days_inactive"] >= 180]
        a, b, c = st.columns(3)
        a.metric("模拟客户画像", len(pool))
        b.metric("180天未操作", len(dormant))
        c.metric("已模拟发送任务", sum(t["sent"] is not None for t in tasks))
        counts = pd.DataFrame({"原因": TYPES, "客户数": [sum(classify(c)[0] == dtype for c in dormant) for dtype in TYPES]})
        chart = alt.Chart(counts).mark_bar(color="#c7000b").encode(
            y=alt.Y("原因:N", sort=None, title=None), x=alt.X("客户数:Q"), tooltip=["原因", "客户数"])
        st.altair_chart(chart, use_container_width=True)
        st.caption("分布仅统计180天未操作客群；不再用静态折线或预设转化率充当本次操作结果。")


def render_classification(pool, tasks):
    st.markdown("## 客户原因与服务依据")
    customer = select_customer(pool, "classification_picker")
    show_profile(customer)
    with st.expander("为什么采用这条规则？"):
        st.write("明确反馈优先；缺少反馈时，低知识测评仅提示认知可能不足，其余进入原因待确认。")
        st.write("收入高、年龄小、浏览多或领取过奖励均不能证明客户有可缴存资金或缺乏行动意愿。")
        st.write("客户真实原因由回访复核；修正后看板、客户库与新生成话术同步使用当前证据。")
    if st.button("进入话术与回访 →", type="primary"):
        go("🤖 AI策略工场", customer["id"])


def render_history(task):
    """展示冻结原稿、实际编辑稿、模拟发送稿及不可覆盖的事件快照。"""
    with st.expander(f"{task['id']} · 三版本与时间线", expanded=False):
        st.caption(f"{task['customer_id']} · {task['channel']} · {task['source']} · {task['rule_version']}")
        for label, content in [("候选原稿", task["original"]), ("当前经办版", text_of(task)),
                               ("实际模拟发送版", task["sent"]["text"] if task["sent"] else "尚未模拟发送")]:
            st.markdown(f"**{label}**")
            st.text(content)
        difference = "\n".join(difflib.unified_diff(
            task["original"].splitlines(), text_of(task).splitlines(),
            fromfile="候选原稿", tofile="经办修改版", lineterm=""))
        if difference:
            st.code(difference, language="diff")
        st.dataframe([{"时间": e["时间"], "动作": e["动作"]} for e in task["history"]], hide_index=True, use_container_width=True)
        st.download_button("导出此任务完整记录", json.dumps(task, ensure_ascii=False, indent=2),
                           file_name=f"{task['id']}-simulation.json", mime="application/json", key=f"export_{task['id']}")


def render_task(task, customer):
    st.markdown(f"### {task['id']} · {task['status']} · {task['channel']}")
    st.caption(f"生成时原因：{task['type']} · 来源：{task['source']}")
    if not task["sent"]:
        # 只开放问候语；规则正文、风险提示在服务端保存，不信任浏览器提交的锁定字段。
        greeting = st.text_area("可编辑：称呼与问候语", value=task["greeting"], key=f"greeting_{task['id']}", height=80)
        st.text_area("规则正文与风险提示（锁定）", task["body"] + "\n" + task["locked"],
                     disabled=True, height=180, key=f"locked_{task['id']}")
        if st.button("保存修改并重新预检", key=f"edit_{task['id']}"):
            try:
                edit_greeting(task, greeting)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        unsaved = greeting.strip() != task["greeting"]
        if unsaved:
            st.warning("有未保存修改，保存后原审核将失效；当前不能审核或模拟发送。")
        issues = check_content(text_of(task))
        if issues:
            st.error("自动预检拦截：请按以下规则修正。")
            st.dataframe(issues, hide_index=True, use_container_width=True)
        else:
            st.success("自动规则预检通过；仍须人工核对内容与客户意愿。")
        st.caption("规则依据：R01收益承诺、R02领取限制、R03催促/推介、R04固定提示；均为原型预检规则，待行内审批。")
        blocked = contact_block(customer)
        stale = customer != task["customer_snapshot"]
        if blocked or stale:
            st.warning(blocked or "客户画像已更新，此任务不能发送，请重新生成并审核。")
        reviewer = st.text_input("模拟审核人", key=f"reviewer_{task['id']}", placeholder="如：演示审核员A")
        confirmed = st.checkbox("我已核对当前文本、客户反馈及服务边界（模拟审核）", key=f"review_confirm_{task['id']}")
        disabled = bool(issues or unsaved or blocked or stale)
        if st.button("确认人工审核（模拟）", disabled=disabled or not confirmed or not reviewer.strip(), key=f"approve_{task['id']}"):
            try:
                approve(task, reviewer)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if task["approval"]:
            st.caption(f"已由 {task['approval']['reviewer']} 于 {task['approval']['at']} 审核。")
        if st.button("模拟发送并进入回访", type="primary", disabled=disabled or not task["approval"], key=f"send_{task['id']}"):
            try:
                send_simulated(task, customer)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    elif not task["feedback"]:
        st.success("模拟发送已记录，未向任何真实客户发送消息。")
        st.markdown("#### 回访记录")
        outcome = st.selectbox("本次联系结果", OUTCOMES, key=f"outcome_{task['id']}")
        selected_type = st.selectbox("客户反馈的实际原因", TYPES, index=TYPES.index("原因待确认"), key=f"feedback_type_{task['id']}")
        reason = st.text_area("反馈依据（仅填写模拟情景）", key=f"reason_{task['id']}")
        next_date = None
        if outcome == "希望稍后联系":
            next_date = st.date_input("客户约定的下次联系日期", date.today() + timedelta(days=7),
                                      min_value=date.today() + timedelta(days=1), key=f"next_{task['id']}").isoformat()
        if st.button("保存回访并更新客户", type="primary", key=f"feedback_{task['id']}"):
            try:
                save_feedback(task, customer, outcome, selected_type, reason, next_date)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    else:
        st.success("回访已记录，客户画像与下一步已同步。")
        st.write(task["feedback"])
    render_history(task)


def render_strategy(pool, tasks, api_key):
    st.markdown("## 话术审核与回访")
    customer = select_customer(pool, "strategy_picker")
    dtype = classify(customer)[0]
    st.info(f"{dtype} · {contact_block(customer) or ACTIONS[dtype]}")
    channel = st.selectbox("本次服务渠道", ["企微", "短信", "APP推送", "电话"])
    st.caption("所有渠道包含完整领取限制和风险提示；短信可能需多段，不通过删除提示压缩字数。")
    blocked = contact_block(customer)
    if blocked:
        st.warning(blocked)
    if st.button("生成候选话术", disabled=bool(blocked), type="primary"):
        task = new_task(customer, len(tasks) + 1, channel)
        # 可选 LLM 仅改写已批准范围内的模板，不发送身份信息、薪资或客户回访自由文本。
        if api_key:
            try:
                from openai import OpenAI
                with st.spinner("正在整理候选话术……"):
                    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=20, max_retries=0)
                    response = client.chat.completions.create(
                        model="deepseek-chat", temperature=.1, max_tokens=250,
                        messages=[{"role": "system", "content": "仅将给定规则模板改写为清晰的中文服务话术。不得新增事实、数字、产品、收益承诺或缴存劝说。只输出正文。"},
                                  {"role": "user", "content": task["body"]}])
                    candidate = response.choices[0].message.content
                    if not candidate or not candidate.strip():
                        raise ValueError("空候选稿")
                    task["body"] = candidate.strip()
                    task["source"] = "LLM候选稿（待规则预检与人工审核）"
                    task["original"] = text_of(task)
                    event(task, "LLM形成候选原稿", 文本=task["original"])
            except Exception:
                task["source"] = "规则模板（LLM不可用，已回退）"
        tasks.append(task)
        st.session_state[f"task_picker_{customer['id']}"] = task["id"]
        st.rerun()
    own_tasks = customer_tasks(tasks, customer["id"])
    if own_tasks:
        task_id = st.selectbox("当前任务", [t["id"] for t in reversed(own_tasks)], key=f"task_picker_{customer['id']}")
        render_task(next(t for t in own_tasks if t["id"] == task_id), customer)
    else:
        st.info("尚无任务。生成候选稿后可演示锁定、审核、模拟发送与回访。")


def render_batch(pool, tasks):
    st.markdown("## 批量准备任务")
    candidates = [c for c in pool if c["days_inactive"] >= 180 and not contact_block(c)
                  and task_queue(c, tasks) == "待联系"]
    lookup = {c["id"]: c for c in candidates}
    ids = st.multiselect("选择客户（最多10位）", list(lookup),
                         format_func=lambda cid: f"{cid} · {lookup[cid]['name']} · {classify(lookup[cid])[0]}")
    st.caption("仅纳入180天未操作、已同意触达且没有在途任务的客户。批量只生成草稿，每条均需单独审核。")
    if st.button("批量生成待审核草稿", disabled=not ids or len(ids) > 10):
        for cid in ids:
            tasks.append(new_task(lookup[cid], len(tasks) + 1))
        st.rerun()
    if len(ids) > 10:
        st.warning("每批最多选择10位客户。")
    if tasks:
        st.dataframe([{"任务": t["id"], "客户ID": t["customer_id"], "客户": t["customer_name"],
                       "成因": t["type"], "状态": t["status"]} for t in tasks], hide_index=True, use_container_width=True)
        selected = st.selectbox("选择要处理的任务", [t["id"] for t in tasks])
        if st.button("进入单客审核与回访 →"):
            task = next(t for t in tasks if t["id"] == selected)
            st.session_state[f"task_picker_{task['customer_id']}"] = selected
            go("🤖 AI策略工场", task["customer_id"])


def render_library(pool, tasks):
    st.markdown("## 客户库")
    dtype = st.selectbox("原因筛选", ["全部"] + TYPES)
    query = st.text_input("搜索客户编号或姓名")
    filtered = [c for c in pool if (dtype == "全部" or classify(c)[0] == dtype)
                and (not query or query.strip() in c["id"] or query.strip() in c["name"])]
    st.caption(f"共 {len(filtered)} 位模拟客户")
    st.dataframe([{"客户ID": c["id"], "姓名": c["name"], "原因": classify(c)[0],
                   "证据状态": EVIDENCE_LEVELS[classify(c)[1]], "任务状态": task_queue(c, tasks),
                   "最近联系": c["last_contact"]} for c in filtered], hide_index=True, use_container_width=True)
    if filtered:
        customer = select_customer(filtered, "library_picker")
        show_profile(customer)
        if st.button("处理当前客户 →"):
            go("🤖 AI策略工场", customer["id"])


def render_compliance(tasks):
    st.markdown("## 合规与复盘")
    st.caption("规则预检、模拟人工审核与三版本记录已经接入任务流程；真实权限隔离与行内归档待接入。")
    text = st.text_area("独立话术预检（不发送）", "本产品保本稳赚，可随时取出，请立即缴存。")
    if st.button("检查候选文本"):
        issues = check_content(text)
        if issues:
            st.dataframe(issues, hide_index=True, use_container_width=True)
            st.error("预检拦截。命中记录为原型规则提示，仍需人工结合语境判断。")
        else:
            st.success("自动规则预检通过，待人工审核。")
    st.markdown("### 实际操作留痕（本次会话）")
    if not tasks:
        st.info("尚无操作记录。请先生成一个客户任务。")
    for task in reversed(tasks):
        render_history(task)
    st.markdown("### 可复用服务案例")
    completed = [t for t in tasks if t["feedback"]]
    if not completed:
        st.caption("回访后自动形成案例；不会用模拟缴存证明策略有效。")
    for task in completed:
        feedback = task["feedback"]
        with st.container(border=True):
            st.markdown(f"**{task['customer_id']} · {task['id']}**　{feedback['原分型']} → {feedback['复核分型']}")
            st.write(f"采取动作：{ACTIONS[task['type']]}；反馈：{feedback['结果']}。")
            st.write(f"反馈依据：{feedback['反馈依据']}；下一步：{feedback['下一步']}")
            st.caption("适用边界：仅供相似已确认顾虑的服务准备参考；单次反馈与模拟结果不构成因果证据。")
    if tasks:
        st.download_button("导出全部模拟任务记录", json.dumps(tasks, ensure_ascii=False, indent=2),
                           file_name="pension-simulation-audit.json", mime="application/json")


def render_tax():
    st.markdown("## 税优测算")
    st.caption("先算当年减税，再单独查看未来领取税与账户情景。")
    mode = st.radio("输入方式", ["年应纳税所得额", "月薪简算"], horizontal=True)
    if mode == "年应纳税所得额":
        taxable = st.number_input("扣除个人养老金前的年应纳税所得额（元）", min_value=0.0, value=240000.0, step=1000.0)
        st.caption("填写已扣除基本减除费用、社保公积金、专项附加扣除等后的年度金额；本页仅演示综合所得。")
    else:
        salary = st.number_input("税前月薪（元）", min_value=0.0, value=25000.0, step=1000.0)
        deductions = st.number_input("全年社保公积金、专项附加扣除等合计（元）", min_value=0.0, value=0.0, step=1000.0)
        taxable = max(0.0, salary * 12 - 60000 - deductions)
        st.caption(f"假设仅有12个月工资，扣除前年度应纳税所得额为 {taxable:,.2f} 元；未包含年终奖等情况。")
    deposit = st.slider("用于测算的年度缴存额（元）", 0, 12000, 12000, 1000)
    saved = tax_saving(taxable, deposit)
    a, b, c = st.columns(3)
    a.metric("当年预计减少税额", f"¥{saved:,.2f}")
    b.metric("扣除前年度税额", f"¥{calc_tax(taxable):,.2f}")
    c.metric("扣除后年度税额", f"¥{calc_tax(max(0, taxable - deposit)):,.2f}")
    st.info("计算方法：扣除前税额－扣除后税额。自动逐档计算；当年减税不减去未来领取时的3%税款。")
    st.markdown(f"政策依据：[财政部、税务总局公告2024年第21号]({TAX_SOURCE})。实际扣除与汇算结果以税务机关核定为准。")
    st.write("领取环节：按现行政策，领取金额单独按3%计税；未来税额取决于实际领取金额及届时政策，不能直接从当年节税额中扣除。")
    if saved == 0:
        st.warning("当前输入下没有当年减税额；不能据此判断客户是否适合参与，应结合资金安排与长期需要。")
    with st.expander("长期账户情景（可选，不代表收益预测）"):
        years = st.slider("测算年数（不等同于退休年龄）", 1, 40, 20)
        rate = st.slider("假设年化收益率（%）", -5.0, 8.0, 2.0, .5)
        balance = 0.0
        rows = []
        for year in range(1, years + 1):
            balance = (balance + deposit) * (1 + rate / 100)
            rows.append({"年": year, "账户规模": balance, "累计投入": deposit * year})
        st.line_chart(pd.DataFrame(rows).set_index("年"))
        st.caption("假设每年年初缴存，收益率固定；未计费用、波动、领取税或节税资金再投资。负收益情景下账户可能低于累计投入。")
