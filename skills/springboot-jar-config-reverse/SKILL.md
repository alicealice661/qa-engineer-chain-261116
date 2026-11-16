---
name: springboot-jar-config-reverse
description: 从 Spring Boot 业务 jar（含 jar 内嵌套依赖）反推它到底需要哪些配置项——扫描字节码常量池里的 ${...} 占位符，按"几个服务需要它"自动拆分共享配置与服务专属配置，生成交给研发/运维的配置项清单和 Nacos 配置模板。当部署的微服务因缺配置起不来（报 Could not resolve placeholder / 缺数据源 / Nacos 里配置为空）、需要反推配置骨架时使用。
agent_created: true
---

# 从 Spring Boot jar 反推所需配置项

## 链路位置（本包 qa-engineer-chain，先看这段再动手）

- **上一棒**：服务起不来（`Could not resolve placeholder` / 缺数据源 / Nacos 配置为空），或新环境部署缺配置骨架。
- **本技能**：扫字节码常量池里的 `${...}` → 按「几个服务需要它」拆共享/专属 → 出配置项清单 + Nacos 模板。
- **下一棒**：现场执行验证交 `staged-script-remote-diagnosis`（连不上时靠分段脚本取证）。
- **别用本技能做**：① 只是远程跑命令取证 → `staged-script-remote-diagnosis`；② 只是资源不足/慢查询 → `server-resource-trend-analyzer`；③ 有现成 Nacos 可读 → 直接读现场配置，比反推准。
- **纪律**：反推出来的配置只能算候选，必须在运行态验证过（启动成功 + 关键功能可用）才写进交付文档。

## 适用场景

部署的 Java 微服务启动失败，日志典型长这样：

```
Caused by: java.lang.IllegalArgumentException:
    Could not resolve placeholder 'monitor.url' in value "${monitor.url}"
```

或者 Nacos 命名空间是空的、研发的配置包一时拿不到，而你需要知道「到底缺哪些键」。
此时不要靠猜、也不要只翻 `bootstrap.yml`（那里面通常只有 nacos 地址和 `shared-configs`），
**真正的答案在字节码常量池里**。

## 核心原理（三条，缺一不可）

1. **`BOOT-INF/classes/**/*.class`** —— 应用自己的类，`@Value("${x.y}")` 的字符串就在常量池里。
2. **`BOOT-INF/lib/*.jar` 是嵌套 jar，必须再解一层**。跳过这一步会漏掉公共模块
   （如 `xxx-common-redis`、`xxx-common-rabbitmq`）里定义的键。
3. **`${...}` 只能扫出"占位符式"配置**。还有一类是**绑定式配置**
   （`spring.datasource.*` / `spring.redis.*`，由 `@ConfigurationProperties` 或 starter 自动绑定），
   它们**在字节码里看不到 `${}`**，但缺了同样起不来。
   → 靠 `BOOT-INF/lib` 里有没有对应的 starter 来推断（见下方"绑定式配置推断表"）。

## 步骤

### 1. 拿到 jar（远端不要整包顺序下，先看能不能直连）

Seafile/对象存储等分享链接常能换成直链后做 Range 或直接下载。判断标准：先发一个
`Range: bytes=0-8388607` 请求测速，>5 MB/s 就直接整包下（100 MB 约 10 s），
不要为了省流量去逐条 Range 读一个 jar 里几百个 class。

也可参考 `seafile-anon-share-download` skill 里的 `&dl=1 → 302 → seafhttp/files/<token>/` 手法。

### 2. 批量扫描占位符

```python
import zipfile, io, re, os
PH = re.compile(rb"\$\{([^}]{1,120})\}")

def scan_app(z, out):                       # 第一层：应用自己的类
    for n in z.namelist():
        if n.startswith("BOOT-INF/classes/") and n.endswith(".class"):
            for m in PH.finditer(z.read(n)):
                out.setdefault(m.group(1).decode("utf-8","replace"), set()).add(n)

def scan_nested(z, out):                    # 第二层：嵌套依赖 jar
    for n in z.namelist():
        if not (n.startswith("BOOT-INF/lib/") and n.endswith(".jar")):
            continue
        try:
            inner = zipfile.ZipFile(io.BytesIO(z.read(n)))
        except Exception:
            continue
        for m in inner.namelist():
            if "META-INF/maven" in m:       # 必须排除，否则被 pom.xml 淹掉
                continue
            if m.endswith((".class",".yml",".yaml",".properties",".xml")):
                for mm in PH.finditer(inner.read(m)):
                    out.setdefault(mm.group(1).decode("utf-8","replace"), set()).add(n.split("/")[-1]+"!"+m)
```

去噪规则（不加会被 600+ 条噪音淹没）：key 必须匹配 `^[A-Za-z][A-Za-z0-9_.\-]{2,60}$`，
并排除 `LOG_` / `LOGBACK` / `CONSOLE_LOG` / `FILE_LOG` / `logging.` / `PID:-`。

### 3. 归属拆分（决定放共享配置还是服务专属配置）

按「**这个 key 被几个服务的 jar 引用**」拆：

- 被 ≥2 个服务引用 → 共享配置（如 `application-prod.yml`）
- 只被 1 个服务引用 → 该服务的专属配置（如 `eigw-xxx-prod.yml`）

### 4. 补上绑定式配置

对照 `BOOT-INF/lib` 里的 starter 推断：

| lib 里有 | 说明必须配 |
|---|---|
| `druid-spring-boot-starter` + `mysql-connector-j` | `spring.datasource.*` |
| `spring-data-redis` 或 `xxx-common-redis` | `spring.redis.*` |
| `spring-amqp` / `amqp-client` / `xxx-common-rabbitmq` | `spring.rabbitmq.*` |
| `mybatis` / `mybatis-plus-core` | `mybatis.*` / `mybatis-plus.*` |

**没有 DB starter 的服务就是纯接收/转发服务，不需要数据源配置** —— 这条能省掉一半无效排查。

### 4b. ⭐ 反推 `mybatis-plus.typeAliasesPackage`（有 mapper XML 就必须有）

绑定式配置还有个更隐蔽的兄弟：**MyBatis 的短别名**。
mapper XML 里写 `resultType="DeviceData"`（**不带包名**）时，必须靠
`mybatis-plus.typeAliasesPackage` 扫描该包注册别名，否则启动即死在：

```
Failed to parse mapping resource: 'file [.../mapper/handle/DeviceDataMapper.xml]'
  Caused by: org.apache.ibatis.type.TypeException: Could not resolve type alias 'DeviceData'
  Caused by: java.lang.ClassNotFoundException: Cannot find class: DeviceData
```

注意报错链前面会有一大串 `UnsatisfiedDependencyException` → `sqlSessionFactory` → `Failed to parse`，
**真正有信息量的只有最后那个 `Caused by`**。

**扫法**（直接拿到该填什么）：

```python
xmls = [n for n in z.namelist()
        if n.startswith("BOOT-INF/classes/") and n.endswith(".xml")
        and n != "BOOT-INF/classes/logback.xml"]      # logback.xml 要排除
for n in xmls:
    for m in re.finditer(r'(?:resultType|parameterType|type)\s*=\s*"([A-Za-z_][\w.$]*)"', z.read(n).decode()):
        if "." not in m.group(1):                      # 不含点的就是短别名
            alias.add(m.group(1))
```

再把短别名对应的 `.class` 在 jar 里定位到包
（`BOOT-INF/classes/com/x/<模块>/domain/DeviceData.class` → 包名 `com.x.<模块>`），
那个包名就是 `typeAliasesPackage` 的值。

**三条要点**：

- **没有 mapper XML 的服务不会炸** —— 它压根不解析别名。所以"只有个别服务起不来"时优先怀疑这个。
  （实例：7 个 jar 里只有 handle 带 mapper XML，就它一个启动失败）
- **包名 ≠ artifactId**：`eigw-modules-receive-canteen` 的包是 `com.sankun.canteen`，
  不是 `com.sankun.receive-canteen`。**以 jar 内实测为准**，别照名字猜。
- 一旦给某个服务配了 `mapperLocations`，就把 `typeAliasesPackage` 一起配上，别等炸了再补。

### 5. 拿不准语义就上 javap（比猜/比翻文档可靠得多）

本机有 JDK 时：

```bash
# 1) 把目标 class 从 jar 里抽出来（BOOT-INF/classes/ 下）
python -c "import zipfile;open('X.class','wb').write(zipfile.ZipFile('app.jar').read('BOOT-INF/classes/com/x/Y.class'))"

# 2) 读 @Value 的实参 + 字段类型
javap -v -p X.class | grep -E "Utf8 +\$\{|value=|^  private"
```

能一次拿到三样东西：

- **每个 `@Value("${k}")` 到底绑到哪个字段**（字段名往往就是语义，如 `wsUrlPre` vs `clientPrefix`）
- **值的拼装规则**：`javap -c` 看 `run()`/`<init>` 里的 `StringBuilder.append` 链，
  就知道最终字符串长什么样（例：`wsUrlPre + clientPrefix + "-" + clientId`，
  说明配置里那个 `wsUrl` 只是**前缀**，不是完整地址）
- **这个依赖失败会不会让服务起不来**：看调用点是否 `try/catch` + 重连调度。
  如果异常被全捕获只 `log.error` + `scheduleReconnect()`，那么**这个配置填错也不会导致启动失败**，
  排查时可以放心排除，把注意力放到真正致命的键上。

同时别忘了看 `BOOT-INF/lib/*.jar` 里公共模块的 Config 类：
队列名/交换机名这类常量**常常是硬编码的 Bean 名**，不需要写进配置 —— 别把它们当成缺失项去要。

### 6. 交出可用的东西

生成两类文件，别只给一份 JSON：

- `配置项清单.md`：表格 `配置项 | 需要它的服务 | 代码默认值 | 出处类`，出处类能直接拿去问研发
- `配置模板/*.yml`：每项写成 `key: <<待填>>`，把扫到的默认值放注释里；
  头部注明该服务端口、是否需要 DB、这份文件在 Nacos 里叫什么 dataId

### 7. ⭐ 另一条路：直接从部署现场挖出真实配置（比反推准得多）

**反推是下策，真配置往往就在机器上。** 只要这台机器上有人部署过（哪怕失败、哪怕容器已删），
Nacos 客户端会把拉到的配置**落盘缓存**，`docker overlay2` 的可写层里就留着原样文件。

判断该走这条路的信号：

- 日志里报的配置**确实被读到了**（如 `Origin: "spring.datasource.type" from property source
  "bootstrapProperties-application-prod.yml,DEFAULT_GROUP"`）→ 说明配置曾经存在
- Nacos 界面/API 查命名空间却是空的 → 大概率查错了实例，或配置在别的部署里
- 机器上有 `/home/logs/<app>/` 之类的业务日志 → 有人真跑过

挖掘点（按命中率排序）：

```bash
# ① overlay2 可写层里 Nacos 的本地配置存储  ← 命中率最高
find /var/lib/docker/overlay2 -type f -path "*tenant-config-data/*" 2>/dev/null

# 典型路径：/var/lib/docker/overlay2/<id>/diff/home/nacos/data/tenant-config-data/<namespace>/<group>/

# ② 宿主机挂载目录（Nacos 常把 data 挂出来）
find /home/nacos /home/nacos2 -type f -path "*eigw*" 2>/dev/null

# ③ 精准定位某容器的可写层（比盲 find 快）
docker inspect <container> -f '{{.GraphDriver.Data.UpperDir}}'

# ④ 业务日志目录（能看出失败点、也能看到加载了哪些 dataId）
find /home/logs -type f 2>/dev/null
```

**过滤规则**（不滤会捞出一堆中间态文件）：

```bash
case "$b" in *snapshot*|*encrypted*|*\.tmp*) continue;; esac
```

**两个必须注意的点**：

1. **同一份配置在 overlay2 里会有多份副本**（每个容器层各一份，内容可能是不同时期的版本）。
   用 `[ -f "$REAL/$b" ] || cp -f ...` 只留第一份，或按 `stat -c %Y` 取最新的 —— 但要意识到
   你拿到的是**某个时刻的版本**，与线上此刻跑的可能有差异。
2. **文件名相同、内容不同很常见**：生产里同一服务可能同时有 `<name>-prod.yml`（IP 版）
   和 `<name>.yml`（容器名版），靠 `spring.profiles.active` 切换。别只抓一个就下结论。

**挖到之后最有价值的用途**：把真实配置与你的自造配置**逐项对照**，输出的差异表就是最好的部署文档素材
（哪些键是硬编码的、哪些值随环境变、哪些写法是官方"正解"）。

> 实例对照（2026-09，eigw 工控机）：真实共享配置里有
> `spring.autoconfigure.exclude: com.alibaba.druid.spring.boot.autoconfigure.DruidDataSourceAutoConfigure`
> —— 官方是用**排除自动配置类**来根治 druid 绑定问题，而不是"小心翼翼地不放 datasource"。
> 这类"官方正解"只有拿到真配置才知道。

## 顺带能验证的两件事

- **配置份数可以算准**：Spring Boot 的 `bootstrap.yml` 里 `shared-configs` 列出共享配置，
  而 Spring Cloud Alibaba 还会**默认自动加载** `${spring.application.name}-${profile}.${file-extension}`。
  两者相加 = 该服务的全部 dataId。Nacos 命名空间里有几份、该有几份，一次算清。
- **版本不一致能当场发现**：如果日志里报的占位符 `key` 在你手上的 jar 里**搜不到**，
  说明线上那个容器跑的不是这一版镜像 —— 别拿它的报错去推断当前版本的病因。
  用 `docker image inspect <img> --format '{{.Created}}'` 对一下构建时间即可坐实。

## ⭐ 反向校验：配置值填错了，怎么从运行态发现（2026-09-28 实战）

反推配置只保证「键都在、值填得进去」，**不保证值填对了**。
Spring 只校验「键存在且能解析成字符串」，**不校验值的语义** —— 填错照样启动成功、
照样注册服务发现，日志一行错都不报。

**唯一会露馅的地方是运行态的数字。** 本次三个症状全部由此暴露：

| 症状 | 查法 |
|---|---|
| 某队列消费者数比源码多 | `rabbitmqctl list_queues name consumers` |
| 出现源码里搜不到的交换机 / 队列 | `rabbitmqctl list_exchanges name type` / `list_queues` |
| 某个 listener 收不到自己的消息 | 上面两条横向对比（源码要求几个 vs 实测几个） |

### 四步反查路径（可复用）

1. **数运行态**：`list_queues name messages consumers`、`list_exchanges name type`。
   实测消费者数 ≠ 源码里该队列的 `@RabbitListener` 方法数（且没配 `concurrency`）→ 异常，进入 2。
2. **查字面量归属**：`grep -rla "<队列名>" <解包目录>` —— 字面量里出现它的才是"天生"的消费者。
   多出来的消费者必然来自**用占位符的类**。
3. **反查占位符**：`grep -rla '${<前缀>\.' <解包目录>` 拿到用占位符的类，再看它们注解用的是哪个 key：

   ```java
   @RabbitListener(bindings = @QueueBinding(
       exchange = @Exchange(value = "${eigw.listener.exchangeName}"),
       value    = @Queue(value    = "${eigw.listener.queueName}"),
       key      = "${eigw.listener.routeKey}" )))
   ```

   → **这些类消费哪个队列，完全由配置值决定**。
4. **现拉实值**：从配置中心读**实际生效**的那份（不是本地模板！），对齐第 3 步的 key，根因即现。

### 三个高频坑

- **`@Bean` 方法名 ≠ 值**：公共库里 `public DirectExchange eigwExchange()` 内部其实是
  `new DirectExchange("eigw-exchange")`。反推配置时**只认字符串常量**，
  方法名 / 局部变量名 / 类型名都不是依据 —— 本次就是照方法名填了
  `eigw.listener.exchangeName: eigwExchange`，凭空造出一个幽灵交换机。
- **一处配置错误往往不止一个症状**：本次一个 listener 段填错 → 多出 3 个消费者 +
  1 个幽灵交换机 + 1 个撞车队列。看到两个互不相干的怪现象，先怀疑同源。
- **单次快照不足以定性**：本次曾把「某队列 consumers=0」判为"链路断点"，次日复核为 1 ——
  那个 0 只是服务某次启动失败的瞬时态（日志有 `Failed to start bean 'webServerStartStop'`
  与 `NacosException: Client not connected`）。**记录消费者数时，同时看服务的
  `Started ... in N seconds` 与 `.State.RestartCount`**。

## 坑位

| 现象 | 原因 / 解法 |
|---|---|
| 扫出 600+ 条莫名其妙的 key | 没排除 `META-INF/maven/**/pom.xml`，加之依赖 jar 里的 logback 环境变量 |
| 怎么都搜不到日志里报的那个 key | ① 漏了解 `BOOT-INF/lib` 里的嵌套 jar；② 该容器跑的是旧版镜像（见上） |
| 扫出来一堆 `${log.path}` / `${log.pattern}` | 来自 `logback.xml`，不是业务配置，按后缀 `.xml` 过滤或在报告里单列 |
| jar 里找不到 `spring.datasource.url` | 正常。它是绑定式配置，永远不在 `${}` 清单里，靠 lib 推断补上 |
| 从分享/网盘下载的 jar 只有几 KB，或 `docker load` 报格式错 | 下载链接少了下载参数（Seafile 类网盘要 `&dl=1`），拿到的是**预览页 HTML**。下载后一定要按已知字节数校验，别只看"下载成功" |
| 校验"共享配置里没有 datasource"却数出 3 行 | `grep -c datasource` **把注释行也算进去了**。要先剔注释：`grep -v '^[[:space:]]*#'`，或直接 `grep -E '^[[:space:]]*datasource:'` 只认键 |
| 导入 Nacos 后回读字节数与本地不一致 | `GET /nacos/v1/cs/configs` 返回的是 `{"code":200,...,"data":"<内容>"}` 的 **JSON 包裹**，而你比的是整个响应体长度。要解析出 `data` 字段再比；另外长度差几字节属正常（换行转义） |
| 回读只回来一个 100 多字节的短响应 | 没带 `accessToken` 被 403 拒了，**不是导入失败**。判断导入是否真的成功，看服务日志里的 `Origin: ... from property source "bootstrapProperties-<dataId>,DEFAULT_GROUP"` 才可靠 |
| 改了共享配置后服务报 `Failed to bind properties` | 共享配置被所有服务读，改动面最大。新增配置项前先确认**所有**服务的 lib 里都有对应 starter（例：把 `spring.datasource.type=druid` 放进共享配置，会让没有 druid 包的接收服务直接启动失败） |
| `Could not resolve placeholder X.first.host` | 多套连接的配置（`first`/`second`、`master`/`slave`）**不会从单套键推导** —— 必须有几组就显式给几组。动手前先 `javap -v -p` 看 `@Primary`/`@Qualifier`，能判断"只补这几组够不够、会不会 bean 歧义" |
| YAML 里出现两个顶层 `spring:` | 重复顶层键会互相覆盖（SnakeYAML）。往 Nacos 配置里"追加一段"时最容易踩 —— 必须先看该文件已有哪个顶层键，**宁可整份重写**也不要另起一个同名块 |
| 日志里报的 mapper 文件名/jar 条目在自己手上找不到 | 先别怀疑自己看错：① 用 `docker exec <c> md5sum /path/app.jar` 与本地 jar 比 md5，确认是不是同一份；② 低分辨率截图上读长文件名/类名极易出错，以**本地 jar 实测**为准 |
