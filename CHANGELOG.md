# 变更记录

本包不是新写的技能，是**筛选 + 修缺陷 + 补边界 + 补测试集**的产物。下面每一处改动都能用命令复核，证据等级标注在条目末。

标记：`E0` = `darwin.py check` 静态体检；`手工` = E0 查不出、人工补检发现；`E2` = 实跑验证（本包未做，见 README 第五节）。

---

## 2026-11-16 · 建包 v1.0.0

### 一、筛选

从 `~/.workbuddy/skills` 的 21 个技能中入选 16 个，排除 5 个：

| 排除 | 理由 |
|---|---|
| `darwin-skill` | 元工具，评估的是 skill 本身，与测试动作无交接物；留在原目录当常驻工具 |
| `remotion-ai-video-pipeline` | 视频创作，与测试域无关 |
| `workbuddy-data-recovery` | WorkBuddy 平台自身数据维护 |
| `device-manual-docx-generation` | 面向终端用户的操作手册，且与平台内置 docx 能力抢路由 |
| `python-docx-chinese-manual` | 通用中文 docx 生成，同上 |

被排除的 5 个**未改动、未移动**，仍在原位。

### 二、修复（按严重度）

#### 1. 硬错误：`server-resource-trend-analyzer` 缺 frontmatter

- 原状：文件以 `# Server Resource Trend Analyzer` 开头，没有 `---` 块。runtime 读不到 `name` / `description`，**这个技能不会被发现**——等于白装。
- 改法：补 frontmatter，`description` 135 字符，触发词前置。
- 复核：`darwin.py check` 该技能错误数 1 → 0。 `E0`

#### 2. 安全：剔除明文凭据与运行态文件（E0 查不出）

- 发现：`zentao-bug-autosubmit/scripts/config.json` 含明文禅道账号与密码（形如 `"password": "<明文>"`），另有内网地址。
- 同时剔除：`state.json`（运行态）、`提单计划_*.json` ×3（含内网 IP 与真实缺陷数据）、`提报结果_*.csv` ×9（历史提单结果，含内网 bug 链接）、`_attach_*.png` / `_refreshed_*.png`（截图临时件）、`__pycache__`。
- 复核：`scripts/` 只剩 `config.example.json`、`init_config.py`、`zentao_ui_submit.py` 三个文件，包内无任何真实单号、内网地址、账号密码。
- 改法：包内只保留 `config.example.json`；SKILL.md 顶部加一条提示——包内不含 `config.json`，首跑 `init_config.py` 生成。
- 依据：darwin 的 E0 只检查绝对路径，**不检查明文密码**。这是人工补检发现的，属于工具盲区而非工具误报。 `手工`

#### 3. 个人绝对路径 9 处改占位符

| 位置 | 原文 | 改后 |
|---|---|---|
| `apk-network-pentest-recon` 第 16 行 | `C:\Users\Administrator\.workbuddy\...\python.exe` | `python`（附注固定 venv 的写法） |
| `apk-network-pentest-recon` 第 420 行 | `D="C:/Users/Administrator/Desktop/.../frida"` | `D="<留存的 frida 副本目录>"` |
| `apk-network-pentest-recon` 第 425 行 | `"C:/Users/.../python.exe" -m frida_tools.ps` | `python -m frida_tools.ps` |
| `network-only-device-recon` 第 23 行 | venv 绝对路径 | `<venv>\Scripts\python.exe` 或 `python` |
| `device-acceptance-spec-scan` 第 132 行 | `C:\Users\Administrator\Desktop\...` | `<工作区>\三坤晨检仪设备端自动化测试\` |
| `server-resource-trend-analyzer` 第 51/52 行 | 工程目录 / 桌面交付绝对路径 | `C:\Users\<user>\...` |
| `zentao-bug-autosubmit` 第 36/37 行 | `C:/Users/x/Desktop/...` | `C:/Users/<user>/Desktop/...` |
| `zentao-bug-autosubmit` 第 144 行 | 写死 venv 的 `PY=` | `PY="${PYTHON:-python}"` |
| `zentao-bug-autosubmit/scripts/init_config.py` 第 9 行 | 文档串里的示例路径 | `C:/Users/<user>/Desktop/...` |

理由：换机器即失效，且泄露用户名。`E0`

#### 4. 破坏性命令补边界（`device-pack-ai-handoff`）

- 原文两处 `rm -rf "$SIM"` 附近只有一句「原工程目录只读+复制」，没有对该命令本身的确认或禁止说明。
- 改后：
  - 建目录前：`rm -rf "$SIM"   # ⚠ 危险操作：先确认 $SIM 非空且指向临时目录，禁止写成 rm -rf / 或变量为空时执行`，并加 `[ -n "$SIM" ] && mkdir -p "$SIM"` 守卫。
  - 收尾处：`# ⚠ 危险：先确认 $SIM 是刚建的临时副本；禁止变量为空时执行，禁止对工程目录执行`。
- 事实澄清：原命令本身只删自己刚建的临时副本，**不是**真的会误删工程目录；补说明是为了让 AI 照抄时带着约束。`E0`（警告消失）

#### 5. `zentao-bug-autosubmit` description 压缩

- 原：503 字符，触发词在**第 250 字符之后**。
- 改：269 字符，触发词提到**第 69 字符**（`当用户说「提到禅道」「批量提单」...`）。
- 理由：部分 runtime 对 description 截断，截断后这个技能再也命中不了。`E0`（提示消失）

#### 6. `network-only-device-recon` 悬空引用

- 原：正文提到 `open("assets/x.js","w")`，被识别为引用不存在的文件。
- 改：`open("<输出目录>/x.js","w")`——它本来就是举例的相对路径，改成占位符避免歧义。`E0`

### 三、新增

#### 1. 每个技能加 `## 链路位置` 段（16/16）

内容固定四行：上一棒、本技能、下一棒、**别用本技能做**（含反指目标）。插在 H1 之后、正文之前，让 agent 读技能时先撞上边界。

依据：达尔文引用的 138K 条 skill 研究显示 67% 的技能有路由缺陷，有缺陷者首位命中率 88.5% → 82.6%。包级汇总见 README 第三节。

#### 2. 每个技能加 `test-prompts.json`（16/16，共 64 条 / 157 检查项）

| 技能 | 条数 | 检查项 |
|---|---|---|
| device-auto-test-plan-authoring | 4 | 14 |
| device-acceptance-spec-scan | 4 | 11 |
| apk-network-pentest-recon | 4 | 11 |
| device-api-layer-autotest-scaffold | 4 | 12 |
| selfdrawn-ui-template-locate | 4 | 11 |
| device-e2e-flow-driver | 4 | 11 |
| android-adb-test-monitor | 4 | 11 |
| android-component-entry-verify | 4 | 9 |
| network-only-device-recon | 4 | 8 |
| server-resource-trend-analyzer | 4 | 9 |
| springboot-jar-config-reverse | 4 | 9 |
| staged-script-remote-diagnosis | 4 | 9 |
| seafile-anon-share-download | 4 | 7 |
| zentao-bug-autosubmit | 4 | 9 |
| zentao-cli | 4 | 8 |
| device-pack-ai-handoff | 4 | 8 |

全部 2 dev + 2 holdout；`checks` 只写可核对的结果（「趋势列以首日为基线并标注基线日」），不写「遵循了工作流」这类不可验项。

**局限**：`source` 全部为 `doc`，是从技能文档反推的题。用文档出题考文档，测不出文档没写到的缺口。换成真实请求后这套测试才算数。

### 四、保留未改（wontfix，有理由）

| 技能 | 警告 | 理由 |
|---|---|---|
| `device-e2e-flow-driver` | 正文 1006 行 | 现场逐步照做的 runbook，喂帧注入/三重否证/溯源对照等段落强连贯，拆分会打断执行流；且无 E2 证据表明拆完更好 |
| `android-adb-test-monitor` | 正文 788 行 | 同上 |
| `apk-network-pentest-recon` | 正文 778 行 | 同上，静态逆向四步有顺序依赖 |
| `springboot-jar-config-reverse` | 175/183 行「个人目录」 | **误报**：`/home/logs/<app>/` 与 Docker 容器内 `/home/nacos/data/...` 被正则当成宿主机用户目录；改写法会让命令失效 |

---

## 后续可做

1. **替换测试集**：把真实跑过的请求填进 `test-prompts.json`，`source` 改 `real`/`user`。
2. **跑 E2**：对任一技能用 4 条测试跑「带 skill vs 裸模型」盲评，才有资格给分。
3. **补用例环节**：本链缺独立的用例生成技能（`device-acceptance-spec-scan` 只出判定基准）。
4. **进 git**：`~/.workbuddy/skills` 不是 git 仓库，进化流程只能走目录备份，没有 `git revert` 那条干净退路。
