# -*- coding: utf-8 -*-
"""
禅道 Bug 自动提单（UI 自动化 · 禅道开源版 18.7 实测版）

字段口径（老大 2026-10-21/22 定稿）：
  所属产品  ID=4  智慧后勤服务保障系统智能楼宇子系统（二期）-开发实施项目（页面默认，不动）
  所属模块  /（一律不动）
  所属项目  210 = 二期-开发实施项目
  影响版本  主干（picker 组件，value=trunk）
  当前指派  yangxiaowei = Y:杨小伟
  反馈者    杨昌华（文本框）
  Bug类型   codeerror 代码错误（默认）
  标题      <端前缀>——<缺陷标题>
  重现步骤  步骤 / 结果 / 期望 三段（期望优先用清单里的「解决方案建议」替代）
  附件      有图才传（页面限制 50M）
  其余      一律留空；严重程度/优先级保持页面默认值

用法：
  python zentao_ui_submit.py --dry-run                  # 只看三段切分和标题，不开浏览器
  python zentao_ui_submit.py --submit --only ZH-SEC-01  # 单条试提
  python zentao_ui_submit.py --submit                   # 全部
"""
import argparse
import csv
import html as H
import json
import os
import re
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.environ.get("ZENTAO_CFG") or os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.environ.get("ZENTAO_STATE") or os.path.join(BASE_DIR, "state.json")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

SEV_TO_LEVEL = {"严重": "严重", "致命": "严重", "高": "高危", "中": "中危", "低": "低危",
                "高危": "高危", "中危": "中危", "低危": "低危"}


def load_cfg(path=None):
    with open(path or CFG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg.setdefault("headless", True)
    cfg.setdefault("interval", 5)
    cfg.setdefault("end", "attack")
    cfg.setdefault("attack_default_level", "中危")
    cfg.setdefault("use_proxy", False)
    cfg.setdefault("dup_pages", 4)
    cfg.setdefault("devices", {})
    cfg["_cfg_path"] = path or CFG_PATH
    return cfg


# ---------------------------------------------------------------- 标题
# 四档前缀：测试PC端 / 测试APK端 / 测试IGW端 / 【X危】网络安全攻防
# 端类型优先级：CSV 的「端类型」列（逐条） > config.end（全局兜底）
END_ALIASES = {
    "PC": "PC", "PC端": "PC", "测试PC端": "PC", "电脑端": "PC", "WEB": "PC", "WEB端": "PC",
    "APK": "APK", "APK端": "APK", "测试APK端": "APK", "安卓": "APK", "安卓端": "APK",
    "APP": "APK", "移动端": "APK", "手机端": "APK",
    "IGW": "IGW", "IGW端": "IGW", "测试IGW端": "IGW", "网关": "IGW", "智能网关": "IGW",
    "ATTACK": "attack", "攻防": "attack", "攻击": "attack", "安全": "attack",
    "网络安全攻防": "attack", "渗透": "attack",
}


def norm_end(v, default="attack"):
    """把各种写法的端类型归一成 PC / APK / IGW / attack"""
    s = (v or "").strip()
    if not s:
        return default
    key = s.upper().replace(" ", "").replace("－", "-")
    by_upper = {k.upper(): val for k, val in END_ALIASES.items()}
    if key in by_upper:
        return by_upper[key]
    # 包含关系兜底（「测试PC端」「APK-测试」这类）
    if any(x in s for x in ("攻击", "攻防", "安全", "渗透")):
        return "attack"
    if "IGW" in key or "网关" in s:
        return "IGW"
    if "APK" in key or "安卓" in s or "APP" in key or "移动" in s:
        return "APK"
    if "PC" in key or "WEB" in key or "电脑" in s:
        return "PC"
    return default


def end_summary(plan):
    """按最终标题前缀统计各端分布，让 --dry-run 能一眼看出每档打了几条"""
    from collections import Counter
    c = Counter()
    for p in plan:
        t = p["title"]
        if t.startswith("测试PC端"):
            c["测试PC端"] += 1
        elif t.startswith("测试APK端"):
            c["测试APK端"] += 1
        elif t.startswith("测试IGW端"):
            c["测试IGW端"] += 1
        else:
            c["网络安全攻防"] += 1
    order = ["测试PC端", "测试APK端", "测试IGW端", "网络安全攻防"]
    return " / ".join(f"{k} {c[k]}条" for k in order if c[k]) or "无"


def auto_hints(plan, cfg, end_arg=None):
    """自动来源（json/junit）的额外提醒：端类型没法自动判断、缺截图的证据不足"""
    if not plan:
        return
    src = plan[0].get("source")
    if src == "junit" and not end_arg:
        print(f"      ⚠ junit 里没有端类型信息，现按 config.end={cfg.get('end')} 打前缀；"
              f"若这些不是安全类用例，请加 --end PC / APK / IGW")
    if src in ("json", "junit"):
        low = sum(1 for p in plan if not p["attachments"])
        if low:
            print(f"      ⚠ {low} 条无截图：自动来源建议先补图，否则证据不足")


def pick_device(job, cfg, end):
    """设备名 / 系统名：CSV 的「设备名」列（逐条） > config.devices[end]（按端兜底） > 空

    标题规范：测试APK端——<设备名> <原标题>，如「测试APK端——出入库秤 同步进度文案矛盾」
              测试PC端——<系统名> <原标题>，如「测试PC端——智慧后勤系统 在线用户列表未鉴权」
    """
    d = str(job.get("device_raw") or "").strip()
    if d:
        return d
    m = cfg.get("devices") or {}
    for k in (end, end.upper(), end.lower()):
        v = str(m.get(k) or "").strip()
        if v:
            return v
    return ""


def build_title(job, cfg):
    # CSV 有逐条端类型就用逐条的，否则退回全局 config.end
    end = norm_end(job.get("end_raw") or cfg.get("end"), norm_end(cfg.get("end"), "attack"))
    lv = SEV_TO_LEVEL.get((job.get("severity_raw") or "").strip(), cfg["attack_default_level"])
    if end == "PC":
        prefix = "测试PC端"
    elif end == "APK":
        prefix = "测试APK端"
    elif end == "IGW":
        prefix = "测试IGW端"
    else:
        prefix = f"【{lv}】网络安全攻防"

    dev = pick_device(job, cfg, end)
    t = job["title"].strip()

    # ① 标题已带规范前缀：只在缺设备名时补插，不重复加前缀
    mo = re.match(r"^(测试PC端|测试APK端|测试IGW端|【[^】]{1,4}】网络安全攻防)\s*——?\s*(.*)$", t)
    if mo:
        head, rest = mo.group(1), mo.group(2).strip()
        if dev and rest and not rest.startswith(dev):
            return f"{head}——{dev} {rest}"
        return t

    # ② 编号前缀（ZH-SEC-01 之类）去掉
    t = re.sub(r"^[A-Z]{2,}-[A-Z]{3}-\d+\s*", "", t)

    # ③ 组装：前缀——[设备名 ]标题；标题本身已以设备名开头时不重复
    #    攻防端只在显式给了设备名时才加
    if dev and not t.startswith(dev):
        return f"{prefix}——{dev} {t}"
    return f"{prefix}——{t}"


# ---------------------------------------------------------------- 三段切分
# 只有「行首箭头」或「箭头后紧跟状态码/JSON」才算实测返回行；
# 排除「系统管理 → 用户管理」这类菜单路径箭头
RESULT_PAT = re.compile(r"^\s*→|→\s*(HTTP|http|code\s*=|状态码|2\d\d|4\d\d|5\d\d|\{)")


def split_steps(raw, solution=""):
    """步骤 / 结果 / 期望 三段。
    - 步骤：'预期结果/期望' 之前的正文
    - 结果：正文里实测返回的行（行首 → 或 → 后跟状态码），去序号、去重、最多 6 条
    - 期望：优先用「解决方案建议」，否则用 '预期结果：' 后面的内容
    """
    raw = (raw or "").replace("\r\n", "\n").strip()
    m = re.search(r"(?m)^\s*[【\[]?\s*(预期结果|期望|预期)\s*[】\]]?\s*[：:]\s*", raw)
    if m:
        body = raw[:m.start()].strip()
        tail = raw[m.end():].strip()
    else:
        body, tail = raw, ""

    res_lines = []
    for ln in body.split("\n"):
        s = ln.strip()
        if s and RESULT_PAT.search(s):
            s = re.sub(r"^[-•\s]*", "", s)
            s = re.sub(r"^\d+\s*[\.\)、]\s*", "", s)
            s = re.sub(r"^→\s*", "", s)
            if s and s not in res_lines:
                res_lines.append(s)
    result = "；".join(res_lines[:6])[:600]

    expect = (solution or "").strip() or tail
    return {"步骤": body, "结果": result, "期望": expect}


def to_html(seg):
    out = []
    for name in ("步骤", "结果", "期望"):
        body = (seg.get(name) or "").strip()
        if not body:
            continue
        out.append(f"<p>{name}：</p>")
        in_ol = False
        li_open = False
        p_open = False

        def close_p():
            nonlocal p_open
            if p_open:
                out.append("</p>")
                p_open = False

        for para in body.split("\n"):
            s = para.strip()
            if not s:
                # 空行只切 <li>，不关 <ol>：否则下一步会新开 ol，序号从 1 重排
                if li_open:
                    out.append("</li>")
                    li_open = False
                close_p()
                continue
            mo = re.match(r"^(\d+)\s*[\.\)、]\s*(.*)$", s)
            if mo:
                close_p()
                if li_open:
                    out.append("</li>")
                    li_open = False
                if not in_ol:
                    n = max(1, min(int(mo.group(1)), 99))
                    out.append(f'<ol start="{n}">')
                    in_ol = True
                out.append(f"<li>{H.escape(mo.group(2))}")
                li_open = True
            elif li_open:
                # 缩进续行并入上一条 li，不再另起段落
                out.append(f"<br>{H.escape(s)}")
            elif p_open and para[:1] in (" ", "\t"):
                # 缩进续行并入上一段
                out.append(f"<br>{H.escape(s)}")
            else:
                close_p()
                if in_ol:
                    out.append("</ol>")
                    in_ol = False
                out.append(f"<p>{H.escape(s)}")
                p_open = True
        if li_open:
            out.append("</li>")
        if in_ol:
            out.append("</ol>")
        close_p()
    return "".join(out)


# ---------------------------------------------------------------- 清单
# 上游可以是人工整理的 CSV，也可以是自动化跑出来的 JSON / junit.xml
# 统一收敛成同一份 job 结构，后面的三段切分、抓图、提单全都不变。
JOB_FIELDS_CN = {"编号": "no", "标题": "title", "Bug标题": "title",
                 "严重程度": "severity_raw", "风险等级": "severity_raw", "等级": "severity_raw",
                 "端类型": "end_raw", "终端": "end_raw", "所属端": "end_raw", "测试端": "end_raw",
                 "设备名": "device_raw", "设备": "device_raw", "终端名称": "device_raw",
                 "系统名": "device_raw", "所属系统": "device_raw", "系统": "device_raw",
                 "重现步骤": "steps_raw", "解决方案建议": "solution"}

# 自动化来源没有人工判级，这里用关键字给一个启发式档位（可在 JSON 里显式覆盖）
SEV_HINTS = [
    ("严重", ("数据泄露", "明文", "越权", "未授权", "未鉴权", "崩溃", "crash", "注入", "绕过", "提权")),
    ("高", ("500", "traceback", "exception", "错误", "失败", "不可用", "丢失", "重复扣", "负数", "泄露")),
    ("低", ("文案", "错别字", "样式", "颜色", "对齐", "间距", "提示语", "拼写")),
]


def guess_severity(text, default="中"):
    t = (text or "").lower()
    for lv, kws in SEV_HINTS:
        if any(k in t for k in kws):
            return lv
    return default


def read_jobs_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("[FATAL] CSV 无数据")

    def pick(r, *names):
        for n in names:
            if n in r and r[n] not in (None, ""):
                return str(r[n])
        return ""

    jobs = []
    for i, r in enumerate(rows, 1):
        no = pick(r, "编号").strip() or f"ROW{i}"
        title = pick(r, "标题", "Bug标题").strip()
        if not title:
            raise SystemExit(f"[FATAL] 第 {i} 行缺标题")
        jobs.append({
            "no": no,
            "title": title,
            "severity_raw": pick(r, "严重程度", "风险等级", "等级"),
            "end_raw": pick(r, "端类型", "终端", "所属端", "测试端", "端"),
            "device_raw": pick(r, "设备名", "设备", "终端名称", "系统名", "所属系统", "系统"),
            "steps_raw": pick(r, "重现步骤"),
            "solution": pick(r, "解决方案建议"),
            "evidence": [],
            "auto": False,
        })
    return jobs


def read_jobs_json(path):
    """自动化测试产出的结构化结果（最推荐的自动入口）。

    格式（数组，或 {"findings":[...]} / {"bugs":[...]} 包装均可）：
    [
      {"no": "AUTO-01",          # 可省，省了按 AUTO-001 顺序编号
       "title": "…",             # 必填
       "severity": "高",         # 可省，省了按关键字启发式
       "end": "PC",              # 可省，省了用 config.end
       "steps": "1. …\\n→ code=200 …",   # 重现步骤，带 → 的行会进「结果」段
       "solution": "…",          # 可省，当作「期望」段
       "evidence": ["C:/…/a.png"]}  # 截图绝对路径，可省
    ]
    字段名同时认中文键（标题/严重程度/端类型/重现步骤/解决方案建议）。
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for k in ("findings", "bugs", "items", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    if not isinstance(data, list) or not data:
        raise SystemExit("[FATAL] JSON 无有效条目（应为数组或 {findings:[...]}）")

    def g(d, *names):
        for n in names:
            v = d.get(n)
            if v not in (None, ""):
                return v if not isinstance(v, (list, dict)) else v
        return ""

    jobs = []
    for i, d in enumerate(data, 1):
        if not isinstance(d, dict):
            continue
        title = str(g(d, "title", "标题", "Bug标题") or "").strip()
        if not title:
            continue
        ev = g(d, "evidence", "screenshots", "截图", "附件") or []
        if isinstance(ev, str):
            ev = [ev]
        jobs.append({
            "no": str(g(d, "no", "编号", "code") or f"AUTO-{i:03d}").strip(),
            "title": title,
            "severity_raw": str(g(d, "severity", "严重程度", "风险等级") or
                                 guess_severity(title + " " + str(g(d, "steps", "重现步骤")))),
            "end_raw": str(g(d, "end", "端类型", "终端") or ""),
            "device_raw": str(g(d, "device", "设备名", "设备", "系统名", "system") or ""),
            "steps_raw": str(g(d, "steps", "重现步骤") or ""),
            "solution": str(g(d, "solution", "解决方案建议", "expect") or ""),
            "evidence": [str(x) for x in ev if x],
            "auto": True,
        })
    if not jobs:
        raise SystemExit("[FATAL] JSON 里没有带 title 的条目")
    return jobs


def read_jobs_junit(path):
    """pytest / jest 的 junit.xml：把失败用例转成待提单条目。

    只取 <failure>/<error> 的用例；通过的用例不进提单池。
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        raise SystemExit(f"[FATAL] junit.xml 解析失败：{e}")

    jobs, n = [], 0
    for tc in root.iter("testcase"):
        fail = tc.find("failure")
        if fail is None:
            fail = tc.find("error")
        if fail is None:
            continue
        n += 1
        name = tc.get("name") or f"case{n}"
        cls = tc.get("classname") or ""
        msg = (fail.get("message") or "").strip()
        body = (fail.text or "").strip()

        # 标题：用例名去掉 test_ 前缀、下划线换空格，再接断言摘要
        human = re.sub(r"^test_?", "", name).replace("_", " ").strip() or name
        head = (msg.splitlines()[0] if msg else "").strip()[:80]
        head = re.sub(r"^(AssertionError|assert|Error|Exception|Failed):\s*", "", head).strip()
        title = f"{human}：{head}" if head else human

        # 步骤：定位到用例 + 断言摘要；结果行用 → 标记（split_steps 认这个）
        steps = [f"1. 执行自动化用例 {cls}::{name}" if cls else f"1. 执行自动化用例 {name}"]
        if msg:
            steps.append(f"2. 断言失败：{head}")
        keys = []
        for ln in body.splitlines():
            s = ln.strip()
            if not s:
                continue
            if re.search(r"(AssertionError|assert |Expected|expect\(|Traceback|Error:)", s):
                keys.append(s[:180])
            if len(keys) >= 4:
                break
        for k in keys:
            steps.append(f"→ {k}")
        steps.append("预期结果：该用例应通过（详见断言与实际返回的差异）")

        jobs.append({
            "no": re.sub(r"[^A-Za-z0-9_.-]", "_", f"{cls.split('.')[-1]}.{name}" if cls else name)[:60],
            "title": title,
            "severity_raw": guess_severity(f"{title} {body}"),
            "end_raw": "",
            "device_raw": "",
            "steps_raw": "\n".join(steps),
            "solution": "",
            "evidence": [],
            "auto": True,
        })
    if not jobs:
        raise SystemExit("[FATAL] junit.xml 里没有失败用例（failure/error），无需提单")
    return jobs


def load_jobs(src):
    """按扩展名分派：.csv / .json / .xml(junit)"""
    ext = os.path.splitext(src)[1].lower()
    if ext in (".json",):
        return read_jobs_json(src), "json"
    if ext in (".xml",):
        return read_jobs_junit(src), "junit"
    return read_jobs_csv(src), "csv"



def match_shots(no, ev_dir):
    if not ev_dir or not os.path.isdir(ev_dir):
        return []
    key = (no or "").upper()
    return [os.path.join(ev_dir, f) for f in sorted(os.listdir(ev_dir))
            if f.lower().endswith(IMG_EXT) and key and key in f.upper().replace(" ", "")]


def build_plan(cfg, src, only=None):
    jobs, kind = load_jobs(src)
    if only:
        keep = {x.strip().upper() for x in only.split(",") if x.strip()}

        def _hit(no):
            """支持三种写法：完整编号、尾号简写（04）、中段简写（SEC-04）"""
            u = (no or "").upper()
            return any(u == k or u.endswith("-" + k) for k in keep)

        sel = [j for j in jobs if _hit(j["no"])]
        if not sel:
            sample = "、".join(j["no"] for j in jobs[:5]) or "（清单为空）"
            raise SystemExit(f"[FATAL] --only 未匹配到任何编号：{only}\n"
                             f"        清单里的编号示例：{sample}")
        jobs = sel
    plan = []
    for j in jobs:
        seg = split_steps(j["steps_raw"], j["solution"])
        # 优先用条目自带的截图路径（JSON 显式给的），否则按编号去 evidence_dir 匹配
        shots = [p for p in (j.get("evidence") or []) if os.path.isfile(p)]
        miss = [p for p in (j.get("evidence") or []) if not os.path.isfile(p)]
        for m in miss:
            print(f"  [WARN] {j['no']} 证据文件不存在，已跳过：{m}")
        plan.append({
            "no": j["no"],
            "title": build_title(j, cfg),
            "device": pick_device(j, cfg, norm_end(j.get("end_raw") or cfg.get("end"),
                                                   norm_end(cfg.get("end"), "attack"))),
            "seg": seg,
            "steps_html": to_html(seg),
            "attachments": shots or match_shots(j["no"], cfg.get("evidence_dir", "")),
            "auto": bool(j.get("auto")),
            "source": kind,
        })
    return plan


# ---------------------------------------------------------------- 浏览器 JS
JS_SET_SELECT = r"""(args) => {
  const [id, val] = args;
  const $ = window.jQuery, el = document.getElementById(id);
  if (!el) return {ok: false, err: 'no #' + id};
  if ($) {
    $(el).val(val);
    try { $(el).trigger('chosen:updated'); } catch (e) {}
    try { $(el).trigger('liszt:updated'); } catch (e) {}
    $(el).trigger('change');
  } else {
    el.value = val;
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return {ok: true, val: el.value};
}"""

JS_SET_STEPS = r"""(html) => {
  const ta = document.querySelector('#steps');
  const r = {ta: !!ta, ke: false, keCount: 0};
  if (ta) ta.value = html;
  const inst = (window.KindEditor && KindEditor.instances) ? KindEditor.instances : [];
  r.keCount = inst.length;
  for (const e of inst) {
    try { if (e.textarea && e.textarea[0] === ta) { e.html(html); r.ke = true; } } catch (err) {}
  }
  if (!r.ke && inst.length) { try { inst[0].html(html); r.ke = 'fallback'; } catch (err) {} }
  return r;
}"""

JS_PICK_BUILD = r"""(value) => {
  const opts = Array.from(document.querySelectorAll('a.picker-option'));
  const hit = opts.find(a => (a.getAttribute('data-value') || '') === value);
  if (!hit) return {ok: false, seen: opts.map(a => a.getAttribute('data-value'))};
  hit.click();
  return {ok: true, text: (hit.innerText || '').trim()};
}"""


def launch(cfg, p):
    args = ["--ignore-certificate-errors", "--no-sandbox", "--disable-gpu"]
    if not cfg["use_proxy"]:
        args += ["--no-proxy-server", "--proxy-bypass-list=*"]
    b = p.chromium.launch(channel="msedge", headless=cfg["headless"], args=args)
    kw = {"viewport": {"width": 1600, "height": 1500}, "ignore_https_errors": True}
    if os.path.exists(STATE_PATH):
        kw["storage_state"] = STATE_PATH
    return b, b.new_context(**kw)


def ensure_login(page, ctx, cfg):
    base = cfg["base_url"].rstrip("/")
    page.goto(base + "/index.php", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1200)
    if page.locator("#account").count() or "user-login" in page.url:
        print("  [登录] 会话失效，重新登录…")
        if page.locator("#account").count() == 0:
            page.goto(base + "/index.php?m=user&f=login", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        page.fill("#account", cfg["account"])
        page.fill("#password, input[name=password]", cfg["password"])
        page.locator("button[type=submit], #submit, .btn-primary").first.click()
        page.wait_for_timeout(3000)
        if page.locator("#account").count():
            raise RuntimeError("登录失败：检查账号密码 / 是否需要验证码")
        print("  [登录] OK")
    ctx.storage_state(path=STATE_PATH)


def open_create(page, cfg):
    url = f"{cfg['base_url'].rstrip('/')}/bug-create-{cfg['product_id']}-0-0-0.html"
    page.goto(url, wait_until="networkidle", timeout=40000)
    page.wait_for_timeout(2000)
    fr = page.frame(name="app-qa")
    if fr is None:
        raise RuntimeError("找不到 app-qa iframe（页面结构变了？）")
    if fr.locator("#title").count() == 0:
        raise RuntimeError("提 Bug 页没有 #title（权限不足或页面改版）")
    return fr


def block_customfields_reload(page):
    """拦掉 custom-ajaxSaveCustomFields：它的响应体是
    <script>parent.location.reload(true)</script>，点保存时会把已填内容全冲掉。
    该接口只保存「字段显示偏好」，拦掉不影响建单，还能让禅道走自己的 multipart 提交（附件才带得上）。
    """
    try:
        page.route("**/custom-ajaxSaveCustomFields*",
                   lambda route: route.fulfill(status=200, content_type="text/html", body=" "))
        page.route("**/ajaxSaveCustomFields*",
                   lambda route: route.fulfill(status=200, content_type="text/html", body=" "))
        return True
    except Exception as e:
        print("  [WARN] 拦截自定义字段接口失败:", e)
        return False


def fill_one(page, fr, cfg, job):
    fr.evaluate(JS_SET_SELECT, ["project", str(cfg["project_id"])])
    page.wait_for_timeout(2000)

    fr.click("#pk_openedBuild-search")
    page.wait_for_timeout(1500)
    r = fr.evaluate(JS_PICK_BUILD, cfg["build_value"])
    if not r.get("ok"):
        raise RuntimeError(f"影响版本没找到 {cfg['build_value']}，可见项={r.get('seen')}")
    page.wait_for_timeout(800)
    if fr.evaluate("() => document.querySelector('#openedBuild').value") != cfg["build_value"]:
        raise RuntimeError("影响版本未生效")

    fr.evaluate(JS_SET_SELECT, ["assignedTo", cfg["assigned_to"]])
    fr.evaluate(JS_SET_SELECT, ["type", cfg["bug_type"]])
    fr.fill("#feedbackBy", cfg["feedback_by"])
    fr.fill("#title", job["title"])
    fr.evaluate(JS_SET_STEPS, job["steps_html"])
    page.wait_for_timeout(1000)

    if job["attachments"]:
        fr.set_input_files("#file-input-multiple", job["attachments"])
        page.wait_for_timeout(2500)

    return fr.evaluate("""() => ({
        product: document.querySelector('#product').value,
        module: document.querySelector('#module').value,
        project: document.querySelector('#project').value,
        build: document.querySelector('#openedBuild').value,
        assignedTo: document.querySelector('#assignedTo').value,
        type: document.querySelector('#type').value,
        feedbackBy: document.querySelector('#feedbackBy').value,
        severity: document.querySelector('#severity').value,
        pri: document.querySelector('#pri').value,
        title: document.querySelector('#title').value,
        stepsLen: (document.querySelector('#steps').value || '').length,
        att: Array.from(document.querySelectorAll('a, span, div'))
                .filter(e => !e.children.length && /\\.(png|jpe?g|gif|bmp)$/i.test((e.innerText || '').trim()))
                .map(e => e.innerText.trim())
    })""")


JS_LIST_DATA = r"""() => {
  for (const s of Array.from(document.querySelectorAll('script'))) {
    const txt = s.textContent || '';
    if (/^\s*data\s*=/.test(txt)) {
      try {
        const raw = txt.replace(/^\s*data\s*=\s*/, '').replace(/;\s*$/, '').trim();
        let v = JSON.parse(raw);
        if (typeof v === 'string') v = JSON.parse(v);
        return v;
      } catch (e) { return null; }
    }
  }
  return null;
}"""


def latest_bug_by_title(page, title):
    """保存成功后禅道跳的是 Bug 列表页，从列表内嵌 data 里按标题找回新单 ID"""
    try:
        fr = page.frame(name="app-qa") or page.main_frame
        data = fr.evaluate(JS_LIST_DATA) or []
    except Exception:
        return ""
    key = re.sub(r"<[^>]+>", "", title)[:26]
    for r in data:
        raw = re.sub(r"<[^>]+>", "", str(r.get("title", ""))).strip()
        if not raw:
            continue
        if key and (key in raw or raw[:26] in re.sub(r"<[^>]+>", "", title)):
            return str(r.get("id") or "")
    # 兜底：取列表第一条（id_desc 排序，最新在前）
    if data and data[0].get("id"):
        return str(data[0]["id"])
    return ""


# ---------------------------------------------------------------- 查重
def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(s or ""))).strip()


def fetch_all_titles(page, cfg, pages=None):
    """拉「由我创建」的全部 Bug，供提交前查重（人工单与自动化单同源，都会命中）"""
    base = cfg["base_url"].rstrip("/")
    want = pages or cfg.get("dup_pages", 4)
    rows, seen = [], set()
    for pg in range(1, want + 1):
        url = f"{base}/bug-browse-{cfg['product_id']}-0-openedbyme-0-id_desc-0-100-{pg}.html"
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1400)
        fr = page.frame(name="app-qa") or page.main_frame
        data = fr.evaluate(JS_LIST_DATA) or []
        n = 0
        for r in data:
            rid = str(r.get("id") or "")
            if rid and rid not in seen:
                seen.add(rid)
                rows.append({"id": rid, "title": strip_tags(r.get("title")),
                             "status": strip_tags(r.get("status"))})
                n += 1
        if n == 0:
            break
    return rows


def _strip_dev(s, devs):
    """去掉开头已知的设备名/系统名（如「智慧后勤系统」「体脂秤」），避免同系统所有单都被比中"""
    for d in sorted(devs, key=len, reverse=True):
        if d and s.startswith(d):
            return s[len(d):]
    return s


def find_dup(title, rows, cfg=None, dev="", keylen=12):
    """按「——」后半段前 12 个字符匹配；人工单常在中间插模块名，故用子串匹配。
    2026-10-27 起标题后半段多了设备名/系统名，比对前先剥掉，否则同系统标题首 12 字全一样、全被判重。
    """
    devs = set()
    if dev:
        devs.add(re.sub(r"\s+", "", dev))
    for v in ((cfg or {}).get("devices") or {}).values():
        v = re.sub(r"\s+", "", v or "")
        if v:
            devs.add(v)

    core = _strip_dev(re.sub(r"\s+", "", title.split("——", 1)[-1]), devs)
    key = core[:keylen]
    if not key:
        return None
    for r in rows:
        t = re.sub(r"\s+", "", r["title"])
        head = _strip_dev(re.sub(r"\s+", "", r["title"].split("——", 1)[-1]), devs)
        if key in t or key in head or (len(head) >= 10 and head[:10] in core):
            return r
    return None


def do_save(page, fr, title=""):
    # 先收掉 picker 下拉（它会盖住「保存」，导致点击被判为不可见）
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass
    fr.evaluate("""() => {
        document.querySelectorAll('.picker-drop-menu').forEach(e => e.remove());
        document.querySelectorAll('.picker').forEach(e => e.classList.remove('picker-focus'));
    }""")
    page.wait_for_timeout(400)

    btn = fr.locator("#submit")
    if btn.count() == 0:
        btn = fr.locator(".form-actions button, .form-actions .btn").filter(has_text="保存")
    if btn.count() == 0:
        btn = fr.locator(".form-actions button")
    try:
        btn.first.click(timeout=8000)
    except Exception:
        # 兜底：限定在表单操作区，绝不能落到编辑器工具栏的「保存模板」
        fr.evaluate("""() => {
            const box = document.querySelector('.form-actions');
            if (!box) return;
            const b = Array.from(box.querySelectorAll('button, input[type=submit]'))
                .find(x => (x.innerText || x.value || '').trim() === '保存') || box.querySelector('button');
            b && b.click();
        }""")
    page.wait_for_timeout(4000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    m = re.search(r"bug-view-(\d+)", page.url) or re.search(r"bugID=(\d+)", page.url)
    if m:
        return m.group(1), ""
    # 保存成功后禅道跳的是 Bug 列表页（bug-browse），从列表里按标题找回新单
    if "bug-browse" in page.url:
        bid = latest_bug_by_title(page, title)
        if bid:
            return bid, ""
        return "", "已跳转到列表页但没找回新单 ID"
    err = ""
    try:
        e = page.locator(".form-error, .alert-danger, #notice").first
        if e.count():
            err = e.inner_text()[:200]
    except Exception:
        pass
    return "", err or f"保存后未跳转，URL={page.url}"


# ---------------------------------------------------------------- 维护动作
def frame_of(page):
    """⚠ goto 之后必须重新取 frame：旧句柄会抛 Frame was detached，
    而那种情况下保存往往已经成功，直接重试会把附件传两份。"""
    return page.frame(name="app-qa") or page.main_frame


def open_edit(page, cfg, bid):
    base = cfg["base_url"].rstrip("/")
    page.goto(f"{base}/bug-edit-{bid}-0-0.html", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2200)
    fr = frame_of(page)
    if fr.locator("#steps").count() == 0:
        raise RuntimeError(f"编辑页没有 #steps（bugID={bid} 不存在或无权编辑？）")
    return fr


def save_edit(page, fr):
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass
    fr.evaluate("""() => {
        document.querySelectorAll('.picker-drop-menu').forEach(e => e.remove());
        document.querySelectorAll('.picker').forEach(e => e.classList.remove('picker-focus'));
    }""")
    page.wait_for_timeout(300)
    btn = fr.locator(".form-actions button, .form-actions .btn").filter(has_text="保存")
    if btn.count() == 0:
        btn = fr.locator("#submit")
    btn.first.click(timeout=10000)
    page.wait_for_timeout(3500)


def list_attachments(fr):
    return fr.evaluate("""() => {
        const seen = {};
        document.querySelectorAll('a[href*="file-download"]').forEach(a => {
          const h = a.getAttribute('href'), t = (a.innerText || '').trim();
          if (t && !seen[h]) seen[h] = t;
        });
        return Object.values(seen);
    }""")


def act_refresh(page, cfg, bid, job, retitle=False):
    """重刷正文：只写重现步骤，其它字段/附件原样保留

    retitle=True 时顺带按当前 build_title() 逻辑重写标题，
    用于「标题规范改了，把老单刷成新格式」（如 2026-10-27 加设备名）。
    """
    fr = open_edit(page, cfg, bid)
    before = fr.evaluate("""() => ({
        title: (document.querySelector('#title')||{}).value || '',
        build: (document.querySelector('#openedBuild')||{}).value || '',
        assigned: (document.querySelector('#assignedTo')||{}).value || '',
        project: (document.querySelector('#project')||{}).value || '',
        files: Array.from(document.querySelectorAll('a[href*=file-download]'))
                 .map(a => a.getAttribute('href')).filter((v,i,s)=>s.indexOf(v)===i).length
    })""")
    if retitle:
        fr.fill("#title", job["title"])
        page.wait_for_timeout(300)
    r = fr.evaluate(JS_SET_STEPS, job["steps_html"])
    save_edit(page, fr)
    base = cfg["base_url"].rstrip("/")
    page.goto(f"{base}/bug-view-{bid}.html", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2000)
    fr = frame_of(page)
    after = list_attachments(fr)
    return {"before": before, "ke": r, "attachments": after}


def act_attach(page, cfg, bid, files):
    """给已有单补附件（走编辑页，不新建单）"""
    files = [f for f in files if os.path.exists(f)]
    if not files:
        raise RuntimeError("附件文件都不存在")
    fr = open_edit(page, cfg, bid)
    fr.set_input_files("#file-input-multiple", files)
    page.wait_for_timeout(3000)
    save_edit(page, fr)
    base = cfg["base_url"].rstrip("/")
    page.goto(f"{base}/bug-view-{bid}.html", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2000)
    return {"attachments": list_attachments(frame_of(page))}


def act_delete(page, cfg, bid):
    """删除 Bug：真实地址是 /bug-delete-{id}-yes-.html（?confirm=yes 只是确认页）"""
    base = cfg["base_url"].rstrip("/")
    page.goto(f"{base}/bug-delete-{bid}-yes-.html", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2000)
    return {"url": page.url}


def act_stats(page, cfg):
    """统计「由我创建」的 Bug 状态分布"""
    from collections import Counter
    rows = fetch_all_titles(page, cfg)
    return rows, Counter(r["status"] or "(未识别)" for r in rows)


def api_get(page, cfg, path):
    """禅道 REST API v1，**session cookie 即可认证**，不需要额外 token。
    比列表页可靠：列表会把 deleted=1 的单隐藏掉，API 单条查询能查到真实 deleted 值。"""
    base = cfg["base_url"].rstrip("/")
    r = page.request.get(f"{base}/api.php/v1/{path}", headers={"Accept": "application/json"})
    try:
        return r.status, r.json()
    except Exception:
        return r.status, None


def verify_cfg(page, cfg):
    """首次接入体检：确认地址通、账号能登、产品/项目/指派人都解析得到。
    只读，不创建任何数据。"""
    base = cfg["base_url"].rstrip("/")
    res = []

    st, j = api_get(page, cfg, "user")
    prof = (j or {}).get("profile") or {}
    res.append({
        "项": "登录账号",
        "值": f"{prof.get('account','?')}（{prof.get('realname','?')}，角色 {(prof.get('role') or {}).get('name','?')}）",
        "ok": st == 200 and bool(prof.get("account")),
    })

    st, j = api_get(page, cfg, f"products/{cfg['product_id']}")
    res.append({
        "项": "所属产品",
        "值": f"{cfg['product_id']} · {((j or {}).get('name') or '未取到')[:34]}",
        "ok": st == 200 and bool((j or {}).get("name")),
    })

    st, j = api_get(page, cfg, f"projects/{cfg['project_id']}")
    res.append({
        "项": "所属项目",
        "值": f"{cfg['project_id']} · {((j or {}).get('name') or '未取到')[:34]}",
        "ok": st == 200 and bool((j or {}).get("name")),
    })

    acc = cfg.get("assigned_to") or ""
    if acc:
        st, j = api_get(page, cfg, f"users/{acc}")
        res.append({
            "项": "当前指派",
            "值": f"{acc} · {(j or {}).get('realname') or '账号不存在'}",
            "ok": st == 200 and bool((j or {}).get("realname")),
        })
    else:
        res.append({"项": "当前指派", "值": "config.assigned_to 为空", "ok": False})

    return res


def check_bug(page, cfg, bid):
    st, j = api_get(page, cfg, f"bugs/{bid}")
    if not j:
        return {"id": bid, "err": f"HTTP {st}"}
    return {
        "id": bid,
        "deleted": j.get("deleted"),
        "status": j.get("status"),
        "product": j.get("product"),
        "project": j.get("project"),
        "openedBy": (j.get("openedBy") or {}).get("account"),
        "title": (j.get("title") or "")[:52],
    }


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="禅道 Bug 自动提单（UI 自动化 · 禅道开源版 18.7）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python zentao_ui_submit.py --verify                 # 首次接入：配置体检（只读）
  python zentao_ui_submit.py --dry-run
  python zentao_ui_submit.py --submit --only ZH-SEC-02,ZH-SEC-05
  python zentao_ui_submit.py --submit --force          # 关掉查重强提
  python zentao_ui_submit.py --refresh 6656:ZH-SEC-05  # 重刷正文
  python zentao_ui_submit.py --refresh 6661:SAMPLE-01 --retitle  # 标题也按当前规范重写
  python zentao_ui_submit.py --attach 6656:ZH-SEC-05   # 按编号规则补附件
  python zentao_ui_submit.py --delete 6659
  python zentao_ui_submit.py --count
""")
    ap.add_argument("--csv", help="缺陷清单文件（默认取 config.default_csv）")
    ap.add_argument("--from", dest="from_file",
                    help="上游文件，按扩展名自动分派：.csv / .json（自动化结果）/ .xml（junit 报告）")
    ap.add_argument("--confirmed", action="store_true",
                    help="自动来源（json/xml）默认只出计划不允许提交；加此项表示已人工确认")
    ap.add_argument("--config", help="配置文件路径（默认 ./config.json，可用环境变量 ZENTAO_CFG）")
    ap.add_argument("--dry-run", action="store_true", help="只看标题与三段切分，不开浏览器")
    ap.add_argument("--submit", action="store_true", help="真正提单")
    ap.add_argument("--only", help="只提指定编号，逗号分隔（支持简写 02,05 或 SEC-04）")
    ap.add_argument("--end", help="临时覆盖端类型：PC / APK / IGW / attack（清单无「端类型」列时生效）")
    ap.add_argument("--force", action="store_true", help="关掉提交前查重")
    ap.add_argument("--refresh", metavar="ID:CODE", help="用当前逻辑重刷已有单的正文")
    ap.add_argument("--retitle", action="store_true",
                    help="配合 --refresh：标题也按当前规范重写（改了标题规范后刷老单用）")
    ap.add_argument("--attach", metavar="ID:CODE", help="给已有单补附件（按 evidence_dir 匹配）")
    ap.add_argument("--attach-file", nargs="*", help="配合 --attach，手工指定附件路径")
    ap.add_argument("--delete", metavar="ID", help="删除指定 Bug")
    ap.add_argument("--check", metavar="ID[,ID]", help="用 API 体检指定 Bug（deleted/status/openedBy）")
    ap.add_argument("--count", action="store_true", help="统计由我创建的 Bug 状态分布")
    ap.add_argument("--verify", action="store_true", help="配置体检：确认能登录、产品/项目/指派人都对（只读）")
    ap.add_argument("--headful", action="store_true", help="显示浏览器窗口")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    if args.headful:
        cfg["headless"] = False
    if args.end:
        cfg["end"] = norm_end(args.end, cfg.get("end") or "attack")
    csv_path = args.from_file or args.csv or cfg.get("default_csv")
    if not args.verify and (not csv_path or not os.path.exists(csv_path)):
        raise SystemExit(f"[FATAL] 清单文件不存在：{csv_path}")

    # ---------- 纯离线：只看切分 ----------
    if args.dry_run and not (args.refresh or args.attach or args.delete or args.count):
        plan = build_plan(cfg, csv_path, args.only)
        src_name = {"csv": "人工清单", "json": "自动化 JSON", "junit": "junit 报告"}.get(
            (plan[0].get("source") if plan else "csv"), "清单")
        noatt = sum(1 for p in plan if not p["attachments"])
        print(f"清单：{os.path.basename(csv_path)}   {len(plan)} 条   来源：{src_name}   "
              f"端类型：{end_summary(plan)}")
        auto_hints(plan, cfg, args.end)
        print("=" * 84)
        for p in plan:
            att = "、".join(os.path.basename(a) for a in p["attachments"]) or "⚠无附件"
            print(p["no"])
            print(f"  标题：{p['title']}")
            print(f"  附件：{att}")
            for k in ("步骤", "结果", "期望"):
                v = p["seg"].get(k) or ""
                print(f"  [{k}] {len(v)} 字：{v[:110].replace(chr(10),' / ')}{'…' if len(v)>110 else ''}")
        print("=" * 84)
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        pf = os.path.join(BASE_DIR, f"提单计划_{stamp}.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"计划已存：{pf}")
        print("\n[DRY-RUN] 未开浏览器、未提交。加 --submit 真正提单。")
        return

    from playwright.sync_api import sync_playwright

    # ---------- 维护类动作（单件操作） ----------
    if args.verify or args.refresh or args.attach or args.delete or args.count or args.check:
        with sync_playwright() as p:
            b, ctx = launch(cfg, p)
            page = ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            block_customfields_reload(page)
            ensure_login(page, ctx, cfg)

            if args.verify:
                print(f"配置：{cfg.get('_cfg_path')}")
                print(f"地址：{cfg['base_url']}")
                print("-" * 72)
                rows = verify_cfg(page, cfg)
                bad = 0
                for r in rows:
                    print(f"  {'✔' if r['ok'] else '✘'} {r['项']:<8} {r['值']}")
                    bad += 0 if r["ok"] else 1
                print("-" * 72)
                csv_p = cfg.get("default_csv") or ""
                ev = cfg.get("evidence_dir") or ""
                checks = [
                    ("清单文件", csv_p, os.path.exists(csv_p)),
                    ("截图目录", ev or "（未配置，将不带附件）", (not ev) or os.path.isdir(ev)),
                ]
                for name, val, ok in checks:
                    print(f"  {'✔' if ok else '✘'} {name:<8} {val}")
                    bad += 0 if ok else 1
                print("-" * 72)
                if bad:
                    print(f"[FAIL] {bad} 项待修；改完重跑 --verify 直到全 ✔")
                else:
                    print("[PASS] 配置可用：能登录、产品/项目/指派人都对。可以跑 --dry-run 了。")
                b.close()
                return

            if args.check:
                for bid in [x.strip() for x in args.check.split(",") if x.strip()]:
                    info = check_bug(page, cfg, bid)
                    flag = "⚠已删除" if info.get("deleted") else "✅正常"
                    print(f"#{bid} {flag}  状态={info.get('status')}  "
                          f"产品={info.get('product')} 项目={info.get('project')}  "
                          f"创建人={info.get('openedBy')}  {info.get('title')}")

            if args.count:
                rows, cnt = act_stats(page, cfg)
                print(f"由我创建的 Bug 共 {len(rows)} 条")
                for k, v in cnt.most_common():
                    print(f"  {k}: {v}")
                for r in rows[:8]:
                    print(f"  #{r['id']} [{r['status']}] {r['title'][:60]}")

            if args.refresh:
                bid, code = args.refresh.split(":", 1)
                job = [x for x in build_plan(cfg, csv_path) if x["no"].upper() == code.upper()]
                if not job:
                    raise SystemExit(f"[FATAL] 清单里没有编号 {code}")
                out = act_refresh(page, cfg, bid.strip(), job[0], retitle=args.retitle)
                print(f"#%s 改前：{out['before']}" % bid)
                print(f"#%s 写入编辑器：{out['ke']}" % bid)
                print(f"#%s 附件：{out['attachments']}" % bid)
                page.screenshot(path=os.path.join(BASE_DIR, f"_refreshed_{bid}.png"), full_page=True)

            if args.attach:
                bid, code = args.attach.split(":", 1)
                files = args.attach_file or []
                if not files:
                    job = [x for x in build_plan(cfg, csv_path) if x["no"].upper() == code.upper()]
                    files = job[0]["attachments"] if job else []
                print(f"#%s 上传：{[os.path.basename(f) for f in files]}" % bid)
                out = act_attach(page, cfg, bid.strip(), files)
                print(f"#%s 现有附件：{out['attachments']}" % bid)
                page.screenshot(path=os.path.join(BASE_DIR, f"_attach_{bid}.png"), full_page=True)

            if args.delete:
                out = act_delete(page, cfg, args.delete.strip())
                print(f"已请求删除 #{args.delete} → {out['url']}")

            b.close()
        return

    # ---------- 批量提报 ----------
    plan = build_plan(cfg, csv_path, args.only)
    src_name = {"csv": "人工清单", "json": "自动化 JSON", "junit": "junit 报告"}.get(
        (plan[0].get("source") if plan else "csv"), "清单")
    print(f"清单：{os.path.basename(csv_path)}   {len(plan)} 条   来源：{src_name}   "
          f"端类型：{end_summary(plan)}")
    auto_hints(plan, cfg, args.end)
    print("=" * 84)
    for p in plan:
        att = "、".join(os.path.basename(a) for a in p["attachments"]) or "⚠无附件"
        print(p["no"])
        print(f"  标题：{p['title']}")
        print(f"  附件：{att}")
        for k in ("步骤", "结果", "期望"):
            v = p["seg"].get(k) or ""
            print(f"  [{k}] {len(v)} 字：{v[:110].replace(chr(10),' / ')}{'…' if len(v)>110 else ''}")
    print("=" * 84)

    if not args.submit:
        print("\n[DRY-RUN] 未开浏览器、未提交。加 --submit 真正提单。")
        return

    # ---------- 自动来源的安全阀 ----------
    # 自动化跑出来的条目默认算「候选」，标题与严重程度是启发式生成的，
    # 未经人确认就灌进禅道会污染缺陷库 —— 必须加 --confirmed 才放行。
    if plan and plan[0].get("source") in ("json", "junit") and not args.confirmed:
        print(f"\n[BLOCK] 来源是自动化结果（{plan[0]['source']}），默认只出计划、不允许提交。")
        print("        核对上面的标题、严重程度、三段后，确认无误再加 --confirmed 重跑。")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    pf = os.path.join(BASE_DIR, f"提单计划_{stamp}.json")
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"计划已存：{pf}")

    results = []
    with sync_playwright() as p:
        b, ctx = launch(cfg, p)
        page = ctx.new_page()
        block_customfields_reload(page)
        ensure_login(page, ctx, cfg)

        dup_rows = None
        if not args.force:
            print("\n[查重] 拉取由我创建的 Bug 标题…")
            dup_rows = fetch_all_titles(page, cfg)
            print(f"[查重] 已载入 {len(dup_rows)} 条，标题重复将跳过（--force 可强制提交）")

        for i, job in enumerate(plan, 1):
            print(f"\n[{i}/{len(plan)}] {job['no']} 提交中…")
            row = {"no": job["no"], "bug_id": "", "status": "失败", "url": "", "error": "", "attach": ""}

            if dup_rows is not None:
                hit = find_dup(job["title"], dup_rows, cfg, job.get("device") or "")
                if hit:
                    row.update(bug_id=hit["id"], status="跳过(已存在)",
                               url=f"{cfg['base_url'].rstrip('/')}/bug-view-{hit['id']}.html")
                    print(f"  ⏭ 已存在 #{hit['id']}：{hit['title'][:50]}，跳过")
                    results.append(row)
                    continue

            try:
                fr = open_create(page, cfg)
                chk = fill_one(page, fr, cfg, job)
                print(f"  自检: {chk}")
                bid, err = do_save(page, fr, job["title"])
                if bid:
                    row.update(bug_id=bid, status="成功",
                               url=f"{cfg['base_url'].rstrip('/')}/bug-view-{bid}.html",
                               attach=";".join(os.path.basename(a) for a in job["attachments"]))
                    print(f"  ✅ 成功 bugID={bid}")
                    chk2 = check_bug(page, cfg, bid)
                    if chk2.get("deleted"):
                        print(f"  ⚠️ 体检异常：#{bid} deleted=true（列表里看不到，需人工还原）")
                        row["error"] = "体检: deleted=true"
                    if dup_rows is not None:
                        dup_rows.insert(0, {"id": bid, "title": job["title"], "status": "激活"})
                else:
                    row["error"] = err
                    print(f"  ❌ {err}")
            except Exception as e:
                row["error"] = str(e)[:300]
                print(f"  ❌ {row['error']}")
                try:
                    page.screenshot(path=os.path.join(BASE_DIR, f"_fail_{job['no']}.png"), full_page=True)
                except Exception:
                    pass
            results.append(row)
            time.sleep(cfg["interval"])
        b.close()

    out = os.path.join(BASE_DIR, f"提报结果_{stamp}.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["编号", "bugID", "状态", "链接", "附件", "错误"])
        for r in results:
            w.writerow([r["no"], r["bug_id"], r["status"], r["url"], r["attach"], r["error"]])
    okn = sum(1 for r in results if r["status"] == "成功")
    skn = sum(1 for r in results if r["status"].startswith("跳过"))
    print(f"\n完成：成功 {okn} / 跳过 {skn} / 共 {len(results)}；结果表 {out}")


if __name__ == "__main__":
    main()
