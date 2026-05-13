import { apiGet, toast } from './api.js';

function escapeHtml(s) {
  return String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

// 연도 select 채우기 (현재 ±5년).
const sel = document.getElementById('year-select');
const thisYear = new Date().getFullYear();
for (let y = thisYear + 1; y >= thisYear - 5; y--) {
  const opt = document.createElement('option');
  opt.value = String(y);
  opt.textContent = `${y}년`;
  if (y === thisYear) opt.selected = true;
  sel.appendChild(opt);
}

async function loadAnnual(year) {
  const box = document.getElementById('annual-summary');
  box.textContent = '로딩…';
  try {
    const r = await apiGet(`/api/vacation/annual?year=${year}`);
    if (r.total == null) {
      box.textContent = r.raw_text || '데이터 없음';
    } else {
      // 시각적 강조: 잔여일을 큰 글자로
      box.innerHTML = `
        <span class="vac-metric"><strong>${r.total}</strong> 일 부여</span>
        <span class="vac-sep">·</span>
        <span class="vac-metric"><strong>${r.used}</strong> 일 사용</span>
        <span class="vac-sep">·</span>
        <span class="vac-metric vac-remaining">잔여 <strong>${r.remaining}</strong> 일</span>
      `;
    }
  } catch (e) {
    box.innerHTML = `<span class="muted">불러오기 실패: ${escapeHtml(e.message)}</span>`;
    toast(`연간 요약 실패: ${e.message}`, 'fail');
  }
}

async function loadList(year) {
  const tbody = document.querySelector('#vac-list tbody');
  const summary = document.getElementById('vac-summary');
  tbody.innerHTML = '<tr><td colspan="6" class="muted">로딩…</td></tr>';
  summary.textContent = '';
  try {
    const items = await apiGet(`/api/vacation/applications?year=${year}`);
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">조회 결과 없음</td></tr>';
      summary.textContent = '';
      return;
    }
    // 기간(시작일) 기준 내림차순 정렬
    items.sort((a, b) => (b.from_date || '').localeCompare(a.from_date || ''));
    tbody.innerHTML = items.map((it) => {
      const period = it.from_date === it.to_date
        ? escapeHtml(it.from_date)
        : `${escapeHtml(it.from_date)} ~ ${escapeHtml(it.to_date)}`;
      return `
        <tr>
          <td>${escapeHtml(it.draft_date)}</td>
          <td>${escapeHtml(it.vacation_type)}</td>
          <td>${escapeHtml(it.reason)}</td>
          <td>${period}</td>
          <td>${escapeHtml(it.days)}</td>
          <td>${escapeHtml(it.status)}</td>
        </tr>
      `;
    }).join('');
    summary.textContent = `총 ${items.length}건`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted">불러오기 실패: ${escapeHtml(e.message)}</td></tr>`;
    toast(`목록 조회 실패: ${e.message}`, 'fail');
  }
}

async function refresh() {
  const y = sel.value;
  await Promise.all([loadAnnual(y), loadList(y)]);
}

sel.addEventListener('change', refresh);
document.getElementById('refresh').addEventListener('click', refresh);

refresh();
