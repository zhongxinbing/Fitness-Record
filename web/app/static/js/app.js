/* 健身计划 · 前端交互（原生 JS，无框架依赖）
   页面结构：今日计划（含右下角 + 新建计划）/ 历史（按天记录训练部位）
*/
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* ---------------- 通用 ---------------- */
async function api(url, options = {}) {
    const resp = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
    if (resp.status === 204) return null;
    const data = await resp.json().catch(() => ({}));
    if (resp.status === 401 && !options.ignoreAuth) {
        // 会话失效：回到登录页，避免页面停在半截数据上
        requireLogin();
        throw new Error(data.detail || "请先登录");
    }
    if (!resp.ok) {
        const detail = Array.isArray(data.detail)
            ? data.detail.map((d) => `${(d.loc || []).slice(1).join(".")} ${d.msg}`).join("；")
            : data.detail || "请求失败";
        throw new Error(detail);
    }
    return data;
}

function todayISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseISO(iso) {
    return new Date(`${iso}T00:00:00`);
}

const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function fmtDay(iso) {
    const d = parseISO(iso);
    return `${d.getMonth() + 1}月${d.getDate()}日`;
}

function weekdayOf(iso) {
    return WEEK[parseISO(iso).getDay()];
}

function shortDate(iso) {
    const d = parseISO(iso);
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function num(n) {
    return Number(n).toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}

function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

const TODAY = todayISO();

/* ---------------- 顶部 + 标签 ---------------- */
$("#header-sub").textContent = `${parseISO(TODAY).getFullYear()}年${fmtDay(TODAY)} ${weekdayOf(TODAY)}`;

$$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        $$(".tab-btn").forEach((b) => b.classList.remove("active"));
        $$(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $(`#tab-${btn.dataset.tab}`).classList.add("active");
        // 悬浮 + 只在今日计划页出现
        $("#fab-add").classList.toggle("hidden", btn.dataset.tab !== "plan");
        $("#fab-add").classList.toggle("with-bar", btn.dataset.tab === "plan" && !$("#timer-bar").hidden);
        if (btn.dataset.tab === "history") loadHistory();
    });
});

/* ---------------- 部位 chips ---------------- */
let BODY_PARTS = [];
let selectedParts = new Set();

async function loadBodyParts() {
    const res = await api("/api/body-parts");
    BODY_PARTS = res.body_parts;
    $("#part-chips").innerHTML = BODY_PARTS.map(
        (p) => `<button type="button" class="chip-btn" data-part="${p}">${p}</button>`
    ).join("");
    $("#part-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip-btn");
        if (!chip) return;
        const part = chip.dataset.part;
        if (selectedParts.has(part)) {
            selectedParts.delete(part);
            chip.classList.remove("active");
        } else {
            if (selectedParts.size >= 5) {
                setMsg("最多选择 5 个部位", true);
                return;
            }
            selectedParts.add(part);
            chip.classList.add("active");
        }
        $("#part-hint").textContent = selectedParts.size
            ? `已选：${[...selectedParts].join("、")}`
            : "已选 0 个";
    });
}

/* ---------------- 动作行（弹层内） ---------------- */
const rowsBox = $("#exercise-rows");
const rowTpl = $("#exercise-row-tpl");

function addRow(focus = false) {
    const node = rowTpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".er-del").addEventListener("click", () => {
        if (rowsBox.children.length <= 1) {
            node.querySelectorAll("input").forEach((i) => (i.value = ""));
            return;
        }
        node.remove();
        renumber();
    });
    rowsBox.appendChild(node);
    renumber();
    if (focus) node.querySelector(".ex-name").focus();
    return node;
}

function renumber() {
    [...rowsBox.children].forEach((row, i) => {
        row.querySelector(".er-index").textContent = `动作 ${i + 1}`;
    });
    $("#ex-counter").textContent = `${rowsBox.children.length} 个`;
}

function collectExercises() {
    const result = [];
    let error = "";
    [...rowsBox.children].forEach((row, i) => {
        const name = row.querySelector(".ex-name").value.trim();
        const sets = row.querySelector(".ex-sets").value;
        const reps = row.querySelector(".ex-reps").value;
        const weight = row.querySelector(".ex-weight").value;
        const restField = row.querySelector(".ex-rest");
        const rest = restField && restField.value !== "" ? Number(restField.value) : 90;
        if (!name && !sets && !reps && !weight) return; // 整行空白跳过
        if (!name) error = error || `动作 ${i + 1} 缺少名称`;
        else if (!sets || Number(sets) < 1) error = error || `动作 ${i + 1} 缺少组数`;
        else if (!reps || Number(reps) < 1) error = error || `动作 ${i + 1} 缺少次数`;
        else {
            result.push({
                name,
                sets: Number(sets),
                reps: Number(reps),
                weight: weight === "" ? 0 : Number(weight),
                rest_seconds: Math.min(600, Math.max(1, rest || 90)),
            });
        }
    });
    if (error) throw new Error(error);
    if (!result.length) throw new Error("请至少添加一个动作");
    if (new Set(result.map((r) => r.name)).size !== result.length) throw new Error("动作名称不能重复");
    return result;
}

$("#add-ex-btn").addEventListener("click", () => addRow(true));

/* ---------------- 弹层 ---------------- */
const mask = $("#sheet-mask");

function openSheet() {
    $("#p-date").value = TODAY;
    $("#p-title").value = "";
    $("#p-note").value = "";
    setMsg("");
    selectedParts.clear();
    $$("#part-chips .chip-btn").forEach((c) => c.classList.remove("active"));
    $("#part-hint").textContent = "已选 0 个";
    rowsBox.innerHTML = "";
    addRow();
    mask.hidden = false;
    document.body.style.overflow = "hidden";
}

function closeSheet() {
    mask.hidden = true;
    document.body.style.overflow = "";
}

$("#fab-add").addEventListener("click", openSheet);
$("#sheet-close").addEventListener("click", closeSheet);
mask.addEventListener("click", (e) => { if (e.target === mask) closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !mask.hidden) closeSheet(); });

function setMsg(text, isError = false) {
    const el = $("#p-msg");
    el.textContent = text;
    el.className = `form-msg ${isError ? "error" : "ok"}`;
}

/* ---------------- 保存计划 ---------------- */
$("#plan-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    let exercises;
    try {
        exercises = collectExercises();
    } catch (err) {
        setMsg(err.message, true);
        return;
    }
    if (selectedParts.size === 0) {
        setMsg("请至少选择一个训练部位", true);
        return;
    }
    const payload = {
        plan_date: $("#p-date").value || TODAY,
        body_parts: [...selectedParts],
        title: $("#p-title").value.trim(),
        note: $("#p-note").value.trim(),
        exercises,
    };
    try {
        await api("/api/plans", { method: "POST", body: JSON.stringify(payload) });
        closeSheet();
        await refreshAll();
    } catch (err) {
        setMsg(err.message, true);
    }
});

/* ---------------- 计划列表渲染 ---------------- */
function planCard(plan, mode) {
    const chips = plan.body_parts.map((p) => `<span class="part-chip">${escapeHtml(p)}</span>`).join("");
    const title = plan.title ? escapeHtml(plan.title) : `${escapeHtml(plan.body_parts.join("/"))}训练`;
    const volText = plan.total_volume > 0 ? ` · 容量 ${num(plan.total_volume)} kg` : "";

    const exRows = plan.exercises.map((e) => {
        const logs = (e.done_sets || []).map((x) => `${x.reps}×${x.weight > 0 ? x.weight + "kg" : "自重"}`);
        const logLine = logs.length
            ? `<div class="ex-log">已做 ${logs.length} 组：${logs.join(" / ")}</div>`
            : "";
        return `
        <div class="ex-item">
            <div class="ex-name-cell">
                <div class="ex-label">${escapeHtml(e.name)}</div>
                <div class="ex-detail">${e.sets} 组 × ${e.reps} 次 · ${e.weight > 0 ? e.weight + " kg" : "自重"}</div>
                ${logLine}
            </div>
            <button class="rest-chip" data-action="open-timer" data-pid="${plan.id}" data-eid="${e.id}"
                    data-rest="${e.rest_seconds}" data-name="${escapeHtml(e.name)}">⏱ ${fmtRest(e.rest_seconds)}</button>
            ${mode === "done" ? "" : `<button class="ex-edit" data-action="edit-ex" data-pid="${plan.id}" data-eid="${e.id}"
                    data-name="${escapeHtml(e.name)}" data-sets="${e.sets}" data-reps="${e.reps}"
                    data-weight="${e.weight}" data-rest="${e.rest_seconds}" title="修改该动作">✎</button>`}
            <div class="ex-vol ${e.volume > 0 ? "" : "muted"}">${e.volume > 0 ? num(e.volume) + " kg" : "—"}</div>
            ${mode === "done" ? "" : `<button class="ex-x" data-action="del-ex" data-pid="${plan.id}" data-eid="${e.id}" title="删除该动作">✕</button>`}
        </div>`;
    }).join("");

    const foot = mode === "done"
        ? `<div class="pc-foot">
             <button class="btn-sm flex1 good" data-action="reopen" data-pid="${plan.id}">撤销打卡</button>
             <button class="btn-sm danger" data-action="del-plan" data-pid="${plan.id}">删除</button>
           </div>`
        : `<div class="pc-foot">
             <button class="btn-sm flex1 primary" data-action="start-train" data-pid="${plan.id}">开始训练</button>
             <button class="btn-sm flex1" data-action="complete" data-pid="${plan.id}">直接打卡</button>
             <button class="btn-sm" data-action="toggle-add" data-pid="${plan.id}">＋动作</button>
             <button class="btn-sm danger" data-action="del-plan" data-pid="${plan.id}">删</button>
           </div>
           <div class="quick-add" data-qa="${plan.id}">
             <div class="qa-grid">
               <div class="field span-2"><label>动作名称</label><input type="text" class="qa-name" maxlength="50" placeholder="如 绳索下压"></div>
               <div class="field"><label>组数</label><input type="number" class="qa-sets" min="1" max="99" placeholder="3"></div>
               <div class="field"><label>次数</label><input type="number" class="qa-reps" min="1" max="999" placeholder="12"></div>
               <div class="field"><label>重量 (kg)</label><input type="number" class="qa-weight" min="0" max="1000" step="0.5" placeholder="20"></div>
               <div class="field"><label>休息 (秒)</label><input type="number" class="qa-rest" min="1" max="600" step="5" placeholder="90" value="90"></div>
             </div>
             <div class="qa-actions">
               <button class="btn-sm primary flex1" data-action="save-add" data-pid="${plan.id}">保存动作</button>
               <button class="btn-sm" data-action="toggle-add" data-pid="${plan.id}">取消</button>
             </div>
           </div>`;

    return `
    <div class="plan-card ${mode === "done" ? "is-done" : ""}" data-pid="${plan.id}">
        <div class="pc-head">
            <div class="pc-head-actions">
                ${mode === "done" ? "" : `<button class="card-icon-btn" data-action="edit-plan" data-pid="${plan.id}" title="编辑计划">✎</button>`}
            </div>
            <div class="pc-chips">${chips}</div>
            <div class="pc-title">${title}</div>
            <div class="pc-meta">
                ${shortDate(plan.plan_date)} · ${plan.exercise_count} 个动作 · ${plan.total_sets} 组${volText}
            </div>
            ${plan.note ? `<div class="pc-note">${escapeHtml(plan.note)}</div>` : ""}
            <div class="set-progress ${plan.done_set_count > 0 ? "" : "idle"}">${plan.done_set_count > 0
                ? `已完成 ${plan.done_set_count}/${plan.total_set_count} 组 · 实际容量 ${num(plan.actual_volume)} kg`
                : `共 ${plan.total_set_count} 组待记录`}</div>
        </div>
        <div class="pc-ex">${exRows}</div>
        ${foot}
    </div>`;
}

async function loadPlanTab() {
    const [todayList, others] = await Promise.all([
        api(`/api/plans?plan_date=${TODAY}&status=planned`),
        api("/api/plans/others"),
    ]);

    $("#today-count").textContent = `${todayList.length} 个计划`;
    $("#today-plans").innerHTML = todayList.length
        ? todayList.map((p) => planCard(p, "plan")).join("")
        : `<div class="empty"><span class="empty-icon">📋</span>今天还没有训练计划<br>点右下角 <b>＋</b> 新建一个<br>
             <button type="button" class="empty-pick" data-action="pick-hist">从历史里选一个</button></div>`;

    $("#other-wrap").style.display = others.length ? "" : "none";
    $("#other-plans").innerHTML = others.map((p) => planCard(p, "plan")).join("");
}

/* ---------------- 从历史选择计划 ---------------- */
const histMask = $("#hist-mask");

function closeHistPicker() {
    histMask.hidden = true;
    document.body.style.overflow = "";
}

async function openHistPicker() {
    const list = $("#hist-pick-list");
    list.innerHTML = `<div class="hp-empty">加载中…</div>`;
    histMask.hidden = false;
    document.body.style.overflow = "hidden";
    try {
        const days = await api("/api/history");
        if (!days.length) {
            list.innerHTML = `<div class="hp-empty">还没有已完成的训练记录<br>先把一条计划「完成打卡」，之后就能一键复用</div>`;
            return;
        }
        // 只保留有动作明细的计划，避免复制出空计划
        const groups = days
            .map((d) => ({ ...d, plans: d.plans.filter((p) => p.exercise_count > 0) }))
            .filter((d) => d.plans.length);
        if (!groups.length) {
            list.innerHTML = `<div class="hp-empty">历史里的计划还没有动作明细<br>建计划时填上动作，才能一键复用</div>`;
            return;
        }
        list.innerHTML = groups.slice(0, 20).map((day) => `
            <div class="hp-day">
                <div class="hp-day-head">
                    <span class="hp-date">${fmtDay(day.date)}</span>
                    <span>${weekdayOf(day.date)}</span>
                    <span>· ${day.body_parts.map(escapeHtml).join("/")}</span>
                </div>
                ${day.plans.map((p) => `
                    <div class="hp-item">
                        <div class="hp-main">
                            <div class="hp-title">${escapeHtml(p.title || p.body_parts.join("+") + "训练")}</div>
                            <div class="hp-sub">${p.exercise_count} 个动作 · ${p.total_sets} 组 · ${p.exercises.slice(0, 3).map((e) => escapeHtml(e.name)).join(" / ")}${p.exercise_count > 3 ? " …" : ""}</div>
                        </div>
                        <button type="button" class="hp-btn" data-copy="${p.id}">加入今日</button>
                    </div>`).join("")}
            </div>`).join("");
    } catch (err) {
        list.innerHTML = `<div class="hp-empty">${escapeHtml(err.message)}</div>`;
    }
}

$("#hist-close").addEventListener("click", closeHistPicker);
histMask.addEventListener("click", (e) => { if (e.target === histMask) closeHistPicker(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !histMask.hidden) closeHistPicker(); });

// 入口：页头按钮 + 空状态按钮（后者由深层的点击委托处理）
document.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="pick-hist"]');
    if (btn) openHistPicker();
});

// 选择某条历史计划 → 复制到今天
$("#hist-pick-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = "复制中…";
    try {
        const plan = await api(`/api/plans/${btn.dataset.copy}/copy`, { method: "POST" });
        closeHistPicker();
        if ($("#timer-bar").hidden) $("#fab-add").classList.remove("with-bar");
        $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === "plan"));
        $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-plan"));
        $("#fab-add").classList.remove("hidden");
        await loadPlanTab();
        toast(`已加入今日：${plan.title || plan.body_parts.join("+")} · ${plan.exercise_count} 个动作`);
    } catch (err) {
        btn.disabled = false;
        btn.textContent = "加入今日";
        toast(err.message);
    }
});

/* ---------------- 历史渲染 ---------------- */
async function loadHistory() {
    const [days, stats] = await Promise.all([api("/api/history"), api("/api/stats")]);
    loadBodyPanel().catch(() => {});

    const partChips = Object.entries(stats.body_part_dist || {})
        .map(([p, n]) => `<span class="part-chip">${escapeHtml(p)} ${n}</span>`)
        .join("");

    $("#overview").innerHTML = `
        <div class="ov-row">
            <div class="ov-cell"><div class="ov-value">${stats.done_plans}</div><div class="ov-label">累计训练</div></div>
            <div class="ov-cell"><div class="ov-value">${stats.week_sessions}</div><div class="ov-label">本周</div></div>
            <div class="ov-cell"><div class="ov-value">${stats.total_sets}</div><div class="ov-label">累计组数</div></div>
            <div class="ov-cell"><div class="ov-value">${num(stats.total_volume)}</div><div class="ov-label">累计容量 kg</div></div>
        </div>
        ${partChips ? `<div class="ov-line"></div><div class="ov-parts">${partChips}</div>` : ""}`;

    $("#history-count").textContent = days.length ? `${days.length} 天有记录` : "";

    $("#history-list").innerHTML = days.length
        ? days.map(dayCard).join("")
        : `<div class="empty"><span class="empty-icon">🗓️</span>还没有训练历史<br>完成今日计划的打卡后会记录在这里</div>`;
}

function dayCard(day) {
    const parts = day.body_parts.map((p) => `<span class="part-chip">${escapeHtml(p)}</span>`).join("");
    const plans = day.plans.map((p) => `
        <div class="dc-plan">
            <div class="dc-plan-title">
                ${p.title ? escapeHtml(p.title) : p.body_parts.join(" + ")} · ${p.exercise_count} 个动作 · ${p.total_sets} 组
            </div>
            ${p.exercises.map((e) => `
                <div class="dc-ex">
                    <span>${escapeHtml(e.name)}</span>
                    <span>${e.sets}×${e.reps}${e.weight > 0 ? ` · ${e.weight}kg` : ""}</span>
                </div>`).join("")}
        </div>`).join("");

    return `
    <div class="day-card">
        <div class="dc-head">
            <div class="dc-date">${fmtDay(day.date)}<span class="dc-week">${weekdayOf(day.date)}</span></div>
            <div class="dc-meta">${day.plan_count} 次 · 容量 ${num(day.total_volume)} kg</div>
        </div>
        <div class="dc-parts">${parts}</div>
        <div class="dc-body">${plans}</div>
    </div>`;
}

/* ---------------- 卡片操作（事件委托） ---------------- */
document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const pid = btn.dataset.pid;
    const card = btn.closest(".plan-card");

    try {
        if (action === "complete") {
            await api(`/api/plans/${pid}/complete`, { method: "POST" });
            await refreshAll();
        } else if (action === "reopen") {
            if (!confirm("撤销这次打卡，放回今日计划？")) return;
            await api(`/api/plans/${pid}/reopen`, { method: "POST" });
            await refreshAll();
        } else if (action === "del-plan") {
            if (!confirm("删除这个计划？")) return;
            await api(`/api/plans/${pid}`, { method: "DELETE" });
            await refreshAll();
        } else if (action === "del-ex") {
            if (!confirm("删除这个动作？")) return;
            await api(`/api/plans/${pid}/exercises/${btn.dataset.eid}`, { method: "DELETE" });
            await refreshAll();
        } else if (action === "open-timer") {
            openTimer(pid, btn.dataset.eid, btn.dataset.name, btn.dataset.rest);
        } else if (action === "edit-ex") {
            openExEditor(btn);
        } else if (action === "start-train") {
            await openTraining(pid);
        } else if (action === "toggle-set") {
            await toggleTrainingSet(btn);
        } else if (action === "edit-plan") {
            await openPlanEditor(pid);
        } else if (action === "open-progress") {
            openProgSheet();
        } else if (action === "prog-open") {
            await showProgDetail(btn.dataset.name);
        } else if (action === "prog-back") {
            await loadProgList();
        } else if (action === "add-body") {
            $("#b-date").value = TODAY;
            $("#b-msg").className = "form-msg";
            $("#b-msg").textContent = "";
            bodyMask.hidden = false;
            document.body.style.overflow = "hidden";
            setTimeout(() => $("#b-weight").focus(), 100);
        } else if (action === "del-body") {
            if (!confirm("删除这条体重记录？")) return;
            await api(`/api/bodies/${btn.dataset.id}`, { method: "DELETE" });
            await loadBodyPanel();
        } else if (action === "toggle-add") {
            const qa = card.querySelector(".quick-add");
            qa.classList.toggle("open");
            if (qa.classList.contains("open")) qa.querySelector(".qa-name").focus();
        } else if (action === "save-add") {
            const qa = card.querySelector(".quick-add");
            const name = qa.querySelector(".qa-name").value.trim();
            const sets = Number(qa.querySelector(".qa-sets").value);
            const reps = Number(qa.querySelector(".qa-reps").value);
            const wv = qa.querySelector(".qa-weight").value;
            const rv = qa.querySelector(".qa-rest").value;
            if (!name) return alert("请填写动作名称");
            if (!sets || sets < 1) return alert("请填写组数");
            if (!reps || reps < 1) return alert("请填写次数");
            await api(`/api/plans/${pid}/exercises`, {
                method: "POST",
                body: JSON.stringify({
                    name, sets, reps,
                    weight: wv === "" ? 0 : Number(wv),
                    rest_seconds: rv === "" ? 90 : Number(rv),
                }),
            });
            await refreshAll();
        }
    } catch (err) {
        alert(err.message);
    }
});


/* ================= 每组休息计时 ================= */
const RING_R = 86;
const RING_C = 2 * Math.PI * RING_R;

const timer = {
    pid: null,
    eid: null,
    name: "",
    total: 90,      // 本次设定时长（秒）
    remaining: 90,  // 剩余秒数
    running: false,
    deadline: 0,    // 运行时的结束时间戳
    handle: null,
    finished: false,
};

const timerMask = $("#timer-mask");

function fmtRest(sec) {
    const s = Number(sec) || 0;
    if (s < 60) return `${s}秒`;
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r === 0 ? `${m}分` : `${m}分${r}秒`;
}

function fmtClock(sec) {
    const total = Math.max(0, Math.ceil(sec));
    const m = String(Math.floor(total / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
}

function renderTimer() {
    const timeEl = $("#timer-time");
    timeEl.textContent = fmtClock(timer.remaining);

    const subEl = $("#timer-sub");
    if (timer.finished) subEl.textContent = "休息结束，开始下一组";
    else if (timer.running) subEl.textContent = `休息中 · ${timer.name || "本组"}`;
    else if (timer.remaining !== timer.total) subEl.textContent = `暂停 · 还剩 ${Math.ceil(timer.remaining)} 秒`;
    else subEl.textContent = `每组休息 ${timer.total} 秒`;

    const ratio = timer.total > 0 ? Math.max(0, Math.min(1, timer.remaining / timer.total)) : 0;
    const ring = $("#ring-progress");
    ring.style.strokeDasharray = String(RING_C);
    ring.style.strokeDashoffset = String(RING_C * (1 - ratio));
    ring.classList.toggle("finished", timer.finished);
    ring.classList.toggle("paused", !timer.running && !timer.finished);

    $$("#timer-presets button").forEach((b) => {
        b.classList.toggle("active", Number(b.dataset.sec) === timer.total);
    });

    const startBtn = $("#timer-start");
    startBtn.textContent = timer.running ? "暂停" : timer.finished ? "重新开始" : timer.remaining < timer.total ? "继续" : "开始休息";

    // 悬浮条：运行中、或已开始但被暂停时显示；结束后收起，交给提示与面板
    const bar = $("#timer-bar");
    const pausedMidway = !timer.running && !timer.finished && timer.remaining > 0 && timer.remaining < timer.total;
    bar.hidden = !(timer.running || pausedMidway);
    const showBar = !bar.hidden;
    $("#tb-time").textContent = fmtClock(timer.remaining);
    $("#tb-name").textContent = timer.name || "休息中";
    $("#tb-toggle").textContent = timer.running ? "暂停" : "继续";
    $(".tb-dot").classList.toggle("paused", !timer.running);
    $("#fab-add").classList.toggle("with-bar", showBar && $("#tab-plan").classList.contains("active"));
}

function ringTick() {
    if (!timer.running) return;
    timer.remaining = Math.max(0, (timer.deadline - Date.now()) / 1000);
    if (timer.remaining <= 0.05) {
        timer.remaining = 0;
        finishTimer();
        return;
    }
    renderTimer();
}

function startTimer() {
    if (timer.remaining <= 0) timer.remaining = timer.total;
    timer.running = true;
    timer.finished = false;
    timer.deadline = Date.now() + timer.remaining * 1000;
    clearInterval(timer.handle);
    timer.handle = setInterval(ringTick, 100);
    unlockAudio();
    renderTimer();
}

function pauseTimer() {
    if (!timer.running) return;
    timer.remaining = Math.max(0, (timer.deadline - Date.now()) / 1000);
    timer.running = false;
    clearInterval(timer.handle);
    renderTimer();
}

function stopTimer(silent = true) {
    timer.running = false;
    timer.finished = false;
    clearInterval(timer.handle);
    timer.remaining = timer.total;
    renderTimer();
    if (silent) toast("");
}

function finishTimer() {
    timer.running = false;
    timer.finished = true;
    clearInterval(timer.handle);
    renderTimer();
    playAlarm();
    toast("休息结束，开始下一组 💪");
}

function shiftTimer(delta) {
    if (timer.running) {
        timer.deadline += delta * 1000;
        timer.remaining = Math.max(0, (timer.deadline - Date.now()) / 1000);
        timer.total = Math.max(timer.total, timer.remaining);
    } else {
        timer.remaining = Math.max(1, timer.remaining + delta);
        timer.total = Math.max(timer.total, timer.remaining);
        timer.finished = false;
    }
    renderTimer();
}

function setPreset(sec) {
    timer.total = sec;
    timer.remaining = sec;
    timer.finished = false;
    if (timer.running) {
        timer.deadline = Date.now() + sec * 1000;
    }
    renderTimer();
    // 记住为该动作的每组休息时长
    if (timer.pid && timer.eid) {
        api(`/api/plans/${timer.pid}/exercises/${timer.eid}`, {
            method: "PATCH",
            body: JSON.stringify({ rest_seconds: sec }),
        }).then(() => {
            $$(`.rest-chip[data-eid="${timer.eid}"]`).forEach((chip) => {
                chip.dataset.rest = String(sec);
                chip.textContent = `⏱ ${fmtRest(sec)}`;
            });
        }).catch(() => {});
    }
}

function openTimer(pid, eid, name, restSeconds) {
    const sameRunning = timer.running && String(timer.eid) === String(eid);
    if (!sameRunning) {
        clearInterval(timer.handle);
        timer.running = false;
        timer.finished = false;
        timer.pid = pid;
        timer.eid = eid;
        timer.name = name;
        timer.total = Number(restSeconds) || 90;
        timer.remaining = timer.total;
    }
    $("#timer-title").textContent = name ? `${name} · 组间休息` : "组间休息";
    closeSheet();
    timerMask.hidden = false;
    document.body.style.overflow = "hidden";
    renderTimer();
}

function closeTimer() {
    timerMask.hidden = true;
    document.body.style.overflow = "";
}

/* ---- 声音与震动 ---- */
let audioCtx = null;

function unlockAudio() {
    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === "suspended") audioCtx.resume();
    } catch (e) { /* 不支持音频时静默降级 */ }
}

function playAlarm() {
    unlockAudio();
    try {
        if (audioCtx) {
            for (let i = 0; i < 3; i++) {
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                const t0 = audioCtx.currentTime + i * 0.3;
                osc.type = "sine";
                osc.frequency.value = i === 2 ? 1180 : 880;
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.exponentialRampToValueAtTime(0.4, t0 + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.26);
                osc.connect(gain).connect(audioCtx.destination);
                osc.start(t0);
                osc.stop(t0 + 0.28);
            }
        }
    } catch (e) { /* 忽略 */ }
    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
}

/* ---- 轻提示 ---- */
let toastHandle = null;
function toast(text, ms = 2200) {
    const el = $("#toast");
    if (!text) { el.hidden = true; clearTimeout(toastHandle); return; }
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastHandle);
    toastHandle = setTimeout(() => (el.hidden = true), ms);
}

/* ---- 计时器控件绑定 ---- */
$("#timer-close").addEventListener("click", closeTimer);
timerMask.addEventListener("click", (e) => { if (e.target === timerMask) closeTimer(); });
$("#timer-start").addEventListener("click", () => {
    if (timer.running) pauseTimer();
    else startTimer();
});
$("#timer-add15").addEventListener("click", () => shiftTimer(15));
$("#timer-sub15").addEventListener("click", () => shiftTimer(-15));
$("#timer-stop").addEventListener("click", () => { stopTimer(); closeTimer(); });
$("#tb-toggle").addEventListener("click", () => (timer.running ? pauseTimer() : startTimer()));
$("#tb-stop").addEventListener("click", () => stopTimer());
$("#tb-open").addEventListener("click", () => {
    timerMask.hidden = false;
    document.body.style.overflow = "hidden";
    renderTimer();
});
$("#timer-presets").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-sec]");
    if (btn) setPreset(Number(btn.dataset.sec));
});
window.addEventListener("keydown", (e) => { if (e.key === "Escape" && !timerMask.hidden) closeTimer(); });

/* ---------------- 刷新 ---------------- */
async function refreshAll() {
    await Promise.all([loadPlanTab(), loadHistory()]);
}

/* ================= 折线图（纯 SVG，无第三方库） ================= */
function lineChart(points, opts = {}) {
    const unit = opts.unit || "";
    const dec = opts.decimals === undefined ? 0 : opts.decimals;
    if (!points || !points.length) return `<div class="chart-empty">暂无数据</div>`;

    const W = 336, H = 176, L = 44, R = 30, T = 16, B = 36;
    const vals = points.map((p) => p.value);
    let min = Math.min(...vals), max = Math.max(...vals);
    if (max === min) { max = min + (min === 0 ? 1 : Math.abs(min) * 0.2); min = min - (min === 0 ? 1 : Math.abs(min) * 0.2); }
    const padY = Math.max((max - min) * 0.18, 0.4);
    const lo = min - padY, hi = max + padY;
    const span = hi - lo || 1;
    const px = (i) => (points.length === 1 ? (L + (W - R)) / 2 : L + (W - L - R) * i / (points.length - 1));
    const py = (v) => T + (H - T - B) * (1 - (v - lo) / span);
    const fx = (v) => Number(v).toFixed(dec);

    // 网格与刻度
    let grid = "";
    for (let g = 0; g <= 2; g++) {
        const val = lo + (span * g) / 2;
        const yy = py(val);
        grid += `<line x1="${L}" y1="${yy.toFixed(1)}" x2="${W - R}" y2="${yy.toFixed(1)}" stroke="#e6ebf2" stroke-width="1"/>`;
        grid += `<text x="${L - 6}" y="${(yy + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="#9aa3b2">${fx(val)}</text>`;
    }

    const pts = points.map((p, i) => [px(i), py(p.value)]);
    const path = pts.map((c, i) => `${i ? "L" : "M"}${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" ");
    const area = `${path} L${pts[pts.length - 1][0].toFixed(1)},${H - B} L${pts[0][0].toFixed(1)},${H - B} Z`;

    const dots = pts.map((c, i) => {
        const last = i === pts.length - 1;
        const anchor = c[0] > W - 56 ? "end" : "middle";
        const label = last ? `<text x="${c[0].toFixed(1)}" y="${(c[1] - 10).toFixed(1)}" text-anchor="${anchor}" font-size="11" font-weight="700" fill="#2563eb">${fx(points[i].value)}${unit}</text>` : "";
        return `<circle cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="${last ? 4 : 3}" fill="${last ? "#2563eb" : "#93c5fd"}" stroke="#fff" stroke-width="1.2"/>${label}`;
    }).join("");

    // X 轴标签：最多 4 个
    const showIdx = points.length <= 4
        ? points.map((_, i) => i)
        : [0, Math.floor((points.length - 1) / 3), Math.floor((2 * (points.length - 1)) / 3), points.length - 1];
    const seenLabels = new Set();
    const xLabelIdx = showIdx.filter((i) => {
        if (seenLabels.has(points[i].label)) return false;
        seenLabels.add(points[i].label);
        return true;
    });
    const xLabels = xLabelIdx.map((i) => `<text x="${pts[i][0].toFixed(1)}" y="${H - B + 16}" text-anchor="middle" font-size="10" fill="#8b95a5">${escapeHtml(points[i].label)}</text>`).join("");

    return `<div class="chart-wrap">
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHtml(opts.title || "趋势图")}">
      ${grid}
      <path d="${area}" fill="rgba(37,99,235,0.08)"/>
      <path d="${path}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
      ${dots}
      ${xLabels}
    </svg>
  </div>`;
}

/* ================= 训练专注模式 ================= */
const trainMask = $("#train-mask");
let trainPlan = null;
let trainTick = null;

function trainDoneCount(plan) {
    return plan.exercises.reduce((n, e) => n + (e.done_sets || []).length, 0);
}
function trainSetCount(plan) {
    return plan.exercises.reduce((n, e) => n + Number(e.sets), 0);
}

async function openTraining(pid) {
    try {
        const plan = await api(`/api/plans/${pid}`);
        trainPlan = plan;
        $("#train-title").textContent = plan.title || `${plan.body_parts.join("/")}训练`;
        trainMask.hidden = false;
        document.body.style.overflow = "hidden";
        renderTraining();
        clearInterval(trainTick);
        trainTick = setInterval(syncRestBanner, 300);
        const active = $("#train-body .te-card.is-active");
        if (active) setTimeout(() => active.scrollIntoView({ block: "start", behavior: "smooth" }), 60);
    } catch (err) {
        toast(err.message);
    }
}

function renderTraining() {
    if (!trainPlan) return;
    const plan = trainPlan;
    $("#train-progress").textContent = `${trainDoneCount(plan)} / ${trainSetCount(plan)} 组`;

    if (!plan.exercises.length) {
        $("#train-body").innerHTML = `<div class="empty"><span class="empty-icon">💪</span>这个计划还没有动作<br>先回到计划页添加动作</div>`;
        return;
    }

    const firstUndone = plan.exercises.findIndex((e) => (e.done_sets || []).length < e.sets);

    $("#train-body").innerHTML = plan.exercises.map((e, idx) => {
        const done = (e.done_sets || []).slice().sort((a, b) => a.set_index - b.set_index);
        const byIdx = {};
        done.forEach((s) => { byIdx[s.set_index] = s; });
        const rows = Array.from({ length: e.sets }, (_, i) => {
            const n = i + 1;
            const logged = byIdx[n];
            const w = logged ? logged.weight : e.weight;
            const r = logged ? logged.reps : e.reps;
            return `<div class="ts-row ${logged ? "done" : ""}">
          <span class="ts-idx">${n}</span>
          <input class="ts-in ts-w" type="number" inputmode="decimal" step="0.5" min="0" max="1000" value="${w}" data-set="${n}" aria-label="第 ${n} 组重量（kg）">
          <span class="ts-x">kg ×</span>
          <input class="ts-in ts-r" type="number" inputmode="numeric" step="1" min="1" max="999" value="${r}" data-set="${n}" aria-label="第 ${n} 组次数">
          <span class="ts-x">次</span>
          <button class="ts-check ${logged ? "on" : ""}" data-action="toggle-set" data-pid="${plan.id}" data-eid="${e.id}" data-set="${n}" aria-label="${logged ? "取消" : "完成"}第 ${n} 组">✓</button>
        </div>`;
        }).join("");

        const cls = idx === firstUndone ? "is-active" : (done.length >= e.sets ? "is-done" : "");
        return `<div class="te-card ${cls}">
      <div class="te-head">
        <span class="te-name">${escapeHtml(e.name)}</span>
        <span class="te-count">${done.length}/${e.sets} 组</span>
      </div>
      <div class="te-sub">计划 ${e.reps} 次 × ${e.weight > 0 ? e.weight + " kg" : "自重"} · 休息 ${fmtRest(e.rest_seconds)}</div>
      ${rows}
    </div>`;
    }).join("");

    syncRestBanner();
}

async function toggleTrainingSet(btn) {
    const pid = Number(btn.dataset.pid);
    const eid = Number(btn.dataset.eid);
    const n = Number(btn.dataset.set);
    if (!trainPlan) return;
    const ex = trainPlan.exercises.find((x) => x.id === eid);
    if (!ex) return;
    ex.done_sets = ex.done_sets || [];
    const logged = ex.done_sets.some((x) => x.set_index === n);
    const card = btn.closest(".te-card");
    let payload;

    if (logged) {
        payload = { done: false };
    } else {
        const wIn = card.querySelector(`.ts-w[data-set="${n}"]`);
        const rIn = card.querySelector(`.ts-r[data-set="${n}"]`);
        const weight = wIn.value === "" ? 0 : Number(wIn.value);
        const reps = Number(rIn.value);
        if (!reps || reps < 1 || reps > 999) return toast("次数需在 1–999 之间");
        if (weight < 0 || weight > 1000) return toast("重量需在 0–1000 kg 之间");
        payload = { done: true, reps, weight };
    }

    btn.disabled = true;
    try {
        const res = await api(`/api/plans/${pid}/exercises/${eid}/sets/${n}`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        ex.done_sets = ex.done_sets.filter((x) => x.set_index !== n);
        if (res && res.reps !== null && res.reps !== undefined) {
            ex.done_sets.push({ set_index: n, reps: res.reps, weight: res.weight });
        }
        renderTraining();
        if (payload.done) {
            if (ex.rest_seconds) beginRest(pid, eid, ex.name, ex.rest_seconds);
            if (ex.done_sets.length >= ex.sets) toast(`「${ex.name}」${ex.sets} 组全部完成 🎉`);
            else toast(`第 ${n} 组已记录 · ${payload.weight ? payload.weight + "kg × " : ""}${payload.reps} 次`);
        } else {
            toast(`已取消第 ${n} 组`);
        }
    } catch (err) {
        toast(err.message);
        renderTraining();
    } finally {
        btn.disabled = false;
    }
}

/* 训练中勾完一组 → 自动开始组间休息 */
function beginRest(pid, eid, name, restSeconds) {
    clearInterval(timer.handle);
    timer.running = false;
    timer.finished = false;
    timer.pid = pid;
    timer.eid = eid;
    timer.name = name;
    timer.total = Number(restSeconds) || 90;
    timer.remaining = timer.total;
    $("#timer-title").textContent = `${name} · 组间休息`;
    startTimer();
    syncRestBanner();
}

function syncRestBanner() {
    const banner = $("#rest-banner");
    if (!banner) return;
    const mine = trainPlan && String(timer.pid) === String(trainPlan.id) && (timer.running || timer.finished);
    if (!mine) { banner.hidden = true; return; }
    banner.hidden = false;
    $(".rb-dot").classList.toggle("paused", !timer.running);
    $("#rb-text").textContent = timer.finished
        ? "休息结束，开始下一组"
        : `${timer.running ? "组间休息" : "已暂停"} ${fmtClock(timer.remaining)}`;
}

function closeTraining() {
    const dirty = trainPlan && trainDoneCount(trainPlan) > 0;
    trainMask.hidden = true;
    trainPlan = null;
    clearInterval(trainTick);
    trainTick = null;
    $("#rest-banner").hidden = true;
    document.body.style.overflow = "";
    if (dirty) loadPlanTab().catch(() => {});
}

$("#train-close").addEventListener("click", closeTraining);
$("#rb-skip").addEventListener("click", () => {
    stopTimer();
    if (trainPlan) {
        const ex = trainPlan.exercises.find((x) => String(x.id) === String(timer.eid));
        const seconds = ex ? ex.rest_seconds : 90;
        timer.total = seconds || 90;
        timer.remaining = timer.total;
    }
    syncRestBanner();
});
$("#train-finish").addEventListener("click", async () => {
    if (!trainPlan) return;
    const pid = trainPlan.id;
    const btn = $("#train-finish");
    btn.disabled = true;
    try {
        await api(`/api/plans/${pid}/complete`, { method: "POST" });
        closeTraining();
        await refreshAll();
        toast("训练已打卡，去历史里看曲线吧 📈");
    } catch (err) {
        toast(err.message);
    } finally {
        btn.disabled = false;
    }
});

/* ================= 编辑计划 ================= */
const planEditMask = $("#plan-edit-mask");
let editingPlan = null;
let editParts = new Set();

function renderEditChips() {
    $("#pe-chips").innerHTML = BODY_PARTS.map(
        (p) => `<button type="button" class="chip-btn ${editParts.has(p) ? "active" : ""}" data-part="${p}">${p}</button>`
    ).join("");
    $("#pe-hint").textContent = editParts.size ? `已选：${[...editParts].join("、")}` : "已选 0 个";
}

async function openPlanEditor(pid) {
    try {
        const plan = await api(`/api/plans/${pid}`);
        editingPlan = plan;
        $("#pe-date").value = plan.plan_date;
        $("#pe-title").value = plan.title || "";
        $("#pe-note").value = plan.note || "";
        editParts = new Set(plan.body_parts);
        renderEditChips();
        $("#pe-msg").className = "form-msg";
        $("#pe-msg").textContent = "";
        planEditMask.hidden = false;
        document.body.style.overflow = "hidden";
    } catch (err) {
        toast(err.message);
    }
}

function closePlanEditor() {
    planEditMask.hidden = true;
    editingPlan = null;
    document.body.style.overflow = "";
}

$("#pe-chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip-btn");
    if (!chip) return;
    const part = chip.dataset.part;
    if (editParts.has(part)) {
        editParts.delete(part);
        chip.classList.remove("active");
    } else {
        if (editParts.size >= 5) return toast("最多选择 5 个部位");
        editParts.add(part);
        chip.classList.add("active");
    }
    $("#pe-hint").textContent = editParts.size ? `已选：${[...editParts].join("、")}` : "已选 0 个";
});

$("#plan-edit-close").addEventListener("click", closePlanEditor);
planEditMask.addEventListener("click", (e) => { if (e.target === planEditMask) closePlanEditor(); });
$("#plan-edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!editingPlan) return;
    const msg = $("#pe-msg");
    const fail = (t) => { msg.className = "form-msg error"; msg.textContent = t; };
    const planDate = $("#pe-date").value;
    if (!planDate) return fail("请选择计划日期");
    if (!editParts.size) return fail("至少选择一个训练部位");
    const btn = $("#plan-edit-form .primary-btn");
    btn.disabled = true;
    try {
        const plan = await api(`/api/plans/${editingPlan.id}`, {
            method: "PATCH",
            body: JSON.stringify({
                plan_date: planDate,
                body_parts: [...editParts],
                title: $("#pe-title").value.trim(),
                note: $("#pe-note").value.trim(),
            }),
        });
        closePlanEditor();
        await refreshAll();
        toast(`已保存：${plan.title || plan.body_parts.join("+")} · ${shortDate(plan.plan_date)}`);
    } catch (err) {
        fail(err.message);
    } finally {
        btn.disabled = false;
    }
});

/* ================= 体重曲线 ================= */
const bodyMask = $("#body-mask");

async function loadBodyPanel() {
    const rows = await api("/api/bodies");
    const panel = $("#body-panel");
    const list = rows
        .slice()
        .sort((a, b) => (a.date === b.date ? a.id - b.id : a.date < b.date ? -1 : 1));

    if (!list.length) {
        panel.innerHTML = `<div class="empty sm"><span class="empty-icon">⚖️</span>还没有体重记录<br>点右上角「＋ 记录」记一笔</div>`;
        return;
    }

    const last = list[list.length - 1];
    const prev = list.length > 1 ? list[list.length - 2] : null;
    let deltaHtml = `<span class="body-delta flat">首次记录</span>`;
    if (prev && prev.weight && last.weight) {
        const d = Number(last.weight) - Number(prev.weight);
        const cls = Math.abs(d) < 0.05 ? "flat" : d < 0 ? "down" : "up";
        const txt = Math.abs(d) < 0.05 ? "持平" : `${d > 0 ? "+" : ""}${d.toFixed(1)} kg`;
        deltaHtml = `<span class="body-delta ${cls}">${txt}</span><span class="body-unit">较上次</span>`;
    }

    const points = list.filter((r) => r.weight).map((r) => ({ label: shortDate(r.date), value: Number(r.weight) }));
    const fatLine = last.body_fat ? `<span class="body-unit">体脂 ${last.body_fat}%</span>` : "";

    const rowsHtml = list.slice().reverse().slice(0, 5).map((r) => `
        <div class="ex-item">
            <div class="ex-name-cell">
                <div class="ex-label">${shortDate(r.date)} · ${weekdayOf(r.date)}</div>
                <div class="ex-detail">${r.weight} kg${r.body_fat ? " · 体脂 " + r.body_fat + "%" : ""}${r.note ? " · " + escapeHtml(r.note) : ""}</div>
            </div>
            <button class="ex-x" data-action="del-body" data-id="${r.id}" title="删除这条记录">✕</button>
        </div>`).join("");

    panel.innerHTML = `
        <div class="body-panel">
            <div class="body-stat">
                <span class="body-now">${last.weight}<span class="body-unit"> kg</span></span>
                ${deltaHtml}
                ${fatLine}
            </div>
            ${lineChart(points, { unit: " kg", decimals: 1, title: "体重趋势" })}
            <div class="pc-ex">${rowsHtml}</div>
        </div>`;
}

$("#body-close").addEventListener("click", () => {
    bodyMask.hidden = true;
    document.body.style.overflow = "";
});
bodyMask.addEventListener("click", (e) => {
    if (e.target === bodyMask) { bodyMask.hidden = true; document.body.style.overflow = ""; }
});
$("#body-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#b-msg");
    const fail = (t) => { msg.className = "form-msg error"; msg.textContent = t; };
    const weight = $("#b-weight").value;
    if (!weight) return fail("请填写体重");
    const w = Number(weight);
    if (w < 20 || w > 500) return fail("体重需在 20–500 kg 之间");
    const fat = $("#b-fat").value;
    if (fat !== "" && (Number(fat) < 2 || Number(fat) > 70)) return fail("体脂率需在 2–70% 之间");
    const btn = $("#body-form .primary-btn");
    btn.disabled = true;
    try {
        await api("/api/bodies", {
            method: "POST",
            body: JSON.stringify({
                date: $("#b-date").value || TODAY,
                weight: w,
                body_fat: fat === "" ? null : Number(fat),
                note: $("#b-note").value.trim(),
            }),
        });
        bodyMask.hidden = true;
        document.body.style.overflow = "";
        $("#b-weight").value = "";
        $("#b-fat").value = "";
        $("#b-note").value = "";
        msg.className = "form-msg";
        msg.textContent = "";
        await loadBodyPanel();
        toast(`已记录体重 ${w} kg`);
    } catch (err) {
        fail(err.message);
    } finally {
        btn.disabled = false;
    }
});

/* ================= 动作进步 ================= */
const progMask = $("#prog-mask");

function openProgSheet() {
    progMask.hidden = false;
    document.body.style.overflow = "hidden";
    loadProgList();
}

function closeProgSheet() {
    progMask.hidden = true;
    document.body.style.overflow = "";
}

async function loadProgList() {
    const body = $("#prog-body");
    body.innerHTML = `<div class="chart-empty">加载中…</div>`;
    try {
        const names = await api("/api/progress/exercise-names");
        if (!names.length) {
            body.innerHTML = `<div class="empty sm"><span class="empty-icon">📈</span>还没有可对比的动作<br>完成一次训练打卡后就会出现在这里</div>`;
            return;
        }
        body.innerHTML = `
            <p class="hint mb-10">挑一个动作，看重量、容量和预估 1RM 的变化</p>
            <div class="prog-list">
                ${names.map((n) => `
                    <div class="prog-item" data-action="prog-open" data-name="${escapeHtml(n.name)}">
                        <span class="pi-name">${escapeHtml(n.name)}</span>
                        <span class="pi-meta">${n.session_count} 次 · 最近 ${shortDate(n.last_date)}</span>
                        <span class="pi-arrow">›</span>
                    </div>`).join("")}
            </div>`;
    } catch (err) {
        body.innerHTML = `<div class="chart-empty">${escapeHtml(err.message)}</div>`;
    }
}

async function showProgDetail(name) {
    const body = $("#prog-body");
    body.innerHTML = `<div class="chart-empty">加载中…</div>`;
    try {
        const data = await api(`/api/progress/exercise?name=${encodeURIComponent(name)}`);
        const pts = data.points.map((p) => ({ label: shortDate(p.date), value: Number(p.max_weight), extra: p }));
        const lastP = data.points[data.points.length - 1];
        body.innerHTML = `
            <div class="prog-detail">
                <button type="button" class="prog-back" data-action="prog-back">‹ 换个动作</button>
                <div class="te-head"><span class="te-name">${escapeHtml(data.name)}</span>
                    <span class="te-count">${data.points.length} 次训练 · ${data.total_sets} 组</span></div>
                <div class="prog-stats">
                    <div class="ps-cell"><div class="ps-value">${num(data.pr_weight)}</div><div class="ps-label">最好重量 kg</div></div>
                    <div class="ps-cell"><div class="ps-value">${num(lastP ? lastP.est_1rm : 0)}</div><div class="ps-label">预估 1RM kg</div></div>
                    <div class="ps-cell"><div class="ps-value">${num(data.best_volume)}</div><div class="ps-label">单次容量 kg</div></div>
                </div>
                ${data.pr_date ? `<div><span class="pr-badge">🏆 PR ${num(data.pr_weight)} kg · ${shortDate(data.pr_date)}</span></div>` : ""}
                ${lineChart(pts, { unit: " kg", decimals: 1, title: `${data.name} 最大重量趋势` })}
                <div class="pc-ex">
                    ${data.points.slice().reverse().map((p) => `
                        <div class="ex-item">
                            <div class="ex-name-cell">
                                <div class="ex-label">${shortDate(p.date)} · ${weekdayOf(p.date)}</div>
                                <div class="ex-detail">最大 ${p.max_weight} kg · 容量 ${num(p.volume)} kg · ${p.sets} 组 · 1RM≈${num(p.est_1rm)}</div>
                            </div>
                        </div>`).join("")}
                </div>
            </div>`;
    } catch (err) {
        body.innerHTML = `<div class="chart-empty">${escapeHtml(err.message)}</div>`;
    }
}

$("#prog-close").addEventListener("click", closeProgSheet);
progMask.addEventListener("click", (e) => { if (e.target === progMask) closeProgSheet(); });

/* ---------------- 修改动作 ---------------- */
const exMask = $("#ex-mask");
let editing = null;   // { pid, eid }

function openExEditor(btn) {
    editing = { pid: btn.dataset.pid, eid: btn.dataset.eid };
    $("#ex-name").value = btn.dataset.name;
    $("#ex-sets").value = btn.dataset.sets;
    $("#ex-reps").value = btn.dataset.reps;
    $("#ex-weight").value = Number(btn.dataset.weight) || 0;
    $("#ex-rest").value = btn.dataset.rest;
    $("#ex-msg").className = "form-msg";
    $("#ex-msg").textContent = "";
    exMask.hidden = false;
    document.body.style.overflow = "hidden";
}

function closeExEditor() {
    exMask.hidden = true;
    editing = null;
    document.body.style.overflow = "";
}

$("#ex-close").addEventListener("click", closeExEditor);
exMask.addEventListener("click", (e) => { if (e.target === exMask) closeExEditor(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !exMask.hidden) closeExEditor(); });

$("#ex-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!editing) return;
    const msg = $("#ex-msg");
    const fail = (t) => { msg.className = "form-msg error"; msg.textContent = t; };

    const name = $("#ex-name").value.trim();
    const sets = Number($("#ex-sets").value);
    const reps = Number($("#ex-reps").value);
    const weight = $("#ex-weight").value === "" ? 0 : Number($("#ex-weight").value);
    const rest = Number($("#ex-rest").value);

    if (!name) return fail("动作名称不能为空");
    if (!sets || sets < 1 || sets > 99) return fail("组数需在 1–99 之间");
    if (!reps || reps < 1 || reps > 999) return fail("次数需在 1–999 之间");
    if (weight < 0 || weight > 1000) return fail("重量需在 0–1000 kg 之间");
    if (!rest || rest < 1 || rest > 600) return fail("休息时长需在 1–600 秒之间");

    const btn = $("#ex-form .primary-btn");
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "保存中…";
    try {
        await api(`/api/plans/${editing.pid}/exercises/${editing.eid}`, {
            method: "PATCH",
            body: JSON.stringify({ name, sets, reps, weight, rest_seconds: rest }),
        });
        closeExEditor();
        await refreshAll();
        toast(`已更新动作：${name}`);
    } catch (err) {
        fail(err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = label;
    }
});

/* ================= 账号与登录 ================= */
let CURRENT_USER = null;
let authMode = "login";

function showAuth(message) {
    $("#auth-view").hidden = false;
    $("#app-view").hidden = true;
    document.body.classList.add("auth-mode");
    const msg = $("#auth-msg");
    msg.className = message ? "form-msg error" : "form-msg";
    msg.textContent = message || "";
    setTimeout(() => $("#auth-username").focus(), 60);
}

function requireLogin() {
    CURRENT_USER = null;
    stopTimer();
    $("#timer-bar").hidden = true;
    document.body.style.overflow = "";
    $("#sheet-mask").hidden = true;
    $("#timer-mask").hidden = true;
    showAuth("登录已过期，请重新登录");
}

function showApp(user) {
    CURRENT_USER = user;
    $("#auth-view").hidden = true;
    $("#app-view").hidden = false;
    document.body.classList.remove("auth-mode");
    $("#user-name").textContent = user.username;
    bootData();
}

function setAuthMode(mode) {
    authMode = mode;
    $$(".auth-tab").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    $("#confirm-field").hidden = mode !== "register";
    $("#auth-submit").textContent = mode === "register" ? "注册并登录" : "登录";
    $("#auth-password").autocomplete = mode === "register" ? "new-password" : "current-password";
    $("#auth-msg").className = "form-msg";
    $("#auth-msg").textContent = "";
    $("#auth-confirm").value = "";
}

$$(".auth-tab").forEach((btn) => {
    btn.addEventListener("click", () => setAuthMode(btn.dataset.mode));
});

$("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("#auth-username").value.trim();
    const password = $("#auth-password").value;
    const msg = $("#auth-msg");

    const fail = (text) => { msg.className = "form-msg error"; msg.textContent = text; };
    if (!username) return fail("请输入用户名");
    if (!password) return fail("请输入密码");
    if (authMode === "register") {
        if (username.length < 2) return fail("用户名至少 2 位");
        if (password.length < 8) return fail("密码至少 8 位");
        if (password !== $("#auth-confirm").value) return fail("两次输入的密码不一致");
    }

    const submit = $("#auth-submit");
    submit.disabled = true;
    submit.textContent = authMode === "register" ? "注册中…" : "登录中…";
    msg.className = "form-msg";
    msg.textContent = "";
    try {
        const data = await api(`/api/auth/${authMode}`, {
            method: "POST",
            body: JSON.stringify({ username, password }),
            ignoreAuth: true,
        });
        $("#auth-form").reset();
        $("#auth-password").value = "";
        $("#auth-confirm").value = "";
        showApp(data.user);
        if (data.adopted_legacy) toast("已把之前本机保存的训练数据归到你的账号");
        else toast(authMode === "register" ? "注册成功，开始记录吧" : `欢迎回来，${data.user.username}`);
    } catch (err) {
        fail(err.message);
    } finally {
        submit.disabled = false;
        submit.textContent = authMode === "register" ? "注册并登录" : "登录";
    }
});

$("#logout-btn").addEventListener("click", async () => {
    if (!confirm("确定退出登录？下次需重新输入密码。")) return;
    try {
        await api("/api/auth/logout", { method: "POST", ignoreAuth: true });
    } catch (err) {
        /* 会话可能已失效，退出动作照常执行 */
    }
    requireLogin();
    const m = $("#auth-msg");
    m.className = "form-msg";
    m.textContent = "已退出登录";
});

/* ---------------- 数据加载入口 ---------------- */
let booted = false;
async function bootData() {
    if (!booted) {
        booted = true;
        await loadBodyParts().catch(() => {});
        if (!$("#exercise-rows").children.length) addRow();
    }
    await refreshAll().catch((err) => toast(err.message));
}

/* ---------------- 初始化 ---------------- */
(async function init() {
    document.body.classList.add("auth-mode");
    try {
        const me = await api("/api/auth/me", { ignoreAuth: true });
        showApp(me);
    } catch (err) {
        showAuth();
    }
})();
