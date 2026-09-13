"""用 Streamlit 官方 AppTest 验证页面状态与跨页闭环，无需外部API。"""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()

    def assert_clean(self):
        self.assertEqual([e.message for e in self.app.exception], [])

    def nav(self, page):
        self.app.radio(key="nav").set_value(page).run()
        self.assert_clean()

    def test_all_pages(self):
        for page in ["📊 运营看板", "🔍 客户分型", "🤖 AI策略工场", "批量任务",
                     "📈 A/B试验台", "客户库", "🔒 合规中心", "🧮 税优计算器"]:
            self.nav(page)

    def test_complete_flow_and_customer_identity(self):
        self.nav("🔍 客户分型")
        self.app.selectbox(key="classification_picker").set_value("C1000").run()
        self.nav("🤖 AI策略工场")
        self.assertEqual(self.app.selectbox(key="strategy_picker").value, "C1000")
        next(b for b in self.app.button if b.label == "生成候选话术").click().run()
        self.assert_clean()
        self.assertTrue(self.app.button(key="send_T0001").disabled)
        self.app.text_input(key="reviewer_T0001").set_value("审核员A").run()
        self.app.checkbox(key="review_confirm_T0001").check().run()
        self.app.button(key="approve_T0001").click().run()
        self.assertFalse(self.app.button(key="send_T0001").disabled)

        # 保存编辑后原审核必须撤销，且原稿和选中客户不能丢失。
        self.app.text_area(key="greeting_T0001").set_value("陈女士，下午好！").run()
        self.assertTrue(self.app.button(key="send_T0001").disabled)
        self.app.button(key="edit_T0001").click().run()
        self.assertTrue(self.app.button(key="send_T0001").disabled)
        self.app.text_input(key="reviewer_T0001").set_value("审核员A").run()
        self.app.checkbox(key="review_confirm_T0001").check().run()
        self.app.button(key="approve_T0001").click().run()
        self.app.button(key="send_T0001").click().run()
        self.assert_clean()
        self.app.selectbox(key="outcome_T0001").set_value("暂不参与").run()
        self.app.selectbox(key="feedback_type_T0001").set_value("当前现金流受限").run()
        self.app.text_area(key="reason_T0001").set_value("模拟客户：近期还贷支出增加").run()
        self.app.button(key="feedback_T0001").click().run()
        self.assert_clean()
        self.assertTrue(next(b for b in self.app.button if b.label == "生成候选话术").disabled)
        tasks = self.app.session_state["tasks"]
        self.assertEqual(tasks[0]["status"], "已回访")
        self.assertIn("下午好", tasks[0]["sent"]["text"])
        self.assertNotIn("下午好", tasks[0]["original"])
        self.nav("客户库")
        self.assertEqual(self.app.selectbox(key="library_picker").value, "C1000")
        self.nav("🔒 合规中心")
        self.assertTrue(any("C1000" in m.value for m in self.app.markdown))

    def test_batch_creates_real_task_drafts(self):
        self.nav("批量任务")
        self.app.multiselect[0].set_value(["C1000", "C1001"]).run()
        next(b for b in self.app.button if b.label == "批量生成待审核草稿").click().run()
        self.assert_clean()
        self.assertEqual(len(self.app.session_state["tasks"]), 2)
        self.assertTrue(all(t["status"] == "待审核" for t in self.app.session_state["tasks"]))
        next(b for b in self.app.button if b.label == "进入单客审核与回访 →").click().run()
        self.assert_clean()
        self.assertEqual(self.app.selectbox(key="strategy_picker").value, "C1000")


if __name__ == "__main__":
    unittest.main()
