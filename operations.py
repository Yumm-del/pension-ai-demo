"""养老金原型业务规则：纯 Python，可独立测试，不连接真实客户或渠道。"""

from copy import deepcopy
from datetime import datetime, timezone, timedelta, date
import hashlib
import re


RULE_VERSION = "运营规则 v2.0 · 2026-09-13（演示）"
TAX_SOURCE = "https://fgk.chinatax.gov.cn/zcfgk/c102416/c5237110/content.html"
TYPES = ["规则认知不足", "资金锁定顾虑", "当前现金流受限", "参与流程受阻", "原因待确认"]
ACTIONS = {
    TYPES[0]: "提供规则解释，确认客户是否理解",
    TYPES[1]: "如实说明领取限制，暂缓缴存营销",
    TYPES[2]: "尊重资金安排，暂缓缴存营销",
    TYPES[3]: "按客户意愿提供操作协助",
    TYPES[4]: "先确认原因，不推断意愿或缴存能力",
}
EVIDENCE_LEVELS = {1.0: "客户反馈已记录", 0.8: "测评信号待复核", 0.0: "信息不足"}
OUTCOMES = ["已联系", "未接通", "希望稍后联系", "暂不参与", "需要规则解释", "已完成缴存"]
LOCKED_TEXT = (
    "个人养老金账户封闭运行，除法定情形外不得提前领取。"
    "本内容仅供规则解读，不构成投资建议，不涉及具体产品推荐。"
    "是否参与及缴存金额由客户根据资金安排自主决定。"
)
SENIOR_TEXT = "客户已满65岁：本原型仅提供规则解释与人工服务，不生成产品推介内容。"
BRACKETS = [(36000, .03), (144000, .10), (300000, .20), (420000, .25),
            (660000, .30), (960000, .35), (float("inf"), .45)]


def calc_tax(taxable):
    """输入年应纳税所得额，返回综合所得年度税额；逐档累进避免跨档误算。"""
    remaining = max(0.0, float(taxable))
    tax, previous = 0.0, 0
    for upper, rate in BRACKETS:
        width = min(remaining, upper - previous)
        tax += width * rate
        remaining -= width
        if remaining <= 0:
            break
        previous = upper
    return round(tax, 2)


def tax_saving(taxable, deposit):
    """输入扣除养老金前的年应纳税所得额与缴存额，返回当年减税，不扣未来领取税。"""
    deduction = min(12000.0, max(0.0, float(deposit)))
    return round(calc_tax(taxable) - calc_tax(max(0.0, taxable - deduction)), 2)


def classify(customer):
    """返回(成因、证据代码、依据)。仅使用明确反馈或知识测评，不从收入/年龄推断动机。"""
    confirmed = customer.get("confirmed_type")
    if confirmed in TYPES:
        return confirmed, 1.0, "人工复核记录：" + customer.get("confirmed_reason", "客户反馈")
    concern = customer.get("stated_concern", "")
    if concern in TYPES[:-1]:
        return concern, 1.0, "模拟客户主动反馈：" + customer.get("concern_evidence", "")
    if customer.get("knowledge", 3) <= 2:
        return TYPES[0], .8, "知识测评得分不高于2/5；原因仍需人工确认"
    return TYPES[-1], 0.0, "没有明确顾虑或操作求助记录；浏览、收入及年龄不足以判断原因"


def contact_block(customer):
    """返回不可新建/发送任务的原因；拒绝优先于其他信号，预约到期前不重复联系。"""
    if not customer.get("contact_allowed", False):
        return "客户未同意触达或已明确暂不参与，停止主动联系"
    if customer.get("status") == "已完成缴存（模拟回填）":
        return "已完成本轮缴存服务，不再进入唤醒队列"
    next_date = customer.get("next_contact_date")
    if next_date and next_date > date.today().isoformat():
        return f"按客户约定于 {next_date} 后联系"
    return ""


def candidate_body(customer, channel):
    """按已知成因生成服务候选稿；短渠道也保留固定风险提示，不展示未经核实的节税金额。"""
    dtype = classify(customer)[0]
    bodies = {
        TYPES[0]: "您可以先了解个人养老金的缴存、税收与领取规则；有疑问时可由客户经理解释。",
        TYPES[1]: "已记录您对资金锁定的顾虑，当前暂缓缴存营销。如您需要，可进一步解释领取条件。",
        TYPES[2]: "已记录您当前的资金安排，本次不推动缴存。后续是否继续了解由您决定。",
        TYPES[3]: "已记录您的操作求助，可由客户经理说明办理步骤；请勿提供密码或验证码。",
        TYPES[4]: "您是否愿意说明暂未参与的原因？也可以选择暂不沟通，我们会尊重您的决定。",
    }
    prefix = "【电话服务提纲】" if channel == "电话" else ""
    if customer.get("age", 0) >= 65:
        return prefix + "如您需要，可由客户经理逐项解释个人养老金规则，并确认您是否理解。"
    return prefix + bodies[dtype]


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def event(task, action, **details):
    task["history"].append({"时间": now(), "动作": action, **deepcopy(details)})


def text_of(task):
    return "\n".join([task["greeting"], task["body"], task["locked"]])


def digest(task):
    return hashlib.sha256(text_of(task).encode("utf-8")).hexdigest()


def check_content(text):
    """规则预检返回命中位置及依据；词库不能覆盖所有语义风险，通过后仍须人工审核。"""
    issues = []
    rules = {
        "R01 收益承诺预检": ["保本", "稳赚", "无风险", "零风险", "保证收益", "收益有保障", "包赚", "稳赚不赔"],
        "R02 领取限制预检": ["随时可取", "随存随取", "随时支取", "随时取出"],
        "R03 催促与产品推介预检": ["立即缴存", "尽快办理", "最后机会", "建议购买", "推荐购买", "买入", "申购"],
    }
    # 去掉字符间的空白，覆盖“保 本”“保\n本”等常见分隔写法。
    normalized = re.sub(r"\s+", "", text)
    for rule, words in rules.items():
        for word in words:
            if word in normalized:
                issues.append({"规则": rule, "命中": word, "处置": "修改后重新预检"})
    if "不构成投资建议" not in normalized:
        issues.append({"规则": "R04 固定提示", "命中": "缺少风险提示", "处置": "补充固定提示"})
    if "账户封闭运行" not in normalized:
        issues.append({"规则": "R04 固定提示", "命中": "缺少领取限制", "处置": "补充固定提示"})
    return issues


def new_task(customer, sequence, channel="企微"):
    """根据客户当前证据创建任务，冻结候选版和画像快照，后续更新不能改写原稿。"""
    blocked = contact_block(customer)
    if blocked:
        raise ValueError(blocked)
    dtype, _, reason = classify(customer)
    task = {
        "id": f"T{sequence:04d}", "customer_id": customer["id"],
        "customer_name": customer["name"], "channel": channel,
        "type": dtype, "reason": reason, "rule_version": RULE_VERSION,
        "customer_snapshot": deepcopy(customer), "created_at": now(),
        "greeting": f"{customer['name']}您好，", "body": candidate_body(customer, channel),
        "locked": LOCKED_TEXT + (SENIOR_TEXT if customer.get("age", 0) >= 65 else ""),
        "status": "待审核", "history": [], "approval": None,
        "sent": None, "feedback": None, "source": "规则模板",
    }
    task["original"] = text_of(task)
    event(task, "生成候选版", 文本=task["original"], 规则=RULE_VERSION)
    return task


def edit_greeting(task, greeting):
    """仅允许经办人修改问候语；任何修改撤销原审核，禁止修改已发送记录。"""
    if task["sent"]:
        raise ValueError("已模拟发送的任务不可修改，请新建任务")
    if not greeting.strip():
        raise ValueError("问候语不能为空")
    if task["greeting"] != greeting.strip():
        task["greeting"] = greeting.strip()
        task["approval"] = None
        task["status"] = "待审核"
        event(task, "保存经办修改版；原审核失效", 文本=text_of(task))


def approve(task, reviewer):
    """将人工审核绑定到确切文本指纹；词库通过不等于人工审核通过。"""
    if task["sent"]:
        raise ValueError("任务已模拟发送")
    if not reviewer.strip():
        raise ValueError("请填写模拟审核人")
    issues = check_content(text_of(task))
    if issues:
        raise ValueError("自动预检未通过，请修改命中内容")
    task["approval"] = {"reviewer": reviewer.strip(), "at": now(), "digest": digest(task)}
    task["status"] = "已审核"
    event(task, "人工审核通过（模拟）", **task["approval"])


def send_simulated(task, customer):
    """模拟发送前再次校验客户资格、当前画像与审核指纹；不调用任何外部发送接口。"""
    if task["sent"]:
        raise ValueError("任务已模拟发送，不得重复发送")
    if customer["id"] != task["customer_id"]:
        raise ValueError("客户不匹配")
    if contact_block(customer):
        raise ValueError(contact_block(customer))
    if customer != task["customer_snapshot"]:
        raise ValueError("画像已更新，请按当前证据重新生成任务并审核")
    approval = task["approval"]
    if not approval or approval["digest"] != digest(task) or check_content(text_of(task)):
        raise ValueError("当前内容未审核或已变更，请重新审核")
    task["sent"] = {"text": text_of(task), "at": now(), "channel": task["channel"],
                    "approval": deepcopy(approval)}
    task["status"] = "待回访"
    event(task, "模拟发送完成", **task["sent"])


def save_feedback(task, customer, outcome, confirmed_type, reason, next_date=None):
    """发送后记录一次回访；更新客户证据及联系限制，保留任务生成时的原分型。"""
    if not task["sent"] or task["feedback"]:
        raise ValueError("仅能对已模拟发送且未回填的任务记录一次结果")
    if customer["id"] != task["customer_id"] or outcome not in OUTCOMES:
        raise ValueError("客户或结果不匹配")
    if confirmed_type not in TYPES or not reason.strip():
        raise ValueError("请选择原因并填写反馈依据")
    if outcome == "未接通" and confirmed_type != "原因待确认":
        raise ValueError("未接通不能确认为客户真实原因")
    if outcome == "希望稍后联系" and (not next_date or next_date <= date.today().isoformat()):
        raise ValueError("请选择今天之后的约定联系日期")
    previous_type = classify(customer)[0]
    if outcome != "未接通":
        customer["confirmed_type"] = confirmed_type
        customer["confirmed_reason"] = reason.strip()
    if outcome == "暂不参与":
        customer["contact_allowed"] = False
    if outcome == "已完成缴存":
        customer["status"] = "已完成缴存（模拟回填）"
    if outcome in ("希望稍后联系", "未接通"):
        customer["next_contact_date"] = next_date if outcome == "希望稍后联系" else (
            date.today() + timedelta(days=7)).isoformat()
    customer["last_contact"] = "本次未接通" if outcome == "未接通" else "本次已联系（模拟）"
    next_action = contact_block(customer) or ACTIONS[classify(customer)[0]]
    task["feedback"] = {
        "结果": outcome, "原分型": previous_type, "复核分型": classify(customer)[0],
        "反馈依据": reason.strip(), "下一步": next_action, "时间": now(),
    }
    task["status"] = "已回访"
    event(task, "记录回访（模拟）", **task["feedback"])
