---
name: device-api-layer-autotest-scaffold
description: 为一台已逆向出接口签名的智能终端设备（RK3568 Android 类：出入库秤、取盘机、晨检仪、留样柜等）搭建「接口层自动化测试骨架」（pytest + 标准库，不依赖设备与人脸）。当用户说「开工」「搭骨架」「实现自动化」「阶段 3」「把接口跑起来」「写接口用例」时使用。产出：framework/{signer,api_client,adb_driver} + pages + tests(A~E 组 marker) + conf + 双击即跑 bat + HTML 报告。
agent_created: true
---

# 设备接口层自动化测试骨架搭建

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：`apk-network-pentest-recon` 已给出签名算法、接口清单与鉴权方式；没有这一步就先回上一棒，别猜接口。
- **本技能**：产出 `framework/(signer, api_client, adb_driver)` + pages + tests(A~E)，用**标准库 + pytest**，不依赖设备与人脸。
- **下一棒**：界面补集交给 `device-e2e-flow-driver`；实机执行与取证交给 `android-adb-test-monitor`。
- **别用本技能做**：① 从零逆向接口 → 先 `apk-network-pentest-recon`；② 只有界面流程、没有接口 → `device-e2e-flow-driver`；③ 要跑完整业务流程（含物理环节）→ 也不在本技能，接口层只覆盖软件可自动部分。
- **铁律**：接口层是主力，界面层只做补集；写操作必须物理隔离（默认只读，写要显式开关）。
**前置条件**：已由 `apk-network-pentest-recon` 还原出签名算法（含两条路径与 DTO 模板）。
**本 skill 负责**：把逆向成果落地成可重复执行的 pytest 工程 —— 即「阶段 3 工程骨架」。

与相邻 skill 的分工：`device-auto-test-plan-authoring` 出计划（规划）→ **本 skill 出骨架（实现）** →
`device-e2e-flow-driver` 跑多步业务流程 / `android-adb-test-monitor` 做监测。

---

## 一、铁律：接口层是主力，界面层只做补集

规范 §3：**能下沉到接口层验证的，不放到界面层**。

判断方法：设备若卡在自绘人脸 / 权限 / 物理动作，但**签名可复现 + 后端可直连** →
业务逻辑（勾稽、分页、字段类型、边界、安全）**全部**放接口层，界面层只留三件事：
**渲染是否正常 / 交互联动 / 跨层数据一致性**。

实测比例参考（出入库秤）：**接口层 58 条 : 界面层 7 条**，且接口层 89s 内 100% 免设备。

---

## 二、骨架结构

```
<设备>设备端自动化测试/
├── framework/
│   ├── signer.py       ← 由逆向工具移植（KEY + 全部 DTO.toString 模板 + 内置样本自检）
│   ├── api_client.py   ← ★ 核心：ENDPOINTS 注册表 + 签名→请求→断言→留痕
│   ├── adb_driver.py   ← 由既有产线移植，改 3 处（见坑 ⑨）
│   └── ui_node.py      ← 原样移植（无设备耦合）
├── pages/base_page.py  ← 页面对象；入口映射写成类常量
├── tests/
│   ├── conftest.py     ← api(session,免设备) / driver(惰性,可skip) / 写闸门
│   ├── test_01_api_contract.py     # A 契约冒烟
│   ├── test_02_api_consistency.py  # B 跨接口勾稽
│   ├── test_03_api_boundary.py     # C 边界异常入参
│   ├── test_04_api_security.py     # D 安全向只读探测
│   └── test_05_ui_*.py             # E 界面层
├── conf/{api.json,device.json}
├── run_smoke.bat / run_api.bat / run_ui.bat
└── reports/  evidence/api/  evidence/ui/
```

### ENDPOINTS 注册表（代码即契约）

每个接口登记：`path` / `sign`(A 或 B) / `dto` / `write`(bool)。
用例只写 `api.query("warehouse", {...})`，不重复拼签名。
**这是把逆向结论沉淀为可维护资产的关键** —— 以后契约变了自己改一行。

---

## 三、六个必踩的坑（接口层）★

### ① 签名输入必须与发送体**逐字段对齐**（最高频失败）

服务端是**拿发送体重建**待签串再比对的，所以：

```
签名串的字段集与值  MUST ≡  发送体（不含 sign）的字段集与值
```

典型错法：只给 `canteenId/sysOrganId` 补默认值，`pageSize/warehouseName` 在签名串里
落到 `null`、发送体里是实际值 → **全部接口回「验签失败」**（但阶段 0 手搓脚本能过，
因为那边是手工全字段对齐的 —— 移植到框架时最容易丢）。

正确做法：先用 DTO 字段列表生成完整 `vals`，**再拿同一份 vals 同时**渲染签名串和发送体。

排障入口：`msg == "验签失败"` ⇒ 立刻打印 `sign_input` 与实际 body 逐字段 diff。

### ② 「验签失败」是最好的 Oracle

服务端验签 = 按该接口**约定字段集**重建 → 所以「验签失败」⇔ DTO 用错了。
**遍历全部 DTO 模板，第一个"不再验签失败"的即正确映射。**

实测价值：能反查出**接口名与 DTO 名完全对不上**的映射（如 `queryWaitOutStorageOrder → QueryInStorageDto`），
按命名猜必然错。骨架里给每个接口配一个"错误签名必须被拒"的回归用例，反向证明 oracle 仍有效。

### ③ 未导出的 Activity **不能** `am start`

实测：`EnterAndExitMainActivity`、`MaterialQueryActivity` **均 not exported**，
shell（uid=2000）启动会抛 `SecurityException: not exported from uid 10154`；
**唯一可直启的是 launcher Activity**（如 `...face.MainActivity`）。

正确路径：`am start <launcher>` → 落到主界面 → **点入口图标**进目标页。
探测方法：dump 主界面拿到所有 `iv_home_*` 入口，逐个 tap + dump，看哪个出现目标页 marker。
**把入口映射写进 `conf/device.json` 与 Page 类常量**，别每次重探。

### ④ 无 root 设备：UI dump 在动画页必失败

有实时刷新动画的页面（称重校准等）`uiautomator dump` 报 `could not get idle state`。
驱动必须**降级为截图**而不抛异常打断用例：捕获后抛 `UiNotAvailable`，
`wait_for` 内部吞掉并继续轮询，需要断言时才截图取证。

### ⑤ fixture 作用域搞错会让整套慢十倍

页面 fixture 若用 `function` 作用域，**每条用例都重启 App** → 7 条 UI 用例从 ~20s 涨到 150s+ 并超时。
正确：进页面的 fixture 用 **`module`/`session`**，用例内部各自 `switch_to` 保证起点一致。

### ⑥ 负向用例自己起 urllib → 留痕台账会自相矛盾

错签名 / 篡改 / 重放这类**负向用例**要故意构造非法报文，很自然会绕开 client 自己发
（`urllib.request` 裸调）。后果：**服务端拒绝的证据不进台账** ——
实测屏幕上打印了两次「验签失败」，会话台账却写 `sign_rejected: 0`，证据链自己打自己脸。

正确做法：client 暴露一个 **`post_raw(path, payload, label)`** ——
不做签名构造、照样**写进同一份留痕**，并给它打上 `[负向]xxx` 标签便于举证定位。
再在该 helper 里加一行防回归断言：

```python
before = len(api.calls)
r = api.post_raw(path, payload, label="[负向]错签名")
assert len(api.calls) == before + 1, "负向报文未记入留痕台账"
```

修完效果：`{'total': 67, 'ok': 60, 'sign_rejected': 2}` —— 数字与屏幕现象一致。

> 通则：**只要一个用例发了请求，就必须进留痕**，它期望成功还是失败不影响这条规则。

---

## 三·B、五个必踩的坑（界面层 / 页面对象）★

> 这几个坑的共性是：**不报错，只是慢或者"假通过"**，不看耗时和断言细节很难发现。
> 实测代价：设置页 14 条用例模块 **490s → 262s**，并修掉一整轮「全部串页」的假失败。

### ① 页面对象必须缓存 UI 层级（最烧时间的一个）

一次 `uiautomator dump` 实测 **≈2.2s**。若 `threshold()` / `face_size()` / `has()` 每个
getter 都重新 dump，一个用例轻松跑几十秒，模块直接超时。

```python
def tree(self, force=False):
    if force or self._tree is None:
        self._tree = self.d.dump_ui()
    return self._tree

def tap_id(self, id_contains, wait=1.2):
    ok = self.d.tap_id(id_contains, wait=wait)
    self.invalidate()          # ★ 任何点击/返回后必须失效
    return ok
```

### ② Activity 判定必须**全类名精确比对**，不能子串

```python
# ✗ 会撞车：算法配置页被误判成「已在设置菜单」，于是漏掉返回 → 后续每条用例全部串页
if "SettingActivity" in driver.current_activity(): ...

# ✓ 取最后一个 '/' 之后整段做等值比较
act = driver.current_activity().rsplit("/", 1)[-1]
if act == "com.ali.framework.view.activity.set.SettingActivity": ...
```

> 本包里的 `MaterialAlgorithmSettingActivity` 天然包含子串 `SettingActivity`。
> **凡是靠 Activity 名做状态判断的地方，一律精确比对。**

### ③ 「返回上一级」优先用 Activity 判定，别用 dump

子页里 `is_loaded()`（找本页 marker）会失败 → 白等一个 timeout 再 dump 一次 **≈10s/次**。
改用 Activity 判定 **≈0.15s**，仅在兜底时才回落 dump。

### ④ 两态页面（空态 / 有数据）marker 要取**交集**

同一页在不同数据状态下元素集可能完全不同：已学清单**有数据**时有
`rv_learned / tv_learned_no`，**空态**只有 `ll_learned_empty`（RecyclerView 根本不存在）。
若 marker 取 `rv_learned`，用例只在有数据时通过 → 一到空数据就假失败。

正确：marker 取两态都有的元素（如标题栏返回键），再 `if 空态 / else 有数据` 分支断言，
并把「数据从有到无」这种漂移**大声打印**出来（可能是真缺陷，如算法服务未激活）。

### ⑤ 只读纪律要做成**代码约束**，不能只靠自觉

危险控件的 id 在页面对象里**只登记、不提供点击方法**，再加一条机械校验用例：

```python
forbidden = ("reset_learning", "activate", "start_service", "upload_offline",
             "learned_delete", "take_photo", "export_learning", "import_learning", ...)
leaked = [n for n in dir(page_module) if any(f in n.lower() for f in forbidden)]
assert not leaked, f"页面对象暴露了危险动作方法：{leaked}"
```

> 这样"用例写错名字就把学习数据清了"在**结构上**不可能发生，而不是靠 review 兜。

---

## 四、写操作必须物理隔离（安全闸门）

`conf/api.json` 里 `allow_write: false`（默认）时，调用任何 `write=True` 的接口
**直接抛 `WriteNotAllowed`，连请求都不发** —— 杜绝"用例名字写错就把业务数据改了"。

配套：
- 写用例统一打 **`e2e_write`** marker；
- `conftest.py` 的 `pytest_collection_modifyitems` 在未传 `--allow-write` 时**自动 skip** 它们；
- 加一条自测用例：`test_write_gate_blocks_by_default`，断言闸门真的拦得住。

> 与"批量清零 / 库存变更不可逆"的风险隔离原则一致。

---

## 五、marker 体系（沿用全部门命名）

`smoke`（冒烟）/ `api`（接口层主力）/ `consistency`（勾稽）/ `readonly`（只读）/
`boundary`（边界）/ `security`（安全向）/ `ui`（界面层）/ `e2e_write`（写入，默认不跑）。

`conftest.py` 关键点：
- `driver` 夹具先做 **TCP 端口预检（2s）**，不可达直接 `pytest.skip` —— 否则 adb 连接重试会把整套拖到超时；
- `pytest.skip` 在 `pytest_runtest_makereport` 里要**单独判** `Skipped`，否则被误记为 failed。

---

## 六、验证闭环（做完必须三跑）

```bash
pytest -m smoke            # ① 冒烟：签名+契约（不碰设备，秒级）
pytest -m "not ui"         # ② 接口层全量（CI 用，约 2s）
pytest -m ui               # ③ 界面层（设备在线时；真机 dump 慢，分钟级）
pytest -q                  # ④ 全套（当前基线：79 passed / 2 xfailed，约 5.6min）
```

给老大交付时**务必同时给三个双击即跑的 bat**（纯 ASCII，见本 skill 第八节），
并在 README 里写清「哪个需要设备、大概多久」。

三跑全绿 + 生成 `reports/execution_report.html` 才算骨架完成。

**bat 入口**（本机约定）：纯 ASCII 内容、`chcp 65001 >nul` 置顶、`cd /d "%~dp0"`、
固定 Python 绝对路径、末尾 `pause >nul`；给 `pause` 加 `if /i not "%~1"=="-y"` 开关以便自动验证。
**验证 bat 不能在 bash 里调 `powershell.exe`/`cmd.exe`（被拦）** —— 用 Python
`subprocess.run(["cmd.exe","/c", bat, "-y"], capture_output=True)` 可绕过并拿到真实退出码。

---

## 七、纪律

- **不假装有能力**：无 root 就不写 su/frida/抓包用例；后端不可达就明确标注而不是硬跑。
- **区分"业务空态"与"失败"**：`暂无数据` 是合法业务态，只断言「验签通过 + 结构正确」。
- **失败用例先怀疑自己的期望**：字段名猜错、fixture 作用域、签名对齐 —— 三类占绝大多数。
- 真发现的缺陷（如回显服务端异常堆栈）**固化为用例并标 `xfail(reason=...)`**，别删掉。
- 交付物统一落 `Desktop\自动化测试\<设备>设备端自动化测试\`。

## 八、阶段交付物：接口层 + 界面层「合并实测记录」

全部用例跑完后，**主动**产出这一份（不等用户要）—— 老大默认期待「一个文件看懂两层实测」。
落 `recon/接口层与界面层实测记录_<日期>.md`，必含 **9 节**（照抄顺序）：

1. **〇 结论先行** —— 一张表：总结果(passed/xfailed/exit/耗时)、用例账(接口层N+界面层M)、
   接口留痕(total/ok/sign_rejected/avg_ms)、设备在线、后端直连、写操作零执行。
2. **一 分层结构与用例账** —— 每文件 × (用例数/通过/xfail)，并给**单文件 collect 数**
   （用 `pytest -o addopts="" --collect-only -q <file> | grep -c "::"` 取，别手数参数化）。
3. **二 接口层实测** —— 接口清单表(code/数据量) + 勾稽结论 + 边界现象 + 安全向探测（逐条给性质）。
4. **三 界面层实测** —— 设备基线 + 各页取值表（只读）+ **跨层一致性三处**。
5. **四 发现汇总** —— 安全向 / 健壮性 / 状态漂移，**每条挂 `test_xx::test_yy` 证据定位**。
6. **五 只读纪律** —— 明确列出未触碰的写接口与危险控件（含写闸门机制）。
7. **六 工程坑** —— 本轮暴露并已修的坑（表格：现象→修法），带改前改后量化。
8. **七 复现方式** —— 三个 bat + 命令行等价式 + 本轮产物路径（html/log/留痕 json）。
9. **八 待办** —— 剩余口子（通常就是 `e2e_write`）。

**记录铁律**：所有数字必须来自**刚跑完的日志**，不抄上次的；耗时、留痕 `session.json`
时间戳、`pytest_result.json` 三者要能对上。跑之前**先探连通性**（`adb devices` + `curl --noproxy '*'`
打后端），不通就别跑 UI 层，说明原因。

## 九、完整实例

`Desktop\自动化测试\出入库秤设备端自动化测试\` —— 共 **97 条**；接口层 `-m "not ui"` 基线
**69 passed / 5 skipped / 2 xfailed**（授权模式 72 passed / 2 skipped / 2 xfailed）；
界面层 `-m ui` 单独跑 **21 passed / 340.96s / exit 0**。
分层：接口层·业务 **60**（A契约38 + B勾稽7 + C边界9含2xfail + D安全6）
+ 接口层·学习集 **4**（H组，1 skip）+ 接口层·清单核对 **6**（I组，IApi 30 方法全表对齐）
+ 界面层 **21**（E货品查询7 + F系统设置14）+ 端到端 **6**（G组，默认跳4条）。
详见该工程 `README.md`、`recon/阶段0完成报告.md`、`recon/接口层与界面层实测记录_2026-10-10.md`、
`recon/端到端写链路实测记录_2026-10-12.md`（第八节 = learning/* 落地实录）、
`recon/IApi接口全表核对与补登_2026-10-12.md`（30 方法全表 + 名实不符 + Token 鉴权）、
`recon/界面层复跑与状态漂移复核_2026-10-13.md`（三时点漂移复核 + 跨层印证）、
`tests/test_09_registry_completeness.py`。

## 十、端到端写链路（阶段 6，`e2e_write`）

只读接口跑通后，业务上真正难的是**写入链路**。三条经验直接决定成败：

**① 两道闸门必须联动** ★
`--allow-write`（pytest CLI）只让用例"不 skip"；真正拦请求的是 `conf["allow_write"]`（json 里默认 false）。
不联动时的症状：用例跑起来了、却在 ApiClient 抛 `WriteNotAllowed`（实测踩过）。
修法 —— `conftest.api` 夹具里按 CLI 选项**同步覆盖**：
```python
conf = dict(api_conf)
if request.config.getoption("allow_write"):
    conf["allow_write"] = True
```
另外，`test_write_gate_blocks_by_default` 这类「断言闸门会拦」的用例，**授权模式下要 skip**（断言不适用）。

**② add 返回的 id ≠ confirm 要传的 id** ★★（最容易误判成"接口坏了"）
| 链路 | add 接口返回 | confirm 接口要传 | 来源 |
|---|---|---|---|
| 入库 | `detailId` | **`depositOrderId`** | `in_storage` 记录字段 |
| 出库 | `orderId` | **`outboundOrderId`** | `wait_out_storage` 记录字段 |
传错一律回 `500「……信息不存在」`。**破解法**：add 之后先查对应的"待处理列表"接口
（`in_storage` / `wait_out_storage`），dump 记录全字段，遍历 `*Id` 逐个试 confirm —— 一次就出。

**③ 回滚边界要实测标定，别假设**
| 状态 | 能否回滚 | 手段 | 残留 |
|---|---|---|---|
| 未确认 | ✅ 完全回退 | `delete_detail(detailId)` | 无（**含单据流水**） |
| 已确认 | ⚠ 库存可回滚 | 反向单据冲销 | **单据流水留痕不可删** |
实测过 `inbound_outbound` total 从 105 → 110（跑几轮用例就累积 5 条），**必须如实上报**。

**端到端用例写法（自清理）**：每个写用例 `try/finally` → `_revert()` 兜底三连
（删残留待确认 → 确认残留待出库 → 库存残留则全量出库冲销），保证**无论成败都回基线**。
断言要落在**业务事实**（库存数量 `基线→+N→回基线`），不能只看返回码。
测试数据从 `conf/api.json` 的 `e2e` 段读（专用测试物料/仓库/仓货单），**不碰业务数据**。

> 若后端是**测试环境**（用户明确），"已确认单据流水"这类平台审计留痕可作为**可接受残留**，
> 不必强行要求研发给清理接口 —— 但仍要保留 `_revert()` 把**库存**打回基线。

---

## 十一、接口「宿主判定」与「未部署」识别 ★（别把 404 当接口坏了）

处理冷门接口（学习集同步、文件上传等）时，最容易犯的错是**凭路径猜宿主**。三步坐实：

**① 从 dex 读真值，别猜** —— `RetrofitManager` 常把 base url **动态拼**出来：
```python
# work/classes27.dex -> RetrofitManager.<clinit>
BASE_URL = "http://" + prefs.get("PROJECT_SERVER", "192.168.2.171") \
                    + ":" + prefs.get("PROJECT_PORT", "18011")
```
含义：**同一个 `IApi` 实例下所有方法共用 BASE_URL**，不存在"另开一台学习服务器"。
用 androguard 直接读 `Constant` 类的静态字段真值（比 grep 字符串池可靠）：
```python
from androguard.core.dex import DEX
import loguru; loguru.logger.remove()          # 关掉 androguard 的 DEBUG 刷屏
d = DEX(open("work/classes18.dex","rb").read())
for c in d.get_classes():
    if c.get_name() == "Lcom/ali/framework/app/Constant;":
        for f in c.get_fields():
            print(f.get_name(), "=", f.get_init_value().get_value())
```
再列 `IApi` 的方法名，确认接口是否真被客户端声明：
```python
if c.get_name() == "Lcom/ali/framework/model/api/IApi;":
    for m in c.get_methods(): print(m.get_name(), m.get_descriptor())
```
> ⚠ **方法名 ≠ 路径**！列方法名只能告诉你"有这个接口"，**拿不到它挂在哪个 URL**。
> 必须进一步读 **方法注解**（见第十二节），否则会像本例一样踩坑：
> 把字符串池里的 `pushPhotoOrderInfo` 当路径、把 `registerFace` 的路径猜成 `…/registerFace`。

**② ★ 判定"未部署"必须用 bogus 对照路径** —— 这是本类设备最容易踩的陷阱：

| 请求 | 响应 | 含义 |
|---|---|---|
| `POST /app/learning/getLearningSet` | **HTTP 404** + Spring 白标 `{"timestamp":..,"status":404,"path":"/learning/getLearningSet"}` | 网关剥掉 `/app` 后无人处理 |
| `POST /learning/getLearningSet` | **HTTP 200** 但 body `{"code":500,"msg":"404 NOT_FOUND"}` | ← **HTTP 200 是假的**，别被 `curl -w %{http_code}` 骗了 |
| `POST /xyz/bogus`（对照） | 与上一行**同形** | → 路由缺失兜底，**不是**鉴权/签名问题 |

**只有"目标路径"与"随机 bogus 路径"响应同形，才能断言"未部署"**；否则可能只是签名/鉴权被拒。
判定脚本务必同时打**正对照**（一个已知可用的接口，如 `queryWarehouse` → 200）。

**③ 结论要落成两条互补用例**（既固化现状、又自动升级）：
- `xfail(strict=False)` 固化"客户端已声明、本环境未部署" → **研发一旦部署就 XPASS 自动提醒**；
- 文件型接口（流式下载 / multipart）不能进 JSON-only 的 `call()` 注册表语义，
  用独立一组用例 + `deployed=False` 标记，并配 `socket.create_connection` 可达性探针
  （设备本地回环需 `adb forward tcp:<port> tcp:<port>`，打通即自动升级为真实探测）。

**④ 写型接口（如 `uploadLearningSet`）一律不写用例**：它会改**服务端数据集**、污染其他设备，
自动化收益为负 —— 在文档里明确"不覆盖"，比写一条会闯祸的用例更专业。

---

## 十二、接口清单只认**注解**，不认字符串搜索 ★★

**血泪教训**：用 `grep` / `strings` 在 dex 里搜接口名，会搜到 **R8 的「字母序合并字符串池」** ——
它把成千上万个短字符串塞进一个大 blob 里按字典序排列，方法名/字段名/资源名混在一起：

```
...position||pushPhotoOrderInfo||put||queryAllBatchOrders...     ← 这是「方法名词典」，不是路径
/app/inventory/queryInboundAndOutbound                           ← 这才是注解里的真路径
```

**判据：真路径必带 `/`**；合并池里的是裸标识符。仅凭"字符串里有这个词 + 名字像接口"就登记，
会导致**路径全错**（本例 3 个漏项里 2 个路径需修正，1 个"疑似 SDK 残留"其实是被误判的真接口）。

### 12.1 正确姿势：读 dex 方法注解（androguard 三段链）

```python
import logging, loguru
from androguard.core.dex import DEX
loguru.logger.remove(); logging.getLogger().setLevel(logging.CRITICAL)
d = DEX(open("work/classes21.dex", "rb").read())

for c in d.get_classes():
    if c.get_name() != "Lcom/ali/framework/model/api/IApi;":
        continue
    adi = c.annotations_directory_item                  # ★ 注解不在 EncodedMethod 上！
    for it in adi.method_annotations:                   # list[MethodAnnotationsItem]
        cm = d.get_cm_method(it.get_method_idx())       # → [class, name, [desc]]
        aset = adi.CM.get_annotation_set_item(it.get_annotations_off())
        for aoi in aset.get_annotation_off_item():
            ea = adi.CM.get_annotation_item(aoi.get_annotation_off()).get_annotation()
            aname = d.get_cm_type(ea.get_type_idx())    # @POST / @GET / @Multipart / @Headers ...
            for e in ea.get_elements():
                key = d.get_cm_string(e.get_name_idx()) # "value"
                val = e.get_value().get_value()         # ← 真路径
                print(cm[1], aname.split("/")[-1].rstrip(";"), key, val)
```

**四个 API 坑（全踩过）**：
1. `EncodedMethod` **没有** `get_annotations()` → 注解在 `ClassDef.annotations_directory_item`。
2. `AnnotationsDirectoryItem.get_annotation_set_item()` **不收参数**（那是取 class 注解的）；
   取方法注解要用 **`adi.CM.get_annotation_set_item(off)`**。
3. `EncodedAnnotation` **无** `get_name()` → 用 `DEX.get_cm_type(type_idx)`；
   `AnnotationElement` **无** `get_name()` → 用 `DEX.get_cm_string(name_idx)`。
4. 方法名用 `DEX.get_cm_method(idx)`（返回 `[class, name, descriptor]`），
   `get_methods_id_item(idx).get_name()` 在部分版本会失败。

> 把解出的全表**固化成 oracle 常量**写进用例（本例 `IAPI_METHOD_PATHS` 30 条），
> 双向断言：注册表 ⊇ oracle（无遗漏）**且** 注册表 ⊆ oracle（无臆造/拼写错）。

### 12.2 三个衍生事实（都值得单独记一笔）

**① 名实不符是常态，别按名字猜路径**
| 方法名 | 真实 `@POST` 路径 |
|---|---|
| `registerFace` | `/app/sample/queryCanteenEmployeeInfo` ← 字面看像"查询" |
| `wait_out_storage`（注册表键） | `/app/inventory/queryWaitOutStorageOrder`，且 DTO 是 `QueryInStorageDto` |

→ 遇"名字与语义不符"的接口，**必须写一条用例把这件事固化**（含"路径中不含方法名"的断言），
否则下一个人一定会再猜错一次。同时用 `write=True/False` 纠正语义（`registerFace` 是写，不是查）。

**② 注解会暴露"另一套鉴权体系"**
本例 `pushPhotoOrderInfo` = `@Multipart @POST /file/uploadAndSync`，**路径在业务前缀之外**，
实测无 token 直接 `401「令牌不能为空」` —— 与其余接口「body 内 sign、无 header」**是两套体系**。
→ 注解里同时出现 `@Multipart`/`@Streaming`/非常规路径前缀，就该单独探一次鉴权模型。

**③ `@GET`/`@Streaming` 的接口进不了 JSON-only 的 `call()`**
注册表若统一假设 POST + JSON，会把 `downloadLearningSet`（`@GET` + `@Streaming`）写成错的。
→ 给注册表加 `transport` / `supported` 字段：**不能调的接口照样登记**（清单完整），
但 `call()`/`post_raw()` 前置拦截 `supported=False`（比写闸门更根本：授权了也不该调）。

### 12.3 对照实验的前缀铁律（与第十一节配套）

同一后端，三种"路由不存在"的响应完全不同：

| 请求 | HTTP | 响应 |
|---|---|---|
| `/app/xyz/bogus` | **404** | Spring 白标 `{"status":404,"error":"Not Found"}` |
| `/xyz/bogus`（**无** `/app`） | **200** | `{"code":500,"msg":"404 NOT_FOUND"}`（网关兜底） |
| `/app/inventory/queryWarehouse`（正对照） | 200 | 正常业务响应 |

→ **对照路径必须与被测路径同前缀**。拿"网关兜底 200"去比"框架白标 404"，
会把"未部署"误判成"已部署"，或反过来。**判定"未部署" = 同前缀 bogus 同形 + 正对照可用**。

---

## 十三、UI 观测异常的复核纪律：暂时态 ≠ 持久缺陷 ★

界面层跑出的异常态（**空列表 / 「加载失败」/ 授权或激活态掉了**）**极易误报**。
实测教训：某设备 10-08 观测到「设备激活=已激活 + 已学清单 50 种」，
10-10 变成「未激活 + 空态"加载失败,请检查算法服务"」，两条方向一致、看着像同一根因的真缺陷；
**10-13 复跑，两项全部自行恢复**（已激活 + 有数据）—— 说明 10-10 只是**服务/激活态尚未就绪的窗口**。

**判据（定缺陷前必走）**：

| 步骤 | 做法 |
|---|---|
| ① 同一条用例**跨时点复跑 ≥2 次** | 单次观测只能记「现象」，不能定「缺陷」 |
| ② 检查**伴随状态** | 本例：算法服务本身**一直「已启动」**，只有激活态掉 → 指向"激活握手"而非"服务挂了" |
| ③ 抓**设备侧日志**（`logcat`）与**服务就绪时序** | 设备刚开机 / 服务重启窗口内的异常，多半是时序问题 |
| ④ 复现不了 → **降级为「观察项」**，不占缺陷单 | 写明触发条件；"再复现 + 伴随文案"才升级上报 |

> 反面教材：把 10-10 那次当缺陷转研发 —— 研发复现不了，反噬测试的可信度。
> 一条铁律：**「一次观测 = 现象；两次以上同向复现 = 才叫证据」**。

**顺带的高价值副产品**：UI 文本常与接口层结论**互证**，能一次性闭合悬案 ——
例：「学习集=未同步」≡ 服务端 `learning/*` 未部署（404 对照同形）；
「算法服务已启动 @`127.0.0.1:17339`」≡ 该服务在**设备本地**存活，PC 侧探测不到属正常。
**做 UI 复跑时顺手找这类互证点，比多跑10条用例更值钱。**
