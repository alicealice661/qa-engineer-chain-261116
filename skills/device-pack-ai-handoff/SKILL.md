---
name: device-pack-ai-handoff
description: 把一台智能终端设备（RK3568/Android 类：出入库秤、晨检仪、留样柜、取盘机等）的自动化测试工程，改造成「同事或 AI（WorkBuddy）可直接接手」的交付包。当用户说「这个包/文件夹给别人能不能直接用」「让同事喂给 AI」「做成开箱即用」「解压到哪都能跑」时使用。覆盖六步：依赖声明、路径自适应、文档剥离本机路径、文档引用与实际文件缺口核对、写《给AI的执行说明》入口页、异路径实测。
agent_created: true
---

# 设备自动化包 → AI/同事可接手改造

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：测试工程已能跑（`device-api-layer-autotest-scaffold` + `device-e2e-flow-driver` 的产物），要交给同事或 AI 接手。
- **本技能**：六步改造 —— 缺口核对、依赖声明、路径自适应、剥离本机路径、写《给AI的执行说明》、异路径实测。
- **下一棒**：交付给接手人；后续复跑回到 `android-adb-test-monitor`。
- **别用本技能做**：① 工程本身还跑不通 → 先把 `device-e2e-flow-driver` 跑绿，移交跑不通的包只会放大问题；② 只是写操作手册 → 不在本包（用内置 docx 能力）。
- **验收判据**：换一个完全不同的路径能跑起来，才算移交完成；原地跑通不算。

## 何时用

用户有一个**设备自动化资产包**（形如 `Desktop\<设备名>\`，含 `01_手册/ 02_规范/ 03_运行资产/ 06_测试报告/` + 一个参照包），
想确认「能不能直接给别人 / 喂给 WorkBuddy 用」，或明确要求「做成开箱即用」。

**先回答结论**（不要先动手）：
- **能，但要满足 3 条件**：① 对方 AI 有**文件系统+终端**能力（WorkBuddy ✓，纯聊天窗 ✗）；② **设备/网络现场有人在**（AI 连不上设备、刷不了脸、起不了 frida-server）；③ 包里有**给 AI 的执行入口**且无"会照抄踩坑"的残留。
- 分层给结论：**接口层免设备**（最易复用）/ **界面层需同款设备** / **写库层需设备 root + frida**。
- **口径澄清（用户常追问「不是已经全流程自动化了吗，现场为啥还要人」）**：自动化 = **免人工操作步骤**，
  指「**环境就绪后**，一次跑批（接口/界面/写库/断言/报告）全程零人工点击」；而「把设备从不可跑变成可跑」
  属**环境供给/值守**，不属测试自动化。**"现场要人"= 环境供给层，不是测试执行层**，两层必须分开讲。

## 六步改造（照做）

### ① 先做缺口核对（最容易漏，优先级最高）
用**文档实际引用的工具/命令**去反查文件是否存在。典型翻车：AI 任务书引用 `tools/e2e_assert.py`，但迁包时漏了该脚本 → AI 照做必失败。
```bash
# 列出参照工程 tools 与包内 tools 的差集（找漏搬的运行必需脚本）
comm -23 <(ls 原工程/tools | sort) <(ls 包/03_运行资产/tools | sort)
# 抓脚本间调用依赖
grep -oE "[A-Za-z_0-9]+\.(py|sh)" 包/03_运行资产/tools/*.sh | sort -u
grep -n "^import \|^from " 包/03_运行资产/tools/*.py
```
补齐「被 README/任务书引用」或「属主链路/维护必需」的脚本；**逆向、一次性探针脚本不补**。

### ② 依赖声明 `requirements.txt`（包根放一份）
必须标明**分层**：哪些是必需、哪些只在特定层/工具用。
```text
# 必需（接口层+界面只读+跑批）
pytest>=7.0
pytest-html>=3.1          # 生成 reports/execution_report.html
# 写库四大分支（frida 注入）
frida>=16.0
# 部分工具
Pillow>=9.0
```
> 常见：核心框架其实**只用标准库**（urllib/hashlib/base64/subprocess/xml.etree）→ 只有 pytest 一族是硬依赖，要写清以免对方装一堆。

### ③ 路径自适应（三处，缺一不可）
**(a) `run_*.bat` 自动探测 Python + 依赖自检**（纯 ASCII + CRLF；写完用 python 转 CRLF）：
```bat
set "PY="
if defined PYTHON set "PY=%PYTHON%"
if not defined PY if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PY for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i WindowsApps') do if not defined PY set "PY=%%i"
if not defined PY if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not defined PY ( echo [ERROR] Python 3 not found. & if /i not "%~1"=="-y" pause >nul & exit /b 1 )
"%PY%" -c "import pytest, pytest_html" 2>nul
if errorlevel 1 ( echo [ERROR] Missing deps. Fix:  "%PY%" -m pip install -r requirements.txt & if /i not "%~1"=="-y" pause >nul & exit /b 2 )
```
> ⚠ **`where python` 会选中 WindowsApps 的商店 stub 或"装了但没装 pytest-html"的另一个解释器** → 必须排除 WindowsApps、且**优先 WorkBuddy venv**（通常预装齐）、并加依赖自检。这是实测踩到的最真坑。

**(b) py 工具脚本向上找工程根**（替换写死的 `ARK = "C:/Users/..."`）：
```python
def _detect_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(d, "conf")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.dirname(os.path.abspath(__file__))
        d = parent
```
> pytest 工程若 `conftest.py` 用 `ROOT = dirname(dirname(__file__))`，则 **`conf/` 必须与 `tests/` 同级** → 整个工程要放在「工程根」目录里，别学参照包把 conf 放包根。

**(c) 设备地址走环境变量**（shell + py 都要改）：
```bash
export A=${DEV:-192.168.2.246:5555}                 # .sh
DEFAULT_DEV = os.environ.get('DEV', '192.168.2.246:5555')   # .py
```
并在 README 写一句「换设备：`export DEV=<ip:port>`」。

### ④ 剥离文档里的本机路径
`grep -rn "C:/Users\|/c/Users\|Administrator\|D:\\\\adb" --include="*.md" --include="*.py" --include="*.bat" --include="*.json" .`
> **不只要改脚本，文档也要改** —— AI 读 md 会**照抄命令**。把 `"<venv>/python.exe" tools/x.py` 改成 `python tools/x.py`。
> 例外：README 的「改造记录（改前/改后）」表保留原文（历史对比），并明确标注。
> ⚠ heredoc 里 `\\` 会被吞：替换串**避免反斜杠**（把 `"...python.exe"` 换成 `python`，保留行尾的 ` \` 续行符）。

### ⑤ 写《给AI的执行说明.md》（包根，本流程的核心产出）
一页，六节：**阅读顺序 / AI 能做（命令表）/ AI 做不了（现场项）/ 换环境改哪几处 / 执行红线 / 报错速查**。
并在 `README.md` 顶部挂一行入口链接。要点：
- 「AI 做不了」必须写实：连设备、刷脸、真实称重、frida-server 重启消失需手动拉起。
- 「执行红线」写清写库闸门（`--allow-write`）、不覆盖只读基线、失败只单条重跑。

### ⑥ 异路径实测（给结论的硬证据）
复制到**完全不同的路径**再跑，不是原地跑：
```bash
SIM="${TMPDIR:-/tmp}/sim_pkg"   # 仅限临时目录
rm -rf "$SIM"                   # ⚠ 危险操作：先确认 $SIM 非空且指向临时目录，禁止写成 rm -rf / 或变量为空时执行
[ -n "$SIM" ] && mkdir -p "$SIM"
cp -r "<包>/03_运行资产" "$SIM/"
cd "$SIM/03_运行资产" && python -m pytest --collect-only -q      # 期望：N tests collected
python -c "import subprocess;print(subprocess.run(['cmd.exe','/c',r'<SIM>\...\run_smoke.bat','-y'],capture_output=True,text=True).stdout[-500:])"
python -c "import py_compile,glob;[py_compile.compile(f,doraise=True) for f in glob.glob('<包>/**/*.py')]"  # 语法 0 错
rm -rf "$SIM"   # ⚠ 危险：先确认 $SIM 是刚建的临时副本；禁止变量为空时执行，禁止对工程目录执行
```
> 原工程目录**只读+复制，不做改动**。

### ⑦ 补一个「环境自愈」入口 `ensure_env.py`（强烈推荐，把"现场那一下"压成一条命令）
覆盖**环境供给层**的全部必做项，最好还做成可定时任务：
1. `adb connect <serial>` + `ensure_online`（TCP 不通直接给结论，不吐堆栈）
2. 查 `/data/local/tmp/fs16` 是否在跑；不在则 `adb push` + `setsid /data/local/tmp/fs16 -l 0.0.0.0:27042 &`
3. 触发**按需服务**（如内嵌算法服务 `127.0.0.1:17339`）——走 App 自身入口点一次（不硬起进程）
4. 跑只读预检：后端可达 + **业务数据前提**（待验收明细 `isAcceptance=0` / 目标物料库存 / 无残留待出库单）
5. 全部就绪 → exit 0；有缺 → 打印「缺什么 + 怎么补」，**绝不静默跳过**

> 设备侧固定漂移源就两个：**`frida-server` 不自启（重启即消失）**、**按需服务不随冷启动自启**。
> 写库/刷脸/称重全部依赖前一环，所以"现场要人"绝大多数就是这两件事。

### ⑧ 传递落地（任务要求"成果落地/内部传递"时必做，最容易漏）
> 老大绩效口径：「**不存在研究成果不落地，不传递**」+「**最终成果用云库链接证明**」。
> 所以**把包做好 ≠ 任务完成**，还要有"传出去"的动作和证据：
1. **拉通总结**：一份跨设备/跨模块的《研究成果总结报告》（方法 / 通用规范版本演进 / 可复用资产清单 / 量化指标 / 踩坑与结论 / 边界与限制），放独立目录（如 `Desktop\自动化测试研究成果总结\`），**不要只留设备级报告**。
2. **把"根"收进包**：真正可复制的核心是**跨设备通用规范**（如 `AI自动化测试规范_v1.5.md`），它常在**首个研究工程**的 `规范/` 里、**没进任何交付包** → 必须显式收进拉通目录或各包。
3. **云库传递**：成果包上传云库（Seafile，`http://192.168.2.123/`）→ 生成分享链接 → 回填日报/绩效（"最终成果用云库链接证明"）。
4. **一页《传递说明》**：给谁 / 读哪份先 / 怎么验证跑通 / 边界在哪。
> 判断"任务是否完成"的三要素：**可复制（别人也能照做）· 已拉通（有总报告）· 已传递（有链接与接收方）** —— 缺任一项都只能算部分完成。

**「拉通总结」怎么写（多台设备版，实测有效）**
先**扫盘取实据**（别凭印象）：各研究工程的 《总结/结论/执行报告》+ 里程碑（日报 `工作反馈.txt`）+ 量化口径，逐项记下出处。
报告骨架：① 一句话定性 ② **研究主线时间线**（从日报抽，标"从 0 摸索 / 照规范走 + 撞了什么"）
③ **可复制性硬证据 = 两张表**：**统一不变的内核**（技术选型/骨架/分层/防失真条款，三台是否一致）+ **每台设备自己新增的约束→解法→沉淀到哪** ④ 量化汇总（用例/自动化率/稳定性/耗时/归因准确率，**每格可溯源**）
⑤ 最值钱的产出（防失真条款 + 边界红线 + 主动撤回的误判）⑥ 可复用资产清单（谁该拿哪个文件）⑦ 边界与限制 ⑧ 缺口与下一步。
> 定性句最有力的一句是：**「第二台/第三台没有重写骨架，只补了它自己的两三条约束」**——这就是可复制的证明。

## 坑清单（实测）
1. `where python` 选到商店 stub / 缺 pytest-html 的 Python → 排 WindowsApps + 优先 WorkBuddy venv + 依赖自检。
2. Write 工具产出 **LF 行尾** → bat 需转 CRLF（python 批量 `replace(b'\n', b'\r\n')`）。
3. heredoc（`<<'EOF'` 才安全）里替换串含反斜杠会被吞 → 避开反斜杠。
4. 「路径自适应」只做了一半：脚本改了，**文档/任务书里还留着本机路径** → AI 照抄。
5. 迁包漏脚本：文档引用了但包内没有（用 ① 的差集命令查）。
6. **把「全流程自动化」说成「无人值守」** → 交付文档必须写清**环境供给层仍需现场**（设备上电/网络/adb/frida-server/按需服务/数据前提），否则接手人以为插上电就能 7×24 无人跑，一重启就全红。
7. 案例（出入库秤 2026-10-16 实测）：设备在线且 `fs16` 在跑（27042 监听），但**算法服务 17339 未监听** —— 设备没重启也会漂移（按需服务）。所以预检要**逐项探测**，不能只看"能 adb 连上"就判环境 OK。
