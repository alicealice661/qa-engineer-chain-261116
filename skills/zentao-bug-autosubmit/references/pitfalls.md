# 禅道 18.7 提单坑清单（现场实测原文）

> 每条都是踩过之后记的，含**错误信息原文**与**当时的误判**，照着避。

## 1. iframe 与 frame 句柄

- 内容区在 `iframe[name="app-qa"]`；产品列表在 `app-product`，后台在 `app-admin`。主文档查 DOM 永远 0 行。
- **`goto` 之后必须重新 `page.frame(name="app-qa")`**。旧句柄会抛：
  ```
  playwright._impl._errors.Error: Frame.evaluate: Frame was detached
  ```
- **这个错误会骗人**：编辑/建单保存后页面会重新加载，frame 失效但**保存往往已经成功**。
  当时照着报错重跑一次 → **同一批附件传了两份（file 9821~9824）**。
  **正确做法：先回详情页核对，再决定要不要重试。**

## 2. 保存时页面被强制刷新

- 现象：点「保存」后字段全部回默认、URL 不变、**无任何报错**，建单永远失败。
- 元凶：`POST /custom-ajaxSaveCustomFields-bug-custom-createFields.html`，响应体是
  `<script>parent.location.reload(true)</script>`。
- 解法：网络层拦掉，返回空 body。
  ```python
  page.route("**/custom-ajaxSaveCustomFields*",
             lambda route: route.fulfill(status=200, content_type="text/html", body=" "))
  ```
  该接口只保存「字段显示偏好」，拦掉不影响建单，且能让禅道走自己的 multipart 提交（附件才带得上）。

## 3. 保存按钮点错地方

- 宽选择器会点中 KindEditor 工具栏的「保存模板」，弹「请输入模板标题」。
- 必须限定在 `.form-actions` 容器内按文本「保存」精确匹配。
- 点之前先 `Escape` 并把 `.picker-drop-menu` 移除，否则「保存」被下拉遮住，判定为不可见。

## 4. 三种控件三种写法

| 控件 | 错误做法 | 现象 | 正确做法 |
|---|---|---|---|
| chosen（项目/指派/类型） | `select_option` | 30s 超时 element not visible | jQuery `.val()` + `chosen:updated` + `liszt:updated` + `change` |
| picker（影响版本） | 点 `.chosen-container` | 误中「操作系统」，版本没变 | 点 `#pk_openedBuild-search` → `a.picker-option[data-value="trunk"]` |
| KindEditor（重现步骤） | 只设 `#steps` | 保存后被编辑器内容盖回 `[步骤][结果][期望]` | `KindEditor.instances[0].html(html)` + 同步写 textarea |

## 5. KindEditor 会吃掉 `ol[start]`

- 注入 `<ol start="2">` → 编辑器 DOM 变成 `<ol>`（属性被过滤）→ 序号从 1 重排。
- 表现：**所有步骤都显示「1.」**。
- 根因还有一层：步骤之间有空行，`to_html` 每遇空行就 `</ol>`，导致**每步各开一个 ol**。
- 解法：空行只切 `</li>`，不关 `</ol>`，保证同组共用一个 `<ol>`；缩进续行用 `<br>` 并入上一条 `li`。

## 6. 「结果」段被菜单路径污染

- 现象：结果段开头出现半句 `前置一：账号 sec_view，角色…数据范围"仅本人"，`
- 原因：清单里有 `只勾「系统管理 → 用户管理」1 个菜单`，宽匹配 `→` 把它当成实测返回行。
- 解法：只认
  ```python
  r"^\s*→|→\s*(HTTP|http|code\s*=|状态码|2\d\d|4\d\d|5\d\d|\{)"
  ```
  即「行首箭头」或「箭头后紧跟状态码/JSON」。

## 7. 附件链路

- `#file-input-multiple` 选中后，实际提交的是原生 `input[name="files[]"][type=file]`（保留 fakepath，无 hidden 域）。
- **附件随表单 multipart 一次性提交，不是异步上传**。
- 绕过页面 JS 的原生 `form.submit()` 能建单但**丢附件**；且 `f.submit` 会被表单里 `name="submit"` 的按钮覆盖，需 `HTMLFormElement.prototype.submit.call(f)` —— 但这条路会丢附件，**别用**。
- 页面上限 **50M**（不是 2MB），不用压缩。

## 8. 建单后拿不到单号

- 保存成功后跳的是 **Bug 列表页** `bug-browse-*`，不是详情页。
- 单号在列表内嵌的 `<script>data = "[...]"</script>` JSON 里，按标题匹配找回；匹配不到回退取第一条（id_desc 即最新）。

## 9. 删单 / 删附件

- 删单真实地址：`/bug-delete-{id}-yes-.html`。`?confirm=yes` 只是确认页，**不执行删除**。
- 删附件：编辑页每个 `<li class="file">` 内有 `<a onclick="deleteFile(9823, this)">`（默认 `hidden`，hover 才显示）。
  直接 JS 调 `deleteFile(id, el)` 有效，但**必须再保存表单**才落库。
- 删除会弹 confirm。Playwright 默认 **dismiss**，表现为「点了没反应」→ 必须
  ```python
  page.on("dialog", lambda d: d.accept())
  ```
  ⚠ 副作用：这个 handler 会接受**页面上一切**对话框，操作前想清楚当前页还有没有别的确认框。

## 10. ★ 单被置 `deleted=true` 但看不见

这是最阴的一个：

- `bug-browse` 列表**隐藏 deleted=1 的单**，但该单**仍能直接打开详情页、仍可编辑、附件还在**。
- 后果一：列表查重永远查不到它 → **重复提单**；
- 后果二：用户在产品里看不到 → 以为没提上去；
- 体检方式（session cookie 即可，无需 token）：
  ```
  GET /api.php/v1/bugs/{id}     → 看 deleted 字段
  GET /api.php/v1/bugs?product=4&limit=3
  ```
- 现场实测：两条单在 10:25 被置删除，列表最新只到前两天的 6652，而详情页一切正常。
- **恢复入口**：开源版 18.7 前台没找到「还原」按钮，`/bug-undelete-{id}.html` 返回 200 空 body 但无效。
  可行路径是后台回收站（若有权限）或由运维在库层把 `deleted` 改回 `0`，**别靠猜**。

## 11. 重复单

- 已实际发生两次：ZH-SEC-01 人工 #6642 与自动化 #6647 重复；后来自动化又差点与 #6641/#6648 重复。
- 人工单与自动化条目**同源**：`测试PC端——智慧后勤3 个接口可匿名访问…` vs `【高危】网络安全攻防——3 个接口可匿名访问…`，
  说明人工单会在前缀后插入模块名 → 查重必须**子串匹配**，不能用整串相等。
- 人工单的三段常残留 `[步骤][结果][期望]` 占位符；

---

## 12. 打包分发时把登录态一起发出去了（2026-10-26）

- 现象：在待分发目录里跑 `--verify` 或任何会登录的命令后，该目录 `scripts/state.json` 里多出一份**含 `zentaosid` 的登录态**；直接 `Compress-Archive` 就把它打进了压缩包。
- 根因：`ensure_login()` 结尾无条件 `ctx.storage_state(path=STATE_PATH)`，而 `STATE_PATH = BASE_DIR/state.json`。
- 解决：**在分发目录里执行任何会登录的命令，必须设环境变量** `ZENTAO_STATE=<临时文件路径>`（脚本第 40 行已支持覆盖）。
- 发出去之前的必检三项：
  1. 真实密码（照 config.json 里的 password 值全文搜）不得出现；
  2. 不得含 `state.json`；
  3. 不得含本机绝对路径（`C:/Users/<用户名>/...`）。
- 一行校验：解压后 `grep -rn "state.json\|C:/Users/\|<密码>" .` 应为空。

---

## 13. `init_config.py` 在无终端环境下挂住

- 现象：管道 / AI 代跑 / bat 里调用 `python scripts/init_config.py`，卡在密码那一步不动。
- 根因：`getpass.getpass()` 在非 TTY 下等 `/dev/tty`。
- 解决：脚本已按 `sys.stdin.isatty()` 判断，非终端退回普通 `input()`；若自行改脚本，别去掉这个分支。
- AI 代跑更推荐**一次性传参**：`--account --password --feedback --csv --evidence --end --assigned ...`，不进交互分支。

---

## 14. junit.xml 里有未转义的 `<` 导致解析失败（2026-10-26）

- 现象：`--from report.xml` 报 `[FATAL] junit.xml 解析失败：not well-formed (invalid token): line N, column M`。
- 根因：断言消息里出现裸 `<`（例如 pytest 打印 `<Response [200]>.status_code`），XML 要求转义成 `&lt;`。手工拼 XML 时最容易踩，pytest 自己生成的报告一般没问题。
- 解决：报错行号就是位置，改 `&lt;` / `&gt;` / `&amp;` 即可；或用 `xml.sax.saxutils.escape()` 生成。
- 另一类「解析失败」：文件其实是 HTML 错误页（下载错），看前 200 字节就能判断。

## 15. 自动化来源的判级和标题是「猜」的，不能直接提（2026-10-26）

- 现象：junit 转出来的单，标题形如 `【中危】网络安全攻防——reserve amount rounding：expected 9.90, got 9.900000001`，端类型还是攻防——但这是业务用例，前缀整个打错。
- 根因：junit 里没有严重程度、没有端类型；`guess_severity()` 只能按关键字猜，`end` 只能退回 `config.end`。
- 解决（已在脚本里做成硬闸）：
  1. 自动来源（json/xml）`--submit` 直接 `[BLOCK]`，必须加 `--confirmed`；
  2. junit 未给 `--end` 时打印警告；
  3. 无截图的条数单独提示。
- 正确姿势：**自动化只负责产出「候选清单」，人核一遍再 `--confirmed` 提交**，与 C 候选 / D 确认双轨制一致。

## 16. 标题加设备名后，查重会把同系统所有单判成重复（2026-10-27）

- 现象：标题规范改成 `测试PC端——智慧后勤系统 xxx` 后，`--submit` 对每一条都报「疑似重复，已跳过」。
- 根因：`find_dup()` 取 `——` 后半段前 12 字做子串比对。加上设备名后，同系统所有单的前 12 字都是「智慧后勤系统 在线用…」这类高度重合的前缀，key 变成公共前缀。
- 解决（已修）：比对前先 `_strip_dev()` 剥掉开头的设备名（来源 = 本条 device + `config.devices` 的全部值），两侧都剥完再取 key。
- 验证过的 5 种组合：同系统不同缺陷 → 不判重；同系统同缺陷 → 判重；新标题带设备名 vs 老单无设备名 → 判重；同设备不同缺陷 → 不判重；同设备同缺陷 → 判重。
- 教训：**凡是给标题加固定前缀/固定段的功能，都要检查所有「按标题比对」的逻辑**（查重、`--refresh` 定位、`--check` 匹配）。

## 17. 设备名被拼两遍 / 标题里已经有设备名（2026-10-27）

- 现象：自动化 JSON 里标题写成「体脂秤一键测量用例超时」，device 又填「体脂秤」→ 生成 `测试APK端——体脂秤 体脂秤一键测量用例超时`。
- 解决（已修）：`build_title()` 组装前判断 `t.startswith(dev)`，已以设备名开头就不再拼；标题已带端前缀时同理只补插缺失的设备名。
- 写清单时的建议：**标题里不要重复写设备名**，设备名统一走「设备名」列或 `devices` 配置。
