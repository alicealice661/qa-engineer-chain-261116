# -*- coding: utf-8 -*-
"""禅道提单 · 配置初始化向导

用法（交互，推荐同事自己跑）：
    python scripts/init_config.py

用法（AI 代跑，把答案一次性传入）：
    python scripts/init_config.py --account zhangsan --password xxx \
        --feedback 杨昌华 --csv "C:/Users/<user>/Desktop/清单.csv" --evidence "C:/Users/<user>/Desktop/evidence"

说明：
- 交互模式下**逐项问，直接回车 = 沿用方括号里的默认值**，不用手改 JSON。
- 已存在的 config.json 会作为默认值载入，所以重跑 = 更新配置。
- 写完会打印摘要，**密码一律打码**。
"""
import argparse
import getpass
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.environ.get("ZENTAO_CFG") or os.path.join(BASE_DIR, "config.json")

ENDS = {"1": "PC", "2": "APK", "3": "IGW", "4": "attack", "pc": "PC", "apk": "APK", "igw": "IGW", "attack": "attack"}

DEFAULTS = {
    "base_url": "http://192.168.2.121:8099",
    "account": "",
    "password": "",
    "product_id": 4,
    "project_id": 210,
    "module_id": 0,
    "build_value": "trunk",
    "build_text": "主干",
    "assigned_to": "",
    "assigned_text": "",
    "feedback_by": "",
    "bug_type": "codeerror",
    "end": "attack",
    "attack_default_level": "中危",
    "devices": {"PC": "智慧后勤系统", "APK": "", "IGW": ""},
    "evidence_dir": "",
    "default_csv": "",
    "headless": True,
    "interval": 5,
    "use_proxy": False,
}


def load_existing():
    if not os.path.exists(CFG_PATH):
        return {}
    try:
        with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def ask_text(label, cur, hint="", required=True):
    tip = f" [{cur}]" if cur not in ("", None) else ""
    while True:
        print(f"\n{label}{tip}")
        if hint:
            print(f"    ({hint})")
        v = input("    > ").strip()
        if not v:
            v = cur
        if v or not required:
            return v
        print("    ⚠ 必填，不能为空")


def ask_secret(label, cur):
    tip = " [已设置，回车沿用]" if cur else " [必填]"
    print(f"\n{label}{tip}")
    print("    (输入时不回显；直接回车 = 沿用现有值)")
    if sys.stdin.isatty():
        v = getpass.getpass("    > ").strip()
    else:
        # 管道/AI 代跑场景没有终端，getpass 会挂住，退回普通读入
        v = input("    > ").strip()
    return v or cur


def ask_choice(label, cur, mapping, order):
    print(f"\n{label}  当前 = {cur}")
    for k in order:
        print(f"    {k}. {mapping[k]}")
    while True:
        v = input("    选序号，回车沿用 > ").strip().lower()
        if not v:
            return cur
        if v in mapping:
            return mapping[v]
        print("    ⚠ 选 1~4")


def normalize(p):
    """把 Windows 反斜杠统一成正斜杠，避免 JSON 里 \\\\ 转义踩坑"""
    if not p:
        return p
    p = p.strip().strip('"').strip("'")
    return p.replace("\\", "/")


def main():
    ap = argparse.ArgumentParser(description="禅道提单配置初始化")
    ap.add_argument("--base-url")
    ap.add_argument("--account")
    ap.add_argument("--password")
    ap.add_argument("--feedback")
    ap.add_argument("--csv")
    ap.add_argument("--evidence")
    ap.add_argument("--product", type=int)
    ap.add_argument("--project", type=int)
    ap.add_argument("--assigned", help="指派人登录名，如 yangxiaowei")
    ap.add_argument("--assigned-name", help="指派人显示名，如 杨小伟")
    ap.add_argument("--end", help="PC / APK / IGW / attack")
    ap.add_argument("--device", help="设备名/系统名，格式 PC=智慧后勤系统,APK=出入库秤（标题 —— 后面那段）")
    ap.add_argument("--out", help=f"输出路径，默认 {CFG_PATH}")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    cfg.update(load_existing())

    # ---- 一次性传参模式（AI 代跑）：缺的字段仍按默认值补 ----
    provided = {
        "base_url": args.base_url,
        "account": args.account,
        "password": args.password,
        "feedback_by": args.feedback,
        "default_csv": normalize(args.csv) if args.csv else None,
        "evidence_dir": normalize(args.evidence) if args.evidence else None,
        "product_id": args.product,
        "project_id": args.project,
        "assigned_to": args.assigned,
        "assigned_text": args.assigned_name,
        "end": args.end,
    }
    for k, v in provided.items():
        if v not in (None, ""):
            cfg[k] = v

    # 设备名/系统名：PC=智慧后勤系统,APK=出入库秤
    if args.device:
        devs = dict(cfg.get("devices") or {})
        for part in args.device.replace("，", ",").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                k = k.strip().upper()
                if k in ("PC", "PC端"):
                    k = "PC"
                elif k in ("APK", "APK端", "安卓"):
                    k = "APK"
                elif k in ("IGW", "网关"):
                    k = "IGW"
                devs[k] = v.strip()
        cfg["devices"] = devs
        provided["devices"] = devs

    batch_mode = any(v not in (None, "") for v in provided.values())
    if batch_mode and not (args.account and args.password):
        # 批量模式下账号密码必须给，否则后面登录必失败
        print("[ERR] 批量模式至少要给 --account 和 --password")
        return 2

    if not batch_mode:
        print("=" * 66)
        print(" 禅道提单 · 配置初始化（回车 = 沿用方括号里的值）")
        print("=" * 66)
        cfg["base_url"] = ask_text("1) 禅道地址", cfg["base_url"], "例：http://192.168.2.121:8099")
        cfg["account"] = ask_text("2) 你的禅道登录账号", cfg["account"], "例：zhangsan")
        cfg["password"] = ask_secret("3) 你的禅道登录密码", cfg["password"])
        cfg["feedback_by"] = ask_text("4) 提单页「反馈者」填谁", cfg["feedback_by"], "一般写你自己的姓名")
        cfg["default_csv"] = normalize(ask_text(
            "5) 缺陷清单 CSV 路径", cfg["default_csv"],
            "需含列：编号、标题、严重程度、重现步骤；可拖文件到窗口"))
        cfg["evidence_dir"] = normalize(ask_text(
            "6) 截图目录", cfg["evidence_dir"],
            "截图文件名要含条目编号，如 ZH-SEC-01_实测.png；没有就留空", required=False))
        cfg["end"] = ask_choice("7) 这次提的是哪一端？", cfg["end"], ENDS, ["1", "2", "3", "4"])
        # 设备名/系统名：标题 —— 后面那一段，按端分别问
        devs = dict(cfg.get("devices") or {})
        print("   ── 设备名/系统名（标题 `——` 后面那段，混设备就留空、改用清单的「设备名」列）")
        for k, hint in (("PC", "如：智慧后勤系统"), ("APK", "如：出入库秤 / 体脂秤 / 取盘机"), ("IGW", "如：智能网关")):
            v = ask_text(f"   {k} 端的设备名/系统名", devs.get(k, ""), hint, required=False)
            if v:
                devs[k] = v
        cfg["devices"] = devs
        cfg["product_id"] = int(ask_text("8) 所属产品 ID", str(cfg["product_id"]), "智慧后勤二期 = 4"))
        cfg["project_id"] = int(ask_text("9) 所属项目 ID", str(cfg["project_id"]), "二期 = 210"))
        cfg["assigned_to"] = ask_text("10) 指派给谁（登录名）", cfg["assigned_to"], "例：yangxiaowei")
        cfg["assigned_text"] = ask_text("11) 指派给谁（显示名）", cfg["assigned_text"], "例：杨小伟")

    # ---- 校验 ----
    warn = []
    if not str(cfg.get("base_url", "")).startswith("http"):
        warn.append(f"base_url 不是 http 开头：{cfg.get('base_url')}")
    if not cfg.get("account"):
        warn.append("account 为空，登录会失败")
    if not cfg.get("password"):
        warn.append("password 为空，登录会失败")
    if not cfg.get("feedback_by"):
        warn.append("feedback_by 为空，提单页「反馈者」会是空的")
    csv_p = cfg.get("default_csv") or ""
    if not csv_p:
        warn.append("default_csv 为空，空跑时会报 [FATAL] 清单文件不存在")
    elif not os.path.exists(csv_p):
        warn.append(f"清单文件当前不存在：{csv_p}")
    ev = cfg.get("evidence_dir") or ""
    if ev and not os.path.isdir(ev):
        warn.append(f"截图目录当前不存在：{ev}（没有附件也能提，只是不带图）")
    if not cfg.get("assigned_to"):
        warn.append("assigned_to 为空，建单会落不到人")

    out = args.out or CFG_PATH
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 66)
    print(f"已写入：{out}")
    print("-" * 66)
    print(f"  禅道地址   {cfg['base_url']}")
    print(f"  账号       {cfg['account']}")
    print(f"  密码       {'*' * 6}（已保存，不回显）")
    print(f"  反馈者     {cfg['feedback_by']}")
    print(f"  产品/项目  {cfg['product_id']} / {cfg['project_id']}")
    print(f"  影响版本   {cfg['build_value']}（{cfg['build_text']}）")
    print(f"  指派       {cfg['assigned_to']}（{cfg.get('assigned_text','')}）")
    print(f"  端类型     {cfg['end']}")
    dv = cfg.get("devices") or {}
    print(f"  设备名     PC={dv.get('PC') or '（空）'} / APK={dv.get('APK') or '（空）'} / IGW={dv.get('IGW') or '（空）'}")
    print(f"  清单       {cfg.get('default_csv') or '（空）'}")
    print(f"  截图目录   {cfg.get('evidence_dir') or '（空）'}")
    print("=" * 66)
    if warn:
        print("⚠ 需要你确认的 %d 项：" % len(warn))
        for w in warn:
            print("   - " + w)
    else:
        print("✔ 配置项齐全")
    print("\n下一步：验证配置能不能登录 → python scripts/zentao_ui_submit.py --verify")
    print("再下一步：空跑看标题与三段 → python scripts/zentao_ui_submit.py --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
