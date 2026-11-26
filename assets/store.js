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

    const KEY = "fitness_local_v1";
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
        return { version: 1, seq: { plan: 1, ex: 1, body: 1 }, plans: [], bodies: [] };
    }

    function normalize(parsed) {
        if (!parsed || !Array.isArray(parsed.plans)) return emptyDB();
        parsed.seq = parsed.seq || { plan: 1, ex: 1, body: 1 };
        parsed.bodies = parsed.bodies || [];
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

    let db = load();

    function load() {
        try {
            const raw = localStorage.getItem(KEY);
            return raw ? normalize(JSON.parse(raw)) : emptyDB();
        } catch (err) {
            console.warn("本地数据读取失败，按空库启动：", err);
            return emptyDB();
        }
    }

    function save() {
        try {
            localStorage.setItem(KEY, JSON.stringify(db));
        } catch (err) {
            console.error("本地数据写入失败：", err);
            throw new HttpError(507, "浏览器本地存储已满，请先在「备份」里导出，再清理旧数据");
        }
    }

    function nextId(kind) {
        const id = db.seq[kind] || 1;
        db.seq[kind] = id + 1;
        return id;
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

    /* ---- 元信息 / 账号（静态版没有真账号，固定返回本机用户） ---- */
    route("GET", "/api/body-parts", () => ({ body_parts: BODY_PARTS.slice() }));
    route("GET", "/api/auth/me", () => ({ id: 1, username: "本机" }));
    route("POST", "/api/auth/logout", () => null);

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
        save();
        return null;
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
        };
    });

    /* ---- 动作进步 ---- */
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
        // 让调用方仍能 await，内部其实是同步计算
        return dispatch(method, path, queryObject(query), body);
    }

    /* ---------------- 备份 / 导入 / 清空 ---------------- */
    function exportBlob() {
        const payload = {
            app: "健身记录·静态版",
            version: db.version || 1,
            exported_at: nowLocal(),
            data: db,
        };
        return new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    }

    function importJSON(text) {
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (err) {
            throw new Error("备份文件不是合法 JSON");
        }
        const data = parsed && parsed.data && parsed.data.plans ? parsed.data : parsed;
        if (!data || !Array.isArray(data.plans)) throw new Error("备份文件里没有找到训练数据");
        db = normalize(data);
        save();
        return db.plans.length;
    }

    function clearAll() {
        db = emptyDB();
        save();
    }

    function stats() {
        return {
            plans: db.plans.length,
            done: db.plans.filter((p) => p.status === "done").length,
            bodies: db.bodies.length,
            bytes: (localStorage.getItem(KEY) || "").length,
        };
    }

    window.FitnessStore = { call, exportBlob, importJSON, clearAll, stats, BODY_PARTS };
})();
