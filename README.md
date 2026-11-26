# 健身计划（Fitness Planner）

企业级分层架构的健身计划 Web 应用：Python（FastAPI）后端 + SQLite 持久化 + 原生前端，移动优先，手机浏览器直接访问。

两个页面：**今日计划**（右下角悬浮 `+` 新建计划，可多部位、多动作）和**历史**（按天记录训练了哪些部位）。支持**注册 / 登录**，多账号各自独立记录，互不可见。

## 功能

| 模块 | 能力 |
| --- | --- |
| 账号 | 注册（用户名 2–20 位，密码 ≥ 8 位）、登录、退出；会话 Cookie 保持 7 天，刷新/关浏览器不掉登录 |
| 数据隔离 | 每个账号只看得到自己的计划、动作、历史与统计；访问他人计划一律 404 |
| 今日计划 | 展示当天未完成的计划；右下角悬浮 `＋` 弹出新建面板 |
| 新建计划 | 选日期、多选部位（最多 5 个）、填动作（动作名/组数/次数/重量，最多 20 个）、主题与备注 |
| 从历史复用 | 计划页右上角「从历史选」：列出已打卡的计划（按天分组），点「加入今日」把部位、动作、组次重量、休息时长原样复制到今天，可改重量后再打卡 |
| 计划内动作管理 | 已保存的计划卡片上可继续「＋ 动作」追加，也可逐个删除动作 |
| 动作可编辑 | 每个动作行右侧「✎」打开编辑面板，名称/组数/次数/重量/休息时长都可改；改名撞重名返回 409，历史（已打卡）计划只读，需先「撤销打卡」再改 |
| 组间休息计时 | 每个动作可自定义每组休息秒数（1–600，默认 90）；点动作上的「⏱」唤起倒计时面板，支持预设 30/45/60/90/120/180 秒、±15 秒微调、暂停/继续，到点响铃 + 震动提示；关闭面板后底部悬浮计时条继续倒计时 |
| 训练专注模式 | 计划卡片点「开始训练」进入全屏训练视图：逐动作列出每组，勾选即记录该组实际次数与重量，勾完自动开始该动作的组间休息倒计时，顶部可「跳过」；全部组完成后点「完成训练并打卡」 |
| 逐组 RPE | 每组可记主观强度 RPE（6–10，0.5 步进）：勾组前选好会随组一起存，勾完也能改或清除；训练卡片显示该动作平均 RPE，进步明细里带每次训练的平均 RPE |
| 替换 / 跳过动作 | 训练中每个动作都有「↔ 替换」和「跳过这个动作」：替换只改动作名（组数/次数/重量/休息不变，可从历史动作里点选），跳过的动作变灰、不计入必做组数，可随时「恢复」；跳过时若已有记录会提示并清空 |
| 逐组记录 | 每组可单独勾选/取消，实际重量与次数可现场改（不影响计划值）；取消某组后可重新记录。卡片上显示「已完成 2/3 组 · 实际容量 xxx kg」与每动作「已做 2 组：10×60kg / 8×60kg」 |
| 计划整体编辑 | 卡片右上「✎」改日期/部位/标题/备注，保存后立刻生效（改到别的日期会从今日列表移走） |
| 打卡 | 计划完成后点「完成打卡」转入历史；历史里可「撤销打卡」退回计划 |
| 体重曲线 | 历史页「体重」区块记体重与体脂，展示最新值、较上次增减与折线趋势，可删除单条记录 |
| 周视图 | 历史页顶部按自然周（周一…周日）汇总近 8 周：柱状为该周训练容量、折线为该周体重，另给周均容量 / 周均训练次数 / 最近体重 |
| 动作进步 | 历史页「动作进步」按动作看历史最大重量折线、最好重量 PR、单次容量与预估 1RM（Epley 公式），并列出每次训练明细 |
| 历史 | 按天聚合：日期 + 星期 + 当天训练部位 + 每次计划的动作明细，顶部有累计/本周/组数/容量与部位分布 |
| 数据自动汇总 | 每个动作算容量（组数 × 次数 × 重量），每个计划算总组数/总容量，每一天算总容量 |
| 接口校验 | Pydantic 校验；部位白名单、部位数上限、动作名不可重复、动作列表非空，非法输入返回 422 |
| 移动端适配 | 移动优先、≥44px 触控热区、底部安全区、悬浮按钮、底部抽屉式弹层 |

## 技术栈

- Python 3.12 + FastAPI + Uvicorn + Pydantic v2
- SQLite（标准库 `sqlite3`，WAL、外键级联、日期与状态索引）
- 前端：原生 HTML / CSS / JS，零框架依赖
- 分层：配置层 → 数据访问层（Repository）→ 路由层 → 模型 Schema
- 鉴权：标准库 `hashlib.pbkdf2_hmac`（SHA-256，20 万次迭代 + 16 字节随机盐）+ `hmac.compare_digest`、服务端会话表 + HttpOnly Cookie，零第三方依赖

## 数据模型

```
users                        账号
├── id, username(唯一), password_hash(pbkdf2 加盐摘要), created_at
└── auth_sessions            服务端会话（token 仅存 SHA-256 摘要，7 天过期）
    └── token_hash(PK), user_id, expires_at

training_plans               一条训练计划（可多部位，按 user_id 隔离）
├── id, plan_date, body_parts(逗号分隔, 如 "胸,肩"), title, note
├── status  planned(待完成) / done(已打卡)
└── plan_exercises           计划内动作（一对多，级联删除）
    ├── id, plan_id, name, sets, reps, weight, rest_seconds, skipped, sort_order
    └── exercise_sets        逐组打卡记录（一对多，级联删除，UNIQUE(动作,组号)）
        └── id, exercise_id, set_index, done, reps, weight, rpe, done_at

body_records                 体重记录（按 user_id 隔离）
└── id, user_id, date, weight, body_fat, note, created_at
```

数据迁移全部自动完成，无需手动操作：

- 旧版 `training_sessions` 表 → 迁移为“已完成”的历史计划后删除旧表
- 旧库升级到多用户版本时自动补 `user_id` 列；**首个注册的账号会自动认领此前本机保存的所有训练数据**（注册成功时返回 `adopted_legacy: true`），换了账号体系的旧数据不会丢

## 目录结构

```
fitness_tracker/
├── main.py                  启动入口
├── requirements.txt
├── README.md
├── scripts/
│   └── doctor.py            数据库体检/修复（缺表缺列、路径不对时用）
└── app/
    ├── __init__.py          应用工厂（日志/静态资源/路由/异常处理）
    ├── config.py            配置 + 业务时区
    ├── database.py          连接管理、建表、索引、旧数据迁移
    ├── models.py            Pydantic Schema 与校验
    ├── security.py          口令哈希、会话令牌、登录限流
    ├── auth.py              鉴权依赖（Cookie → 当前用户）
    ├── repository.py        SQL 集中封装（全部按 user_id 隔离）
    ├── routers/
    │   ├── auth.py          注册 / 登录 / 退出 / 当前用户
    │   ├── plans.py         计划 CRUD、打卡/撤销、历史聚合
    │   ├── bodies.py        体重接口（保留）
    │   └── stats.py         概览统计
    ├── templates/index.html
    └── static/{css,js}
```

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

首次打开会先看到登录页，点「注册」建账号即可（第一个注册的账号会自动继承本机旧数据）。

- 本机浏览器：`http://127.0.0.1:8000`
- 手机：与电脑同一 WiFi，打开 `http://<电脑局域网IP>:8000`（Windows 放行 8000 端口）
- 接口文档：`http://127.0.0.1:8000/docs`

> `0.0.0.0:8000` 只是监听绑定地址，浏览器不能直接打开，请用 `127.0.0.1` 或局域网 IP。

## 部署到云端

想让手机在任意网络下都能访问，需要部署到有公网 IP 的服务器，见 [DEPLOY.md](DEPLOY.md)：

- 云服务器一键：`sudo bash deploy/deploy.sh`（自动装 Python/Nginx/systemd，有域名则一并申请 HTTPS）
- 容器：`docker compose up -d --build`
- Render（无需服务器）：仓库自带 `Dockerfile` 和 `render.yaml`，Blueprint 一键建服务；**必须挂持久磁盘并把 `FIT_DB_PATH` 指到挂载点**，否则每次重新部署数据清空。端口自动读平台注入的 `PORT`

## API

除注册/登录外，**所有 `/api/*` 接口都需要登录会话**，未登录返回 401。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册并自动登录（用户名已存在 409） |
| POST | `/api/auth/login` | 登录（连续 5 次失败锁定 60 秒，返回 429） |
| POST | `/api/auth/logout` | 退出登录（清除会话与 Cookie） |
| GET | `/api/auth/me` | 当前登录用户 |
| GET | `/api/body-parts` | 训练部位白名单 |
| GET | `/api/plans` | 查计划，支持 `plan_date`、`status=planned\|done` |
| GET | `/api/plans/others` | 非今日的待完成计划 |
| POST | `/api/plans` | 新建计划（多部位 + 多动作） |
| GET | `/api/plans/{id}` | 计划详情 |
| POST | `/api/plans/{id}/complete` | 完成打卡（重复打卡返回 409） |
| POST | `/api/plans/{id}/reopen` | 撤销打卡 |
| POST | `/api/plans/{id}/copy` | 从历史复制该计划到今天（可用 `?plan_date=` 指定日期） |
| POST | `/api/plans/{id}/exercises` | 追加动作 |
| PATCH | `/api/plans/{id}` | 整体修改计划：日期/部位/标题/备注任意子集，至少一项，空对象 422 |
| PUT | `/api/plans/{id}/exercises/{eid}/sets/{n}` | 记录/取消第 n 组：`{"done":true,"reps":12,"weight":60,"rpe":8.5}` 记录实际值（不传 reps/weight 保留已有、缺省沿用计划值；RPE 需为 0.5 的整数倍且 1–10），`{"done":false}` 取消；组号超出计划组数 404 |
| POST | `/api/plans/{id}/exercises/{eid}/skip?skip=true\|false` | 跳过 / 恢复该动作（跳过会清空其已记录组），返回更新后的计划 |
| PATCH | `/api/plans/{id}/exercises/{eid}` | 局部修改动作：只传要改的字段（名称/组数/次数/重量/休息），空对象 422，改名重复 409 |
| DELETE | `/api/plans/{id}/exercises/{eid}` | 删除动作 |
| DELETE | `/api/plans/{id}` | 删除计划（级联动作） |
| GET | `/api/history` | 历史按天聚合 |
| GET | `/api/stats` | 概览统计 |
| GET/POST | `/api/bodies` | 体重记录列表 / 新增 |
| GET | `/api/progress/exercise-names` | 有历史的动作名列表（次数、最近训练日） |
| GET | `/api/weekly?weeks=8` | 周视图：每周容量/组数/训练次数/体重，及周均容量与周均次数 |
| GET | `/api/progress/exercise?name=` | 某动作的进步数据：每次最大重量/容量/组数/预估 1RM、PR、最好容量；无历史 404 |
| GET | `/health` | 健康检查 |

### 新建计划示例

```json
{
  "plan_date": "2026-11-26",
  "body_parts": ["胸", "肩"],
  "title": "推日",
  "note": "训练 60 分钟",
  "exercises": [
    {"name": "杠铃卧推", "sets": 4, "reps": 12, "weight": 60, "rest_seconds": 120},
    {"name": "哑铃肩推", "sets": 3, "reps": 10, "weight": 20, "rest_seconds": 90}
  ]
}
```

约束：`body_parts` 限 胸/背/腿/肩/臂/核心/有氧/全身/其他 且 1–5 个；动作 1–20 个且同计划内不重名；组数 1–99；次数 1–999；重量 0–1000 kg（自重填 0）；休息 1–600 秒；`plan_date` 省略时默认业务时区的今天。

## 配置项（环境变量，前缀 `FIT_`）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FIT_HOST` | `0.0.0.0` | 监听地址 |
| `FIT_PORT` | `8000` | 端口；云平台（Render 等）注入的 `PORT` 优先级更高 |
| `FIT_DB_PATH` | `data/fitness.db` | 数据库文件 |
| `FIT_DEBUG` | `false` | 调试/热重载 |
| `FIT_CORS_ORIGINS` | 空 | 允许跨域来源 |
| `FIT_TIMEZONE` | `Asia/Shanghai` | 业务时区（决定“今天”） |
| `FIT_SESSION_DAYS` | `7` | 登录会话有效期（天） |
| `FIT_COOKIE_SECURE` | `false` | 部署在 HTTPS 时设为 `true`，Cookie 只走加密通道 |

## 实现要点

- 每个请求使用独立 SQLite 连接（`check_same_thread=False`），避免线程池跨线程报错；
- 打卡用 `UPDATE ... WHERE status='planned'` 条件更新，天然防止重复打卡；
- 历史聚合在仓储层完成，路由只做序列化；
- 前端事件统一用委托处理，删改后整体刷新，避免状态不一致；
- 弹层用 `hidden` 属性 + `[hidden]{display:none}` 保证关闭后不遮挡页面（`.field`、`.sheet-mask` 都是 flex，必须显式覆盖）；
- 鉴权用 `Depends(current_user)` 注入，业务仓储一律 `PlanRepository(conn, user["id"])`，隔离写在 SQL 里而不是路由里，避免漏过滤；
- 口令只存 `pbkdf2_sha256$迭代$盐$摘要`；会话令牌落库前做 SHA-256，数据库泄露也无法直接冒用；
- 会话 Cookie 为 `HttpOnly + SameSite=Lax`，前端 JS 读不到，降低 XSS 窃取风险；HTTPS 部署时开 `FIT_COOKIE_SECURE`。

## 休息计时器实现说明

- 计时基于绝对截止时间（`Date.now() + 剩余秒数`）计算，不用累加 `setInterval` 次数，切后台/卡顿后剩余时间依然准确；
- 到点用 Web Audio 播三次短音 + `navigator.vibrate` 震动，部分浏览器不支持音频时静默降级；
- 面板里选中的预设时长会 `PATCH` 回该动作的 `rest_seconds`，下次打开直接沿用；
- 每请求独立连接、`check_same_thread=False`，避免线程池跨线程报错。

## 疑难排查

先跑一次体检（只读，不改数据），两种写法等价：

```bash
python main.py --doctor        # 不用先起服务，直接体检
python scripts/doctor.py
```

它会打印**库文件的绝对路径**、现有表、缺失的表与列、账号与计划数量。发现问题后：

```bash
python scripts/doctor.py --fix     # 先备份成 .bak-时间戳，再自动补齐缺失的表与列
```

常见报错对照：

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `sqlite3.OperationalError: no such table: users` | 库文件里没有账号体系相关的表（库是旧版本建的，或启动时初始化没落到这个文件上） | `python scripts/doctor.py --fix` 自动补表；服务运行中还缺表时会**自动自愈**并在日志里打一条 `数据库缺少表 [...]，尝试自动补齐` |
| `sqlite3.OperationalError: no such column: user_id` | 旧库缺少多用户列 | 同上，启动时会自动 `ALTER TABLE` 补列 |
| `/api/auth/register` 返回 404 | 跑的是旧版代码（没有 auth 路由），或进程没重启 | 访问 `/health`，看 `version` 是否为 `7.2`；确认端口上跑的是当前目录的代码 |
| 启动直接抛 `RuntimeError: 数据库初始化后仍缺表 [...]` | 建表被同名的视图/索引挡住，或库文件不可写 | `python scripts/doctor.py --fix`（会先备份，并清理同名冲突对象）；日志里会有 `建表语句执行失败（…）` 的具体语句 |
| 接口返回 503 +「数据库不可用」 | 数据库文件被杀毒软件/网盘占用，或所在目录不可写 | 把项目放到非同步目录，或用 `FIT_DB_PATH` 指定一个普通本地路径 |

数据库默认在项目根目录下的 `data/fitness.db`（相对路径按项目根解析，与启动时的当前目录无关）。如果你之前在别的目录跑过，可能生成了两份库文件——以 `/health` 返回的 `db` 字段为准。

启动成功后日志里会有一行自检横幅：

```
启动完成 v7.2 | 库文件：/…/data/fitness.db | 表数量：7
```

版本号对不上，就说明端口上跑的还是旧代码（或者你在另一个目录启动过）。

`/health` 现在返回版本号和库路径，是最快的“我到底跑的是哪一版、用的哪个库”的自检方式：

```json
{"status": "ok", "app": "健身记录", "version": "7.2", "db": "/…/data/fitness.db"}
```

## 后续可扩展方向

按真实使用顺序排列的优先级：

1. **执行态记录**：每组单独打勾、记录实际重量/次数，自动进入下一组，计划与实际对比；
2. **计划复用**：动作库 + 计划模板（一键套用「推日」）、复制上次训练、周计划日历；
3. **离线可用**：PWA + Service Worker（健身房信号差）、倒计时期间屏幕常亮（Wake Lock）；
4. **分析与提醒**：单动作力量趋势、PR 识别、部位间隔提醒、周/月训练量热力图；
5. **数据安全**：JSON/CSV 导出导入、多设备账号体系（JWT）；
6. **体验**：深色模式、动作排序拖拽、语音快捷输入、体重/围度模块接回前端。
