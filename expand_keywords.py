#!/usr/bin/env python3
"""
01 收集智能体 · 关键词扩展脚本
读取 collect_config.yaml,用 LLM 把三轨种子词扩成长尾词,
输出到 data/collected.json 的 keywords 字段(不抓小红书,纯 LLM 扩展)。
"""
import json
import os
import sys
import time
from pathlib import Path

import yaml
import requests

# 路径
PLAN_DIR = Path(__file__).parent
DATA_DIR = PLAN_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_PATH = PLAN_DIR / "collect_config.yaml"
OPENCLAW_PATH = Path.home() / ".openclaw" / "openclaw.json"
OUTPUT_PATH = DATA_DIR / "collected.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_openclaw():
    """从 ~/.openclaw/openclaw.json 读取 provider 配置"""
    with open(OPENCLAW_PATH, "r", encoding="utf-8") as f:
        oc = json.load(f)
    providers = oc.get("models", {}).get("providers", {})
    return providers


def call_llm(providers, provider_name, model, prompt):
    """调用 LLM,返回文本。优先 OpenAI 兼容格式,失败回退 anthropic-messages"""
    p = providers.get(provider_name)
    if not p:
        raise ValueError(f"provider {provider_name} not found in openclaw.json")

    base_url = p["baseUrl"].rstrip("/")
    api_key = p["apiKey"]
    api_type = p.get("api", "openai")

    if "anthropic" in api_type:
        # anthropic-messages 格式(百炼 token plan)
        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"]
    else:
        # openai 兼容格式(智谱 coding plan)
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


def expand_seed(providers, provider_name, model, seed, n):
    """把单个种子词扩成 n 个长尾词"""
    prompt = f"""你是小红书运营专家。基于种子词「{seed}」扩展 {n} 个小红书上的长尾关键词。
要求:
1. 贴合小红书用户真实搜索习惯(口语化、带场景)
2. 与种子词不重复,彼此之间不重复
3. 优先选有搜索热度、有具体场景的词
4. 不要泛泛的词(如"AI"),要带具体动作/场景(如"AI一键做表格")

只输出关键词,每行一个,不要编号不要解释。"""
    text = call_llm(providers, provider_name, model, prompt)
    # 清理:去编号、去空行、去标点
    words = []
    for line in text.splitlines():
        line = line.strip().lstrip("0123456789.、- )(").strip()
        if line and len(line) <= 20:
            words.append(line)
    # 去重保序
    seen = set()
    out = []
    for w in words:
        if w not in seen and w != seed:
            seen.add(w)
            out.append(w)
    return out[:n]


def main():
    cfg = load_config()
    providers = load_openclaw()
    provider_name = cfg["llm"]["provider"]
    model = cfg["llm"]["model"]
    print(f"[INFO] LLM: {provider_name} / {model}")

    result = {
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "niche": cfg["niche"],
        "tracks": {},
        "feedback_weighted": {"tutorial": [], "skill": [], "ppt": []},
    }

    for track_name, track_cfg in cfg["tracks"].items():
        print(f"\n[Track] {track_name} - {len(track_cfg['seeds'])} seeds")
        all_keywords = []
        seed_set = set(track_cfg["seeds"])

        # 种子词本身入库
        for s in track_cfg["seeds"]:
            all_keywords.append({
                "word": s,
                "source": "seed",
                "hot_score": 0,         # 未抓数据前先置 0
                "trend": "unknown",
                "samples_count": 0
            })

        # 每个种子词扩展
        for seed in track_cfg["seeds"]:
            n = track_cfg["expand_per_seed"]
            try:
                expanded = expand_seed(providers, provider_name, model, seed, n)
                print(f"  {seed} -> {len(expanded)}: {expanded[:3]}...")
                for w in expanded:
                    if w not in seed_set:
                        seed_set.add(w)
                        all_keywords.append({
                            "word": w,
                            "source": f"llm_expand_from:{seed}",
                            "hot_score": 0,
                            "trend": "unknown",
                            "samples_count": 0
                        })
            except Exception as e:
                print(f"  [WARN] {seed} expand failed: {e}")
            time.sleep(0.3)  # 限速

        result["tracks"][track_name] = {
            "keywords": all_keywords,
            "samples": []   # 抓取脚本后续填充
        }
        print(f"[Track] {track_name} total keywords: {len(all_keywords)}")

    # 写出
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] -> {OUTPUT_PATH}")

    # 汇总
    total = sum(len(t["keywords"]) for t in result["tracks"].values())
    print(f"[SUM] total keywords: {total}")
    for name, t in result["tracks"].items():
        print(f"  {name}: {len(t['keywords'])}")


if __name__ == "__main__":
    main()
