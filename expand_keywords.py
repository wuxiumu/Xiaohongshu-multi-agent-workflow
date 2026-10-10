#!/usr/bin/env python3
"""
01 收集智能体 · 关键词扩展脚本
读取 collect_config.yaml,用 LLM 把三轨种子词扩成长尾词,
输出到 data/collected.json 的 keywords 字段(不抓小红书,纯 LLM 扩展)。

EXTENSION（定制流水线）：
- 种子词与每词扩展条数：collect_config.yaml 的 tracks.<轨>.seeds / expand_per_seed。
- 长尾词提示词：expand_seed()。
- 不要改 collected.json 的 tracks.<轨>.keywords / samples 形状，02 与抓取脚本依赖它。
"""
import json
import time

import yaml
import requests

import runtime_env

# 路径。DATA_DIR / 配置文件可被 .env 覆盖，见 .env.example。
DATA_DIR = runtime_env.data_dir()
CONFIG_PATH = runtime_env.collect_config_path()
OUTPUT_PATH = DATA_DIR / "collected.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    # 密钥来自 .env 或 openclaw.json；provider/model 名仍可被 collect_config.yaml 提供。
    providers, provider_name, model = runtime_env.require_llm()
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
