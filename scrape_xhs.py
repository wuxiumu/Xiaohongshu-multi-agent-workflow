#!/usr/bin/env python3
"""
01 收集智能体 · 小红书爆款样本抓取
读 collected.json 中三轨关键词,对每轨 top N 关键词搜索小红书,
抓取笔记标题/作者/点赞数/封面图/标签,填充 samples 字段。

登录策略:
- 首次运行:启动有头浏览器,打开小红书登录页,等用户扫码登录,
  保存 storage_state 到 xhs_state.json
- 后续运行:复用 state,headless 抓取

反爬:
- 每关键词间隔 5-8 秒
- 模拟人类滚动
- 单次抓取量 ≤ 50 条
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

PLAN_DIR = Path(__file__).parent
DATA_DIR = PLAN_DIR / "data"
STATE_PATH = DATA_DIR / "xhs_state.json"
COLLECTED_PATH = DATA_DIR / "collected.json"

# 抓取配置(扩量:每关键词 15 条,每轨 7 个词,跳过已抓的)
KEYWORDS_PER_TRACK = 7      # 每轨抓 top 7 关键词(已抓过的会自动跳过)
SAMPLES_PER_KEYWORD = 15    # 每个关键词抓 15 条样本
SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={}&source=web_search_result_notes"
LOGIN_URL = "https://www.xiaohongshu.com/explore"


LOGIN_WAIT_SECONDS = 600  # 给 10 分钟扫码登录


def ensure_login(headless=False):
    """启动浏览器,等用户扫码登录。自动检测 web_session cookie,登录成功后立即保存并继续。
    不用 input(),方便后台运行;检测到 cookie 就走,不依赖用户回终端按键。"""
    print(f"[LOGIN] 启动浏览器,请扫码登录小红书,登录成功后自动继续...")
    print(f"[LOGIN] 最多等待 {LOGIN_WAIT_SECONDS} 秒")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # 每 3 秒检测一次 web_session cookie,登录成功后立即保存
        for i in range(LOGIN_WAIT_SECONDS // 3):
            time.sleep(3)
            try:
                cookies = ctx.cookies()
                ws = next((c for c in cookies if c["name"] == "web_session"), None)
                # web_session 存在且值非空才算登录成功
                if ws and ws.get("value") and len(ws.get("value", "")) > 10:
                    print(f"[LOGIN] 检测到 web_session cookie,登录成功!")
                    time.sleep(3)  # 让页面稳定
                    ctx.storage_state(path=str(STATE_PATH))
                    print(f"[LOGIN] 已保存到 {STATE_PATH}")
                    browser.close()
                    return
            except Exception:
                pass
            if i % 10 == 0:
                print(f"[LOGIN] 等待扫码登录... ({(i+1)*3}s 已过)", flush=True)

        # 超时兜底
        print("[LOGIN] 超时,保存当前 state(可能未登录)")
        ctx.storage_state(path=str(STATE_PATH))
        browser.close()


def parse_note_card(card):
    """解析一个笔记卡片的 DOM,返回结构化数据"""
    try:
        # 标题:note-title / desc / class 含 title 文案
        title = ""
        for sel in [".note-title", "[class*='title']", ".desc", ".footer .title", ".note-text"]:
            el = card.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                if t:
                    title = t
                    break
        if not title:
            # 兜底:取卡片内最长文本
            txt = card.inner_text("compact").strip()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            title = max(lines, key=len) if lines else ""

        # 作者
        author = ""
        el = card.query_selector("[class*='author'] .name, .author .name, .user .name, [class*='name']")
        if el:
            author = el.inner_text().strip()

        # 点赞数:通常在 .like-wrapper .count / .like .count
        likes_str = ""
        for sel in [".like-wrapper .count", ".like .count", "[class*='like'] [class*='count']"]:
            el = card.query_selector(sel)
            if el:
                likes_str = el.inner_text().strip()
                break

        # 链接
        href = ""
        a = card.query_selector("a.cover, a[href*='/explore/'], a[href*='/note/']")
        if a:
            href = a.get_attribute("href") or ""
        if href and not href.startswith("http"):
            href = "https://www.xiaohongshu.com" + href

        # 封面
        cover = ""
        img = card.query_selector("img")
        if img:
            cover = img.get_attribute("src") or ""

        return {
            "title": title[:80],
            "author": author,
            "likes_text": likes_str,
            "likes": parse_likes(likes_str),
            "cover_url": cover,
            "note_url": href,
            "published_at": "",
            "body_preview": "",
            "tags": [],
            "has_cta": False
        }
    except Exception as e:
        return {"title": "", "error": str(e)}


def parse_likes(s):
    """'1.2万' -> 12000, '532' -> 532"""
    if not s:
        return 0
    s = s.strip().replace("+", "")
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "k" in s.lower():
            return int(float(s.lower().replace("k", "")) * 1000)
        return int(s)
    except Exception:
        return 0


def search_keyword(page, keyword, n):
    """搜一个关键词,返回 n 条样本"""
    url = SEARCH_URL.format(quote(keyword))
    print(f"  -> 搜索: {keyword}")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))

    # 诊断:打印当前 URL 和标题,判断是否被重定向到登录页
    cur_url = page.url
    cur_title = page.title()
    print(f"     URL={cur_url[:80]} | title={cur_title[:40]}")

    # 滚动加载更多
    for _ in range(2):
        page.mouse.wheel(0, 800)
        time.sleep(random.uniform(1.5, 2.5))

    # 找笔记卡片:小红书搜索结果通常是 section.note-item 或 div[class*='note']
    cards = []
    used_sel = ""
    for sel in ["section.note-item", "div.note-item", "[class*='note-item']", "a.cover", "section[class*='note']"]:
        cards = page.query_selector_all(sel)
        if cards:
            used_sel = sel
            break
    print(f"     cards={len(cards)} (selector={used_sel})")

    # 兜底:如果 0 条,把页面 inner_text 前 300 字打印出来,便于诊断 DOM
    if not cards:
        try:
            body_text = page.inner_text("body")[:300].replace("\n", " ")
            print(f"     [DIAG] body: {body_text}")
        except Exception:
            pass

    samples = []
    for c in cards[:n * 2]:  # 多取一倍做兜底
        data = parse_note_card(c)
        if data.get("title") and not data.get("error"):
            data["keyword"] = keyword
            samples.append(data)
        if len(samples) >= n:
            break

    return samples


def main():
    if not COLLECTED_PATH.exists():
        print(f"[ERR] {COLLECTED_PATH} 不存在,先跑 expand_keywords.py")
        sys.exit(1)

    with open(COLLECTED_PATH, "r", encoding="utf-8") as f:
        collected = json.load(f)

    # 检查登录态
    if not STATE_PATH.exists():
        ensure_login()
        if not STATE_PATH.exists():
            print("[ERR] 未保存登录态,无法继续")
            sys.exit(1)

    total_new = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 有头模式,反爬通过率高
        ctx = browser.new_context(
            storage_state=str(STATE_PATH),
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = ctx.new_page()

        for track_name, track in collected["tracks"].items():
            # 已抓关键词(从 samples 的 keyword 字段取)
            existing_samples = track.get("samples", [])
            scraped_kws = set()
            for s in existing_samples:
                if s.get("keyword"):
                    scraped_kws.add(s["keyword"])
            existing_titles = set(s.get("title", "") for s in existing_samples)

            # 选 top N 关键词(种子词优先,LLM 扩展词补充)
            seeds = [k for k in track["keywords"] if k["source"] == "seed"]
            expanded = [k for k in track["keywords"] if k["source"] != "seed"]
            candidates = [k["word"] for k in seeds] + [k["word"] for k in expanded]
            # 跳过已抓的词
            to_scrape = [w for w in candidates if w not in scraped_kws]
            top_kws = to_scrape[:KEYWORDS_PER_TRACK]

            print(f"\n[Track] {track_name} - 已抓 {len(scraped_kws)} 词,本次新抓 {len(top_kws)} 词,已有样本 {len(existing_samples)} 条")

            new_samples = []
            for kw in top_kws:
                try:
                    samples = search_keyword(page, kw, SAMPLES_PER_KEYWORD)
                    # 跨关键词去重:与 existing_titles 和本轮已加的标题去重
                    unique = []
                    for s in samples:
                        t = s.get("title", "")
                        if t and t not in existing_titles and t not in set(x.get("title","") for x in unique):
                            unique.append(s)
                    print(f"     {kw}: {len(samples)} -> {len(unique)} 条(去重后)")
                    new_samples.extend(unique)
                    total_new += len(unique)
                except Exception as e:
                    print(f"     {kw}: FAILED {e}")
                time.sleep(random.uniform(5, 8))  # 关键词间限速

            # 追加到现有 samples,不是覆盖
            track["samples"] = existing_samples + new_samples

        browser.close()

    # 回写
    with open(COLLECTED_PATH, "w", encoding="utf-8") as f:
        json.dump(collected, f, ensure_ascii=False, indent=2)
    total_all = sum(len(t.get("samples", [])) for t in collected["tracks"].values())
    print(f"\n[DONE] 本次新增 {total_new} 条,合计 {total_all} 条 -> {COLLECTED_PATH}")
    for t, d in collected["tracks"].items():
        print(f"  {t}: {len(d.get('samples', []))} samples")


if __name__ == "__main__":
    main()
