# -*- coding: utf-8 -*-
"""工银智养仓 · 原型演示视频自动录制 v2（平滑版）
====================================================
v2 相对 v1 的改进（解决"不够丝滑"）：
  1. 鼠标移动改为插值平滑移动（每步 ≤15px，人手感）
  2. 滚动改为分步平滑滚动（每步 60px + 间隔，无跳跃）
  3. 每次操作后等待 Streamlit rerun 完成（spinner 消失）再继续，
     避免视频里出现页面半加载/闪烁
  4. 转码提高码率（crf 16），UI 文本不再被压缩糊掉

用法：
  1. 先启动 demo：python -m streamlit run app.py --server.headless true
  2. python record_demo_v2.py
  3. 输出：桌面「工银智养仓-原型演示.mp4」（约 2分30秒）
"""
import os
import time
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

STATUS = '[data-testid="stStatusWidget"]'


def smooth_move(page, x1, y1, x2, y2, steps=24):
    """鼠标平滑移动：按步进插值，模拟人手移动"""
    for i in range(1, steps + 1):
        t = i / steps
        # ease-in-out 缓动，起止慢、中间快，更像人手
        ease = t * t * (3 - 2 * t)
        page.mouse.move(x1 + (x2 - x1) * ease, y1 + (y2 - y1) * ease)
        page.wait_for_timeout(22)


def smooth_scroll(page, total, step=60, interval=110):
    """分步滚动：每步小滚 + 间隔，模拟滚轮连续滚动"""
    if total > 0:
        n = max(1, total // step)
        for _ in range(n):
            page.mouse.wheel(0, step)
            page.wait_for_timeout(interval)
    elif total < 0:
        n = max(1, -total // step)
        for _ in range(n):
            page.mouse.wheel(0, -step)
            page.wait_for_timeout(interval)


def wait_rerun(page, timeout=15000):
    """等待 Streamlit rerun 完成：spinner 从页面消失"""
    try:
        page.wait_for_selector(STATUS, state="hidden", timeout=timeout)
    except Exception:
        pass  # 没等到也不阻塞，页面内容已在


def goto_nav(page, key):
    """点击导航并等 rerun 完成、页面稳定"""
    page.get_by_text(NAV[key], exact=True).first.click()
    wait_rerun(page)
    page.wait_for_timeout(1500)


def set_slider(page, idx, value):
    """设置 Streamlit slider 值（原生 setter + 事件派发）"""
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
            record_video_dir=r"C:\Users\雨濛濛\Desktop",
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.goto(URL)
        wait_rerun(page)
        page.wait_for_timeout(3000)

        # ===== 场景0：运营看板（0-12s）=====
        # 鼠标缓慢划过「休眠成因分布」图表（三段平滑移动）
        smooth_move(page, 1050, 660, 1180, 600)
        page.wait_for_timeout(800)
        smooth_move(page, 1180, 600, 1320, 650)
        page.wait_for_timeout(800)
        smooth_move(page, 1320, 650, 1150, 500)
        page.wait_for_timeout(6000)

        # ===== 场景1：分型 → 策略（12-55s）=====
        goto_nav(page, "分型")
        page.wait_for_timeout(2000)
        # 平滑移动经过分型结果卡片，停留展示
        smooth_move(page, 1350, 660, 1350, 800)
        page.wait_for_timeout(8000)
        goto_nav(page, "策略")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="🚀 生成AI激活策略").click()
        wait_rerun(page, timeout=20000)
        page.wait_for_timeout(2000)
        # 平滑滚动展示策略全文 → 合规状态 → 多渠道输出
        smooth_scroll(page, 520)
        page.wait_for_timeout(3500)
        smooth_scroll(page, 320)
        page.wait_for_timeout(3500)
        smooth_scroll(page, -760)
        page.wait_for_timeout(2500)

        # ===== 场景2：合规拦截（55-90s）=====
        goto_nav(page, "合规")
        smooth_scroll(page, 560)
        page.wait_for_timeout(1500)
        ta = page.get_by_label("话术文本（演示）")
        ta.fill("尊敬的客户，本产品保本稳赚，收益绝对有保障，推荐您立即缴存！")
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="🔍 检查合规性").click()
        wait_rerun(page)
        page.wait_for_timeout(3000)  # 停留展示红色拦截
        # 删除违规词 → 重查通过
        ta.fill("尊敬的客户，个人养老金账户资金封闭管理，缴存可享税优政策，不构成投资建议。")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="🔍 检查合规性").click()
        wait_rerun(page)
        page.wait_for_timeout(5000)

        # ===== 场景3：留痕审计（90-115s）=====
        smooth_scroll(page, 760)
        page.wait_for_timeout(3500)
        smooth_scroll(page, -220)
        page.wait_for_timeout(3000)
        smooth_scroll(page, 420)
        page.wait_for_timeout(7000)

        # ===== 场景4：AB效果 + 税优（115-150s）=====
        goto_nav(page, "AB")
        page.wait_for_timeout(2000)
        smooth_scroll(page, 360)
        page.wait_for_timeout(4000)
        smooth_scroll(page, 420)
        page.wait_for_timeout(4000)
        goto_nav(page, "税优")
        page.wait_for_timeout(2000)
        set_slider(page, 1, 60000)  # 月薪 25000 → 60000
        wait_rerun(page)
        page.wait_for_timeout(4000)
        smooth_scroll(page, 420)
        page.wait_for_timeout(5000)
        smooth_scroll(page, -340)
        page.wait_for_timeout(3000)

        # ===== 场景5：收尾（150-160s）=====
        goto_nav(page, "看板")
        page.wait_for_timeout(1500)
        smooth_move(page, 700, 500, 760, 470)
        page.wait_for_timeout(8000)

        # ---- 保存视频 ----
        video = page.video
        ctx.close()
        video.save_as(OUT_WEBM)
        print("已录制 webm:", OUT_WEBM)
        browser.close()

    # 转码 mp4：crf 16 高码率，UI 文本清晰
    ffmpeg = get_ffmpeg_exe()
    import subprocess
    r = subprocess.run([ffmpeg, "-y", "-i", OUT_WEBM,
                        "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                        "-pix_fmt", "yuv420p", OUT_MP4],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print("转码 exit:", r.returncode)
    print("完成！mp4:", OUT_MP4)


if __name__ == "__main__":
    main()
