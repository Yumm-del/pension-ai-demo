"""税额、证据边界和任务状态的回归测试，不调用外部模型或真实渠道。"""
import unittest
from copy import deepcopy
from datetime import date, timedelta

from operations import (
    LOCKED_TEXT, TYPES, approve, calc_tax, check_content, classify, contact_block,
    edit_greeting, new_task, save_feedback, send_simulated, tax_saving,
)


def customer():
    return {"id": "C1000", "name": "陈女士", "age": 32, "salary": 25000,
            "knowledge": 4, "status": "已开户未缴存", "contact_allowed": True}


class TaxTests(unittest.TestCase):
    def test_same_bracket(self):
        self.assertEqual(tax_saving(240000, 12000), 2400)

    def test_cross_bracket(self):
        # 4,000元落在10%档，8,000元落在3%档，减税应为640而不是1200。
        self.assertEqual(tax_saving(40000, 12000), 640)

    def test_low_bracket_still_has_current_saving(self):
        self.assertEqual(tax_saving(36000, 12000), 360)

    def test_zero_and_deduction_cap(self):
        self.assertEqual(tax_saving(0, 12000), 0)
        self.assertEqual(tax_saving(5000, 12000), 150)
        self.assertEqual(tax_saving(240000, 50000), 2400)
        self.assertEqual(tax_saving(240000, 0), 0)

    def test_annual_bracket_boundaries(self):
        for taxable, expected in [(36000, 1080), (144000, 11880), (300000, 43080),
                                  (420000, 73080), (660000, 145080), (960000, 250080)]:
            self.assertEqual(calc_tax(taxable), expected)


class ClassificationTests(unittest.TestCase):
    def test_demographics_do_not_invent_motive(self):
        c = customer()
        for age in [22, 67]:
            for salary in [5000, 100000]:
                c.update(age=age, salary=salary)
                self.assertEqual(classify(c)[0], "原因待确认")

    def test_cash_constraint_overrides_knowledge(self):
        c = customer()
        c.update(knowledge=1, stated_concern="当前现金流受限", concern_evidence="近期还贷")
        self.assertEqual(classify(c)[0], "当前现金流受限")

    def test_pending_and_confirmed_evidence(self):
        c = customer()
        c["knowledge"] = 1
        self.assertEqual(classify(c)[1], .8)
        c.update(confirmed_type="资金锁定顾虑", confirmed_reason="半年内购房")
        self.assertEqual(classify(c)[:2], ("资金锁定顾虑", 1.0))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.customer = customer()
        self.task = new_task(self.customer, 1)

    def send(self):
        approve(self.task, "审核员A")
        send_simulated(self.task, self.customer)

    def test_unapproved_send_is_blocked(self):
        with self.assertRaises(ValueError):
            send_simulated(self.task, self.customer)
        self.assertIsNone(self.task["sent"])

    def test_edit_revokes_approval_and_retains_original(self):
        original = self.task["original"]
        approve(self.task, "审核员A")
        edit_greeting(self.task, "陈女士，下午好！")
        self.assertIsNone(self.task["approval"])
        self.assertEqual(self.task["original"], original)
        with self.assertRaises(ValueError):
            send_simulated(self.task, self.customer)
        self.send()
        self.assertIn("下午好", self.task["sent"]["text"])

    def test_text_tampering_is_detected(self):
        approve(self.task, "审核员A")
        self.task["locked"] = "被改写"
        with self.assertRaises(ValueError):
            send_simulated(self.task, self.customer)

    def test_prohibited_text_blocks_review(self):
        edit_greeting(self.task, "保 本稳赚，请立即缴存")
        with self.assertRaises(ValueError):
            approve(self.task, "审核员A")
        self.assertTrue(check_content("可随时取出" + LOCKED_TEXT))

    def test_sent_records_cannot_be_edited_or_resent(self):
        self.send()
        frozen = deepcopy(self.task["sent"])
        with self.assertRaises(ValueError):
            edit_greeting(self.task, "修改")
        with self.assertRaises(ValueError):
            send_simulated(self.task, self.customer)
        self.assertEqual(frozen, self.task["sent"])

    def test_feedback_refusal_blocks_existing_and_new_tasks(self):
        other = new_task(self.customer, 2)
        approve(other, "审核员B")
        self.send()
        save_feedback(self.task, self.customer, "暂不参与", "当前现金流受限", "还贷压力大")
        self.assertTrue(contact_block(self.customer))
        with self.assertRaises(ValueError):
            new_task(self.customer, 3)
        with self.assertRaises(ValueError):
            send_simulated(other, self.customer)

    def test_feedback_corrects_profile_without_rewriting_snapshot(self):
        self.send()
        save_feedback(self.task, self.customer, "已联系", "资金锁定顾虑", "近期购房")
        self.assertEqual(classify(self.customer)[0], "资金锁定顾虑")
        self.assertEqual(self.task["type"], "原因待确认")
        self.assertNotIn("confirmed_type", self.task["customer_snapshot"])

    def test_followup_date_suppresses_contact(self):
        self.send()
        later = (date.today() + timedelta(days=7)).isoformat()
        save_feedback(self.task, self.customer, "希望稍后联系", "原因待确认", "约定下周", later)
        self.assertIn(later, contact_block(self.customer))

    def test_unsuccessful_call_cannot_invent_feedback(self):
        self.send()
        with self.assertRaises(ValueError):
            save_feedback(self.task, self.customer, "未接通", "资金锁定顾虑", "猜测")

    def test_feedback_requires_send_and_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            save_feedback(self.task, self.customer, "已联系", "原因待确认", "尚不清楚")
        self.send()
        save_feedback(self.task, self.customer, "已联系", "原因待确认", "尚不清楚")
        with self.assertRaises(ValueError):
            save_feedback(self.task, self.customer, "已完成缴存", "参与流程受阻", "已办理")

    def test_updated_profile_invalidates_prepared_task(self):
        approve(self.task, "审核员A")
        self.customer.update(confirmed_type="资金锁定顾虑", confirmed_reason="近期购房")
        with self.assertRaises(ValueError):
            send_simulated(self.task, self.customer)

    def test_senior_channels_all_include_protection(self):
        self.customer["age"] = 67
        for channel in ["企微", "短信", "APP推送", "电话"]:
            task = new_task(self.customer, 1, channel)
            self.assertIn("65岁", task["locked"])
            self.assertFalse(check_content(task["original"]))

    def test_every_type_generates_valid_template(self):
        for dtype in TYPES:
            self.customer["confirmed_type"] = dtype
            task = new_task(self.customer, 1)
            self.assertFalse(check_content(task["original"]))


if __name__ == "__main__":
    unittest.main()
