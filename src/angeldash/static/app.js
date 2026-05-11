// AngelNet 회의실 대시보드 — 클라이언트 측 단일 페이지 로직
// 빌드 도구 없음. 모듈 구조는 IIFE 또는 단일 파일.

const GRID_START_HOUR = 8;
const GRID_END_HOUR = 18; // 18시 퇴근 기준
const SLOT_MIN = 30;
const ROW_HEIGHT_PX = 24; // style.css --row-h 와 동기화

const state = {
  date: todayISO(),
  floor: 8,
  rooms: [],
  reservations: [],
  me: null,
  isLoading: false,
  view: localStorage.getItem("view") || "day",
  unchecked: loadUnchecked(),
};

function loadUnchecked() {
  try {
    const raw = localStorage.getItem("uncheckedRooms");
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveUnchecked() {
  localStorage.setItem("uncheckedRooms", JSON.stringify(Array.from(state.unchecked)));
}

function isRoomVisible(roomId) {
  return !state.unchecked.has(roomId);
}

function visibleRooms() {
  return state.rooms.filter((r) => isRoomVisible(r.id));
}

// Date 객체를 로컬 시간대 기준 "YYYY-MM-DD" 로 변환.
// toISOString() 는 UTC 기준이라 KST 자정 같은 케이스에서 하루가 밀린다 — 사용 금지.
function isoFromLocalDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function todayISO() {
  return isoFromLocalDate(new Date());
}

function setLoading(on) {
  state.isLoading = on;
  document.body.classList.toggle("app-loading", !!on);
}

function escapeHtml(s) {
  // user data 를 innerHTML 로 삽입할 때 XSS 방지
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtHHMM(h, m) {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function timeToMinutes(hhmmss) {
  // "14:30:00" -> 870
  const [h, m] = hhmmss.split(":").map(Number);
  return h * 60 + m;
}

function gridStartMinutes() { return GRID_START_HOUR * 60; }
function gridEndMinutes() { return GRID_END_HOUR * 60; }

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ message: r.statusText }));
    const e = new Error(err.message || "API error");
    e.status = r.status;
    e.payload = err;
    throw e;
  }
  if (r.status === 204) return null;
  return r.json();
}

function toast(message, type = "ok") {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

// 예약이 특정 날짜에 발생하는지 판단
//  - 반복 예약(is_repeat): 시작~종료 범위 + 요일 비트 매칭
//  - 비반복 multi-day (end_date 있음): 시작~종료 범위 매일 (종일 기간 예약 케이스)
//  - 비반복 단일: 시작일에만
function reservationOccursOn(res, isoDate) {
  if (res.is_repeat) {
    if (isoDate < res.date) return false;
    if (res.end_date && isoDate > res.end_date) return false;
    // is_repeat=true 이지만 weekdays 가 0/null 이면 매일 발생
    if (!res.weekdays || res.weekdays === 0) return true;
    // 요일 비트: 월=1 화=2 수=4 목=8 금=16 토=32 일=64
    const d = new Date(isoDate + "T00:00:00");
    const weekday = d.getDay() === 0 ? 7 : d.getDay(); // Sun=7
    const bit = 1 << (weekday - 1);
    return (res.weekdays & bit) !== 0;
  }

  // 비반복 multi-day 예약 (AngelNet 의 종일 기간 예약: isRepeat=0 + endDate 있음)
  if (res.end_date) {
    return res.date <= isoDate && isoDate <= res.end_date;
  }

  // 비반복 단일 일자
  return res.date === isoDate;
}

const MY_LIST_WINDOW_DAYS = 90;

function isoAddDays(iso, days) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return isoFromLocalDate(d);
}

function isoMonday(iso) {
  const d = new Date(iso + "T00:00:00");
  const wd = d.getDay() || 7; // 일=0 → 7
  d.setDate(d.getDate() - (wd - 1));
  return isoFromLocalDate(d);
}

// fromIso 이상 fromIso+daysAhead 이하 중 res 가 발생하는 첫 날짜 (없으면 null)
function nextOccurrenceWithin(res, fromIso, daysAhead) {
  for (let i = 0; i <= daysAhead; i++) {
    const iso = isoAddDays(fromIso, i);
    if (reservationOccursOn(res, iso)) return iso;
  }
  return null;
}

async function loadAll() {
  if (state.isLoading) return; // 중복 호출 방지
  setLoading(true);
  try {
    state.rooms = await api("GET", `/api/rooms?floor=${state.floor}`);
    const start = state.date;
    const endIso = isoAddDays(state.date, MY_LIST_WINDOW_DAYS);
    state.reservations = await api(
      "GET",
      `/api/reservations?start=${start}&end=${endIso}`,
    );
    if (!state.me) {
      state.me = await api("GET", "/api/me");
      document.getElementById("user-name").textContent =
        `${state.me.name}(${state.me.user_id})`;
    }
    renderRoomFilter();
    render();
  } finally {
    setLoading(false);
  }
}

function render() {
  applyVisibility();
  if (state.view === "day") {
    renderGrid();
  } else if (state.view === "week2") {
    renderWeek2();
  }
  renderMyList();
}

function applyVisibility() {
  document.getElementById("schedule-grid").hidden = state.view !== "day";
  document.getElementById("week-container").hidden = state.view !== "week2";
  document.querySelectorAll(".view-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === state.view);
  });
}

function renderGrid() {
  const table = document.getElementById("schedule-grid");
  table.innerHTML = "";
  const rooms = visibleRooms();
  if (rooms.length === 0) {
    // 회의실 모두 체크 해제 시 안내 메시지
    table.innerHTML = "<tbody><tr><td style='padding:20px;color:var(--color-fg-mute)'>위 체크박스에서 회의실을 1개 이상 선택하세요.</td></tr></tbody>";
    return;
  }

  // 헤더
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  trh.innerHTML = `<th></th>` + rooms.map((r) => `<th>${escapeHtml(r.name)}</th>`).join("");
  thead.appendChild(trh);
  table.appendChild(thead);

  // 본문 (시간대 행 × 회의실 열)
  const tbody = document.createElement("tbody");
  for (let mins = gridStartMinutes(); mins < gridEndMinutes(); mins += SLOT_MIN) {
    const tr = document.createElement("tr");
    const h = Math.floor(mins / 60), m = mins % 60;
    const tdTime = document.createElement("td");
    tdTime.className = "time-cell";
    tdTime.textContent = fmtHHMM(h, m);
    tr.appendChild(tdTime);

    const timeLabel = fmtHHMM(h, m);
    for (const room of rooms) {
      const td = document.createElement("td");
      td.className = "empty";
      td.dataset.roomId = room.id;
      td.dataset.minutes = String(mins);
      td.dataset.time = timeLabel;
      td.dataset.date = state.date;
      // native title 제거 — 즉각 반응하는 #grid-hover-tooltip 사용 (OS 1초 지연 회피)
      td.addEventListener("click", () => openCreateModal(room, mins));
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  // 예약 블록 오버레이 (분 단위 정확)
  for (const res of state.reservations) {
    if (!reservationOccursOn(res, state.date)) continue;
    const room = rooms.find((r) => r.id === res.room_id);
    if (!room) continue;
    paintReservation(res, room);
  }
}

function paintReservation(res, room) {
  const startMin = res.is_all_day ? gridStartMinutes() : timeToMinutes(res.time);
  const durMin = res.is_all_day
    ? (gridEndMinutes() - gridStartMinutes())
    : res.duration;

  // 그리드 범위 밖이면 건너뜀
  if (startMin + durMin <= gridStartMinutes()) return;
  if (startMin >= gridEndMinutes()) return;

  const offsetMin = Math.max(0, startMin - gridStartMinutes());
  const visibleMin = Math.min(
    durMin,
    gridEndMinutes() - Math.max(startMin, gridStartMinutes()),
  );

  const top = (offsetMin / SLOT_MIN) * ROW_HEIGHT_PX;
  const height = (visibleMin / SLOT_MIN) * ROW_HEIGHT_PX - 1;

  // 해당 회의실 컬럼의 첫 행 td 를 찾아 그 위에 absolute 블록 배치
  const cell = document.querySelector(
    `#schedule-grid tbody tr:first-child td[data-room-id="${room.id}"]`,
  );
  if (!cell) return;

  const block = document.createElement("div");
  const isMine = state.me && (res.creator_id || res.creator_name) === (state.me.user_id || state.me.name);
  block.className = "reservation-block " + (isMine ? "mine" : "other") +
    (res.is_repeat ? " repeat" : "");
  block.style.top = `${top}px`;
  block.style.height = `${height}px`;
  block.title = `${res.creator_name} · ${res.reason}`;
  // 예약자 이름을 굵게 강조해 다크 배경에서도 식별 용이
  block.innerHTML =
    `<strong class="who">${escapeHtml(res.creator_name)}</strong>` +
    ` · ${escapeHtml(res.reason)}`;
  block.addEventListener("click", (e) => {
    e.stopPropagation();
    openDetailModal(res, room, isMine);
  });
  cell.appendChild(block);
}

function renderRoomFilter() {
  const chips = document.getElementById("room-chips");
  chips.innerHTML = "";

  // 전체 chip
  const allChecked = state.unchecked.size === 0;
  const allChip = document.createElement("label");
  allChip.className = "room-chip all" + (allChecked ? " checked" : "");
  allChip.innerHTML =
    `<input type="checkbox" id="room-all" ${allChecked ? "checked" : ""}> 전체`;
  allChip.querySelector("input").addEventListener("change", (e) => {
    if (e.target.checked) {
      state.unchecked = new Set();
    } else {
      state.unchecked = new Set(state.rooms.map((r) => r.id));
    }
    saveUnchecked();
    renderRoomFilter();
    render();
  });
  chips.appendChild(allChip);

  // 회의실별 chip
  for (const room of state.rooms) {
    const checked = isRoomVisible(room.id);
    const chip = document.createElement("label");
    chip.className = "room-chip" + (checked ? " checked" : "");
    chip.innerHTML =
      `<input type="checkbox" data-room="${escapeHtml(room.id)}" ${
        checked ? "checked" : ""
      }> ${escapeHtml(room.name)}`;
    chip.querySelector("input").addEventListener("change", (e) => {
      const id = e.target.dataset.room;
      if (e.target.checked) state.unchecked.delete(id);
      else state.unchecked.add(id);
      saveUnchecked();
      renderRoomFilter();
      render();
    });
    chips.appendChild(chip);
  }
}

function renderWeek2() {
  const container = document.getElementById("week-container");
  container.innerHTML = "";

  const thisMon = isoMonday(state.date);
  const nextMon = isoAddDays(thisMon, 7);
  const today = todayISO();

  const rooms = visibleRooms();
  if (rooms.length === 0) {
    container.innerHTML =
      "<div style='padding:20px;color:var(--color-fg-mute)'>위 체크박스에서 회의실을 1개 이상 선택하세요.</div>";
    return;
  }

  container.appendChild(buildWeekSection(thisMon, rooms, "this-week", "이번 주", today));
  container.appendChild(buildWeekSection(nextMon, rooms, "next-week", "다음 주", today));
}

function buildWeekSection(monIso, rooms, kindClass, tagText, todayIso) {
  const section = document.createElement("section");
  section.className = "week-section " + kindClass;

  // 헤더 (주차 레이블 + 날짜 범위)
  const friIso = isoAddDays(monIso, 4);
  const header = document.createElement("div");
  header.className = "week-header";
  header.innerHTML =
    `<span class="week-tag">${escapeHtml(tagText)}</span>` +
    `<span class="week-range-label">${escapeHtml(monIso)} (월) ~ ${escapeHtml(friIso)} (금)</span>`;
  section.appendChild(header);

  // 그리드 — 회의실 수에 따라 컬럼 너비 동적 계산 (창 폭 활용)
  const wrap = document.createElement("div");
  wrap.className = "week-wrap";
  const table = document.createElement("table");
  table.className = "week-grid";
  table.style.setProperty("--wg-col-w", calcWeekColumnWidth(rooms.length) + "px");

  const dayNames = ["월", "화", "수", "목", "금"];
  const ROOMS_N = rooms.length;

  // thead 1단: 요일 헤더 (rooms.length 만큼 colspan)
  const thead = document.createElement("thead");
  const tr1 = document.createElement("tr");
  const th0 = document.createElement("th");
  th0.className = "time-col";
  th0.rowSpan = 2;
  tr1.appendChild(th0);
  for (let d = 0; d < 5; d++) {
    const iso = isoAddDays(monIso, d);
    const th = document.createElement("th");
    th.className = "day-head" + (iso === todayIso ? " today" : "");
    th.colSpan = ROOMS_N;
    const [, mm, dd] = iso.split("-");
    th.textContent = `${dayNames[d]} ${mm}/${dd}`;
    tr1.appendChild(th);
  }
  thead.appendChild(tr1);

  // thead 2단: 회의실명
  const tr2 = document.createElement("tr");
  for (let d = 0; d < 5; d++) {
    rooms.forEach((room, idx) => {
      const th = document.createElement("th");
      th.className = "room-head" + (idx === ROOMS_N - 1 ? " day-last" : "");
      th.textContent = shortRoomName(room.name);
      th.title = room.name;
      tr2.appendChild(th);
    });
  }
  thead.appendChild(tr2);
  table.appendChild(thead);

  // tbody: 시간 행
  const tbody = document.createElement("tbody");
  for (let mins = gridStartMinutes(); mins < gridEndMinutes(); mins += SLOT_MIN) {
    const tr = document.createElement("tr");
    const h = Math.floor(mins / 60), m = mins % 60;
    const tdTime = document.createElement("td");
    tdTime.className = "wg-time-cell";
    tdTime.textContent = fmtHHMM(h, m);
    tr.appendChild(tdTime);

    for (let d = 0; d < 5; d++) {
      const iso = isoAddDays(monIso, d);
      rooms.forEach((room, idx) => {
        const td = document.createElement("td");
        td.className = "wg-cell" + (idx === ROOMS_N - 1 ? " day-last" : "");
        td.dataset.date = iso;
        td.dataset.roomId = room.id;
        td.dataset.minutes = String(mins);
        // native title 제거 — body mousemove 가 즉각 처리
        td.addEventListener("click", () => openCreateModalForDate(room, mins, iso));
        tr.appendChild(td);
      });
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  section.appendChild(wrap);

  // 예약 블록 painting
  for (let d = 0; d < 5; d++) {
    const iso = isoAddDays(monIso, d);
    for (const res of state.reservations) {
      if (!reservationOccursOn(res, iso)) continue;
      const roomIdx = rooms.findIndex((r) => r.id === res.room_id);
      if (roomIdx < 0) continue;
      paintWeekReservation(res, rooms[roomIdx], tbody, d, roomIdx, ROOMS_N);
    }
  }

  return section;
}

function paintWeekReservation(res, room, tbody, dayIdx, roomIdx, roomsN) {
  const startMin = res.is_all_day ? gridStartMinutes() : timeToMinutes(res.time);
  const durMin = res.is_all_day
    ? gridEndMinutes() - gridStartMinutes()
    : res.duration;
  if (startMin + durMin <= gridStartMinutes()) return;
  if (startMin >= gridEndMinutes()) return;

  const offsetMin = Math.max(0, startMin - gridStartMinutes());
  const visibleMin = Math.min(
    durMin,
    gridEndMinutes() - Math.max(startMin, gridStartMinutes()),
  );
  const top = (offsetMin / SLOT_MIN) * ROW_HEIGHT_PX;
  const height = (visibleMin / SLOT_MIN) * ROW_HEIGHT_PX - 1;

  // 첫 번째 행의 해당 컬럼 td 에 absolute 블록 배치 (time-cell=0 이후 day*rooms+room 인덱스)
  const firstRow = tbody.children[0];
  if (!firstRow) return;
  const cellIdx = 1 + dayIdx * roomsN + roomIdx;
  const cell = firstRow.children[cellIdx];
  if (!cell) return;

  const isMine =
    state.me &&
    (res.creator_id || res.creator_name) === (state.me.user_id || state.me.name);
  const block = document.createElement("div");
  block.className =
    "wg-res " +
    (isMine ? "" : "other") +
    (res.is_all_day ? " all-day" : "") +
    (res.is_repeat ? " repeat" : "");
  block.style.top = `${top}px`;
  block.style.height = `${height}px`;
  block.title = `${res.creator_name} · ${res.reason}`;
  block.innerHTML =
    `<strong class="who">${escapeHtml(res.creator_name)}</strong>` +
    `<br>${escapeHtml(res.reason)}`;
  block.addEventListener("click", (e) => {
    e.stopPropagation();
    openDetailModal(res, room, isMine);
  });
  cell.appendChild(block);
}

function shortRoomName(name) {
  // "8층 대회의실" → "대" / "8층 1번 회의실" → "1번" / "8층 2번 LAB" → "LAB2"
  if (/대회의실$/.test(name)) return "대";
  let m = name.match(/(\d+)번\s*LAB$/);
  if (m) return `LAB${m[1]}`;
  m = name.match(/(\d+)번\s*회의실$/);
  if (m) return `${m[1]}번`;
  return name.replace(/^\d+층\s*/, "").trim();
}

// 가용 가로 공간을 컬럼 갯수로 나눠 회의실 적을 때 빈 공간을 활용
function calcWeekColumnWidth(roomsN) {
  const timeCol = 56;
  const containerPad = 40; // .grid-wrap padding 좌우 + 여유
  const scrollbar = 16;
  const available = Math.max(
    window.innerWidth - timeCol - containerPad - scrollbar,
    800,
  );
  const totalCols = 5 * roomsN; // 평일 5일 × 회의실
  const calc = Math.floor(available / totalCols);
  return Math.max(76, Math.min(calc, 240)); // 최소 76, 최대 240
}

function openCreateModalForDate(room, slotMin, iso) {
  // 2주 뷰 셀 클릭 시 해당 날짜로 예약 모달을 열기 위해 state.date 를 임시 교체
  const prev = state.date;
  state.date = iso;
  openCreateModal(room, slotMin);
  state.date = prev;
}

function renderMyList() {
  const ul = document.getElementById("my-list");
  ul.innerHTML = "";
  if (!state.me) return;

  const meId = state.me.user_id || state.me.name;
  const isMine = (r) => (r.creator_id || r.creator_name) === meId;

  const mine = state.reservations
    .filter(isMine)
    .map((r) => ({
      res: r,
      nextDate: nextOccurrenceWithin(r, state.date, MY_LIST_WINDOW_DAYS),
    }))
    .filter((x) => x.nextDate !== null)
    .sort((a, b) =>
      (a.nextDate + a.res.time).localeCompare(b.nextDate + b.res.time),
    );

  if (mine.length === 0) {
    ul.innerHTML = "<li>예약 없음</li>";
    return;
  }
  for (const { res: r, nextDate } of mine) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span>★ ${escapeHtml(nextDate)} ${escapeHtml(r.time.slice(0, 5))} · ${escapeHtml(r.room)} · ${escapeHtml(r.reason)}</span>
      <span><button data-id="${escapeHtml(r.id)}" data-date="${escapeHtml(nextDate)}" class="del">삭제</button></span>
    `;
    li.querySelector(".del").addEventListener("click", () => confirmDelete(r));
    ul.appendChild(li);
  }
}

// ─── 모달 공통 헬퍼 ──────────────────────────────────────────
function showModal(html, onMount) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-backdrop"><div class="modal">${html}</div></div>`;
  const backdrop = root.querySelector(".modal-backdrop");
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closeModal();
  });
  if (onMount) onMount(root.querySelector(".modal"));
}

function closeModal() {
  document.getElementById("modal-root").innerHTML = "";
}

// ─── 예약 생성 모달 ──────────────────────────────────────────
function openCreateModal(room, slotMin) {
  const startH = Math.floor(slotMin / 60);
  const startM = slotMin % 60;

  showModal(`
    <h3>회의실 예약 — ${escapeHtml(room.name)}</h3>
    <div class="form-row">
      <label>제목</label>
      <input id="m-reason" type="text" placeholder="회의 제목" required>
    </div>
    <div class="form-row">
      <label>날짜</label>
      <input id="m-date" type="date" value="${state.date}">
    </div>
    <div class="form-row">
      <label>시작 시간 (HH:MM, 30분 단위)</label>
      <input id="m-time" type="time" value="${String(startH).padStart(2, "0")}:${String(startM).padStart(2, "0")}" step="1800">
    </div>
    <div class="form-row">
      <label>예약 시간 (분, 30~720, 30분 단위)</label>
      <div class="stepper">
        <button type="button" class="stepper-btn" data-target="m-duration" data-delta="-30">−</button>
        <input id="m-duration" type="number" min="30" max="720" step="30" value="60">
        <button type="button" class="stepper-btn" data-target="m-duration" data-delta="30">+</button>
      </div>
    </div>
    <div class="form-row">
      <label>참석자 수</label>
      <div class="stepper">
        <button type="button" class="stepper-btn" data-target="m-participants" data-delta="-1">−</button>
        <input id="m-participants" type="number" min="1" max="999" value="3">
        <button type="button" class="stepper-btn" data-target="m-participants" data-delta="1">+</button>
      </div>
    </div>
    <div class="actions">
      <button class="cancel">취소</button>
      <button class="primary" id="m-submit">예약</button>
    </div>
  `, (modal) => {
    modal.querySelector(".cancel").addEventListener("click", closeModal);
    modal.querySelector("#m-reason").focus();
    // stepper +/- 버튼 핸들러 (큰 클릭 영역 — native spin button 대체)
    modal.querySelectorAll(".stepper-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = modal.querySelector("#" + btn.dataset.target);
        if (!input) return;
        const min = input.min !== "" ? Number(input.min) : -Infinity;
        const max = input.max !== "" ? Number(input.max) : Infinity;
        const delta = Number(btn.dataset.delta);
        const v = Math.max(min, Math.min(max, (Number(input.value) || 0) + delta));
        input.value = String(v);
      });
    });
    modal.querySelector("#m-submit").addEventListener("click", async () => {
      const reason = modal.querySelector("#m-reason").value.trim();
      const date = modal.querySelector("#m-date").value;
      const time = modal.querySelector("#m-time").value + ":00";
      const duration = Number(modal.querySelector("#m-duration").value);
      const participants = Number(modal.querySelector("#m-participants").value);

      if (!reason) { toast("회의 제목을 입력하세요", "err"); return; }

      try {
        await api("POST", "/api/reservations", {
          date, time, duration, room_id: room.id, reason, participants,
        });
        closeModal();
        toast("예약 완료", "ok");
        await loadAll();
      } catch (e) {
        toast("예약 실패: " + (e.payload?.message || e.message), "err");
      }
    });
  });
}

// weekdays 비트마스크 → 한글 ("평일", "월/수/금" 등). 0/null 이면 "매일".
// 비트: 월=1 화=2 수=4 목=8 금=16 토=32 일=64
function weekdaysToKor(bits) {
  if (!bits) return "매일";
  if (bits === 31) return "평일";
  if (bits === 96) return "주말";
  const names = ["월", "화", "수", "목", "금", "토", "일"];
  const out = [];
  for (let i = 0; i < 7; i++) {
    if (bits & (1 << i)) out.push(names[i]);
  }
  return out.join("/");
}

// ─── 예약 상세/삭제 모달 ──────────────────────────────────────
function openDetailModal(res, room, isMine) {
  const endMin = timeToMinutes(res.time) + res.duration;
  const endH = Math.floor(endMin / 60),
    endM = endMin % 60;

  // 날짜 라인: 종료일/반복/기간 정보 보강
  let dateLine = escapeHtml(res.date);
  if (res.end_date && res.end_date !== res.date) {
    dateLine += ` ~ ${escapeHtml(res.end_date)}`;
  }
  if (res.is_repeat) {
    dateLine += ` (반복: ${escapeHtml(weekdaysToKor(res.weekdays))})`;
  } else if (res.end_date && res.end_date !== res.date) {
    dateLine += " (기간 예약)";
  }

  // 시간 라인: 종일이면 "종일"로 단순 표시, 아니면 시작~종료 + 분
  const timeLine = res.is_all_day
    ? "종일"
    : `${escapeHtml(res.time.slice(0, 5))} ~ ${escapeHtml(fmtHHMM(endH, endM))} (${res.duration}분)`;

  showModal(`
    <h3>예약 상세</h3>
    <div class="form-row"><label>회의실</label><div>${escapeHtml(room.name)}</div></div>
    <div class="form-row"><label>제목</label><div>${escapeHtml(res.reason)}</div></div>
    <div class="form-row"><label>예약자</label><div>${escapeHtml(res.creator_name)}</div></div>
    <div class="form-row"><label>날짜</label><div>${dateLine}</div></div>
    <div class="form-row"><label>시간</label><div>${timeLine}</div></div>
    <div class="actions">
      <button class="cancel">닫기</button>
      ${isMine ? `<button class="danger" id="m-del">삭제</button>` : ""}
    </div>
  `, (modal) => {
    modal.querySelector(".cancel").addEventListener("click", closeModal);
    if (isMine) {
      modal.querySelector("#m-del").addEventListener("click", () => {
        closeModal();
        confirmDelete(res);
      });
    }
  });
}

function confirmDelete(res) {
  if (!confirm(`정말 삭제할까요?\n\n${res.date} ${res.time.slice(0,5)} · ${res.room} · ${res.reason}`)) {
    return;
  }
  api("DELETE", `/api/reservations/${res.id}?event_date=${res.date}`)
    .then(() => {
      toast("삭제 완료", "ok");
      return loadAll();
    })
    .catch(e => toast("삭제 실패: " + (e.payload?.message || e.message), "err"));
}

// 이벤트 바인딩
document.addEventListener("DOMContentLoaded", () => {
  const dateInput = document.getElementById("date-input");
  dateInput.value = state.date;
  dateInput.addEventListener("change", () => {
    state.date = dateInput.value;
    loadAll().catch(e => toast(e.message, "err"));
  });
  document.getElementById("date-prev").addEventListener("click", () => {
    const unit = state.view === "week2" ? 7 : 1;
    state.date = isoAddDays(state.date, -unit);
    dateInput.value = state.date;
    loadAll().catch((e) => toast(e.message, "err"));
  });
  document.getElementById("date-next").addEventListener("click", () => {
    const unit = state.view === "week2" ? 7 : 1;
    state.date = isoAddDays(state.date, unit);
    dateInput.value = state.date;
    loadAll().catch((e) => toast(e.message, "err"));
  });
  document.getElementById("floor-select").addEventListener("change", (e) => {
    state.floor = Number(e.target.value);
    loadAll().catch(err => toast(err.message, "err"));
  });
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadAll().catch(e => toast(e.message, "err"));
  });

  document.querySelectorAll(".view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      localStorage.setItem("view", state.view);
      render();
    });
  });

  // 셀 hover 시 시간·회의실·날짜 즉시 표시 툴팁 — 일/2주 뷰 모두 적용.
  // body 전체에 mousemove 를 걸어 native title (~1초 지연) 대신 즉각 반응.
  const tip = document.createElement("div");
  tip.id = "grid-hover-tooltip";
  document.body.appendChild(tip);

  document.body.addEventListener("mousemove", (e) => {
    const cell = e.target.closest("td.empty, td.wg-cell");
    if (!cell) {
      tip.style.display = "none";
      return;
    }
    const mins = Number(cell.dataset.minutes);
    if (Number.isNaN(mins)) {
      tip.style.display = "none";
      return;
    }
    const time = fmtHHMM(Math.floor(mins / 60), mins % 60);
    const date = cell.dataset.date || state.date;
    const roomId = cell.dataset.roomId;
    const room = state.rooms.find((r) => r.id === roomId);
    const roomLabel = room ? room.name : "";
    tip.textContent = roomLabel
      ? `${time} · ${roomLabel} · ${date}`
      : `${time} · ${date}`;
    tip.style.display = "block";
    tip.style.left = `${e.clientX + 14}px`;
    tip.style.top = `${e.clientY - 28}px`;
  });
  document.body.addEventListener("mouseleave", () => {
    tip.style.display = "none";
  });

  // 창 크기 변경 시 2주 뷰 컬럼 너비 재계산 (debounce 200ms)
  let _resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(() => {
      if (state.view === "week2") render();
    }, 200);
  });

  loadAll().catch((e) => toast(e.message, "err"));
});
