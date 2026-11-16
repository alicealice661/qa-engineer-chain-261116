---
name: server-resource-trend-analyzer
description: 把多天、多份 Seafile 分享链接里的服务器资源 docx、慢 SQL 与网关日志汇总成趋势报告，并把未修复项生成禅道可导入的 CSV。当用户说「服务器与数据库资源情况多日汇总」「这几天的慢 SQL/资源报告合起来看趋势」「把这些链接里的日志出一份资源趋势」时使用。
---

# Server Resource Trend Analyzer

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：用户一次给出多天、多份 Seafile 分享链接（内网资源 / 慢 SQL / 服务日志三类目录）。
- **本技能**：逐日解析 → `days/<YYYYMMDD>.json` → 多日趋势汇总 md + 未修复项禅道导入 CSV（UTF-8 BOM）。
- **下一棒**：CSV → `zentao-bug-autosubmit` 提单；链接里的大文件先用 `seafile-anon-share-download` 拉下来更稳。
- **别用本技能做**：① 只拉文件不分析 → `seafile-anon-share-download`；② 单日单台的资源快照 → 手工看 docx 更快，做趋势不值；③ 服务起不来要反推配置 → `springboot-jar-config-reverse`。
- **数据纪律**：慢 SQL 行数常写成 `2.95M` 这类字符串，解析必须展开；趋势列以首日为基线，且要写出基线日。

## 触发条件
用户依次发送多个 Seafile 分享链接（内网资源/慢SQL/服务日志 三个目录结构），要求做"服务器与数据库资源情况"多日汇总，并提禅道。

## 输入
- 一个或多个 Seafile 匿名分享链接，例如 `http://192.168.2.123/d/<token>/`
- 每个链接下必须包含固定结构：
  - `/内网资源/`（PC 服务器 docx + RDS.docx）
  - `/慢SQL/`（das_slowlog_*.csv + das_slowlog_record_*.csv + 慢SQL.docx）
  - `/服务日志/IGW端/` 和 `/服务日志/PC端/`（日志 zip 或按文件）
- 用户可能指定"只看某一天"（如链接里包含多天时）

## 输出
- `days/<YYYYMMDD>.json`：每日结构化指标
- `<工作区>/server_resource_trend/汇总_*.md`：多日趋势汇总 Markdown
- `<桌面>/工作日报/服务器与数据库资源情况汇总_趋势_*.md`：桌面副本
- `<桌面>/工作日报/禅道导入模板_服务器与数据库资源问题_<YYYYMMDD>.csv`：单日未修复缺陷导入模板（UTF-8 BOM）

## 执行流程
1. **探测结构**：`GET /api/v2.1/share-links/<token>/dirents/?path=/` 确认三个目录存在；若链接含多天（如 `/260901/`），按用户指定保留对应日期。
2. **下载**：对每一天使用 Seafile 分享打包接口：
   - 目录：`/api/v2.1/share-link-zip-task/?share_link_token=<token>&path=<urlencoded_path>/`
   - 单文件（PC 端 `znly01.log/` 这类带 `.log` 后缀目录）：POST JSON `{token, parent_dir, dirents: [filename]}` 到 `/api/v2.1/share-link-zip-task/`
   - 轮询：`/api/v2.1/query-zip-progress/?token=<zip_token>`
   - 下载：`/seafhttp/zip/<zip_token>`
3. **解压**：使用 Python `zipfile` 解压到 `raw_<YYYYMMDD>/`。
4. **解析慢 SQL**：读取 `das_slowlog_*.csv`（汇总）和 `das_slowlog_record_*.csv`（明细）。注意扫描行字段可能带 `M/K/W` 简写，需要兼容。
5. **扫描日志**：使用 `logscan.py` 对 IGW 和 PC 端日志做 ERROR 聚合与关键词统计。
6. **读取资源截图**：docx 内嵌图位于 `word/media/`，提取后用 `Read` 工具逐张读取，记录 CPU/内存/磁盘/IO。
7. **生成每日 JSON**：字段名必须与 `days/20260827.json` 等历史文件一致（`slowsql.count`、`source_hosts`、`connection.broken_pipe_db`、`app_igw.error_total` / `issues`、`app_pc.error_total` / `issues`、`server_pc` list、`rds.mem_usage` 等）。
8. **生成趋势汇总**：运行 `trend.py --md 汇总_<日期范围>.md`，会读取 `days/*.json` 自动输出六章：慢SQL/连接层/应用层/服务器/RDS/缺陷跟踪。
9. **生成禅道 CSV**：读取当日 JSON 的 `defects`，过滤 `fixed=true`，输出 UTF-8 BOM CSV。

## 关键缺陷编号约定
- D1~D12 为 0827 基线缺陷；0831 新增 D13/D14；0901 新增 D15/D16；0902 新增 D17；0903 新增 D18~D22。后续按顺序顺延。
- 同一缺陷跨天复现标 `√`，本日未复现标 `—`，本日已修复标 `✓修复`，新增标 `+新`。

## 注意事项
- Seafile 下载接口对带 `.log` 后缀的目录名会 404，必须用单文件 JSON API。
- 资源 docx 全是截图，需提取 `word/media/*.png` 后用 `Read` 读取。
- 慢 SQL 扫描行可能为 `2.95M` 等字符串，解析时要展开。
- 汇总 Markdown 的趋势列以首日（0827）为基线计算变化百分比。

## 文件位置
- 工程目录：`C:\Users\<user>\WorkBuddy\<workspace>\server_resource_trend\`
- 桌面交付：`C:\Users\<user>\Desktop\工作日报\`

## 坑位与解法（0904 补充）

| 现象 | 原因 / 解法 |
|---|---|
| 整目录 zip-task 报 `size too large` | 目录内含多个大日志（如 30MB+ gateway 日志）；改用单文件 JSON API 逐个下载 |
| POST zip-task 后 `query-zip-progress` 返回 404 | 同一批次文件数过多（如 22 个 log）时偶发；拆成每批 5-10 个文件 |
| 429 Too Many Requests | Seafile 限流；批次间 sleep 5-10s，遇 429 按 30s×attempt 退避重试 |
| PC 端 ERROR 扫描为 0 | 检查目录名是否带 `.log` 后缀，scan 脚本的 `node_dir` 必须与实际下载目录一致 |
| IGW 下载后仍是 zip | IGW 端可能直接放 `67.zip`/`68.zip`，外层 zip 解压后需再 unzip 内层 zip |
| 资源 docx 解压后不在预期目录 | 脚本 extract 目标与实际不一致；兼容 `extracted/log/` 和 `extracted/resource/` 双路径 |
| 慢 SQL 明细 CSV 字段变化 | 不同日期字段名可能为 `客户端`/`客户端IP`、`执行耗时（秒）`/`执行时间（秒）`；代码需容错 |
| 慢 SQL 总耗时跨天骤变 | DAS 为滚动窗口，跨日快照有重叠；不要直接比绝对值，重点看热点表与峰值时段 |
| PC 端 ERROR 突然暴涨 | 优先看 eibs-file.log（上传失败）、eibs-xxljob.log（Read timed out）、eibs-elasticsearch.log（ES同步失败） |
| POST zip-task 返回 HTML 首页、全部下载 0 文件 | `zip-task`/`query-zip-progress` 端点**不能**带 `/share-links/<token>` 前缀；正确：`POST /api/v2.1/share-link-zip-task/` body `{token, parent_dir, dirents}`；`GET /api/v2.1/query-zip-progress/?token=<zip_token>`；`GET /seafhttp/zip/<zip_token>` |
| 资源 docx 提取后 `image1.png` 0 字节或 Read 报错 `file shorter than offset` | zipfile `namelist()` 含目录条目 `word/media/`；提取时必须 `not n.endswith('/')` 且过滤 `len(data) < 100`，否则目录占位导致索引偏移、真实图被覆盖 |
| PC 端 WARN 暴增 | 关注 `reactor-netty` `Decoding failed: FULL_REQUEST` HTTP/0.9 空请求，可能是网络探测或异常流量 |
| 下载脚本"无输出、每文件空等 3 分钟后全部失败" | `query-zip-progress` 返回字段是 `{"zipped":N,"total":N,"failed":0,"failed_reason":""}`，**不是** `pct`/`percent`/`finished`/`status`。判断完成必须用 `total>0 and zipped>=total`；用错字段会导致永远判定未完成、超时失败（0905/0908 用的旧脚本字段正确，新写脚本时务必照抄同一判断） |
| 单文件逐个下载在 429 下过慢（46 文件 × 3+ 请求） | 改为**分组打包**：慢SQL 3 文件合 1 包；RDS 单包；PC 资源每节点 1 包；PC 日志按"组内总大小 ≤20MB"分组（大文件自成一组）。可将请求数减半以上。注意整节点 200MB 大包会超时，故日志必须分组而非整包 |
| 429 退避不够导致连续失败 | `zip_task`/`fetch` 遇 429 用 `min(20*(i+1), 90)` 秒退避、重试 8-10 次；脚本启动时先 `sleep 20` 冷却，避开上一轮限流窗口。`wait_zip` 轮询间隔用 5s（2s 太密会加剧限流） |
| finalize 后禅道 CSV 出现重复缺陷行（如 D25 两次） | `finalize_XX.py` 的"新增高频异常 D25"逻辑在模板已含 D25 时会重复 append；追加前判断 `not any(x['id']=='D25' for x in defects)` |
| docx 图提取脚本每张 docx 图片数量对不上 | PC/RDS docx 通常含 3 张有效监控图（`image2/3/4.png` 或 `image1/2/3.png`），另有 1 个 0 字节目录占位 `image1`。用通用脚本 `extract_res_correct.py <YYYYMMDD>` 提取，勿用早期的 `extract_res_0905.py` |
| 趋势 MD "数据窗口"列显示 `-` | `days/*.json` 的 `window` 字段有两种结构：历史为 `{"slowsql":"start ~ end"}`，新建为 `{"start":...,"end":...}`。`trend.py` 已加 `win_str(d)` 兼容两者 |
| 桌面趋势 MD 命名混乱（"与"/"和"混用） | 统一为历史风格 `服务器与数据库资源情况汇总_趋势_<起>_<止>.md`，放入 `桌面\服务器和数据库资源汇总\` |
| 缺陷证据计数跨日不变（如 D25 三日都是同一数字） | `finalize_XX.py` 从上一日模板 `dict(x)` 复制缺陷，靠模板顺延的条目（尤其 D25 这类后期新增项）会沿用旧 evidence。**凡由模板顺延的缺陷都要在 finalize 里显式按当日 `logscan.top_errors` 重算**；D25 用 `onerrordropped` 匹配 |
| 用户问"禅道是一个总的吗 / 中途修复的就不管了" | 默认交付是**按快照日各出一份**（只含当日未修复）；已修复不丢弃，轨迹在 `days/*.json` 的 `fixed` 与趋势 MD「缺陷跟踪」章节。如需**跨日合并总单**，跑 `tmp/make_zentao_merged.py` → `禅道导入模板_服务器与数据库资源问题_汇总_<起>_<止>.csv`。注意按日各出会让同一未闭环缺陷在禅道产生多条重复单 |
| 关键词列放什么 | 历史默认放 D 编号，但与标题的 `[Dx]` 前缀重复。用户已定**方案 B：放技术标识**（表名/类名/方法名/错误关键字/接口路径），映射固化在 `make_zentao_merged.py` 的 `KEYWORDS` 字典；未登记缺陷走 `tech_keyword()` 回退（抽 `biz_*` → 抽 `/路径/` → 截标题）。注意 xxljob 类缺陷（D15/D19）必须加限定词区分 |
| 写 CSV 报 `PermissionError` | 目标文件正被 Excel 打开。**目录可写但文件不可写**（`open(...,'a')` 同样失败）。用 `write_csv()` 降级写到 `*_技术关键词.csv` 并提示用户，勿中断脚本 |
| 禅道表交付目录 | 用户会将禅道表与趋势 MD 放在同一目录 `桌面\服务器和数据库资源汇总\`；日度 CSV 可能被用户清理，只留汇总总单。生成前先确认目标目录 |
| 需要标注缺陷归属（数据库/服务器） | 判据：**数据库** = 表级慢 SQL/索引失效（D1/D2/D3/D13/D14）、DB 连接（D4 代理、D20 HikariPool）、表结构缺字段（D5）；**服务器** = PC 端应用异常、网关/网络、定时任务、权限码、ES 同步、IGW 取文件流。同时务必核实"属于资源不足吗"：RDS CPU 低位线常仅 0-5%、PC 节点 CPU 5-20%，**资源未打满时不要写成资源问题**，否则提单会被打回。实现见 `make_zentao_merged.py` 的 `OWNER` 字典 + CSV 末尾 `问题归属` 列 |
| 用户要求按"端"分单（PC端/IGW端/其他端） | **端 = 应用服务的部署节点**，与"问题类型"是不同维度。判据：**PC端** = eibs-* 应用部署在 znly01/znly02，含 PC 端业务系统触发的慢 SQL（D1/D2/D3）；**IGW端** = 异常定义在 IGW 网关层或涉及统一认证/ISC；**其他端** = 移动端/第三方接口/网关外服务。D1/D2/D3 归属辨析：表象在数据库层但触发方是 PC 端服务，按"端"分到 PC 端、按"问题类型"分到数据库——两维度并不冲突，提单时可写"PC 端业务服务 → MySQL 慢查询，DBA 介入改 SQL/加索引"。`make_zentao_merged.py` 用 `END_TIER` 字典映射 D编号 → 端；CSV 末尾追加 `端归属` 列 |
| 用户嫌禅道单内容太薄（期望空、缺报错日志） | 回 `raw_<日期>/extracted/log/pc/<node>.log/eibs-*.log` 用 grep -B5 抓「错误关键字」前后的完整堆栈；慢SQL去 DAS 摘要 CSV 取 SQL模板原文 + 执行/扫描/返回行数。**先做失败类型分布统计（uniq -c 文件名/账号/文件头/时间段）**——高频错误常见"单一文件/单一账号/周期性时间模式"特征，能直接定位根因（如 D18=dishImg.jpg 每10分钟上传被文件头校验拒、D8=sysUserId 16912 缺组织映射）。产出物：每条给「期望（可粘贴）+ 报错日志原文 + 根因分析 + 一句话根因」四段式 |
