/* 本地数据层（纯静态版专用）
   ---------------------------------------------------------------
   把原来 FastAPI 后端提供的 /api/* 接口，用浏览器 localStorage 重新实现一遍：
   路径、请求体、返回结构都照搬后端（app/repository.py），前端逻辑一行不改。
   数据只存在当前浏览器里，换设备或清缓存会丢，所以提供了导出/导入备份。

   内部结构（注意：组数 = sets，逐组记录 = logs）：
   plan = { id, plan_date, body_parts[], title, note, status, completed_at, created_at,
            exercises: [{ id, name, sets, reps, weight, rest_seconds, note, sort_order, skipped,
                          logs: [{ set_index, done, reps, weight, rpe, done_at }] }] }
*/
(function () {
    "use strict";

    // 账号与数据分开放：账号表 / 会话 / 每个账号各自一份数据
    const ACCOUNTS_KEY = "fitness_accounts_v1";
    const SESSION_KEY = "fitness_session_v1";
    const DATA_PREFIX = "fitness_data_v1_";
    const LEGACY_KEY = "fitness_local_v1";   // 上一版（无账号）的数据，首次注册时认领

    const BODY_PARTS = ["胸", "背", "腿", "肩", "臂", "核心", "有氧", "全身", "其他"];
    const MAX_PARTS = 5;
    const MAX_EXERCISES = 20;

    /* ---------------- 小工具 ---------------- */
    const pad = (n) => String(n).padStart(2, "0");

    function todayISO() {
        const d = new Date();
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    function nowLocal() {
        const d = new Date();
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }

    function dateFromISO(iso) {
        return new Date(`${iso}T00:00:00`);
    }

    function weekStart(iso) {
        // 与后端一致：周一为一周起点
        const d = dateFromISO(iso);
        d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    function addDays(iso, days) {
        const d = dateFromISO(iso);
        d.setDate(d.getDate() + days);
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    const r2 = (n) => Math.round((Number(n) || 0) * 100) / 100;

    /* ---------------- 错误 ---------------- */
    class HttpError extends Error {
        constructor(status, detail) {
            super(detail);
            this.status = status;
            this.detail = detail;
        }
    }

    /* ---------------- 持久化 ---------------- */
    function emptyDB() {
        return {
            version: 2,
            seq: { plan: 1, ex: 1, body: 1, tpl: 1, meas: 1, cardio: 1 },
            plans: [],
            bodies: [],
            templates: [],
            goals: { target_weight: null, weekly_sessions: null, target_date: null },
            measurements: [],
            cardios: [],
            trash: [],
            meta: { last_export_at: null, theme: "auto" },
        };
    }

    function normalize(parsed) {
        if (!parsed || !Array.isArray(parsed.plans)) return emptyDB();
        parsed.seq = Object.assign({ plan: 1, ex: 1, body: 1, tpl: 1, meas: 1, cardio: 1 }, parsed.seq || {});
        parsed.bodies = parsed.bodies || [];
        parsed.templates = parsed.templates || [];
        parsed.measurements = parsed.measurements || [];
        parsed.cardios = parsed.cardios || [];
        parsed.trash = parsed.trash || [];
        parsed.goals = Object.assign({ target_weight: null, weekly_sessions: null, target_date: null }, parsed.goals || {});
        parsed.meta = Object.assign({ last_export_at: null, theme: "auto" }, parsed.meta || {});
        parsed.templates.forEach((t) => {
            t.exercises = (t.exercises || []).map((e) => ({
                name: e.name,
                sets: Number(e.sets) || 3,
                reps: Number(e.reps) || 10,
                weight: Number(e.weight) || 0,
                rest_seconds: Number(e.rest_seconds) || 90,
            }));
        });
        parsed.plans.forEach((p) => {
            p.exercises = p.exercises || [];
            p.body_parts = p.body_parts || [];
            p.exercises.forEach((e) => {
                e.logs = e.logs || [];
                e.skipped = !!e.skipped;
                e.note = e.note || "";
                e.rest_seconds = e.rest_seconds || 90;
            });
        });
        return parsed;
    }

    /* ---------------- 账号（本机档案，不是服务器账号） ---------------------------- */
    function loadAccounts() {
        try {
            const list = JSON.parse(localStorage.getItem(ACCOUNTS_KEY));
            return Array.isArray(list) ? list : [];
        } catch (err) {
            console.warn("账号表读取失败：", err);
            return [];
        }
    }

    function saveAccounts() {
        try {
            localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
        } catch (err) {
            throw new HttpError(507, "浏览器本地存储已满，无法创建账号");
        }
    }

    const accounts = loadAccounts();
    let session = null;          // { id, username }
    let db = emptyDB();          // 当前账号的数据
    let dataKey = null;          // 当前账号的存储键

    function requireSession() {
        if (!session) throw new HttpError(401, "请先登录");
    }

    /* ---- 口令派生：优先 WebCrypto，非安全上下文（file:// 或 http 内网 IP）退回轻量哈希 ---- */
    const encoder = new TextEncoder();

    function hexOf(bytes) {
        return Array.from(new Uint8Array(bytes)).map((b) => b.toString(16).padStart(2, "0")).join("");
    }

    function randomSalt() {
        const arr = new Uint8Array(16);
        if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(arr);
        else for (let i = 0; i < arr.length; i += 1) arr[i] = Math.floor(Math.random() * 256);
        return hexOf(arr);
    }

    function weakHash(text) {
        // 仅在 crypto.subtle 不可用时用作兜底：不是密码学强度，只防误看
        let h1 = 0x811c9dc5;
        let h2 = 0x1000193;
        for (let round = 0; round < 20000; round += 1) {
            for (let i = 0; i < text.length; i += 1) {
                h1 = (h1 ^ text.charCodeAt(i)) >>> 0;
                h1 = (h1 * 0x01000193) >>> 0;
                h2 = (h2 + text.charCodeAt(i) + round) >>> 0;
                h2 = ((h2 << 5) | (h2 >>> 27)) >>> 0;
            }
        }
        return `w${h1.toString(16)}${h2.toString(16)}`;
    }

    async function derive(password, saltHex) {
        if (!window.crypto || !window.crypto.subtle) {
            return { scheme: "weak", hash: weakHash(`${saltHex}|${password}`) };
        }
        const salt = new Uint8Array(saltHex.match(/../g).map((h) => parseInt(h, 16)));
        const key = await window.crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
        const bits = await window.crypto.subtle.deriveBits(
            { name: "PBKDF2", salt, iterations: 120000, hash: "SHA-256" },
            key,
            256
        );
        return { scheme: "pbkdf2", hash: hexOf(bits) };
    }

    function currentAccount() {
        return session ? accounts.find((a) => a.id === session.id) || null : null;
    }

    /* ---- 数据读写（按账号分键） ---- */
    function normalize(parsed) {
        if (!parsed || !Array.isArray(parsed.plans)) return emptyDB();
        parsed.seq = Object.assign({ plan: 1, ex: 1, body: 1, tpl: 1, meas: 1, cardio: 1 }, parsed.seq || {});
        parsed.bodies = parsed.bodies || [];
        parsed.templates = parsed.templates || [];
        parsed.measurements = parsed.measurements || [];
        parsed.cardios = parsed.cardios || [];
        parsed.trash = parsed.trash || [];
        parsed.goals = Object.assign({ target_weight: null, weekly_sessions: null, target_date: null }, parsed.goals || {});
        parsed.meta = Object.assign({ last_export_at: null, theme: "auto" }, parsed.meta || {});
        parsed.templates.forEach((t) => {
            t.exercises = (t.exercises || []).map((e) => ({
                name: e.name,
                sets: Number(e.sets) || 3,
                reps: Number(e.reps) || 10,
                weight: Number(e.weight) || 0,
                rest_seconds: Number(e.rest_seconds) || 90,
            }));
        });
        parsed.plans.forEach((p) => {
            p.exercises = p.exercises || [];
            p.body_parts = p.body_parts || [];
            p.exercises.forEach((e) => {
                e.logs = e.logs || [];
                e.skipped = !!e.skipped;
                e.note = e.note || "";
                e.rest_seconds = e.rest_seconds || 90;
            });
        });
        return parsed;
    }

    function emptyDB() {
        return {
            version: 2,
            seq: { plan: 1, ex: 1, body: 1, tpl: 1, meas: 1, cardio: 1 },
            plans: [],
            bodies: [],
            templates: [],
            goals: { target_weight: null, weekly_sessions: null, target_date: null },
            measurements: [],
            cardios: [],
            trash: [],
            meta: { last_export_at: null, theme: "auto" },
        };
    }

    function readJSON(key) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? normalize(JSON.parse(raw)) : null;
        } catch (err) {
            console.warn("本地数据读取失败：", key, err);
            return null;
        }
    }

    function loadFor(account) {
        dataKey = DATA_PREFIX + account.id;
        db = readJSON(dataKey) || emptyDB();
    }

    function save() {
        if (!session) throw new HttpError(401, "请先登录");
        try {
            localStorage.setItem(dataKey, JSON.stringify(db));
        } catch (err) {
            console.error("本地数据写入失败：", err);
            throw new HttpError(507, "浏览器本地存储已满，请先在「备份」里导出，再清理旧数据");
        }
    }

    // 启动时恢复上次登录
    (function restoreSession() {
        try {
            const raw = localStorage.getItem(SESSION_KEY);
            const saved = raw ? JSON.parse(raw) : null;
            const account = saved && accounts.find((a) => a.id === saved.id);
            if (account) {
                session = { id: account.id, username: account.username };
                loadFor(account);
            }
        } catch (err) {
            console.warn("会话恢复失败：", err);
        }
    })();

    function nextId(kind) {
        const id = db.seq[kind] || 1;
        db.seq[kind] = id + 1;
        return id;
    }

    /** 训练用时（分钟）：进入训练 → 打卡之间的时间，缺任一端返回 null。 */
    function planDuration(plan) {
        if (!plan.started_at || !plan.completed_at) return null;
        const start = new Date(plan.started_at.replace(" ", "T"));
        const end = new Date(plan.completed_at.replace(" ", "T"));
        const mins = Math.round((end - start) / 60000);
        return mins > 0 ? mins : 0;
    }

    /* ---------------- 组出参（对齐 PlanOut） ---------------- */
    function planOut(plan) {
        const exercises = plan.exercises
            .slice()
            .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
            .map((e) => {
                const doneLogs = e.logs
                    .filter((s) => s.done)
                    .sort((a, b) => a.set_index - b.set_index)
                    .map((s) => ({ set_index: s.set_index, reps: s.reps, weight: s.weight, rpe: s.rpe }));
                const actualVolume = r2(doneLogs.reduce((sum, s) => sum + (s.reps || 0) * (s.weight || 0), 0));
                const rpeVals = doneLogs.map((s) => s.rpe).filter((v) => v !== null && v !== undefined);
                return {
                    id: e.id,
                    name: e.name,
                    sets: e.sets,
                    reps: e.reps,
                    weight: e.weight,
                    rest_seconds: e.rest_seconds,
                    sort_order: e.sort_order,
                    volume: r2(e.sets * e.reps * e.weight),
                    done_sets: doneLogs,
                    done_count: doneLogs.length,
                    actual_volume: actualVolume,
                    skipped: !!e.skipped,
                    avg_rpe: rpeVals.length
                        ? Math.round((rpeVals.reduce((a, b) => a + b, 0) / rpeVals.length) * 10) / 10
                        : null,
                };
            });

        return {
            id: plan.id,
            plan_date: plan.plan_date,
            body_parts: plan.body_parts.slice(),
            title: plan.title,
            note: plan.note,
            status: plan.status,
            completed_at: plan.completed_at,
            started_at: plan.started_at || null,
            duration_min: planDuration(plan),
            exercises,
            exercise_count: exercises.length,
            total_sets: exercises.reduce((s, e) => s + e.sets, 0),
            total_volume: r2(exercises.reduce((s, e) => s + e.volume, 0)),
            done_set_count: exercises.filter((e) => !e.skipped).reduce((s, e) => s + e.done_count, 0),
            total_set_count: exercises.filter((e) => !e.skipped).reduce((s, e) => s + e.sets, 0),
            actual_volume: r2(exercises.filter((e) => !e.skipped).reduce((s, e) => s + e.actual_volume, 0)),
        };
    }

    /* ---------------- 校验 ---------------- */
    function findPlan(id) {
        const plan = db.plans.find((p) => p.id === Number(id));
        if (!plan) throw new HttpError(404, "计划不存在");
        return plan;
    }

    function findExercise(plan, eid) {
        const ex = plan.exercises.find((e) => e.id === Number(eid));
        if (!ex) throw new HttpError(404, "动作不存在或不属于该计划");
        return ex;
    }

    function checkParts(parts) {
        if (!Array.isArray(parts) || !parts.length) throw new HttpError(422, "至少选择一个训练部位");
        if (parts.length > MAX_PARTS) throw new HttpError(422, `最多选择 ${MAX_PARTS} 个部位`);
        const invalid = parts.filter((p) => !BODY_PARTS.includes(p));
        if (invalid.length) throw new HttpError(422, `部位不合法：${invalid.join("、")}`);
        return Array.from(new Set(parts));
    }

    function checkExercise(ex) {
        const name = String((ex && ex.name) || "").trim();
        if (!name) throw new HttpError(422, "动作名称不能为空");
        const sets = Number(ex.sets);
        const reps = Number(ex.reps);
        const weight = Number(ex.weight) || 0;
        const rest = Number(ex.rest_seconds ?? 90);
        if (!Number.isFinite(sets) || sets < 1 || sets > 99) throw new HttpError(422, "组数需在 1–99 之间");
        if (!Number.isFinite(reps) || reps < 1 || reps > 999) throw new HttpError(422, "次数需在 1–999 之间");
        if (weight < 0 || weight > 1000) throw new HttpError(422, "重量需在 0–1000 kg 之间");
        if (!Number.isFinite(rest) || rest < 1 || rest > 600) throw new HttpError(422, "休息时长需在 1–600 秒之间");
        return { name, sets, reps, weight, rest_seconds: rest };
    }

    function sortDesc(list) {
        return list
            .slice()
            .sort((a, b) => (a.plan_date === b.plan_date ? b.id - a.id : a.plan_date < b.plan_date ? 1 : -1));
    }

    function sortAsc(list) {
        return list
            .slice()
            .sort((a, b) => (a.plan_date === b.plan_date ? b.id - a.id : a.plan_date < b.plan_date ? -1 : 1));
    }

    /* ---------------- 路由 ---------------- */
    const routes = [];

    function route(method, pattern, fn) {
        const keys = [];
        const re = new RegExp(
            "^" +
                pattern.replace(/:([A-Za-z_]+)/g, (_, k) => {
                    keys.push(k);
                    return "([^/]+)";
                }) +
                "$"
        );
        routes.push({ method, re, keys, fn });
    }

    function dispatch(method, path, query, body) {
        // 除注册/登录/查询当前用户外，所有接口都要求已登录
        const authPath =
            path === "/api/auth/register" ||
            path === "/api/auth/login" ||
            path === "/api/auth/me" ||
            path === "/api/auth/logout";
        if (!authPath) requireSession();
        for (const r of routes) {
            if (r.method !== method) continue;
            const m = r.re.exec(path);
            if (!m) continue;
            const params = {};
            r.keys.forEach((k, i) => (params[k] = m[i + 1]));
            return r.fn(query, params, body || {});
        }
        throw new HttpError(404, `本地数据层没有这个接口：${method} ${path}`);
    }

    /* ---- 账号 ---- */
    const NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$/;

    route("POST", "/api/auth/register", async (q, p, body) => {
        const username = String(body.username || "").trim();
        const password = String(body.password || "");
        if (!NAME_RE.test(username)) throw new HttpError(422, "用户名只能包含字母、数字、下划线或中文，长度 2–20");
        if (password.length < 8) throw new HttpError(422, "密码至少 8 位");
        if (accounts.some((a) => a.username === username)) throw new HttpError(409, "该用户名已被占用");

        const salt = randomSalt();
        const derived = await derive(password, salt);
        const account = {
            id: accounts.reduce((mx, a) => Math.max(mx, a.id), 0) + 1,
            username,
            salt,
            scheme: derived.scheme,
            hash: derived.hash,
            created_at: nowLocal(),
        };
        accounts.push(account);
        saveAccounts();

        session = { id: account.id, username: account.username };
        localStorage.setItem(SESSION_KEY, JSON.stringify(session));

        // 首个账号认领上一版（无账号）留下的数据，避免升级后记录看不见
        let adopted = false;
        const legacy = readJSON(LEGACY_KEY);
        if (legacy && legacy.plans.length) {
            dataKey = DATA_PREFIX + account.id;
            db = legacy;
            save();
            localStorage.removeItem(LEGACY_KEY);
            localStorage.removeItem("fitness_local_v1"); // 兼容旧键名
            adopted = true;
        } else {
            loadFor(account);
        }
        return { user: { id: account.id, username: account.username }, adopted_legacy: adopted };
    });

    route("POST", "/api/auth/login", async (q, p, body) => {
        const username = String(body.username || "").trim();
        const password = String(body.password || "");
        const account = accounts.find((a) => a.username === username);
        if (!account) throw new HttpError(401, "用户名或密码不正确");
        const derived = await derive(password, account.salt);
        if (derived.hash !== account.hash) throw new HttpError(401, "用户名或密码不正确");
        session = { id: account.id, username: account.username };
        localStorage.setItem(SESSION_KEY, JSON.stringify(session));
        loadFor(account);
        return { user: { id: account.id, username: account.username }, adopted_legacy: false };
    });

    route("GET", "/api/auth/me", () => {
        if (!session) throw new HttpError(401, "请先登录");
        return { id: session.id, username: session.username };
    });

    route("POST", "/api/auth/logout", () => {
        session = null;
        db = emptyDB();
        dataKey = null;
        localStorage.removeItem(SESSION_KEY);
        return null;
    });

    /* ---- 元信息 ---- */
    route("GET", "/api/body-parts", () => ({ body_parts: BODY_PARTS.slice() }));

    /* ---- 计划查询 ---- */
    route("GET", "/api/plans", (q) => {
        let list = db.plans.slice();
        if (q.plan_date) list = list.filter((p) => p.plan_date === q.plan_date);
        if (q.status) list = list.filter((p) => p.status === q.status);
        return sortDesc(list).map(planOut);
    });

    route("GET", "/api/plans/others", () => {
        const today = todayISO();
        return sortAsc(
            db.plans.filter((p) => p.status === "planned" && p.plan_date !== today)
        ).map(planOut);
    });

    route("GET", "/api/plans/:id", (q, p) => planOut(findPlan(p.id)));

    /* ---- 计划写操作 ---- */
    route("POST", "/api/plans", (q, p, body) => {
        const parts = checkParts(body.body_parts);
        const rawExercises = body.exercises || [];
        if (!rawExercises.length) throw new HttpError(422, "至少需要一个动作");
        if (rawExercises.length > MAX_EXERCISES) throw new HttpError(422, `最多 ${MAX_EXERCISES} 个动作`);
        const exercises = rawExercises.map(checkExercise);
        const names = exercises.map((e) => e.name);
        if (names.length !== new Set(names).size) throw new HttpError(422, "同一个计划内动作名称不能重复");

        const plan = {
            id: nextId("plan"),
            plan_date: body.plan_date || todayISO(),
            body_parts: parts,
            title: String(body.title || "").trim(),
            note: String(body.note || "").trim(),
            status: "planned",
            completed_at: null,
            created_at: nowLocal(),
            exercises: [],
        };
        exercises.forEach((e, idx) => {
            plan.exercises.push({ id: nextId("ex"), ...e, note: "", sort_order: idx, skipped: false, logs: [] });
        });
        db.plans.push(plan);
        save();
        return planOut(plan);
    });

    route("PATCH", "/api/plans/:id", (q, p, body) => {
        const plan = findPlan(p.id);
        const fields = body || {};
        if (!Object.keys(fields).length) throw new HttpError(422, "没有可更新的字段");
        if (fields.plan_date !== undefined && fields.plan_date !== null) plan.plan_date = fields.plan_date;
        if (fields.body_parts !== undefined && fields.body_parts !== null) plan.body_parts = checkParts(fields.body_parts);
        if (fields.title !== undefined && fields.title !== null) plan.title = String(fields.title).trim();
        if (fields.note !== undefined && fields.note !== null) plan.note = String(fields.note).trim();
        save();
        return planOut(plan);
    });

    route("DELETE", "/api/plans/:id", (q, p) => {
        const plan = findPlan(p.id);
        db.plans = db.plans.filter((x) => x !== plan);
        // 软删除：先进回收站，30 天后再彻底清掉，前端可「撤销」
        db.trash.push(Object.assign({}, plan, { deleted_at: nowLocal() }));
        purgeTrash();
        save();
        return { trashed: true, id: plan.id, name: plan.title || plan.body_parts.join("+") };
    });

    route("POST", "/api/plans/:id/restore", (q, p) => {
        const idx = db.trash.findIndex((x) => String(x.id) === String(p.id));
        if (idx < 0) throw new HttpError(404, "回收站里没有这个计划");
        const plan = db.trash.splice(idx, 1)[0];
        delete plan.deleted_at;
        db.plans.push(plan);
        save();
        return planOut(plan);
    });

    route("GET", "/api/trash", () => {
        purgeTrash();
        return db.trash
            .slice()
            .sort((a, b) => (a.deleted_at < b.deleted_at ? 1 : -1))
            .map((x) => ({
                id: x.id,
                plan_date: x.plan_date,
                title: x.title,
                body_parts: x.body_parts.slice(),
                exercise_count: x.exercises.length,
                deleted_at: x.deleted_at,
            }));
    });

    route("POST", "/api/plans/:id/start", (q, p) => {
        const plan = findPlan(p.id);
        if (!plan.started_at) {
            plan.started_at = nowLocal();
            save();
        }
        return planOut(plan);
    });

    route("POST", "/api/plans/:id/copy", (q, p) => {
        const src = findPlan(p.id);
        const plan = {
            id: nextId("plan"),
            plan_date: q.plan_date || todayISO(),
            body_parts: src.body_parts.slice(),
            title: src.title,
            note: src.note,
            status: "planned",
            completed_at: null,
            created_at: nowLocal(),
            exercises: src.exercises
                .slice()
                .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
                .map((e, idx) => ({
                    id: nextId("ex"),
                    name: e.name,
                    sets: e.sets,
                    reps: e.reps,
                    weight: e.weight,
                    rest_seconds: e.rest_seconds,
                    note: "",
                    sort_order: idx,
                    skipped: false,
                    logs: [],
                })),
        };
        db.plans.push(plan);
        save();
        return planOut(plan);
    });

    route("POST", "/api/plans/:id/complete", (q, p) => {
        const plan = findPlan(p.id);
        if (plan.status === "done") throw new HttpError(409, "该计划已完成，无需重复打卡");
        plan.status = "done";
        plan.completed_at = nowLocal();
        save();
        return planOut(plan);
    });

    route("POST", "/api/plans/:id/reopen", (q, p) => {
        const plan = findPlan(p.id);
        if (plan.status !== "done") throw new HttpError(409, "该计划尚未完成");
        plan.status = "planned";
        plan.completed_at = null;
        save();
        return planOut(plan);
    });

    /* ---- 动作 ---- */
    route("POST", "/api/plans/:id/exercises", (q, p, body) => {
        const plan = findPlan(p.id);
        const checked = checkExercise(body);
        if (plan.exercises.some((e) => e.name === checked.name)) {
            throw new HttpError(409, "同一计划内动作名称不能重复");
        }
        const order = plan.exercises.length ? Math.max(...plan.exercises.map((e) => e.sort_order)) + 1 : 0;
        const ex = { id: nextId("ex"), ...checked, note: "", sort_order: order, skipped: false, logs: [] };
        plan.exercises.push(ex);
        save();
        return planOut(plan).exercises.find((e) => e.id === ex.id);
    });

    route("PATCH", "/api/plans/:id/exercises/:eid", (q, p, body) => {
        const plan = findPlan(p.id);
        const ex = findExercise(plan, p.eid);

        if (body.name !== undefined && body.name !== null) {
            const name = String(body.name).trim();
            if (!name) throw new HttpError(422, "动作名称不能为空");
            if (plan.exercises.some((e) => e.id !== ex.id && e.name === name)) {
                throw new HttpError(409, "同一计划内动作名称不能重复");
            }
            ex.name = name;
        }
        if (body.sets !== undefined && body.sets !== null) ex.sets = Number(body.sets);
        if (body.reps !== undefined && body.reps !== null) ex.reps = Number(body.reps);
        if (body.weight !== undefined && body.weight !== null) ex.weight = Number(body.weight);
        if (body.rest_seconds !== undefined && body.rest_seconds !== null) ex.rest_seconds = Number(body.rest_seconds);

        if (ex.sets < 1 || ex.sets > 99) throw new HttpError(422, "组数需在 1–99 之间");
        if (ex.reps < 1 || ex.reps > 999) throw new HttpError(422, "次数需在 1–999 之间");
        if (ex.weight < 0 || ex.weight > 1000) throw new HttpError(422, "重量需在 0–1000 kg 之间");
        if (ex.rest_seconds < 1 || ex.rest_seconds > 600) throw new HttpError(422, "休息时长需在 1–600 秒之间");

        // 组数调小：超出新组数的已记录组一并清掉，避免残留脏数据
        ex.logs = ex.logs.filter((s) => s.set_index <= ex.sets);
        save();
        return planOut(plan).exercises.find((e) => e.id === ex.id);
    });

    route("DELETE", "/api/plans/:id/exercises/:eid", (q, p) => {
        const plan = findPlan(p.id);
        findExercise(plan, p.eid);
        plan.exercises = plan.exercises.filter((e) => e.id !== Number(p.eid));
        save();
        return null;
    });

    /* ---- 逐组记录 ---- */
    route("PUT", "/api/plans/:id/exercises/:eid/sets/:idx", (q, p, body) => {
        const plan = findPlan(p.id);
        const ex = findExercise(plan, p.eid);
        const idx = Number(p.idx);
        if (!Number.isInteger(idx) || idx < 1 || idx > ex.sets) {
            throw new HttpError(404, "组序号超出该动作的计划组数");
        }
        const existing = ex.logs.find((s) => s.set_index === idx);
        const wantDone = body.done === undefined ? true : !!body.done;

        if (!wantDone) {
            ex.logs = ex.logs.filter((s) => s.set_index !== idx);
            save();
            return { set_index: idx, reps: null, weight: null, rpe: null, done: false };
        }

        // 实际次数/重量：传了就用，没传则沿用已有记录，再退回计划值
        const reps = body.reps !== undefined && body.reps !== null
            ? Number(body.reps)
            : existing && existing.reps !== null && existing.reps !== undefined
                ? existing.reps
                : ex.reps;
        const weight = body.weight !== undefined && body.weight !== null
            ? Number(body.weight)
            : existing && existing.weight !== null && existing.weight !== undefined
                ? existing.weight
                : ex.weight;
        let rpe = body.rpe !== undefined && body.rpe !== null ? Number(body.rpe) : null;
        if (rpe !== null && !Number.isFinite(rpe)) rpe = null;
        if (rpe !== null) {
            if (rpe < 1 || rpe > 10) throw new HttpError(422, "RPE 需在 1–10 之间");
            if (Math.abs(rpe * 2 - Math.round(rpe * 2)) > 1e-9) throw new HttpError(422, "RPE 需为 0.5 的整数倍");
            rpe = Math.round(rpe * 10) / 10;
        }

        if (existing) {
            existing.done = true;
            existing.reps = reps;
            existing.weight = weight;
            existing.rpe = rpe;
            existing.done_at = nowLocal();
        } else {
            ex.logs.push({ set_index: idx, done: true, reps, weight, rpe, done_at: nowLocal() });
        }
        save();
        return { set_index: idx, reps, weight, rpe, done: true };
    });

    /* ---- 跳过 / 恢复某个动作 ---- */
    route("POST", "/api/plans/:id/exercises/:eid/skip", (q, p) => {
        const plan = findPlan(p.id);
        const ex = findExercise(plan, p.eid);
        const skip = String(q.skip ?? "true") !== "false";
        let cleared = 0;
        if (skip) {
            cleared = ex.logs.filter((s) => s.done).length;
            ex.logs = [];
        }
        ex.skipped = skip;
        save();
        const out = planOut(plan);
        out.cleared_sets = cleared;
        return out;
    });

    /* ---- 历史 / 统计 ---- */
    route("GET", "/api/history", () => {
        const done = sortDesc(db.plans.filter((p) => p.status === "done")).map(planOut);
        const days = new Map();
        done.forEach((p) => {
            let day = days.get(p.plan_date);
            if (!day) {
                day = {
                    date: p.plan_date,
                    body_parts: [],
                    plan_count: 0,
                    exercise_count: 0,
                    total_sets: 0,
                    total_volume: 0,
                    plans: [],
                };
                days.set(p.plan_date, day);
            }
            day.plans.push(p);
            day.plan_count += 1;
            day.exercise_count += p.exercise_count;
            day.total_sets += p.total_sets;
            day.total_volume = r2(day.total_volume + p.total_volume);
            p.body_parts.forEach((part) => {
                if (!day.body_parts.includes(part)) day.body_parts.push(part);
            });
        });
        return Array.from(days.values())
            .sort((a, b) => (a.date < b.date ? 1 : -1))
            .slice(0, 120);
    });

    route("GET", "/api/stats", () => {
        const donePlans = db.plans.filter((p) => p.status === "done");
        const durations = donePlans.map(planDuration).filter((v) => v !== null && v > 0);
        const streak = streakInfo();
        const mw = latestMeasurement();
        const week = weekStart(todayISO());
        let totalSets = 0;
        let totalVolume = 0;
        donePlans.forEach((p) => {
            p.exercises.forEach((e) => {
                totalSets += e.sets;
                totalVolume += e.sets * e.reps * e.weight;
            });
        });
        const latest = db.bodies.slice().sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1))[0];
        const dist = {};
        donePlans.forEach((p) => p.body_parts.forEach((part) => (dist[part] = (dist[part] || 0) + 1)));
        const distSorted = Object.fromEntries(Object.entries(dist).sort((a, b) => b[1] - a[1]));
        return {
            total_plans: db.plans.length,
            done_plans: donePlans.length,
            week_sessions: donePlans.filter((p) => p.plan_date >= week).length,
            total_sets: totalSets,
            total_volume: r2(totalVolume),
            latest_weight: latest ? latest.weight : null,
            body_part_dist: distSorted,
            // ---- 以下为扩展字段 ----
            streak_current: streak.current,
            streak_best: streak.best,
            avg_duration: durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null,
            goals: db.goals,
            weekly_target: db.goals.weekly_sessions || null,
            latest_measurement: mw,
            last_export_at: db.meta.last_export_at || null,
            cardio_minutes: db.cardios.reduce((sum, c) => sum + (Number(c.minutes) || 0), 0),
        };
    });

    /* ---- 连续打卡 / 热力图 ---- */
    function streakInfo() {
        const days = new Set(db.plans.filter((p) => p.status === "done").map((p) => p.plan_date));
        const today = todayISO();
        const yesterday = addDays(today, -1);
        let current = 0;
        if (days.has(today) || days.has(yesterday)) {
            let cursor = days.has(today) ? today : yesterday;
            while (days.has(cursor)) {
                current += 1;
                cursor = addDays(cursor, -1);
            }
        }
        const sorted = Array.from(days).sort();
        let best = 0;
        let run = 0;
        let prev = null;
        sorted.forEach((d) => {
            run = prev && addDays(prev, 1) === d ? run + 1 : 1;
            best = Math.max(best, run);
            prev = d;
        });
        return { current, best, days: sorted };
    }

    route("GET", "/api/streak", () => {
        const info = streakInfo();
        const today = todayISO();
        const start = addDays(today, -118);
        const heat = [];
        const doneByDay = new Map();
        db.plans
            .filter((p) => p.status === "done" && p.plan_date >= start)
            .forEach((p) => {
                const item = doneByDay.get(p.plan_date) || { sessions: 0, volume: 0 };
                const out = planOut(p);
                item.sessions += 1;
                item.volume = r2(item.volume + (out.actual_volume || out.total_volume));
                doneByDay.set(p.plan_date, item);
            });
        for (let i = 0; i < 119; i += 1) {
            const d = addDays(start, i);
            const item = doneByDay.get(d) || { sessions: 0, volume: 0 };
            heat.push({ date: d, sessions: item.sessions, volume: item.volume });
        }
        return { current: info.current, best: info.best, days: heat };
    });

    /* ---- 某个动作最近一次的表现（训练页「上次」提示） ---- */
    route("GET", "/api/last-performance", (q) => {
        const name = String(q.name || "").trim();
        if (!name) throw new HttpError(422, "请提供动作名称");
        const done = db.plans
            .filter((p) => p.status === "done")
            .sort((a, b) => (a.plan_date === b.plan_date ? b.id - a.id : a.plan_date < b.plan_date ? 1 : -1));
        for (const plan of done) {
            const ex = plan.exercises.find((e) => e.name === name && !e.skipped);
            if (!ex) continue;
            const logs = ex.logs.filter((s) => s.done).sort((a, b) => a.set_index - b.set_index);
            const sets = logs.length
                ? logs.map((l) => ({ reps: l.reps, weight: l.weight, rpe: l.rpe }))
                : Array.from({ length: ex.sets }, () => ({ reps: ex.reps, weight: ex.weight, rpe: null }));
            return {
                name,
                plan_date: plan.plan_date,
                max_weight: sets.reduce((mx, s) => Math.max(mx, Number(s.weight) || 0), 0),
                sets,
                volume: r2(sets.reduce((sum, s) => sum + (s.reps || 0) * (s.weight || 0), 0)),
            };
        }
        return { name, plan_date: null, max_weight: 0, sets: [], volume: 0 };
    });

    /* ---- 训练模板 ---- */
    route("GET", "/api/templates", () =>
        db.templates
            .slice()
            .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
            .map((t) => ({ ...t, exercise_count: t.exercises.length }))
    );

    route("POST", "/api/templates", (q, p, body) => {
        // 两种来源：直接传动作数组，或传 plan_id 把某个计划存成模板
        let source = null;
        if (body.plan_id) source = planOut(findPlan(body.plan_id));
        const name = String(body.name || (source ? source.title || source.body_parts.join("+") : "") || "未命名模板").trim().slice(0, 50);
        const parts = source ? source.body_parts.slice() : (body.body_parts || []).slice();
        const exercises = source
            ? source.exercises.map((e) => ({
                  name: e.name,
                  sets: e.sets,
                  reps: e.reps,
                  weight: e.weight,
                  rest_seconds: e.rest_seconds,
              }))
            : (body.exercises || []).map((e) => {
                  const c = checkExercise(e);
                  return { name: c.name, sets: c.sets, reps: c.reps, weight: c.weight, rest_seconds: c.rest_seconds };
              });
        if (!exercises.length) throw new HttpError(422, "模板里至少要有一个动作");
        if (db.templates.some((t) => t.name === name)) throw new HttpError(409, "已有同名模板，换个名字");
        const tpl = {
            id: nextId("tpl"),
            name,
            body_parts: parts.length ? parts : ["其他"],
            note: String(body.note || "").trim(),
            exercises,
            created_at: nowLocal(),
        };
        db.templates.push(tpl);
        save();
        return { ...tpl, exercise_count: exercises.length };
    });

    route("DELETE", "/api/templates/:id", (q, p) => {
        const before = db.templates.length;
        db.templates = db.templates.filter((t) => String(t.id) !== String(p.id));
        if (db.templates.length === before) throw new HttpError(404, "模板不存在");
        save();
        return null;
    });

    route("POST", "/api/templates/:id/apply", (q, p, body) => {
        const tpl = db.templates.find((t) => String(t.id) === String(p.id));
        if (!tpl) throw new HttpError(404, "模板不存在");
        const plan = {
            id: nextId("plan"),
            plan_date: body.plan_date || todayISO(),
            body_parts: tpl.body_parts.slice(),
            title: tpl.name,
            note: tpl.note,
            status: "planned",
            completed_at: null,
            started_at: null,
            created_at: nowLocal(),
            exercises: tpl.exercises.map((e, idx) => ({
                id: nextId("ex"),
                name: e.name,
                sets: e.sets,
                reps: e.reps,
                weight: e.weight,
                rest_seconds: e.rest_seconds,
                note: "",
                sort_order: idx,
                skipped: false,
                logs: [],
            })),
        };
        db.plans.push(plan);
        save();
        return planOut(plan);
    });

    /* ---- 界面偏好（主题） ---- */
    route("GET", "/api/meta", () => db.meta);

    route("PATCH", "/api/meta", (q, p, body) => {
        if (body.theme !== undefined) {
            const theme = String(body.theme);
            if (!["auto", "light", "dark"].includes(theme)) throw new HttpError(422, "主题取值只能是 auto/light/dark");
            db.meta.theme = theme;
            save();
        }
        return db.meta;
    });

    /* ---- 目标 ---- */
    route("GET", "/api/goals", () => db.goals);

    route("PATCH", "/api/goals", (q, p, body) => {
        if (body.target_weight !== undefined) {
            db.goals.target_weight = body.target_weight === null || body.target_weight === "" ? null : Number(body.target_weight);
            if (db.goals.target_weight !== null && (db.goals.target_weight < 20 || db.goals.target_weight > 500)) {
                throw new HttpError(422, "目标体重需在 20–500 kg 之间");
            }
        }
        if (body.weekly_sessions !== undefined) {
            db.goals.weekly_sessions = body.weekly_sessions === null || body.weekly_sessions === "" ? null : Number(body.weekly_sessions);
            if (db.goals.weekly_sessions !== null && (db.goals.weekly_sessions < 1 || db.goals.weekly_sessions > 21)) {
                throw new HttpError(422, "每周目标次数需在 1–21 之间");
            }
        }
        if (body.target_date !== undefined) db.goals.target_date = body.target_date || null;
        save();
        return db.goals;
    });

    /* ---- 围度 ---- */
    function latestMeasurement() {
        const list = db.measurements.slice().sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1));
        return list[0] || null;
    }

    route("GET", "/api/measurements", () =>
        db.measurements
            .slice()
            .sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1))
            .slice(0, 200)
            .map((m) => ({ ...m }))
    );

    route("POST", "/api/measurements", (q, p, body) => {
        const fields = ["chest", "waist", "arm", "thigh"];
        const record = { id: nextId("meas"), date: body.date || todayISO() };
        let any = false;
        fields.forEach((f) => {
            const raw = body[f];
            if (raw === undefined || raw === null || raw === "") {
                record[f] = null;
                return;
            }
            const v = Number(raw);
            if (!Number.isFinite(v) || v < 10 || v > 200) throw new HttpError(422, "围度需在 10–200 cm 之间");
            record[f] = v;
            any = true;
        });
        if (!any) throw new HttpError(422, "至少填写一个围度");
        record.note = String(body.note || "").trim();
        record.created_at = nowLocal();
        db.measurements.push(record);
        save();
        return { ...record };
    });

    route("DELETE", "/api/measurements/:id", (q, p) => {
        const before = db.measurements.length;
        db.measurements = db.measurements.filter((m) => String(m.id) !== String(p.id));
        if (db.measurements.length === before) throw new HttpError(404, "记录不存在");
        save();
        return null;
    });

    /* ---- 有氧 ---- */
    route("GET", "/api/cardios", () =>
        db.cardios
            .slice()
            .sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1))
            .slice(0, 200)
            .map((c) => ({ ...c }))
    );

    route("POST", "/api/cardios", (q, p, body) => {
        const type = String(body.type || "跑步").trim().slice(0, 10);
        const minutes = Number(body.minutes);
        if (!Number.isFinite(minutes) || minutes < 1 || minutes > 600) throw new HttpError(422, "时长需在 1–600 分钟之间");
        let distance = null;
        if (body.distance_km !== undefined && body.distance_km !== null && body.distance_km !== "") {
            distance = Number(body.distance_km);
            if (!Number.isFinite(distance) || distance < 0 || distance > 200) throw new HttpError(422, "距离需在 0–200 km 之间");
        }
        let hr = null;
        if (body.avg_hr !== undefined && body.avg_hr !== null && body.avg_hr !== "") {
            hr = Number(body.avg_hr);
            if (!Number.isFinite(hr) || hr < 40 || hr > 220) throw new HttpError(422, "平均心率需在 40–220 之间");
        }
        const record = {
            id: nextId("cardio"),
            date: body.date || todayISO(),
            type,
            minutes,
            distance_km: distance,
            avg_hr: hr,
            note: String(body.note || "").trim(),
            created_at: nowLocal(),
        };
        db.cardios.push(record);
        save();
        return { ...record };
    });

    route("DELETE", "/api/cardios/:id", (q, p) => {
        const before = db.cardios.length;
        db.cardios = db.cardios.filter((c) => String(c.id) !== String(p.id));
        if (db.cardios.length === before) throw new HttpError(404, "记录不存在");
        save();
        return null;
    });

    /* ---- 回收站清理：只保留 30 天 ---- */
    function purgeTrash() {
        const cutoff = addDays(todayISO(), -30);
        db.trash = db.trash.filter((x) => (x.deleted_at || "").slice(0, 10) >= cutoff);
    }

    /* ---- 动作进步 ---- */
    /* ---- 本周每部位组数（增肌看「每部位每周有效组数」） ---- */
    route("GET", "/api/part-sets", (q) => {
        const weeks = Math.max(1, Math.min(12, Number(q.weeks) || 1));
        const start = addDays(weekStart(todayISO()), -7 * (weeks - 1));
        const parts = {};
        db.plans
            .filter((p) => p.status === "done" && p.plan_date >= start)
            .forEach((p) => {
                const done = p.exercises.filter((e) => !e.skipped);
                // 直接打卡没逐组记录时，按计划组数计（否则会出现「0 组」的假警告）
                const anyLog = done.some((e) => e.logs.some((l) => l.done));
                done.forEach((e) => {
                    const key = p.body_parts && p.body_parts.length === 1 ? p.body_parts[0] : (p.body_parts[0] || "其他");
                    const item = parts[key] || { part: key, sets: 0, plans: 0, exercises: 0 };
                    const logged = e.logs.filter((l) => l.done).length;
                    item.sets += logged || (anyLog ? 0 : e.sets);
                    item.exercises += 1;
                    parts[key] = item;
                });
                (p.body_parts || []).forEach((part) => {
                    if (!parts[part]) parts[part] = { part, sets: 0, plans: 0, exercises: 0 };
                    parts[part].plans += 1;
                });
            });
        const list = Object.values(parts).sort((a, b) => b.sets - a.sets);
        const totalSets = list.reduce((sum, i) => sum + i.sets, 0);
        return { start, weeks, parts: list, total_sets: totalSets };
    });

    /* ---- 某动作最近几次的表现（用于渐进超负荷建议） ---- */
    route("GET", "/api/exercise-history", (q) => {
        const name = String(q.name || "").trim();
        if (!name) throw new HttpError(422, "请提供动作名称");
        const limit = Math.max(1, Math.min(10, Number(q.limit) || 5));
        const sessions = db.plans
            .filter((p) => p.status === "done")
            .sort((a, b) => (a.plan_date === b.plan_date ? b.id - a.id : a.plan_date < b.plan_date ? 1 : -1))
            .map((p) => {
                const ex = p.exercises.find((e) => e.name === name && !e.skipped);
                if (!ex) return null;
                const logs = ex.logs.filter((l) => l.done);
                return {
                    plan_date: p.plan_date,
                    plan_sets: ex.sets,
                    plan_reps: ex.reps,
                    done_sets: logs.length,
                    max_weight: logs.reduce((mx, l) => Math.max(mx, Number(l.weight) || 0), ex.weight || 0),
                    avg_reps: logs.length ? Math.round(logs.reduce((sum, l) => sum + (Number(l.reps) || 0), 0) / logs.length) : null,
                    volume: r2(logs.reduce((sum, l) => sum + (Number(l.reps) || 0) * (Number(l.weight) || 0), 0)),
                    completed: logs.length >= ex.sets,
                };
            })
            .filter(Boolean)
            .slice(0, limit);
        return { name, sessions };
    });

    /* ---- 各动作的 PR（训练页徽章用） ---- */
    route("GET", "/api/prs", () => {
        const map = new Map();
        db.plans
            .filter((p) => p.status === "done")
            .forEach((p) => {
                p.exercises.forEach((e) => {
                    if (e.skipped) return;
                    const logs = e.logs.filter((l) => l.done);
                    const weight = logs.length ? logs.reduce((mx, l) => Math.max(mx, Number(l.weight) || 0), 0) : (e.weight || 0);
                    if (!weight) return;
                    const item = map.get(e.name) || { name: e.name, pr_weight: 0, pr_date: null, sessions: 0 };
                    item.sessions += 1;
                    if (weight > item.pr_weight) { item.pr_weight = weight; item.pr_date = p.plan_date; }
                    map.set(e.name, item);
                });
            });
        return Array.from(map.values()).sort((a, b) => b.pr_weight - a.pr_weight);
    });

    route("GET", "/api/progress/exercise-names", () => {
        const map = new Map();
        db.plans.forEach((p) => {
            p.exercises.forEach((e) => {
                const item = map.get(e.name) || { name: e.name, session_count: 0, last_date: null, _plans: new Set() };
                item._plans.add(p.id);
                if (!item.last_date || p.plan_date > item.last_date) item.last_date = p.plan_date;
                map.set(e.name, item);
            });
        });
        return Array.from(map.values())
            .map((i) => ({ name: i.name, session_count: i._plans.size, last_date: i.last_date }))
            .sort((a, b) => b.session_count - a.session_count || (a.last_date < b.last_date ? 1 : -1));
    });

    route("GET", "/api/progress/exercise", (q) => {
        const name = String(q.name || "").trim();
        if (!name) throw new HttpError(422, "请提供动作名称");
        const points = new Map();
        let found = false;

        db.plans
            .filter((p) => p.status === "done")
            .forEach((p) => {
                p.exercises
                    .filter((e) => e.name === name && !e.skipped)
                    .forEach((e) => {
                        found = true;
                        const doneLogs = e.logs.filter((s) => s.done);
                        // 没有逐组记录时用计划值兜底，保证老数据也能出曲线
                        const pairs = doneLogs.length
                            ? doneLogs.map((s) => [s.reps || 0, s.weight || 0])
                            : Array.from({ length: e.sets }, () => [e.reps, e.weight]);

                        const volume = pairs.reduce((sum, [rep, wt]) => sum + rep * wt, 0);
                        const maxWeight = pairs.reduce((mx, [, wt]) => Math.max(mx, wt), 0);
                        const est1rm = pairs.reduce((mx, [rep, wt]) => (wt > 0 ? Math.max(mx, wt * (1 + rep / 30)) : mx), 0);
                        const rpes = doneLogs.map((s) => s.rpe).filter((v) => v !== null && v !== undefined);

                        const point = points.get(p.plan_date) || {
                            date: p.plan_date,
                            max_weight: 0,
                            volume: 0,
                            sets: 0,
                            est_1rm: 0,
                            _rpe: [],
                        };
                        point.max_weight = Math.max(point.max_weight, maxWeight);
                        point.volume = r2(point.volume + volume);
                        point.sets += pairs.length;
                        point.est_1rm = Math.round(Math.max(point.est_1rm, est1rm) * 10) / 10;
                        point._rpe.push(...rpes);
                        points.set(p.plan_date, point);
                    });
            });

        if (!found) throw new HttpError(404, "还没有这个动作的历史记录");

        const list = Array.from(points.values())
            .sort((a, b) => (a.date < b.date ? -1 : 1))
            .map((pt) => {
                const rpes = pt._rpe;
                const { _rpe, ...rest } = pt;
                return { ...rest, avg_rpe: rpes.length ? Math.round((rpes.reduce((a, b) => a + b, 0) / rpes.length) * 10) / 10 : null };
            });

        const allRpe = list.map((p) => p.avg_rpe).filter((v) => v !== null);
        const prWeight = list.reduce((mx, p) => Math.max(mx, p.max_weight), 0);
        const prDate = list.find((p) => p.max_weight === prWeight);
        return {
            name,
            points: list,
            pr_weight: prWeight,
            pr_date: prDate ? prDate.date : null,
            best_volume: list.reduce((mx, p) => Math.max(mx, p.volume), 0),
            total_sets: list.reduce((s, p) => s + p.sets, 0),
            avg_rpe: allRpe.length ? Math.round((allRpe.reduce((a, b) => a + b, 0) / allRpe.length) * 10) / 10 : null,
        };
    });

    /* ---- 周视图 ---- */
    route("GET", "/api/weekly", (q) => {
        const n = Math.max(1, Math.min(Number(q.weeks) || 8, 52));
        const thisWeek = weekStart(todayISO());
        const firstWeek = addDays(thisWeek, -7 * (n - 1));
        const lastDay = addDays(thisWeek, 6);

        const weeks = [];
        for (let i = 0; i < n; i += 1) {
            weeks.push({ week_start: addDays(firstWeek, 7 * i), sessions: 0, volume: 0, sets: 0, body_weight: null });
        }
        const byStart = new Map(weeks.map((w) => [w.week_start, w]));

        db.plans
            .filter((p) => p.status === "done" && p.plan_date >= firstWeek && p.plan_date <= lastDay)
            .forEach((p) => {
                const bucket = byStart.get(weekStart(p.plan_date));
                if (!bucket) return;
                const out = planOut(p);
                bucket.sessions += 1;
                bucket.volume = r2(bucket.volume + (out.actual_volume || out.total_volume));
                bucket.sets += out.done_set_count || out.total_sets;
            });

        db.bodies
            .filter((b) => b.date >= firstWeek && b.date <= lastDay)
            .sort((a, b) => (a.date === b.date ? a.id - b.id : a.date < b.date ? -1 : 1))
            .forEach((b) => {
                const bucket = byStart.get(weekStart(b.date));
                if (bucket && b.weight) bucket.body_weight = Number(b.weight);
            });

        const active = weeks.filter((w) => w.sessions > 0);
        return {
            weeks,
            avg_volume: active.length ? r2(active.reduce((s, w) => s + w.volume, 0) / active.length) : 0,
            avg_sessions: active.length ? r2(active.reduce((s, w) => s + w.sessions, 0) / active.length) : 0,
            week_count: active.length,
        };
    });

    /* ---- 体重 ---- */
    route("GET", "/api/bodies", () => {
        return db.bodies
            .slice()
            .sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1))
            .slice(0, 200)
            .map((b) => ({ ...b }));
    });

    route("POST", "/api/bodies", (q, p, body) => {
        const weight = Number(body.weight);
        if (!Number.isFinite(weight) || weight < 20 || weight > 500) throw new HttpError(422, "体重需在 20–500 kg 之间");
        let bodyFat = null;
        if (body.body_fat !== undefined && body.body_fat !== null && body.body_fat !== "") {
            bodyFat = Number(body.body_fat);
            if (!Number.isFinite(bodyFat) || bodyFat < 2 || bodyFat > 70) throw new HttpError(422, "体脂率需在 2–70 之间");
        }
        const record = {
            id: nextId("body"),
            date: body.date || todayISO(),
            weight,
            body_fat: bodyFat,
            note: String(body.note || "").trim(),
            created_at: nowLocal(),
        };
        db.bodies.push(record);
        save();
        return { ...record };
    });

    route("DELETE", "/api/bodies/:id", (q, p) => {
        const before = db.bodies.length;
        db.bodies = db.bodies.filter((b) => b.id !== Number(p.id));
        if (db.bodies.length === before) throw new HttpError(404, "记录不存在");
        save();
        return null;
    });

    /* ---------------- 对外入口 ---------------- */
    function parseUrl(url) {
        const raw = String(url);
        const idx = raw.indexOf("?");
        const path = idx >= 0 ? raw.slice(0, idx) : raw;
        return { path, query: new URLSearchParams(idx >= 0 ? raw.slice(idx + 1) : "") };
    }

    function queryObject(searchParams) {
        const obj = {};
        searchParams.forEach((v, k) => (obj[k] = v));
        return obj;
    }

    /** 与后端 api() 等价的调用入口：返回 Promise，失败抛 Error(detail)。 */
    async function call(url, options = {}) {
        const method = (options.method || "GET").toUpperCase();
        const { path, query } = parseUrl(url);
        let body = {};
        if (options.body) {
            try {
                body = typeof options.body === "string" ? JSON.parse(options.body) : options.body;
            } catch (err) {
                console.warn("请求体不是合法 JSON：", err);
                body = {};
            }
        }
        // 处理器可能是异步的（口令派生要等 WebCrypto），统一 await
        return await dispatch(method, path, queryObject(query), body);
    }

    /* ---------------- 备份 / 导入 / 清空 ---------------- */
    function exportBlob() {
        requireSession();
        db.meta.last_export_at = nowLocal();
        save();
        const payload = {
            app: "健身记录·静态版",
            version: db.version || 1,
            account: session.username,
            exported_at: nowLocal(),
            data: db,
        };
        return new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    }

    function importJSON(text) {
        requireSession();
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (err) {
            throw new Error("备份文件不是合法 JSON");
        }
        const data = parsed && parsed.data && parsed.data.plans ? parsed.data : parsed;
        if (!data || !Array.isArray(data.plans)) throw new Error("备份文件里没有找到训练数据");
        db = normalize(data);
        // 数据可能来自别的账号，序号要重新对齐，避免 id 冲突
        db.seq = db.seq || { plan: 1, ex: 1, body: 1 };
        const maxOf = (start, items) => items.reduce((mx, v) => (v > mx ? v : mx), start);
        db.seq.plan = maxOf(db.seq.plan || 1, db.plans.map((p) => p.id + 1));
        db.seq.ex = maxOf(db.seq.ex || 1, db.plans.flatMap((p) => p.exercises.map((e) => e.id + 1)));
        db.seq.body = maxOf(db.seq.body || 1, db.bodies.map((b) => b.id + 1));
        save();
        return db.plans.length;
    }

    function clearAll() {
        requireSession();
        db = emptyDB();
        save();
    }

    function stats() {
        const raw = dataKey ? localStorage.getItem(dataKey) || "" : "";
        return {
            user: session ? session.username : "",
            plans: db.plans.length,
            done: db.plans.filter((p) => p.status === "done").length,
            bodies: db.bodies.length,
            bytes: raw.length,
        };
    }

    function accountsInfo() {
        return accounts.map((a) => ({ id: a.id, username: a.username, created_at: a.created_at }));
    }

    window.FitnessStore = { call, exportBlob, importJSON, clearAll, stats, accountsInfo, BODY_PARTS };
})();
