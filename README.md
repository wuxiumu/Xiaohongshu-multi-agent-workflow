# 小红书一周出可发笔记（选题工厂）

> 收集 → 判断 → 执行，本地产出可发物料。**不自动发帖、不站外导流。**

**定制 / 合作：** 微信 **qingbao199101**（备注：品类）｜邮箱 [wuxiumu@163.com](mailto:wuxiumu@163.com)

适合代运营、MCN、知识博主：按你的品类改词库、评分和模板后交付。

---

# 小红书多智能体内容生产流水线（收集 → 判断 → 执行）

> 一套用 **Python + LLM + Playwright + PHP** 实现的小红书（Xiaohongshu / RED）选题研究与内容生产自动化框架。三个智能体分工：**收集市场信号 → 规则+LLM 混合评分决策 → 分派生成可发布成品**，全程产出本地物料，**系统不自动发帖、不导流站外**。

**English:** A multi-agent content production pipeline for Xiaohongshu (RED) operators — a Collector (LLM keyword expansion + Playwright scraping), a Judge (deterministic scoring + LLM topic generation), and an Executor (tutorial / skill / PPT three-track content assembly), orchestrated in Python with a zero-dependency PHP + static-HTML local dashboard.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![PHP](https://img.shields.io/badge/PHP-7.4%2B-777BB4)](https://www.php.net/)
[![Stack](https://img.shields.io/badge/Stack-Python%20%7C%20LLM%20%7C%20Playwright%20%7C%20PHP-orange)]()

---

设计文档见 [docs/](docs/README.md)。

## 这是什么（30 秒概览）

- **三智能体架构**：`收集智能体` 扩词+抓爆款 → `判断智能体` 评分排序+生成选题 → `执行智能体` 按三轨（AI 教程 / Skill 分享 / PPT 模板）生成笔记成品
- **混合决策**：评分用纯 Python 规则（快、确定、零 token），LLM 只做爆款模式提炼与选题生成
- **零框架看板**：根目录静态 `index.html` + 单文件只读 `api.php`，`php -S` 一键起本地内容工坊页面，无需数据库
- **断点续跑**：每一步都落 JSON 文件（`collected.json → judged.json → produced.json`），任何环节中断后重跑命令即可从断点继续
- **真实跑通过的样板数据**：仓库内置 20 篇 produced 样板（4 tutorial / 8 skill / 8 PPT）。图片因体积未入库；只看样板看板不需要 API Key

## 适用人群

做小红书矩阵、自媒体选题研究、AI 内容工程（AI content engineering）、多智能体工作流（multi-agent workflow）的开发者/运营；也适合当作「LLM 应用的文件型状态机」教学样本。

## 架构

```
┌─────────────┐   关键词库+爆款样本   ┌─────────────┐   带优先级选题清单   ┌─────────────┐
│ 01 收集智能体 │ ───────────────────→ │ 02 判断智能体 │ ──────────────────→ │ 03 执行智能体 │
│  Collector   │                      │   Judge     │                     │  Executor   │
│ LLM扩词+爬取  │                      │ 规则评分+LLM │                     │ 三轨内容组装  │
└─────────────┘                      └─────────────┘                     └──────┬──────┘
      ↑ 反馈回流(点赞/收藏数据加权)                                            │
      └──────────────────────────────────────────────────────────────────────┘
                            全部状态落 data/*.json（文件型状态机）
```

## 目录结构

```
Xiaohongshu-multi-agent-workflow/
├── .env.example          # 密钥与路径模板。复制为 .env，不要提交 .env
├── requirements.txt      # Python 依赖（看板演示不需要先装）
├── runtime_env.py        # 读取 .env / openclaw.json。不改变三智能体分工
├── collect_config.yaml   # 赛道、三轨种子词、LLM 名称（不含密钥）
├── expand_keywords.py    # 01a 收集：种子词 → 长尾关键词（LLM）
├── scrape_xhs.py         # 01b 收集：Playwright 抓小红书爆款样本（扫码登录一次）
├── judge.py              # 02 判断：规则评分 + LLM 提炼爆款模式/生成选题
├── execute.py            # 03 执行：三轨成品组装（教程/Skill/PPT）
├── scripts/smoke.py      # 离线冒烟：样板 JSON、配置、看板 API
├── profiles/             # 品类简报示例。手工抄进 collect_config.yaml，不自动加载
├── index.html            # 本地看板（作品墙 / 详情 / 源码 / 流程）
├── api.php               # 只读 JSON API + 图片白名单代理
├── css/  js/             # 看板静态资源
├── data/
│   ├── collected.json    # 关键词库 + 爆款样本
│   ├── judged.json       # 评分结果 + 选题队列
│   ├── produced.json     # 成品笔记（20 篇样板，可直接给看板）
│   ├── ppt_templates/    # PPT 轨 Markdown 成稿
│   ├── images/           # 配图（gitignore，跑 execute.py 才有）
│   └── xhs_state.json    # 登录态（gitignore，跑 scrape 才有）
├── docs/agents/          # 00~03 设计文档，末尾有定制扩展点
├── llms.txt              # GEO：给生成式引擎的项目摘要
├── robots.txt            # 爬虫与 GEO 抓取规则
└── sitemap.xml
```

## 快速开始

### 1. 环境依赖

Python 3.9+。只看样板看板时还需要 PHP 7.4+（Debian/Ubuntu：`sudo apt-get install -y php-cli`；macOS 可用系统自带或 `brew install php`）。

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium   # 仅 scrape_xhs.py 需要
php -v
```

`requirements.txt` 里是当前脚本真实 import 的包：PyYAML、requests、playwright。当前 PPT 轨交付 Markdown，不依赖 python-pptx 或 Pillow。

### 2. 配置密钥与路径

复制模板再填，仓库里不要出现真实 Key：

```bash
cp .env.example .env
```

最少要填的两项（只有要跑扩词 / 判断 / 执行时才需要）：

```bash
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_API_KEY=
```

名称默认读 `collect_config.yaml` 的 `llm.provider` / `llm.model`。也可以用原来的 `~/.openclaw/openclaw.json`（或 `OPENCLAW_CONFIG_PATH`）。两边都有时，`.env` 里的 `LLM_API_KEY` 与 `LLM_BASE_URL` 覆盖同名 provider。可选路径：`DATA_DIR`、`COLLECT_CONFIG_PATH`、`XHS_STATE_PATH`、`BL_BIN`，含义写在 `.env.example` 里。

### 3. 最小可跑演示（不需要密钥，不抓小红书）

仓库已带 `data/collected.json`、`data/judged.json`、`data/produced.json`。

```bash
python3 scripts/smoke.py
php -S 127.0.0.1:8080
# 浏览器打开 http://127.0.0.1:8080/index.html
# 另开终端：curl -s 'http://127.0.0.1:8080/api.php?action=stats'
```

冒烟脚本检查样板 JSON、品类 yaml、`.gitignore` 是否挡住 `.env`，并在本机有 PHP 时请求 `stats` / `list` / `flow`。没有 PHP 时该步为 SKIP。

### 4. 跑完整流水线

先完成第 1、2 步。抓取需要图形界面扫码，服务器上可以跳过，直接用仓库里的样板 `collected.json`。

```bash
python3 expand_keywords.py     # 01a 种子词 → 长尾词（纯 LLM，不爬站）
python3 scrape_xhs.py          # 01b 首次运行弹浏览器扫码登录，登录态写入 data/xhs_state.json
python3 judge.py               # 02 评分排序 + 生成选题
python3 execute.py             # 03 按 judged.json 写 data/produced.json，已 ready 的篇目会跳过
```

## API 一览（api.php，全部只读）

| Action | 说明 |
|---|---|
| `?action=list` | 成品列表（三轨标记、封面、标签数） |
| `?action=post&id=xxx` | 单篇详情（步骤/正文/配图路径） |
| `?action=stats` | 各轨成品统计 |
| `?action=flow` | 三智能体流程元数据 |
| `?action=scripts` / `?action=script&name=judge.py` | 白名单脚本源码查看（防目录穿越） |
| `?action=image&path=data/images/...` | 图片代理，realpath 限制在 data 目录内 |
| `?action=md_download&id=xxx` | PPT 轨 Markdown 模板下载 |

## 设计原则

1. **人在环路（human-in-the-loop）**：系统只产出「待发布物料」，永远不调发布接口；发什么、什么时候发，人决定
2. **确定性优先**：能量化的（热度、轨道配额、优先级）用规则算，LLM 只用在需要语义的环节
3. **文件即数据库**：JSON 中间产物可读、可 diff、可手工修，重启无状态丢失
4. **密钥与仓库分离**：密钥放 `.env` 或 `~/.openclaw/openclaw.json`，两者都不要提交；小红书登录态 `xhs_state.json` 默认 gitignore
5. **礼貌爬取**：单关键词间隔 5–8 秒、模拟滚动、单次 ≤50 条，仅用于个人市场研究

## 技术栈

Python 3.9+ · 智谱 GLM（OpenAI 兼容协议，可替换任意兼容 endpoint）· Playwright/Chromium · 阿里云百炼 `bl` CLI（文生图，可用 `BL_BIN` 替换）· PHP 7.4+（内置 server）· 原生 HTML/CSS/JS 单页

## 定制扩展点

三智能体的文件契约不要改：`collected.json` → `judged.json` → `produced.json`。改品类时动这些位置：

| 要改什么 | 改哪里 |
|---|---|
| 密钥与路径 | `.env`（模板是 `.env.example`） |
| 品类种子词 | `collect_config.yaml` 的 `tracks.*.seeds` |
| 客户简报 | `profiles/*.yaml`，抄进上一行的 yaml，脚本不自动读 |
| 扩词说法 | `expand_keywords.py` → `expand_seed()` |
| 抓取配额与选择器 | `scrape_xhs.py` |
| 评分与选题配额 | `judge.py` → `score_keyword()` / `score_topic()` |
| 三轨成稿 | `execute.py` → `produce_tutorial()` / `produce_skill()` / `produce_ppt()` |

脚本文件头和 [docs/agents/](docs/agents/00_总览.md) 末尾都有同样的 `EXTENSION` / 定制扩展点说明。

## 常见问题（FAQ）

**Q：会不会自动发小红书？**
不会。流水线终点是本地 `produced.json` + 配图文件，复制粘贴由人完成，也不生成任何站外导流话术。

**Q：必须用智谱的模型吗？**
不是。调用走 OpenAI 兼容协议，也支持 `LLM_API_TYPE=anthropic`。在 `.env` 里改 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，或改 `~/.openclaw/openclaw.json` 里的兼容服务（百炼 / 本地 vLLM 等）。

**Q：只想确认环境，不想先申请 Key？**
按上面的「最小可跑演示」即可。`python3 scripts/smoke.py` 与本地看板都读仓库里的样板 JSON。

**Q：抓到的数据合规吗？**
`scrape_xhs.py` 使用你本人扫码后的登录态、限速访问、仅做个人选题研究，不做二次分发、不存储他人内容到公开仓库（图片与登录态均不入库）。

**Q：没有图片看板是空的？**
图片属于生成产物（体积大），未纳入 git。跑完 `execute.py` 后图片落到 `data/images/`，看板自动展示。

**Q：三轨内容分别是什么格式？**
tutorial = 标题+分步教程+配图；skill = 标题+skill 代码+演示输入输出；ppt = 标题+正文+逐页 Markdown 文案（`data/ppt_templates/`）+封面图。当前执行器不生成 pptx。

## License

MIT。本仓库不含任何第三方平台素材；生成内容请自行遵守平台规则与当地法律。

---

---

## 定制合作

面向代运营 / MCN / 知识博主：按你的**品类词库、评分规则、执行轨模板**改一版后交付。系统只出本地可发物料，**不自动发帖**。

加微信备注「品类定制」。

## 联系方式

定制、演示或合作：

- 邮箱：[wuxiumu@163.com](mailto:wuxiumu@163.com)
- 微信：**qingbao199101**（添加请备注来意）

### 赞助支持

如果内容对你有帮助，欢迎自愿赞助。

| 微信赞赏码 | 支付宝收款码 |
|---|---|
| ![微信赞赏码](https://chiguashentan-test.oss-cn-beijing.aliyuncs.com/wxprogram/zan/20261002185236_31_227.png) | ![支付宝收款码](https://chiguashentan-test.oss-cn-beijing.aliyuncs.com/wxprogram/zan/20261002185309_32_227.jpg) |

