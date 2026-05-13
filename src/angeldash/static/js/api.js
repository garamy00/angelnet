// 모든 API 호출 공통 래퍼.
// 에러는 throw, 성공은 응답 본문(JSON) 반환.
// 에러 객체에는 .status (HTTP 상태) 와 .detail (서버가 JSON 으로 보낸 경우 detail 객체) 가 부착됨.

async function rejectFromResponse(method, path, r) {
  const text = await r.text();
  let detail = null;
  try {
    const parsed = JSON.parse(text);
    detail = parsed && typeof parsed === 'object' ? parsed.detail : null;
  } catch (_) { /* not JSON */ }
  const err = new Error(`${method} ${path} failed: ${r.status} ${text}`);
  err.status = r.status;
  err.detail = detail;
  throw err;
}

export async function apiGet(path) {
  const r = await fetch(path, { headers: { 'Accept': 'application/json' } });
  if (!r.ok) await rejectFromResponse('GET', path, r);
  return r.json();
}

export async function apiPut(path, body) {
  const r = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) await rejectFromResponse('PUT', path, r);
  return r.json();
}

export async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) await rejectFromResponse('POST', path, r);
  return r.json();
}

export async function apiDelete(path) {
  const r = await fetch(path, { method: 'DELETE' });
  if (!r.ok) await rejectFromResponse('DELETE', path, r);
  return r.json();
}

// ISO 주 계산: 어떤 Date 객체 -> 'YYYY-Www' 문자열.
export function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

// ISO 주 -> 그 주의 월요일 ~ 금요일 날짜 5개 (YYYY-MM-DD).
export function weekDates(weekIso) {
  const [yearStr, wStr] = weekIso.split('-W');
  const year = parseInt(yearStr, 10);
  const week = parseInt(wStr, 10);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Day - 1));
  const monday = new Date(week1Mon);
  monday.setUTCDate(week1Mon.getUTCDate() + (week - 1) * 7);
  return Array.from({ length: 5 }, (_, i) => {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

const DAY_KR = ['월', '화', '수', '목', '금', '토', '일'];
export function formatDateLabel(yyyyMmDd) {
  const [y, m, d] = yyyyMmDd.split('-').map((v) => parseInt(v, 10));
  const date = new Date(Date.UTC(y, m - 1, d));
  const day = (date.getUTCDay() || 7) - 1;
  return `${String(m).padStart(2, '0')}/${String(d).padStart(2, '0')} (${DAY_KR[day]})`;
}

// 디바운스 헬퍼.
export function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// 토스트 알림 — 하단 작게.
export function toast(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `toast toast--${kind}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// 화면 중앙 큰 메시지 (ok/fail). '확인' 버튼 또는 ms 후 자동 사라짐.
// ms=0 이면 자동 닫힘 없음 (에러 박스 기본 동작 — 호출 측에서 명시).
export function flash(message, kind = 'ok', ms = 6000) {
  const root = document.createElement('div');
  root.className = `flash flash--${kind}`;
  root.innerHTML = `
    <div class="flash__box">
      <div class="flash__head">
        <div class="flash__icon">${kind === 'fail' ? '⚠️' : '✅'}</div>
        <div class="flash__msg"></div>
      </div>
      <div class="flash__actions">
        <button type="button" class="flash__ok primary">확인</button>
      </div>
    </div>`;
  root.querySelector('.flash__msg').textContent = message;
  const dismiss = () => root.remove();
  const okBtn = root.querySelector('.flash__ok');
  okBtn.addEventListener('click', dismiss);
  // 백드롭 클릭으로도 닫기 (박스 내부 클릭은 제외)
  root.addEventListener('click', (e) => {
    if (e.target === root) dismiss();
  });
  // Enter / Escape 단축키
  const onKey = (e) => {
    if (e.key === 'Enter' || e.key === 'Escape') {
      e.preventDefault();
      document.removeEventListener('keydown', onKey);
      dismiss();
    }
  };
  document.addEventListener('keydown', onKey);
  document.body.appendChild(root);
  okBtn.focus();
  if (ms > 0) setTimeout(() => {
    document.removeEventListener('keydown', onKey);
    dismiss();
  }, ms);
}

// 장기 작업용 progress overlay. 반환된 핸들의 .close() 호출 시 종료.
export function startProgress(label) {
  const root = document.createElement('div');
  root.className = 'progress-overlay';
  root.innerHTML = `
    <div class="progress-box">
      <div class="spinner"></div>
      <div class="progress-label"></div>
    </div>`;
  root.querySelector('.progress-label').textContent = label || '처리 중…';
  document.body.appendChild(root);
  return {
    setLabel(text) { root.querySelector('.progress-label').textContent = text; },
    close() { root.remove(); },
  };
}
