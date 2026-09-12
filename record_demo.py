# -*- coding: utf-8 -*-
"""工银智养仓 · 原型演示视频自动录制
====================================================
Playwright 驱动 Streamlit demo（http://localhost:8501），
按「原型演示视频-录屏脚本.txt」的 6 个场景编排操作节奏，
用 Playwright 内置视频录制输出 1920x1080 webm，
再经 imageio-ffmpeg 自带 ffmpeg 转码为 mp4。

用法：
  1. 先启动 demo：python -m streamlit run app.py --server.headless true
  2. python record_demo.py
  3. 输出：桌面「工银智养仓-原型演示.mp4」（约 2分30秒）
"""
import os
from playwright.sync_api import sync_playwright
from imageio_ffmpeg import get_ffmpeg_exe

URL = "http://localhost:8501"
OUT_MP4 = r"C:\Users\雨濛濛\Desktop\工银智养仓-原型演示.mp4"
OUT_WEBM = OUT_MP4.replace(".mp4", ".webm")

NAV = {
    "看板": "📊 运营看板",
    "分型": "🔍 客户分型",
    "策略": "🤖 AI策略工场",
    "批量": "⚡ 批量激活任务",
    "AB": "📈 A/B效果对比",
    "客户库": "🗂️ 客户库",
    "合规": "🔒 合规中心",
    "税优": "🧮 税优计算器",
}

T = 9000  # 超时兜底 ms


def goto_nav(page, key):
    """点击侧边栏导航（精确匹配 radio 标签）"""
    page.get_by_text(NAV[key], exact=True).first.click(timeout=T)
    page.wait_for_timeout(3500)  # 等 Streamlit rerun


def set_slider(page, idx, value):
    """设置 Streamlit slider 的值（原生 setter + 事件派发，触发 React 更新）"""
    slider = page.locator('[data-testid="stSlider"] input[type="range"]').nth(idx)
    slider.evaluate("""(el, v) => {
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, String(v));
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""", value)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=r"C:\Users\雨濛濛\Desktop",  # 1.62 起必须显式指定目录
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)  # Streamlit 首屏渲染

        # ===== 场景0：运营看板（0-10s）=====
        # 鼠标缓慢划过「休眠成因分布」图表
        page.mouse.move(1050, 640); page.wait_for_timeout(1200)
        page.mouse.move(1180, 600); page.wait_for_timeout(1200)
        page.mouse.move(1300, 640); page.wait_for_timeout(1200)
        page.mouse.move(1050, 480); page.wait_for_timeout(6400)

        # ===== 场景1：分型 → 策略（10-50s）=====
        goto_nav(page, "分型")
        page.wait_for_timeout(3000)
        # 停留展示双引擎分型详情（规则初筛+LLM精判、置信度）
        page.mouse.move(1300, 700); page.wait_for_timeout(7000)
        goto_nav(page, "策略")
        page.get_by_role("button", name="🚀 生成AI激活策略").click(timeout=T)
        page.wait_for_timeout(8000)  # 生成中 + 渲染策略
        # 滚动展示策略全文 + 合规状态 + 多渠道输出
        page.mouse.wheel(0, 500); page.wait_for_timeout(6000)
        page.mouse.wheel(0, 300); page.wait_for_timeout(4000)
        page.mouse.wheel(0, -700); page.wait_for_timeout(3000)

        # ===== 场景2：合规拦截（50-80s）=====
        goto_nav(page, "合规")
        page.mouse.wheel(0, 500); page.wait_for_timeout(2000)
        ta = page.get_by_label("话术文本（演示）")
        ta.fill("尊敬的客户，本产品保本稳赚，收益绝对有保障，推荐您立即缴存！")
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="🔍 检查合规性").click(timeout=T)
        page.wait_for_timeout(10000)  # 停留展示红色拦截
        # 删除违规词 → 重查通过
        ta.fill("尊敬的客户，个人养老金账户资金封闭管理，缴存可享税优政策，不构成投资建议。")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="🔍 检查合规性").click(timeout=T)
        page.wait_for_timeout(5000)

        # ===== 场景3：留痕审计（80-105s）=====
        page.mouse.wheel(0, 700); page.wait_for_timeout(4000)
        page.mouse.wheel(0, -200); page.wait_for_timeout(3000)
        page.mouse.wheel(0, 400); page.wait_for_timeout(9000)

        # ===== 场景4：AB效果 + 税优（105-140s）=====
        goto_nav(page, "AB")
        page.mouse.wheel(0, 300); page.wait_for_timeout(5000)
        page.mouse.wheel(0, 400); page.wait_for_timeout(5000)
        goto_nav(page, "税优")
        # 调整月薪滑块（第2个，默认25000 → 60000 展示税优变化）
        set_slider(page, 1, 60000)
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, 400); page.wait_for_timeout(6000)
        page.mouse.wheel(0, -300); page.wait_for_timeout(3000)

        # ===== 场景5：收尾（140-155s）=====
        goto_nav(page, "看板")
        page.mouse.move(700, 480); page.wait_for_timeout(9000)

        # ---- 保存视频 ----
        video = page.video
        ctx.close()  # 先关闭上下文，视频才完整
        video.save_as(OUT_WEBM)
        print("已录制 webm:", OUT_WEBM)
        browser.close()

    # 转码 mp4（imageio-ffmpeg 自带静态 ffmpeg）
    ffmpeg = get_ffmpeg_exe()
    os.system(f'"{ffmpeg}" -y -i "{OUT_WEBM}" -c:v libx264 -pix_fmt yuv420p -crf 20 "{OUT_MP4}"')
    print("已转码 mp4:", OUT_MP4)
    print("完成！可删除 webm 中间文件（如需）")


if __name__ == "__main__":
    main()
