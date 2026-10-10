# multi-agent-workflow（Xiaohongshu-multi-agent-workflow）· 深优化建议（文档先行）

> 与父仓 `docs/OPTIMIZATION-NEXT.md` Top4 对齐。GitHub 仓名：`Xiaohongshu-multi-agent-workflow`。  
> 轻量加固：✅ C1 PR（无 Key 样板看板 / `scripts/smoke.py`）。**下列留给下一轮代码。**

## 现状对照

| 项 | 现状 |
|---|---|
| 流水线 | collect → judge → execute；JSON 断点续跑 |
| profiles | 已有 `profiles/example-beauty.yaml`、`example-education.yaml` |
| 看板 | `index.html` + `api.php`；样板 produced 已入库（图需重生成） |
| 合规 | README 已写「不自动发帖」；可再置顶横幅 |

## 建议（可执行）

| # | 建议 | 类型 | 验收 |
|---|---|---|---|
| 1 | 再补 1–2 个 `profiles/`（美妆深化 / 职场），可直接跑出 produced | 定制 | 选 profile 即出样板 |
| 2 | `docs/samples/`：1 条成品图 + 30s 录屏说明（或 GIF） | Demo | README 中部有图 |
| 3 | `docs/CUSTOM.md`：基础部署 / 单品类 / 加购锚点（价格位自填） | 文档 | 谈单可转发 |
| 4 | smoke 断言看板 API 样板条数 > 0（在现有 `scripts/smoke.py` 上加强） | 可运行 | smoke 失败即红 |
| 5 | 合规横幅固定顶栏：不自动发帖、不养号、不站外导流 | 文档 | README + 看板顶栏一致 |
| 6 | 词库/禁词扩展点：`docs/EXTEND.md`（客户自换 JSON 路径与字段） | 定制 | 半页可跟做 |

## 建议落地顺序

5 → 4 → 1 → 6 → 3 → 2。

## 定制联系

微信 **qingbao199101**（备注：品类）· [wuxiumu@163.com](mailto:wuxiumu@163.com)
