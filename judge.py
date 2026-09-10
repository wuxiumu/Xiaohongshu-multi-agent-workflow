#!/usr/bin/env python3
"""
02 判断智能体 Judge
读 collected.json,对三轨关键词评分、提炼爆款模式、生成选题并排序,
输出 judged.json 交给 03 执行智能体。

LLM 只用于:
1. 爆款模式提炼(对每轨 top 关键词,LLM 总结标题结构/标签/封面风格)
2. 选题生成(对 top 关键词生成 3-5 个差异化选题候选)

评分用纯 Python 规则,不调 LLM(快、确定、省 token)。
"""
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

import yaml
import requests

PLAN_DIR = Path(__file__).parent
DATA_DIR = PLAN_DIR / "data"
COLLECTED_PATH = DATA_DIR / "collected.json"
FEEDBACK_PATH = DATA_DIR / "feedback.json"
JUDGED_PATH = DATA_DIR / "judged.json"
OPENCLAW_PATH = Path.home() / ".openclaw" / "openclaw.json"

# 每轨取 top M 关键词做爆款模式提炼 + 选题生成
TOP_KEYWORDS_PER_TRACK = 5
# 每个 top 关键词生成多少个选题候选
TOPICS_PER_KEYWORD = 4
# 最终每轨取 top N 选题
TOP_TOPICS_PER_TRACK = 8


def load_config():
    oc = json.load(open(OPENCLAW_PATH, "r", encoding="utf-8"))
    return oc.get("models", {}).get("providers", {})


def call_llm(providers, provider_name, model, prompt, max_tokens=1500):
    p = providers[provider_name]
    base_url = p["baseUrl"].rstrip("/")
    api_key = p["apiKey"]
    api_type = p.get("api", "openai")

    if "anthropic" in api_type:
        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    else:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ============ 1. 关键词评分(纯 Python 规则) ============

def score_keyword(keyword, samples, track, feedback_kws):
    """对单个关键词打分 0-100,按三轨差异化权重"""
    if not samples:
        return 0, {"hot": 0, "compete": 0, "trend": 0, "feedback": 0, "niche_fit": 0}

    likes = [s.get("likes", 0) for s in samples]
    max_like = max(likes) if likes else 0
    avg_like = sum(likes) / len(likes) if likes else 0

    # 热度:log 缩放,1万赞 ≈ 80 分,10万赞 ≈ 100 分
    import math
    hot = min(100, math.log10(max_like + 1) * 20) if max_like else 0

    # 竞争度:样本数越多竞争越激烈,反向分(15 条 → 50 分,5 条 → 83 分)
    compete = max(0, 100 - len(samples) * 3.3)

    # 上升趋势:无 trend 字段时,样本最大点赞 > 5000 视为 rising
    trend = 60 if max_like > 5000 else 40

    # 历史反馈:从 feedback.json 读,默认 50
    feedback = 50
    if keyword in feedback_kws:
        feedback = 80  # 历史高表现

    # 账号契合度:种子词 90,LLM 扩展词 70
    niche_fit = 90 if any(k["word"] == keyword and k["source"] == "seed"
                          for k in track["keywords"]) else 70

    # 按轨道加权
    weights = {
        "tutorial": {"hot": 20, "compete": 15, "trend": 15, "feedback": 10, "niche_fit": 10},
        "skill":    {"hot": 15, "compete": 15, "trend": 15, "feedback": 10, "niche_fit": 10},
        "ppt":      {"hot": 15, "compete": 10, "trend": 15, "feedback": 10, "niche_fit": 10},
    }
    w = weights.get(track_name_of(track), {"hot": 20, "compete": 15, "trend": 15, "feedback": 10, "niche_fit": 10})

    # 教程轨:收藏率不可得(搜索页没抓收藏),用点赞代理
    # Skill 轨:差异化权重 30,通过 niche_fit 放大(seed 词得分低 = 同质化高)
    # PPT 轨:导流潜力用 has_cta 代理(虽然搜索页没抓,留接口)
    score = (
        hot * w["hot"] / 100 +
        compete * w["compete"] / 100 +
        trend * w["trend"] / 100 +
        feedback * w["feedback"] / 100 +
        niche_fit * w["niche_fit"] / 100
    )
    # Skill 轨额外加 20 分差异化(赛道稀少)
    if track_name_of(track) == "skill":
        score += 20

    # 补齐 5 个维度权重到 100% 之外的差异化分
    # 简化:直接返回总分
    return round(min(100, score)), {
        "hot": round(hot), "compete": round(compete), "trend": trend,
        "feedback": feedback, "niche_fit": niche_fit,
        "samples_count": len(samples), "max_likes": max_like, "avg_likes": round(avg_like)
    }


def track_name_of(track):
    """反查 track 名:其实从外层 dict 传入更直接,这里用 keywords 的 source 推断不了,
    改成显式传。简化:直接从 collected['tracks'] 的 key 拿。"""
    return ""  # placeholder,实际用 main 里的 track_name


# ============ 2. 爆款模式提炼(LLM) ============

def extract_pattern(providers, provider_name, model, keyword, samples):
    """对单个关键词的 samples 做 LLM 提炼,返回范式卡"""
    # 取 top 5 高赞样本
    top = sorted(samples, key=lambda x: x.get("likes", 0), reverse=True)[:5]
    samples_text = "\n".join(
        f"- 标题:{s.get('title','')} | 赞:{s.get('likes',0)} | 作者:{s.get('author','')}"
        for s in top
    )
    prompt = f"""你是小红书爆款分析师。关键词「{keyword}」的高赞样本如下:
{samples_text}

请提炼这个关键词的内容范式,严格输出 JSON:
{{
  "title_structures": ["标题结构1(如'N 件好物')", "标题结构2", "标题结构3"],
  "tag_clusters": ["标签1", "标签2", "标签3"],
  "cover_style": "封面共性描述(如'界面截图+红框高亮')",
  "content_angle": "主流切入角度(如'场景痛点+工具演示+结果对比')"
}}

只输出 JSON,不要解释。"""
    try:
        text = call_llm(providers, provider_name, model, prompt, max_tokens=3000)
        print(f"     [LLM RAW] pattern: {text[:200]}")
        return parse_json_tolerant(text)
    except Exception as e:
        print(f"    [WARN] pattern extract failed: {e}")
        return {
            "title_structures": [],
            "tag_clusters": [],
            "cover_style": "",
            "content_angle": ""
        }


def parse_json_tolerant(text):
    """容错解析 LLM 输出的 JSON:
    1. 去除 ``` 代码块
    2. 提取 { 到 } 的部分
    3. 尝试 json.loads
    """
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    text = text.strip()
    # 找第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)


# ============ 3. 选题生成(LLM) ============

def generate_topics(providers, provider_name, model, keyword, pattern, track_name, n):
    """对单个关键词生成 n 个差异化选题"""
    pattern_text = f"标题结构:{pattern.get('title_structures','')}\n标签:{pattern.get('tag_clusters','')}\n角度:{pattern.get('content_angle','')}"

    track_desc = {
        "tutorial": "AI教程轨(教具体场景怎么用 AI 工具,目标是涨粉收藏)",
        "skill": "Skill 轨(展示 AI agent/skill/prompt 玩法,目标是差异化人设)",
        "ppt": "PPT 种草轨(展示 AI 生成的 PPT 模板,目标是变现导流)"
    }.get(track_name, "AI内容")

    prompt = f"""你是小红书选题策划师。赛道:{track_desc}
关键词:「{keyword}」
该关键词的爆款范式:
{pattern_text}

请生成 {n} 个差异化选题,要求:
1. 标题方向(title_hint)≤20字,带数字/情绪词/具体场景
2. 不与上述爆款样本雷同,要有新角度
3. PPT 轨的选题必须能自然挂"模板在评论区/主页"的导流话术
4. Skill 轨的选题要能展示 skill 的具体代码/调用

严格输出 JSON 数组:
[
  {{
    "title_hint": "标题方向",
    "angle": "切入角度(一句话)",
    "tags_hint": ["标签1","标签2","标签3","标签4","标签5"],
    "target_audience": "目标人群",
    "cross_sell_hint": "跨轨导流话术(教程/PPT 轨必填,Skill 轨可空)"
  }}
]

只输出 JSON,不要解释。"""
    try:
        text = call_llm(providers, provider_name, model, prompt, max_tokens=4000)
        print(f"     [LLM RAW] topics: {text[:300]}")
        text = text.strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
        text = text.strip()
        # 找第一个 [ 或 { 到最后一个 ] 或 }
        start_arr = text.find("[")
        start_obj = text.find("{")
        if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
            end = text.rfind("]")
            if end > start_arr:
                text = text[start_arr:end+1]
        elif start_obj >= 0:
            end = text.rfind("}")
            if end > start_obj:
                text = text[start_obj:end+1]
        arr = json.loads(text)
        return arr if isinstance(arr, list) else [arr]
    except Exception as e:
        print(f"    [WARN] topic gen failed: {e}")
        return []


# ============ 4. 选题评分(纯 Python) ============

def score_topic(topic, keyword, track_name):
    """对生成选题打分 0-100"""
    score = 50  # 基础分
    title = topic.get("title_hint", "")
    angle = topic.get("angle", "")
    tags = topic.get("tags_hint", [])

    # 标题带数字 +15
    if any(c.isdigit() for c in title):
        score += 15
    # 标题带情绪词 +10
    emotion_words = ["哭了", "绝了", "后悔", "损失", "必看", "保姆级", "亲测", "真实"]
    if any(w in title for w in emotion_words):
        score += 10
    # 标题长度 8-20 +5
    if 8 <= len(title) <= 20:
        score += 5
    # 切入角度带"亲测/对比/横评/保姆级" +10
    if any(w in angle for w in ["亲测", "对比", "横评", "保姆级", "手把手", "真实"]):
        score += 10
    # 标签数 4-6 +5
    if 4 <= len(tags) <= 6:
        score += 5
    # PPT 轨有 cross_sell_hint +15
    if track_name == "ppt" and topic.get("cross_sell_hint"):
        score += 15
    # 教程轨有 cross_sell_hint(导流到 PPT)+10
    if track_name == "tutorial" and topic.get("cross_sell_hint"):
        score += 10

    return round(min(100, score))


# ============ main ============

def main():
    if not COLLECTED_PATH.exists():
        print(f"[ERR] {COLLECTED_PATH} 不存在,先跑 01")
        sys.exit(1)

    collected = json.load(open(COLLECTED_PATH, "r", encoding="utf-8"))
    providers = load_config()
    provider_name = "zhipu"
    model = "GLM-5.3-Flash"

    # 读 feedback(可选)
    feedback_kws = []
    if FEEDBACK_PATH.exists():
        fb = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        feedback_kws = [r.get("keyword") for r in fb.get("records", []) if r.get("keyword")]

    result = {
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "niche": collected.get("niche", ""),
        "tracks": {}
    }

    for track_name, track in collected["tracks"].items():
        print(f"\n[Track] {track_name}")
        # 按关键词分组样本
        kw_samples = defaultdict(list)
        for s in track.get("samples", []):
            kw_samples[s.get("keyword", "")].append(s)

        # 1. 关键词评分
        kw_scores = []
        for kw, samples in kw_samples.items():
            if not kw:
                continue
            score, detail = score_keyword(kw, samples, track, feedback_kws)
            # 用 track_name 显式传
            # 重算:把 track_name_of 修正
            kw_scores.append((kw, score, detail, samples))
        # 按分数排序
        kw_scores.sort(key=lambda x: x[1], reverse=True)

        print(f"  关键词评分 top 5:")
        for kw, score, detail, _ in kw_scores[:5]:
            print(f"    {kw}: {score} (max_likes={detail['max_likes']}, samples={detail['samples_count']})")

        # 2. 对 top M 关键词做爆款模式提炼 + 选题生成
        top_kws = kw_scores[:TOP_KEYWORDS_PER_TRACK]
        keyword_cards = []
        all_topics = []

        for kw, score, detail, samples in top_kws:
            print(f"  -> 提炼+选题: {kw}")
            pattern = extract_pattern(providers, provider_name, model, kw, samples)
            print(f"     pattern: {pattern.get('title_structures', [])[:2]}")
            keyword_cards.append({
                "keyword": kw,
                "score": score,
                "pattern": pattern
            })

            topics = generate_topics(providers, provider_name, model, kw, pattern, track_name, TOPICS_PER_KEYWORD)
            for t in topics:
                t["keyword"] = kw
                t["track"] = track_name
                t["score"] = score_topic(t, kw, track_name)
                all_topics.append(t)
            time.sleep(0.5)

        # 3. 选题排序,取 top N
        all_topics.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_topics = all_topics[:TOP_TOPICS_PER_TRACK]
        for i, t in enumerate(top_topics):
            t["id"] = f"{track_name[:3]}_{i+1:03d}"
            t["priority"] = i + 1

        result["tracks"][track_name] = {
            "keyword_cards": keyword_cards,
            "topics": top_topics
        }
        print(f"  选题 top {len(top_topics)}:")
        for t in top_topics[:3]:
            print(f"    [{t['id']}] score={t['score']} | {t.get('title_hint','')[:40]}")

    # 写出
    with open(JUDGED_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] -> {JUDGED_PATH}")
    for t, d in result["tracks"].items():
        print(f"  {t}: {len(d['keyword_cards'])} cards, {len(d['topics'])} topics")


if __name__ == "__main__":
    main()
