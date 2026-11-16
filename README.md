# 测试工程师技能链 · qa-engineer-chain

从本机 21 个技能里，用达尔文的 E0 体检筛出 16 个属于测试工程师工作流的技能，按「立项 → 基准 → 接口 → 界面 → 执行 → 提单 → 移交」串成一条链路。

不含任何平台内置技能，全部是你自己的技能，未做跨来源混合。

```
21 个技能  ──E0 体检 + 域筛选──▶  16 个入选  ──补路由边界 + 补测试集──▶  一条可交付的链
```

---

## 一、链路总图

```
                        ┌─ device-auto-test-plan-authoring ── 研究计划 md
   ① 立项               │      （分层策略 / 用例分组 / 阶段 / 授权边界）
                        └─ device-acceptance-spec-scan ───── 验收规范 + 扫描结论（两个文件）
   ② 基准                    │
                             ├─▶ 不达标项 ─────────────────────────────┐
                             └─▶ 要走接口路线 ──┐                      │
                                                ▼                      │
   ③ 接口打通        apk-network-pentest-recon        接口清单 / 签名算法 / 凭据
                             │                                         │
                             ▼                                         │
                  device-api-layer-autotest-scaffold  pytest 骨架 + tests(A~E)
                             │                                         │
                             ▼                                         │
   ④ 界面跑通        selfdrawn-ui-template-locate      自绘页定位（dump 无效时）
                             │                                         │
                             ▼                                         │
                  device-e2e-flow-driver             多步流程驱动 + 双源断言
                             │                                         │
                             ▼                                         │
   ⑤ 执行取证        android-adb-test-monitor          多路监测 + 复测报告 + 回填用例表
                             │                                         │
                             ▼                                         │
   ⑥ 缺陷闭环        zentao-bug-autosubmit ──▶ zentao-cli             │
                             │  提单（CSV/JSON/junit）    查询与流转   │
                             ▼                                         ▼
   ⑦ 交付移交        device-pack-ai-handoff ──────── 开箱即用的工程包（异路径实测通过）

   ┌ 支撑技能（不占主线，按现场需要插入）───────────────────────────────┐
   │ android-component-entry-verify   判定「这个入口有没有 / 是不是死代码」│
   │ network-only-device-recon        无 adb 设备的网络侧只读侦察        │
   │ server-resource-trend-analyzer   多天资源/慢 SQL/日志趋势汇总        │
   │ springboot-jar-config-reverse    服务起不来时反推配置项              │
   │ staged-script-remote-diagnosis   连不上目标机时的分段手工排障        │
   │ seafile-anon-share-download      从 /d/<token>/ 链接拉素材           │
   └───────────────────────────────────────────────────────────────┘
```

链路的判断依据不是「技能都跟设备有关」，而是**每两个相邻技能之间存在真实的交接物**：上一棒的产出就是下一棒的输入。没有交接物的技能一律不放主线（比如 `android-component-entry-verify` 的产出是结论而不是工件，所以归支撑）。

---

## 二、筛选过程

### 入选 16 个（按阶段）

| 阶段 | 技能 | 吃进什么 | 吐出什么 |
|---|---|---|---|
| ① 立项 | `device-auto-test-plan-authoring` | 设备型号 + 业务场景 | 研究计划 md |
| ② 基准 | `device-acceptance-spec-scan` | 计划或已有需求 | 验收规范 + 扫描结论 |
| ③ 接口 | `apk-network-pentest-recon` | APK / 目标设备 | 接口清单、签名算法、凭据 |
| ③ 接口 | `device-api-layer-autotest-scaffold` | 上一棒的签名与端点 | pytest 骨架 + tests(A~E) |
| ④ 界面 | `selfdrawn-ui-template-locate` | dump 无效的界面 | 可复用定位方案 |
| ④ 界面 | `device-e2e-flow-driver` | 多步业务流程 | 可重复驱动 + 断言 |
| ⑤ 执行 | `android-adb-test-monitor` | 问题现象 / 复测需求 | 监测记录、复测报告、回填用例表 |
| ⑥ 缺陷 | `zentao-bug-autosubmit` | 缺陷清单 CSV / JSON / junit | 禅道 Bug 单 + 单号 |
| ⑥ 缺陷 | `zentao-cli` | 单号 / 查询需求 | 状态流转、进展汇总 |
| ⑦ 交付 | `device-pack-ai-handoff` | 整个测试工程 | 可移交的包 + 异路径实测结论 |
| 支撑 | `android-component-entry-verify` | 「有没有入口」类问题 | 四级定性结论 + 三线证据 |
| 支撑 | `network-only-device-recon` | 无 adb 的终端 | 侦察报告 + 漏洞清单 |
| 支撑 | `server-resource-trend-analyzer` | 多天 Seafile 链接 | 趋势 md + 禅道导入 CSV |
| 支撑 | `springboot-jar-config-reverse` | 业务 jar | 配置项清单 + Nacos 模板 |
| 支撑 | `staged-script-remote-diagnosis` | 连不上的目标机 | A~F 分段脚本 + 取证 |
| 支撑 | `seafile-anon-share-download` | 匿名分享链接 | 原始素材 |

### 排除 5 个（附理由）

| 技能 | 为什么不在链上 |
|---|---|
| `darwin-skill` | 元工具：它评估的就是 skill 本身，不是测试动作。放进链里会自我指涉（用它体检它自己所在的包）。留在 `~/.workbuddy/skills` 当常驻工具更合适。 |
| `remotion-ai-video-pipeline` | 视频创作，与被测设备、缺陷、交付都不产生交接物。 |
| `workbuddy-data-recovery` | 恢复 WorkBuddy 自身任务数据，属平台维护，不是测试域。 |
| `device-manual-docx-generation` | 面向最终用户的操作手册，不是测试产物；且走 tencent-docx 流水线，与平台内置 docx 能力抢路由。需要时单独装。 |
| `python-docx-chinese-manual` | 通用中文 docx 生成，同上，与内置 docx 重叠。 |

排除的 5 个**没有删除、没有改动**，仍在 `~/.workbuddy/skills/` 原位。

---

## 三、包级路由表

链内技能最容易出的问题是「抢同一个请求」。达尔文引用的 138K 条 skill 研究里，67% 的技能存在路由缺陷，有缺陷的首位命中率从 88.5% 掉到 82.6%。所以每个 SKILL.md 开头都加了一段 `## 链路位置`，写清上一棒 / 下一棒 / **别用本技能做什么**。包级汇总如下：

| 用户这么说 | 该走哪个 | 不要走 |
|---|---|---|
| 「照着 XX 给 YY 做个测试计划」 | `device-auto-test-plan-authoring` | 不要直接写代码 |
| 「出一份验收规范 / 把规范甩给 AI 扫设备」 | `device-acceptance-spec-scan` | 不要出用例步骤表 |
| 「还原这个 App 的接口 / 签名 / 加密」 | `apk-network-pentest-recon` | 有 adb 但只想抓日志 → 监测 |
| 「搭接口自动化骨架 / 写接口用例」 | `device-api-layer-autotest-scaffold` | 界面流程 → e2e |
| 「dump 抓不到控件怎么点」 | `selfdrawn-ui-template-locate` | dump 能用就别上模板匹配 |
| 「跑一遍完整流程 / 能不能全自动」 | `device-e2e-flow-driver` | 单接口 → 接口骨架 |
| 「接上设备看日志/触控/网络、出复测报告」 | `android-adb-test-monitor` | 要驱动点击 → e2e |
| 「这个页面有没有入口 / 是不是死代码」 | `android-component-entry-verify` | 接口清单 → 逆向 |
| 「adb 连不上，只有端口开放」 | `network-only-device-recon` | 有 adb → 逆向 |
| 「多天资源/慢 SQL/日志出趋势」 | `server-resource-trend-analyzer` | 只拉文件 → seafile |
| 「服务起不来，缺什么配置」 | `springboot-jar-config-reverse` | 只是执行命令 → 分段排障 |
| 「机器连不上，我手动敲」 | `staged-script-remote-diagnosis` | 能直连就直接跑 |
| 「把这个链接里的东西拉下来」 | `seafile-anon-share-download` | 有账号走官方客户端 |
| 「把这些 bug 提到禅道」 | `zentao-bug-autosubmit` | 只查单/改状态 → zentao-cli |
| 「查我的待办 / 关掉这个单」 | `zentao-cli` | 批量建单 → 提单技能 |
| 「这个工程给同事能不能直接用」 | `device-pack-ai-handoff` | 还没跑通就先跑通 |

三对最容易混的，边界是这样划的：

- **计划 vs 规范**：计划回答「怎么测、分几步」，规范回答「什么叫通过」。前者是策略，后者是判定基准。
- **用例 vs 评审**：本包内没有独立用例技能，`device-acceptance-spec-scan` 只出判定基准不出步骤；要出用例表请用你原有的用例类技能，别让扫描技能硬生成步骤。
- **逆向 vs 侦察**：有 adb 能拿 APK 就走 `apk-network-pentest-recon`（信息量更大）；没有 adb 才降到 `network-only-device-recon` 的只读侦察。

---

## 四、达尔文做了什么（E0 前后对比）

体检命令：

```bash
python ~/.workbuddy/skills/darwin-skill/scripts/darwin.py check ./skills -v
```

| 指标 | 修前（16 个入选技能在原位） | 修后（本包） |
|---|---|---|
| 错误 | **1**（`server-resource-trend-analyzer` 无 frontmatter，runtime 根本发现不了） | **0** |
| 警告 | 16 | **5**（3 条正文超长 + 2 条误报，理由见下） |
| 有 test-prompts.json | 0 / 16 | **16 / 16**（64 条用例 / 157 个检查项） |
| 有链路边界说明 | 0 / 16 | **16 / 16** |

### 修了什么（逐条有据）

1. `server-resource-trend-analyzer` 补 frontmatter —— 这条是硬错误，不修等于技能白装。
2. 9 处个人绝对路径（`C:\Users\Administrator\...`、`/Users/xxx/...`）改成占位符或标准命令 —— 换机器即失效，且泄露用户名。
3. `device-pack-ai-handoff` 两处 `rm -rf "$SIM"` 补「确认 + 禁止」说明 —— 命令本身只删临时副本，但原文没有边界约束，AI 照着抄容易连工程目录一起删。
4. `zentao-bug-autosubmit` 的 description 从 503 字符压到 269，触发词从第 250 字符之后提到第 69 字符 —— 部分 runtime 会截断，截断后这个技能就再也命中不了。
5. **`zentao-bug-autosubmit/scripts/config.json` 剔除出包** —— 这个文件里有明文的禅道账号与密码。E0 只查绝对路径，查不出明文凭据，是这次人工补检发现的。同时剔除 `state.json`、`提单计划_*.json`（含内网 IP 与真实缺陷数据）、截图临时件、`__pycache__`。包内改为首跑 `init_config.py` 生成。

### 保留的 5 条警告及理由（wontfix）

| 技能 | 警告 | 为什么不改 |
|---|---|---|
| `device-e2e-flow-driver` | 正文 1006 行 > 500 | 现场逐步照做的 runbook，含「喂帧注入 / 三重否证 / 溯源对照」等强连贯段落。拆成 references 会打断执行流，且**没有 E2 证据**表明拆完更好。按达尔文规矩，没有失败证据就不做体积手术。 |
| `android-adb-test-monitor` | 正文 788 行 > 500 | 同上，多路监测与取证清单是连续动作。 |
| `apk-network-pentest-recon` | 正文 778 行 > 500 | 同上，静态逆向四步存在顺序依赖。 |
| `springboot-jar-config-reverse` | 175 / 183 行「个人目录」 | **E0 误报**。这两行是 `/home/logs/<app>/` 和 Docker 容器内的 `/home/nacos/data/...`，正则 `/home/<name>/` 把容器路径当成了宿主机用户目录。改成别的写法会让命令失效，宁可不改。 |

---

## 五、证据等级（说明白，不含糊）

按达尔文的分级：

| 等级 | 含义 | 本包做到了吗 |
|---|---|---|
| **E0** | 脚本静态体检，零 token | ✅ 16/16 跑过，0 错误 |
| **E1** | 读文档评分 | ⚠️ 只用于定位缺陷和写路由边界，**不用于给分** |
| **E2** | 独立 agent 带/不带 skill 实跑对比 | ❌ 未做 |
| **E3** | 真机 / 现场 | ❌ 未做 |

所以：**本包不给 9 维总分**。没跑 E2 的分数按达尔文的规矩应写成「缺实测，不可比」，用读文档推演出来的分数等于编造那部分权重。

另外，64 条测试的 `source` 全部是 `doc`——从技能文档反推出来的题。**用文档出题考文档，测不出文档没写到的缺口。** 你手上真实跑过的请求（提过哪些单、卡在哪一步、复测报告长什么样）替换进去，这套测试才算数。

---

## 六、安装

```bash
bash install.sh --dry-run     # 先看会装什么、有没有同名冲突
bash install.sh               # 默认装到 ~/.workbuddy/skills
bash install.sh /path/to/skills
```

- 已存在的同名技能**不会被覆盖**，脚本会列出来并跳过。
- Windows 也可用 `.\install.ps1 -DryRun`，但系统默认禁止跑脚本，需要先 `Set-ExecutionPolicy -Scope Process Bypass -Force`。
- 装之前先备份原目录：`cp -r ~/.workbuddy/skills ~/.workbuddy/skills.bak`。本包 16 个技能全部来自你的原目录，装进去等于原地替换成修好的版本。

依赖：多数技能只用标准库；`apk-network-pentest-recon` 需要 `androguard`，`android-component-entry-verify` 需要 `androguard`，`zentao-bug-autosubmit` 需要 `playwright`。见 `requirements.txt`。

---

## 七、已知局限

1. **链路是设计出来的，不是测出来的。** 16 个技能各自独立开发，交接物是我按它们现有的输入/输出对齐的，没有一次真实的「从头到尾跑一遍 7 个阶段」。第一次真跑时，阶段之间的产物格式大概率要调。
2. **路由边界是写在文档里的。** 它能让 agent 读到技能时先撞上边界，但不能阻止它在没读技能前就选错——真正的验证要靠 E2 对比首轮命中率。
3. **三个超长技能没瘦身。** 见第四节的 wontfix 表。
4. **未包含用例类技能。** 你的用例能力在别处（如 `device-auto-test-plan-authoring` 的分组只是策略，不是用例表）。如果要把用例生成也并进这条链，需要另找来源并重新划边界。

---

## 八、目录结构

```
qa-engineer-chain/
├── README.md            本文件：链路、筛选、路由、证据等级
├── CHAIN.md             每阶段的交接契约（产物名/格式/验收判据）
├── CHANGELOG.md         逐条修复记录（对应 E0 证据）
├── pack.json            机器可读清单（阶段、依赖、测试集统计）
├── requirements.txt     第三方依赖
├── install.sh           安装（bash）
├── install.ps1          安装（PowerShell）
└── skills/              16 个技能，每个含 SKILL.md + test-prompts.json
```
