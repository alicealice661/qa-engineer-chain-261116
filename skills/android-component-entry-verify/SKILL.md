---
name: android-component-entry-verify
description: 判定 Android APK 中某组件（Activity/Service/Receiver/Provider）是否存在入口、是否用户可达、是否死代码——用"manifest 属性（XML 解析器）+ dex 调用链 + 设备实机"三线证据坐实；并支持判定某配置项（SharedPreferences key）是"用户可配输入"还是"运行时回写的结果字段"。当需要回答"这个页面/服务有没有入口""用户能不能触发它""是不是残留死代码""LAUNCHER 是哪个页""这个配置项能不能拿来做断言基线""prefs 里的值变了是不是有人改过"时使用（如终端设备逆向体检、缺陷触发面核实、页面入口地图补实、配置漂移归因）。
agent_created: true
---

# Android 组件入口核实（三线证据）

## 链路位置（本包 qa-engineer-chain，先看这段后动手）

- **上一棒**：需求或缺陷里出现「这个页面/服务根本没有入口」「这是不是死代码」「这个配置项用户能不能改」。
- **本技能**：用 **manifest 属性 + dex 调用链 + 实机验证**（自绘页再加 UI 真实入口、SharedPreferences 加配置项身份）三线证据坐实，给四级定性。
- **下一棒**：结论直接进用例判定或 `zentao-bug-autosubmit` 提单（标题写「无入口/死代码」类结论时附证据编号）。
- **别用本技能做**：① 要网络侧接口清单/签名算法 → `apk-network-pentest-recon`；② 要跑一遍界面看能不能进 → `device-e2e-flow-driver`；③ 只想看 manifest 里有没有这个组件 → 一条 aapt 命令即可，不必走全套三线。
- **纪律**：三线缺一线只能给「疑似」，不许下「确认无入口」的结论。

## 何时用
- 判断某 Activity/Service/Receiver/Provider **有没有入口、是否用户可达、是否死代码**。
- 缺陷"是否用户可触发"要坐实（配合 v1.5 §8.5 缺陷触发面核实）。
- **给测试规范补"页面/入口地图"**：把"APK 推断的入口路径"做实为"实测坐实"。
- 逆向体检某终端 App 的功能可达性；确认哪个 Activity 是 LAUNCHER。

## 核心结论范式（四级定性）
1. **死注册**：manifest 已声明，但 **dex 中类不存在** → 实机 `am start` 抛 `ClassNotFoundException`，**并会拖崩主进程**。用户不可达，建议删注册。
2. **死代码 / 无调用点**：类存在，但全代码无调用方、无 intent-filter → 用户不可达（如 `ExitActivity`）。
3. **有内部触发但无用户入口**：仅由 socket/云推送、定时器、开机广播触发 → 用户点不到，需后端构造场景（如 `RegisterFaceInfoServer`）。
4. **用户可触发**：存在 UI 入口且能走到该分支（需实机点击坐实，不是 `am start`）。

> **铁律**：`am start` 能渲染 **≠** 用户可达。`am start` 只证"页面能启动"，入口真实性必须看 manifest 导出属性 + 代码调用点 + 实机点击。
>
> **铁律 2（2026-09-23 实测踩坑）**：**DEX 调用链 xref 只证明「代码里能拉起」，不能证明「运行时真的这样跑」**。曾据静态 xref 推断出一条 `A→B→C→D→E` 的主流程串联链路，实机端到端跑完发现 **B/C/D/E 一个都没启动**——真实流程是 `A` 一个页面的**单页状态机**（步骤条在页内切换）。
> **对策**：① 用 xref 只能得出「**候选入口**」，写出链路时必须标注证据等级（静态推断 / 运行实测）；② **凡涉及"主流程链路"的结论，一律以运行时证据为准**——`logcat` 的 `START u0{...} from uid ...` / `Displayed` 序列 + 界面截图序列；③ 单页状态机架构（自绘 UI 终端设备很常见）会让「多 Activity 串联」的推断全盘失效，**先跑一遍端到端再写链路**。

## 三线证据（缺一不可，互相交叉）
### 线 1 · manifest 组件属性（权威，先做）
- ⚠️ **用 XML 解析器，不要用正则**。正则遇"自闭合 `<activity />`"与"含 `intent-filter` 的块"混排时会截断/漏项，**同一份 manifest 两次正则解析结果可能互相矛盾**（曾据此误判 LAUNCHER）。
- ⚠️ `get_android_manifest_xml()` **返回 lxml `Element`（不是字符串）**。若解析出 0 个组件，**先怀疑脚本**（返回类型 / 命名空间 / local-name 匹配），不要急着归因解析器有盲区——实测 `<service>`/`<activity>`/`<receiver>` 都能正确解析。
- 写法（按 local-name 匹配标签与属性，兼容命名空间）：
  ```python
  from androguard.core.apk import APK
  apk = APK(path)
  root = apk.get_android_manifest_xml()
  if not hasattr(root, "iter"):
      root = root.getroot()
  local = lambda t: str(t).split("}")[-1]
  def attr(el, n):
      for k, v in el.attrib.items():
          if local(k) == n:
              return v
  for el in root.iter():
      if local(el.tag) != "activity":        # receiver / service / provider 同理
          continue
      print(attr(el, "name"), "exported=", attr(el, "exported"), "launchMode=", attr(el, "launchMode"))
      for f in el:
          if local(f.tag) == "intent-filter":
              print("   actions:", [attr(x, "name") for x in f if local(x.tag) == "action"])
              print("   cats:   ", [attr(x, "name") for x in f if local(x.tag) == "category"])
  ```
- 正则**仅用于计数粗筛**，并与 XML 结果**双向交叉验证**：
  ```python
  raw = open("manifest_dump.xml", encoding="utf-8", errors="ignore").read()
  for tag in ("activity", "receiver", "service", "provider"):
      print(f"<{tag}> 次数:", raw.count("<" + tag))
  ```
- 判定规则：
  - 有 `intent-filter` 含 `MAIN` + `LAUNCHER` → **该 Activity 是启动页**。
  - 无 `intent-filter` 且无 `exported="true"` →（targetSdk ≥ 31）**默认非导出**，外部/其他应用拉不起。
  - `android:process` 取值集合 → 判断组件挂在**主进程还是独立进程**。

### 线 2 · dex 调用链（证明"谁拉起它"）
```python
from androguard.core.apk import APK
from androguard.core.dex import DEX          # 不要用 DalvikVMFormat(raw)
from androguard.core.analysis.analysis import Analysis
apk = APK(path)
# (a) 逐指令扫描目标描述符，拿到调用原文（类引用是"类型引用"，不是 const-string！）
for x in apk.get_all_dex():
    d = DEX(x)
    for c in d.get_classes():
        for m in c.get_methods():
            body = [str(i.get_name()) + " " + str(i.get_output()) for i in m.get_instructions()]
            if any(TARGET_DESC in b for b in body):   # 如 com/face/faceidentify/server/RegisterFaceInfoServer
                print(c.name, m.get_name() + m.get_descriptor())
                for b in body:
                    if "startService" in b or "bindService" in b or "startActivity" in b or "const-class" in b:
                        print("   ", b)             # 得到调用链原文
# (b) 类级 xref_from 找"谁引用该类"，再顺藤摸瓜找上层触发（如 msgSuccess 回调）
dx = Analysis()
for x in apk.get_all_dex():
    dx.add(DEX(x))
dx.create_xref()
for c in dx.get_classes():                        # 不要 get_class()
    if getattr(c, "name", None) == TARGET_DESC:
        for r in c.get_xref_from():
            print(r[0], r[1])                     # (调用方 ClassAnalysis, MethodAnalysis)
```
- 触发链要挖到**最上层可命名的方法**（如 `FeatureActivity.msgSuccess()` = socket 云推送回调 → 说明非 UI 触发）。
- **空壳判定**：统计方法的指令数 `len(list(m.get_instructions()))`；若 `onReceive`/`onStartCommand` 只有 3~5 条指令且无字符串常量、无外部引用 → 是**空壳实现 + 不可达**，功能等于没做。

### 线 3 · 实机验证（决定性，最后做）
```bash
adb connect <ip>:5555 && adb -s <ip>:5555 get-state
# ① 死注册验证：ClassNotFound → 会崩主进程
adb -s <ip>:5555 shell am start -n <pkg>/.<SomeActivity>
adb -s <ip>:5555 logcat -d -b crash -t 400 | grep -i "ClassNotFound\|FATAL"
# ② LAUNCHER 交叉验证
adb -s <ip>:5555 shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n <pkg>/<cls>
adb -s <ip>:5555 shell dumpsys window | grep -i mCurrentFocus
# ③ 组件运行态
adb -s <ip>:5555 shell dumpsys activity services <pkg>
adb -s <ip>:5555 shell "ps -A | grep <pkg>"
# ④ 广播/服务是否被系统登记
adb -s <ip>:5555 shell "dumpsys package <pkg>" > /tmp/pkg.txt && grep -i -A3 "<ReceiverName>" /tmp/pkg.txt
```

### 线 4 · UI 真实入口（自绘页专用，判定"用户可达"）
自绘渲染页（`uiautomator dump` 只有空壳）→ 用 **截图 + 按分辨率换算坐标 + `input tap`**：
```bash
adb -s <ip>:5555 shell wm size            # 拿真实分辨率（如 1920x1080）
adb -s <ip>:5555 shell screencap -p /sdcard/x.png && adb pull /sdcard/x.png ./x.png
# 用读图工具看图，按 显示坐标 × (真实宽/显示宽) 算出 tap 坐标
adb -s <ip>:5555 shell input tap <x> <y>
adb -s <ip>:5555 logcat -d -t 800 | grep -iE "ActivityTaskManager.*(START|Displayed)"
```
- **隐藏入口**：单击无反应时试**连点 5~6 次**（常见于"版本号 → 设置"这类开发者后门）。日志里 `START u0 {cmp=...}` 是入口坐实的硬证据。
- 渲染成败用**截屏字节数**粗判：正常页 ~1.5–1.9MB / 空白页 10~12KB（不同设备基线需实测标定）。

### 线 5 · 配置项真实身份（SharedPreferences key 专用，判定"是输入还是结果"）

**适用**：拿到一个 prefs 里的 key（如 `detect_degree_rgb`），需要回答"**它是用户可配的输入项，还是程序运行时算出来的结果字段？**"——**只看 key 名和当前值永远定不了性**，必须先查读写方。

**四步坐实链**：

1. **字符串常量 xref** —— 谁引用了这个 key 字符串：
   ```python
   dx = Analysis(); [dx.add(DEX(b)) for b in apk.get_all_dex()]; dx.create_xref()
   for s in dx.get_strings():
       if s.get_value() == "detect_degree_rgb":
           for ref in s.get_xref_from():
               print(ref[0].class_name, ref[0].name)   # 通常命中 Constants.<clinit>
   ```
2. **字段引用（关键一步）** —— key 字符串往往只在 `Constants.<clinit>` 出现一次（定义处），真正用它的地方引用的是**字段**而非字符串。搜字段名：
   ```python
   # ⚠️ androguard 的 get_output() 对字段引用输出为「空格分隔」：
   #    sget-object | v1, Lcom/.../Constants;->DETECT_DEGREE_RGB Ljava/lang/String;
   # 用 "Constants;->FIELD_NAME "（末尾空格）匹配，别用冒号格式，否则全部漏掉
   if ("Constants;->%s " % FIELD_NAME) in ins.get_output():
   ```
   看每个命中点的**指令类型**：`sput`/`iput`/`setParem` = **写**；`sget`/`iget`/`getParem` = **读**。
3. **指令级 dump 定方向** —— 对读写方方法 dump 完整指令，看清**语境**：是从 UI 控件读后写回（=配置输入），还是算完就写（=结果字段）。顺带看 `Constants.<clinit>` 里的 `DEFAULT_XXX` 常量值。
4. **日志对齐实机值** —— 找该类打到日志的关键字符串（如 `"Camera angle:"`、`"Face Recognition:"`），grep 实机 logcat，确认**运行时真实读到/写入的值**与 prefs 快照能否串成时间线。

**四级定性（配置字段版）**：

| 定性 | 判据 |
|---|---|
| **纯配置输入** | 有读有写，写入来自 UI 控件；无运行时写方 |
| **纯结果字段** | 只有运行时写方（算完回写）；无读取方 → 仅供观察，**不参与断言基线** |
| **⚠️ 双向混合（最危险）** | 既有 UI 写入，**又有运行时会覆盖** → 用户设置会被静默改写 |
| **⚠️ 一字段两用/跨模块** | 被 **A 模块**回写、被 **B 模块**读取 → **跨模块污染**（实测案例：字段名义上是人脸引擎参数，却被手部相机角度每次覆盖，用户设置形同虚设） |

**实测案例（2026-09-23 三坤晨检仪 `detect_degree_rgb`）**：
一度被记为"用户人工修改"（0→180）→ 走完四步后发现是**手部相机运行时回写的显示旋转角**，0→180 只是"把无效的相机 ID `1` 改成真实的 `127`"的**连带结果**，**根本没有人工修改**。
→ **教训：prefs 里的值变了 ≠ 有人改过。先定读写方，再谈归因。** 双向混合字段若拿来做"配置漂移"告警，会产生**纯误报**。

## 环境坑（Windows + androguard）
- Python：用 venv 的 `Scripts/python.exe`（不是 `bin/python`）。
- 抑制日志：`logging.getLogger("androguard").setLevel(logging.CRITICAL)` + `loguru.logger.remove()`，或 `2>/dev/null`。
- **方法名用 `m.get_name()`**，`.name` 可能为 None（原始 DEX 对象）。
- 类定位用 `for c in dx.get_classes(): if c.name == DESC`，不要 `get_class()` / `get_classes()[DESC]`。
- 输出中文 `sys.stdout.reconfigure(encoding="utf-8")`。
- 输出被日志淹没时：把结果落盘再 grep，或 `| grep -vE "DEBUG|INFO "`。

## 输出
按"三线证据 + 四级定性"给结论：先列 manifest 事实（注册 / 导出 / intent-filter / process）→ 再列 dex 调用链原文（谁 start、有无调用点、是否空壳）→ 再列实机结果（启动成功/ClassNotFound、前台 Activity、进程）；最后定性（死注册 / 死代码 / 无用户入口有内部触发 / 用户可触发），并给出是否纳入测试范围与真实入口路径。
