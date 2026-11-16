---
name: network-only-device-recon
description: 对「无网络 adb」的嵌入式终端（海康/大华等 IPC、门禁、立柱屏、消费机）做网络侧只读渗透侦察，产出侦察报告 + 漏洞清单。当 adb connect :5555 被拒绝、但设备 80/443/554 等端口开放，需要不走 adb 出网络侧清单时使用。全程非侵入：不做口令尝试、不做漏洞利用、不做状态变更请求。
agent_created: true
---

# 无 adb 嵌入式终端 · 网络侧只读侦察

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：`adb connect <ip>:5555` 被拒绝，但 80/443/554 等端口开放（IPC、门禁、立柱屏、消费机常见）。
- **本技能**：网络侧**只读**侦察 —— 端口、服务指纹、TLS、HTTP 端点、前端 JS 审计 → 侦察报告 + 漏洞清单。
- **下一棒**：漏洞清单 CSV → `zentao-bug-autosubmit` 提单（前缀用「网络安全攻防」档）。
- **别用本技能做**：① 设备有 adb → `apk-network-pentest-recon`（能拿到 APK 就别只在网络侧猜）；② 要判「某端口为什么不通」的现场原因 → `staged-script-remote-diagnosis`。
- **授权红线**：全程非侵入 —— 不做口令尝试、不做漏洞利用、不发状态变更请求；越界即停。

## 何时用
- `adb connect <ip>:5555` 返回 **「由于目标计算机积极拒绝」(WinError 10061)** → 设备未开网络 adb，**这是设备侧设置问题，不是 IP 问题**。
- 目标是海康 / 大华 / 宇视等嵌入式终端（IPC、门禁、立柱屏、消费机、NVR）。
- 老大（授权红队）要求不走 adb 出**网络侧**清单，且明确**只读、非侵入**。

## 铁律（先确认授权口径）
- 老大若说「不允许尝试性动作」→ **禁止**：口令/默认口令尝试、漏洞利用与验证、会改变设备状态的请求。
- 允许：建立 TCP 连接、只读 GET、TLS 握手、被动读 banner。
- 结论只写**只读证据**支持的项；未做的一律进「受限与未覆盖」，**不编造**。

## 步骤

### 0. 环境
- 本机有系统代理 `http_proxy=127.0.0.1:49489` → `curl` 测内网**必须加 `--noproxy '*'`**；自写 socket/ssl 脚本**不受代理影响**，更省心。
- 用固定 venv：`<venv>\Scripts\python.exe`（或直接 `python`，本技能只依赖标准库 asyncio/ssl/socket）

### 1. 主机可达 + 判定有无 adb
```bash
ping -n 2 <ip>            # Windows；通即同网段 ~1-3ms
adb connect <ip>:5555     # 被拒绝 = 无网络 adb（记入报告，别反复重试）
```

### 2. 全端口扫描（asyncio，比 bash /dev/tcp 快几个数量级）
并发 900、timeout 0.7s，**扫 1–40000**（分两段 `1..20000` + `20001..40000` 跑，各几秒完成）：
```python
import asyncio
openp=[]
sem=asyncio.Semaphore(900)
async def probe(p):
    async with sem:
        try:
            r,w=await asyncio.wait_for(asyncio.open_connection(IP,p),timeout=0.7); openp.append(p); w.close()
        except Exception: pass
await asyncio.gather(*[probe(p) for p in range(1,20001)])
await asyncio.gather(*[probe(p) for p in range(20001,40001)])
```
- 海康典型结果：`80/443/554` + 私有 `7681/7682/8102`；**无 5555**。
- 大华典型结果：`80/554/5000/8086/**37777**`；**无 443、无 5555**。
- ⚠️ **必须扫到 40000**：大华私有 SDK 端口 **37777 > 20000**，只扫 1–20000 会**漏掉**（本技能初版就踩过）。

### 3. 服务指纹
- 80 → `curl -sI --noproxy '*' http://ip/`：海康跳 443；页面里 `App-webs/` = 海康嵌入式 Web。
- 443 → SPA 跳 `/doc/index.html`，前端 **HUI**（`hui.<hash>.css`）。
- **ISAPI**：`/ISAPI/System/deviceInfo` → 401 且 `WWW-Authenticate: Digest ... realm="DS-xxxx"`（realm 含型号线索）。
- 激活状态：**`/SDK/activateStatus` 通常无需鉴权返回 200**（`<Activated>true/false</Activated>`）。
  ⚠️ 401 body 里的 `isActivated` 指**会话**未认证，**不是设备未激活**，勿误读。

### 3b. 大华设备分支指纹（与海康不同，别套错）
- **前端**：80 根路径返回 React SPA（title `WEB`），chunk 名带 **`acs~*.chunk.js`**（ACS = Access Control 门禁），引用 `/static/js/*.chunk.js`。
- **管理接口**：`/cgi-bin/magicBox.cgi?action=getXxx` → **401 `ErrorInvalid Authority!`**，且**无 `WWW-Authenticate` 头**（大华自有鉴权，非标准 Digest/Basic）。登录接口 **`/RPC2_Login`、`/RPC2`**（GET 空回复，需 POST）。
- **⭐ 未授权型号泄露（优先试）**：`GET /current_config/webCapsConfig` → 200，返回 JSON 含
  `DeviceType`（精确型号，如 `ASI9213DA-W`）、`SecurityBaselineVersion`、密码策略/能力位；
  `GET /current_config/preLanguage` → 200。其余 `/current_config/*` 多为 404 —— 只这两个是免鉴权。
- **ONVIF**：`POST /onvif/device_service`（SOAP）**GetCapabilities → 200 未鉴权**（泄露 ONVIF 版本范围、能力位）；
  GetDeviceInformation → **401**（受鉴权，不泄露型号/序列号）。海康也有 ONVIF 但默认多为关闭。
- **私有端口**：`8086` = 大华 **Http Stream Server/1.0**（未鉴权可连，`400` + `Session-Id` 头）；`5000` 静默私有；`37777` 私有 SDK。
- 型号只能从 `/current_config/webCapsConfig` 或认证后取，**别从通用前端包里的样例串猜**。

### 4. TLS 评估（python ssl，能精确强制版本）
> ⚠️ 先看 443 是否开放：**大华部分型号根本没有 443（管理面纯明文 HTTP）**，此时步骤 4 整段跳过，
> 直接把「无 HTTPS 入口 → 管理凭据明文传输」列为传输安全项（并记 `GET /` 返回 200 无跳转 作证）。
```python
c=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); c.check_hostname=False; c.verify_mode=ssl.CERT_NONE
c.minimum_version=c.maximum_version=ssl.TLSVersion.TLSv1_2   # 逐个版本试
c.set_ciphers("ALL:@SECLEVEL=0")
s=c.wrap_socket(socket.create_connection((IP,443),timeout=5),server_hostname=IP)
print(s.version(), s.cipher())
```
- 版本被拒 → `SSLError: TLSV1_ALERT_PROTOCOL_VERSION`（= 服务端不支持，**结论成立**）。
- 套件看 `cipher()[0]`：出现 `...-SHA`/`...-CBC-...` = **CBC+SHA1 弱套件仍在**（中危）。
- 证书：`echo | openssl s_client -connect ip:443 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName`。自签 `CN=tmp_comm.cert`/无 SAN/长有效期 = 证书类问题。
- ⚠️ openssl 3.x 下 `-cipher NULL-SHA/AES128-SHA` 会**回落到 TLS1.3**（忽略该参数）→ 别据此判弱套件；用 python 强制 TLS1.2 才准。

### 5. HTTP 端点枚举 + 明文面判定
- 关键判据：**80 端口除根路径 "/" 外是否直接明文服务**？同路径在 80/443 返回一致 = 未强制全站 HTTPS。**ISAPI 在 80 上返回 Digest 挑战 = 明文链路可完成认证协商**。
- 查 443 响应头有无 `Strict-Transport-Security`（无 = 可降级）。
- 端点存在性：401（存在）vs 404（不存在）可被未授权枚举 → 信息泄露类发现。

### 6. 私有端口被动手抓（不注入）
```python
s=socket.create_connection((IP,port),timeout=4); s.settimeout(2)
d=s.recv(256)   # 先静读；再发 b"\r\n"、b"\x00"*16 各读一次
```
实测 8102：**连接即回吐 200B 固定帧** `000000c8 00000000` + 32 位 ASCII 十六进制标识（两次连接一致 = 稳定设备标识）。7682 探测后 RST。

### 7. Web 前端 JS 审计（**重要陷阱**）
- 抓 `/doc/index.html` 里引用的 `js/*_chunk.<hash>.js`（大包几 MB），grep `/ISAPI/([A-Za-z]+)/` 得服务面家族。
- ⚠️ **海康 Web 前端是通用包**，同时含 `AccessControl / Consume / VideoIntercom / Traffic / ITC` 等**多条产品线**，`DS-KB8113-IME1` 之类是**包内样例串** → **不能据此判定本机型号**。型号只能从 ISAPI realm / 认证后 deviceInfo 取。

## 出报告
- 落 `Desktop\<设备名>\`：`xxx_网络侧侦察报告_<日期>.md` + `xxx_漏洞清单_<日期>.md/.xlsx/_禅道导入.csv`（编号前缀自拟，如 `HIK-SEC-`）。
- 清单用「ROWS + GONE + BANNED 自检」生成器（见同族 `gen_vuln_list.py` 写法），CSV 11 列 utf-8-sig。
- **必带「受限与未覆盖」表**：客户端 App 层（无 adb 拿不到 APK/固件）、本地数据、口令尝试（授权限制）、漏洞利用验证（授权限制）、链路 MITM（需单独授权）——逐条写清缺口与原因，并给「建议下一步」（取固件包 / USB `adb tcpip 5555`）。

## 已知坑
- 80 端口：只有 `"/"` 会 301，`/doc/index.html`、`/ISAPI/*`、`/SDK/*` 都可能**明文直接服务** → 这是「未强制 HTTPS」的实证，别只看根路径就下「已跳转」结论。
- 报告别写演练批次名；抬头「授权依据」只写「授权书授权范围内」。
- 全端口扫描不要用 bash `/dev/tcp` 循环（太慢），用 asyncio；**且必须扫到 40000**（大华 37777 会漏）。
- **响应头带 HSTS 但无 443** ≠ 已启用 HTTPS：HSTS 只在 HTTPS 响应生效，纯 HTTP 场景下该头像**摆设** → 作为「配置与实现不一致」的证据写，而不是当成安全措施。
- 生成器用 `%` 格式化时，串里若含 `%{...}`（如 curl 的 `-w '%{http_code}'`）会报 `unsupported format character` → 用字符串拼接或 `%%` 转义。
- 抓 JS 的 heredoc 里若用**相对路径**（如 `open("<输出目录>/x.js","w")`），Bash 工具 cwd 可能漂移，把文件写到项目根 → 用 `cd` 显式定位或**绝对路径**。
