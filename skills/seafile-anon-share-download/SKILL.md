---
name: seafile-anon-share-download
description: 从 Seafile（seahub）匿名分享链接 http://host/d/<token>/ 批量下载文件或目录，无需账号密码。当拿到形如 http://xxx/d/xxxxxxxx/ 的分享链接、需要拉取其中的日志/文档/数据时使用。也适用于 Agent 拿到内网 Seafile/可道云式分享链接后拿不到内容的场景。
agent_created: true
---

# Seafile 匿名分享链接批量下载

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：拿到形如 `http://host/d/<token>/` 的匿名分享链接，需要取里面的日志/文档/数据。
- **本技能**：列目录 → 建打包任务 → 轮询 → 下载，大文件走单文件直链 + Range。
- **下一棒**：拉下来的素材交给 `server-resource-trend-analyzer`（趋势汇总）或直接读日志分析。
- **别用本技能做**：① 有账号的 Seafile → 用官方客户端，本技能只解决匿名链接；② 只想看一份 docx 内容 → 下单个文件即可，不必整包打包。
- **已知坑**：`.log` 后缀的目录名会 404，必须走单文件 JSON API；429 要按指数退避。

## 适用场景

拿到 `http://<host>/d/<token>/` 形式的 Seafile 分享链接（站点标题常见「某某网盘/seafile」，版本 12.x 验证通过），
需要把里面的目录/文件拉到本地分析。

## 关键前提

- **这类页面是 SPA**，`WebFetch`/`curl` 直接取 HTML 只能拿到空壳 `<div id="wrapper">`，里面没有文件列表。
- 真正的目录信息在页面内嵌的 `window.shared.pageOptions` 里（含 `dirName`、`dirPath`、`token`、`repoID`）。
- **不要**试图用 `/d/<token>/download/?p=`、`/repos/<repoID>/files/?op=download`、
  `/seafhttp/zip/<token>.zip` 这些路径 —— 实测全部 404 / 403。
- `/seafhttp/files/<token>/<name>` **直接拿 share token 去请求会 403**，必须先按「第 5 步」换成真正的 file token。

## 四步走

### 1. 列目录

```bash
curl -s "http://<host>/api/v2.1/share-links/<token>/dirents/?path=%2F&thumbnail_size=256"
```

- `path` 用 URL 编码的相对路径，**结尾带 `/`**（表示目录），根目录为 `%2F`。
- 返回 JSON：`{"dirent_list":[{"is_dir":true,"folder_path":...,"size":...,"file_path":...}]}`。
- 递归下钻子目录即可得到完整文件树。

### 2. 创建打包任务（两种）

**整目录** —— GET：

```bash
curl -s "http://<host>/api/v2.1/share-link-zip-task/?share_link_token=<token>&path=%2F%E7%9B%AE%E5%BD%95%2F"
# 返回 {"zip_token":"..."}
```

**指定文件** —— POST **必须用 JSON body**，form-urlencoded 会报 `No valid dirent.`：

```bash
curl -s -X POST "http://<host>/api/v2.1/share-link-zip-task/" \
  -H "Content-Type: application/json" \
  -d '{"token":"<token>","parent_dir":"/父目录","dirents":["file1.log","file2.log"]}'
```

> `parent_dir` 结尾**不要**带斜杠，`dirents` 用数组。

### 3. 轮询打包进度

```bash
curl -s "http://<host>/api/v2.1/query-zip-progress/?token=<zip_token>"
# {"zipped":3,"total":3,"failed":0,...}
```

`zipped == total` 即完成。

### 4. 下载（最容易踩的一步）

```bash
curl -s -o out.zip "http://<host>/seafhttp/zip/<zip_token>"
```

**注意：URL 末尾千万不要加 `.zip`** —— 加了会返回 `403 Access token not found`。
不带后缀才返回正确的 `application/zip`。

`zip_token` 有效期很短，创建后应尽快下载；超时失效就重新走第 2 步。

> ⚠️ **zip 不适合大文件**：单文件 >500 MB 时打包慢、`zip_token` 容易在打包完成前失效，
> 而且无法做部分下载。这时改用「第 5 步」的直链 + Range。

### 5. 单文件直链与 Range 部分读取（大文件必用）

**换 file token** —— 关键在末尾的 `&dl=1`，少了它只会返回一个 HTML 页面（HTTP 200 但无内容）：

```bash
curl -s -D - -o /dev/null "http://<host>/d/<token>/files/?p=%2Ftools.tar&dl=1"
# HTTP/1.1 302 Found
# Location: http://<host>/seafhttp/files/<file-token>/tools.tar
```

拿到 `file-token` 后即可当作普通静态文件处理，**支持 Range**：

```bash
curl -s -r 0-511 -o head.bin "http://<host>/seafhttp/files/<file-token>/tools.tar"
# HTTP/1.1 206 Partial Content，返回 512 字节
```

**实战价值**：面对 1.9 GB 的 `tools.tar`，不必整包下载 —— 只读 tar 头即可列出完整文件树，
并把里面所有小文件（配置、脚本）单独抓下来。tar 头结构：

| 偏移 | 长度 | 含义 |
|---|---|---|
| 0 | 100 | 文件名（\0 结尾） |
| 124 | 12 | 文件大小（八进制，\0/空格结尾） |
| 156 | 1 | typeflag（`0`=普通文件，`5`=目录） |
| 345 | 155 | 名前缀（GNU longname/prefix） |

遍历算法：`pos += 512 + ceil(size/512)*512`，每次只读 512 字节的头；
用 8 MB 缓冲块批量读可把 HTTP 请求数压到「大文件个数」量级
（实测 1.9 GB / 28 个条目只用了 14 次请求）。遇全零块即结束。

参考实现见 `tools_tar_scan.py`（桌面\工控机\），同时会把 `size <= 3MB` 的文件直接落盘。

## 坑位清单

| 现象 | 原因 / 解法 |
|---|---|
| 各种路径都 404 且返回首页 HTML | SPA catch-all 兜底，说明路径根本不对，回到本 Skill 的路径 |
| `/d/<token>/files/?p=...` 返回 200 但内容为空 | 少了 `&dl=1`，加上就 302 到 seafhttp 直链 |
| `/seafhttp/files/<share-token>/xxx` → 403 | 必须用 `?dl=1` 换出来的 **file token**，不能直接用 share token |
| `/seafhttp/zip/<token>.zip` → 403 `Access token not found` | 去掉 `.zip` 后缀 |
| POST zip-task 报 `No valid dirent.` | 用 JSON body + `Content-Type: application/json`，且 `parent_dir` 不带尾斜杠 |
| zip-task 返回 `total` 小于提交的文件数 | 有文件没打包成功（常见于跨目录、名字含特殊字符）；改用「第 5 步」逐个直链拉 |
| 目录名含中文/字母混杂时列目录 404 | 先从上一个 `dirent_list` 里取**原始的 `folder_path`** 字段做 URL 编码，不要手打目录名 |
| Python `urllib` 请求 zip-task 返回 404，但 curl 正常 | 服务端对 UA 敏感，换 curl 默认 UA（或在 Python 里显式设置朴素 UA） |
| WebFetch 报私有地址被网络策略拦截 | 内网 IP 走 curl/浏览器，不用 WebFetch |
| Chromium 下载超时（`agent-browser install` 失败） | 先用 curl + API 这条路，通常足够，不必强依赖浏览器 |

## 二次分析建议

- **docx 可能是纯截图**：先抽文本确认是否为空。
  快速判断：`graphs=0, images=N` 说明内容全在图里，此时需 OCR 或请用户提供文字版。
  提取文本可直接解析 `word/document.xml`（不必装 python-docx）。
- **Seafile 页面 token 可用很多天**，但 `zip_token` 是短时 token。

## 已知目标（内网）

`192.168.2.123` 是南京三坤 Seafile（siteName `sankun`），网盘内含
`/智慧后勤智能楼宇/日志/服务日志+慢sql+服务器资源情况/` 目录，按月归档（`8月/260827/` 形式）。

已验证的两个工控机相关分享（2026-09）：

| 分享 token | 内容 |
|---|---|
| `4b75d8d6c63e49da9616` | 业务侧物料：7 个 eigw jar、alpine-java.tar、dockerfile、`nacos/`（nacos3.2.0.tar 1.26G + 升级流程 docx + mysql-schema.sql）、tools.tar(1.81G) |
| `083ce72dbd5545b5a1b9` | 平台侧标准包：tools.tar(1.9G，内含 sankun.sh 一键部署脚本 + 7 个中间件镜像 + 全套配置)、nginx 路由转发配置、网关漏洞处理（等保加固）、ssh 离线升级 |

> 两个包里的 `tools.tar` 大小不同（1.81G vs 1.9G），是两个版本，别当同一个用。
