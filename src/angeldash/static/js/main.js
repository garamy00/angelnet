import {
  apiGet, apiPut, apiPost,
  isoWeek, weekDates, formatDateLabel,
  debounce, toast,
} from './api.js';
import { initHeader } from './header.js';
import { initOngoingSchedule } from './ongoing_schedule.js';

let currentWeek = isoWeek(new Date());
let currentData = { days: [], note: '', vacations: [], holidays: [] };

async function loadWeek() {
  const months = monthsForWeek(currentWeek);
  // 휴가/공휴일은 월별 호출. 한 주가 두 달에 걸치면 둘 다 fetch.
  const baseFetches = [
    apiGet(`/api/weeks/${currentWeek}`),
    apiGet(`/api/weeks/${currentWeek}/note`),
  ];
  const vacFetches = months.map((ym) => apiGet(`/api/vacations?year_month=${ym}`));
  const holFetches = months.map((ym) => apiGet(`/api/holidays?year_month=${ym}`));
  const results = await Promise.all([...baseFetches, ...vacFetches, ...holFetches]);
  const weekResp = results[0];
  const noteResp = results[1];
  const vacationLists = results.slice(2, 2 + vacFetches.length);
  const holidayLists = results.slice(2 + vacFetches.length);
  currentData = {
    days: weekResp.days,
    note: noteResp.body_md,
    vacations: vacationLists.flat(),
    holidays: holidayLists.flat(),
  };
  render();
}

// 그 주가 걸친 모든 달 (한 주가 두 달에 걸쳐 있을 수 있음).
function monthsForWeek(weekIso) {
  const dates = weekDates(weekIso);
  return [...new Set(dates.map((d) => d.slice(0, 7)))];
}

function render() {
  document.getElementById('week-label').textContent = currentWeek;
  updateExcelButtonLabel();
  const dates = weekDates(currentWeek);
  const byDate = Object.fromEntries(currentData.days.map((d) => [d.date, d]));
  const vacByDate = {};
  for (const v of (currentData.vacations || [])) {
    if (!vacByDate[v.date]) vacByDate[v.date] = [];
    vacByDate[v.date].push(v);
  }
  // 공휴일 한 날짜에 하나만 가정 (UpNote 응답 형식)
  const holByDate = Object.fromEntries(
    (currentData.holidays || []).map((h) => [h.date, h])
  );
  const container = document.getElementById('days');
  container.innerHTML = '';
  for (const date of dates) {
    const day = byDate[date] || { date, entries: [] };
    container.appendChild(
      renderDay(day, vacByDate[date] || [], holByDate[date] || null)
    );
  }
  document.getElementById('week-note').value = currentData.note;
}

// Excel 다운로드 버튼 라벨에 현재 주가 속한 달을 표시.
// 같은 연도이면 'M월', 다르면 'YY년 M월' (예: 12월→1월 경계).
function updateExcelButtonLabel() {
  const ym = monthsForWeek(currentWeek)[0];  // 'YYYY-MM'
  const [yStr, mStr] = ym.split('-');
  const year = parseInt(yStr, 10);
  const month = parseInt(mStr, 10);
  const thisYear = new Date().getFullYear();
  const label = year === thisYear
    ? `📥 ${month}월 타임시트 다운로드`
    : `📥 ${year % 100}년 ${month}월 타임시트 다운로드`;
  const btn = document.getElementById('btn-excel');
  if (btn) {
    btn.textContent = label;
    btn.title = `${ym} 의 회사 시스템 Excel 다운로드`;
  }
}

function renderDay(day, vacations, holiday) {
  const wrap = document.createElement('div');
  wrap.className = 'day-block';
  if (holiday) wrap.classList.add('day-block--holiday');
  wrap.dataset.date = day.date;
  // 좌측 stripe 색상 결정용 — CSS 가 [data-weekday], [data-has-vacation] 셀렉터 사용
  wrap.dataset.weekday = String(new Date(day.date + 'T00:00:00').getDay());
  wrap.dataset.hasVacation = vacations.length > 0 ? 'true' : 'false';
  // 휴가 시간은 updateDayTotals 에서 entries 합과 함께 더해 합계에 반영한다.
  const totalVacHours = vacations.reduce((a, v) => a + v.hours, 0);
  wrap.dataset.vacationHours = String(totalVacHours);

  const header = document.createElement('div');
  header.className = 'day-header';
  const vacLabel = vacations.length
    ? ` <span class="vacation-tag">🏖 휴가 ${totalVacHours}h</span>`
    : '';
  const holLabel = holiday
    ? ` <span class="holiday-tag">🎌 ${escapeHtml(holiday.label)}</span>`
    : '';
  header.innerHTML = `<span>${formatDateLabel(day.date)}${holLabel}${vacLabel}</span>`;
  const totals = document.createElement('span');
  totals.className = 'totals';
  header.appendChild(totals);
  wrap.appendChild(header);

  // 휴가는 read-only row 로 entries 위에 표시
  for (const v of vacations) {
    const row = document.createElement('div');
    row.className = 'vacation-row';
    row.innerHTML = `🏖 <strong>${escapeHtml(v.type)}</strong> ${v.hours}h <span class="muted">(회사 시스템 — 수정 불가)</span>`;
    wrap.appendChild(row);
  }

  for (const entry of day.entries) {
    wrap.appendChild(renderEntry(entry));
  }

  const addBtn = document.createElement('button');
  addBtn.textContent = '+ 카테고리 추가';
  addBtn.addEventListener('click', () => {
    wrap.insertBefore(renderEntry({ category: '', hours: 0, body_md: '' }), addBtn);
    saveDay(day.date);
  });
  wrap.appendChild(addBtn);

  // 소스 Commit 라디오 + 기타 textarea
  const metaSection = document.createElement('div');
  metaSection.className = 'day-meta';
  metaSection.innerHTML = `
    <div class="meta-radio-row">
      <strong>소스 Commit:</strong>
      <label><input type="radio" name="sc-${day.date}" value="done"> 완료</label>
      <label><input type="radio" name="sc-${day.date}" value="later"> 추후</label>
      <label><input type="radio" name="sc-${day.date}" value="local_backup"> 로컬백업</label>
      <label><input type="radio" name="sc-${day.date}" value="none"> 없음</label>
    </div>
    <div class="meta-misc-row">
      <strong>기타:</strong>
      <textarea class="meta-misc" placeholder="예: 내일 연차입니다"></textarea>
      <button class="meta-auto-btn" type="button" title="휴가 정보로 자동 채우기">🔄 자동</button>
    </div>
  `;
  wrap.appendChild(metaSection);

  // 비동기로 meta 로드 후 라디오/textarea 채우기 + autosave 핸들러
  (async () => {
    try {
      const meta = await apiGet(`/api/days/${day.date}/meta`);
      const radios = metaSection.querySelectorAll(`input[name="sc-${day.date}"]`);
      for (const r of radios) r.checked = (r.value === meta.source_commit);
      const ta = metaSection.querySelector('.meta-misc');
      ta.value = meta.misc_note || '';
      const saveMeta = async () => {
        const sel = metaSection.querySelector(`input[name="sc-${day.date}"]:checked`);
        const sourceCommit = sel ? sel.value : 'done';
        try {
          await apiPut(`/api/days/${day.date}/meta`, {
            source_commit: sourceCommit,
            misc_note: ta.value,
          });
        } catch (e) {
          toast(`meta 저장 실패: ${e.message}`, 'fail');
        }
      };
      // 라디오 변경은 즉시 저장 (사용자가 곧장 [팀장 보고 복사] 누를 수 있음)
      for (const r of radios) r.addEventListener('change', saveMeta);
      // textarea 타이핑은 debounce 로 묶어 과다 호출 방지
      ta.addEventListener('input', debounce(saveMeta, 400));

      const autoBtn = metaSection.querySelector('.meta-auto-btn');
      autoBtn.addEventListener('click', async () => {
        autoBtn.disabled = true;
        try {
          const res = await apiGet(`/api/days/${day.date}/misc-auto`);
          const text = res.text || '';
          if (!text) {
            toast('자동 채울 휴가 정보가 없습니다');
            return;
          }
          if (ta.value && !confirm(`기존 내용을 덮어쓸까요?\n\n현재: ${ta.value}\n새 내용: ${text}`)) return;
          ta.value = text;
          await saveMeta();
          toast(`자동 채움: ${text}`);
        } catch (e) {
          toast(`실패: ${e.message}`, 'fail');
        } finally {
          autoBtn.disabled = false;
        }
      });
    } catch (e) {
      console.warn('meta load failed', e);
    }
  })();

  updateDayTotals(wrap);
  return wrap;
}

function renderEntry(entry) {
  const row = document.createElement('div');
  row.className = 'entry';
  row.innerHTML = `
    <div class="entry-header">
      <input class="category" type="text" placeholder="카테고리"
             value="${escapeHtml(entry.category)}">
      <input class="hours" type="number" min="0" max="24" step="0.5"
             value="${entry.hours}">
      <span>h</span>
      <button class="remove">×</button>
    </div>
    <textarea class="entry-body" placeholder="본문 (markdown)">${escapeHtml(entry.body_md)}</textarea>
  `;
  const debounced = debounce(() => {
    const d = row.closest('.day-block')?.dataset.date;
    if (d) { saveDay(d); updateDayTotals(row.closest('.day-block')); }
  }, 600);
  for (const el of row.querySelectorAll('input, textarea')) {
    el.addEventListener('input', debounced);
  }
  row.querySelector('.remove').addEventListener('click', () => {
    const block = row.closest('.day-block');
    row.remove();
    if (block) { saveDay(block.dataset.date); updateDayTotals(block); }
  });
  return row;
}

function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// 오늘 날짜 (로컬 타임존 기준). toISOString 은 UTC 라 한국 새벽~오전에
// 전날로 떨어지는 문제를 회피하기 위해 직접 조합.
function todayLocalIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function collectEntries(block) {
  const out = [];
  for (const row of block.querySelectorAll('.entry')) {
    const category = row.querySelector('.category').value.trim();
    if (!category) continue;
    out.push({
      category,
      hours: parseFloat(row.querySelector('.hours').value || '0'),
      body_md: row.querySelector('.entry-body').value,
    });
  }
  return out;
}

function updateDayTotals(block) {
  const entryHours = collectEntries(block).reduce((a, e) => a + (e.hours || 0), 0);
  const vacHours = parseFloat(block.dataset.vacationHours || '0');
  const sum = entryHours + vacHours;
  const totals = block.querySelector('.totals');
  // 휴가가 있는 날은 출처를 명시
  totals.textContent = vacHours > 0
    ? `합계: ${sum}h (업무 ${entryHours}h + 휴가 ${vacHours}h)`
    : `합계: ${sum}h`;
  totals.classList.remove('ok', 'warn');
  if (sum === 8) totals.classList.add('ok');
  else if (sum === 0 || sum < 8) totals.classList.add('warn');
}

async function saveDay(date) {
  const block = document.querySelector(`.day-block[data-date="${date}"]`);
  if (!block) return;
  const entries = collectEntries(block);
  try {
    await apiPut(`/api/days/${date}`, { week_iso: currentWeek, entries });
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'fail');
  }
}

async function saveNote() {
  try {
    await apiPut(`/api/weeks/${currentWeek}/note`, {
      body_md: document.getElementById('week-note').value,
    });
  } catch (e) {
    toast(`메모 저장 실패: ${e.message}`, 'fail');
  }
}

document.getElementById('week-note').addEventListener(
  'input', debounce(saveNote, 800)
);

document.getElementById('this-week').addEventListener('click', () => {
  currentWeek = isoWeek(new Date());
  loadWeek();
});
document.getElementById('prev-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, -1);
  loadWeek();
});
document.getElementById('next-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, +1);
  loadWeek();
});

function shiftWeek(weekIso, delta) {
  const [yearStr, wStr] = weekIso.split('-W');
  const monday = new Date(Date.UTC(parseInt(yearStr, 10), 0, 4));
  const day = monday.getUTCDay() || 7;
  monday.setUTCDate(monday.getUTCDate() - (day - 1) + (parseInt(wStr, 10) - 1 + delta) * 7);
  return isoWeek(monday);
}

// 팀장 보고는 항상 '오늘' 만 — '대상' 드롭다운과 무관
document.getElementById('btn-report').addEventListener('click', async () => {
  try {
    const today = todayLocalIso();
    const r = await apiPost('/api/actions/team-report', { date: today });
    await navigator.clipboard.writeText(r.text);
    toast(`팀장 보고 (${today}) 가 클립보드에 복사되었습니다`);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

document.getElementById('btn-upnote').addEventListener('click', async () => {
  try {
    if (!confirm(`이번 주(${currentWeek}) UpNote 노트를 생성합니다. 같은 주의 기존 노트는 자동 삭제되지 않습니다. 계속하시겠습니까?`)) return;
    await apiPost('/api/actions/upnote-sync', { week_iso: currentWeek });
    toast('UpNote 에 노트가 생성되었습니다');
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

// btn-verify 버튼과 btn-timesheet 입력 후 자동 호출에서 공용으로 쓰는 verify 핵심 로직.
async function runTimesheetVerify() {
  const data = await apiGet(`/api/timesheet/verify?week_iso=${currentWeek}`);
  applyVerifyResult(data.items);
}

document.getElementById('btn-verify').addEventListener('click', async () => {
  try {
    await runTimesheetVerify();
    toast('타임시트 확인 완료');
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

function applyVerifyResult(items) {
  const byKey = {};
  for (const it of items) byKey[`${it.date}|${it.category}`] = it;

  for (const row of document.querySelectorAll('.entry')) {
    const cat = row.querySelector('.category').value.trim();
    const date = row.closest('.day-block')?.dataset.date;
    if (!cat || !date) continue;
    const info = byKey[`${date}|${cat}`];
    let badge = row.querySelector('.sync-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'sync-badge';
      row.querySelector('.entry-header').appendChild(badge);
    }
    if (!info) {
      badge.textContent = '';
      badge.removeAttribute('title');
      badge.className = 'sync-badge';
      continue;
    }
    badge.className = `sync-badge sync-${info.sync_status}`;
    // local_task_total: 같은 (date, task) 의 도구 entries 합. 회사 시스템과 합 단위로 비교.
    const localTotal = info.local_task_total ?? info.hours;
    const task = info.task_name || '';
    switch (info.sync_status) {
      case 'synced':
        badge.textContent = '✅';
        badge.title = `${task} ${localTotal}h 일치`;
        break;
      case 'not_submitted':
        badge.textContent = `⏳ 미제출 (task 합 ${localTotal}h)`;
        badge.title = `${task} — 회사 시스템에 아직 안 올라감`;
        break;
      case 'remote_only':
        badge.textContent = `⚠️ 회사=${info.remote_hours}h (도구=0h)`;
        badge.title = `${task} — 회사 시스템에 시간 있음`;
        break;
      case 'mismatch':
        badge.textContent = `⚠️ task 합 ${localTotal}h vs 회사=${info.remote_hours}h`;
        badge.title = `${task} — 도구와 회사 시스템의 시간이 다름. 같은 task 로 매핑된 모든 카테고리 합산 기준.`;
        break;
      case 'excluded':
        badge.textContent = '— (제외)';
        badge.title = '의도적으로 타임시트 미입력';
        break;
      case 'no_mapping':
      case 'no_remote_id':
        badge.textContent = '— (매핑 없음)';
        break;
    }

    // 기존 push 버튼 제거 (재호출 대비)
    const existingBtn = row.querySelector('.sync-push-btn');
    if (existingBtn) existingBtn.remove();

    // not_submitted / mismatch / remote_only 일 때 push 버튼 추가
    if (['not_submitted', 'mismatch', 'remote_only'].includes(info.sync_status)
        && info.task_name && info.local_task_total != null) {
      const pushBtn = document.createElement('button');
      pushBtn.textContent = '푸시';
      pushBtn.className = 'sync-push-btn';
      pushBtn.title = `[${info.task_name}] ${info.date} 의 도구 합 ${info.local_task_total}h 를 회사에 overwrite`;
      pushBtn.addEventListener('click', async () => {
        if (!confirm(`회사 시스템에 [${info.task_name}] ${info.date} = ${info.local_task_total}h 로 덮어쓰기 할까요?`)) return;
        pushBtn.disabled = true;
        try {
          await apiPost('/api/actions/timesheet-push-one', {
            date: info.date,
            task_name: info.task_name,
            task_work_type: info.task_work_type || '',
            hours: info.local_task_total,
          });
          toast('회사 시스템에 푸시됨');
        } catch (e) {
          pushBtn.disabled = false;
          toast(`실패: ${e.message}`, 'fail');
        }
      });
      row.querySelector('.entry-header').appendChild(pushBtn);
    }
  }

  // orphan: 회사 시스템에만 있는 항목을 day-block 에 추가 표시
  // 기존 orphan 행들 먼저 제거 (재호출 대비)
  document.querySelectorAll('.orphan-row').forEach((r) => r.remove());
  for (const it of items) {
    if (it.sync_status !== 'orphan') continue;
    const block = document.querySelector(`.day-block[data-date="${it.date}"]`);
    if (!block) continue;
    const row = document.createElement('div');
    row.className = 'orphan-row';
    const wt = (it.task_work_type || '').trim();
    const wtTag = wt
      ? ` <span class="work-type-tag">[${escapeHtml(wt)}]</span>`
      : '';
    const fullLabel = wt ? `${it.task_name} [${wt}]` : it.task_name;
    row.innerHTML = `
      <span class="muted">⚠️ 회사 시스템에만 있음:</span>
      <strong>${escapeHtml(it.task_name)}</strong>${wtTag} ${it.remote_hours}h
    `;
    const delBtn = document.createElement('button');
    delBtn.textContent = '회사에서 삭제';
    delBtn.className = 'orphan-delete';
    delBtn.addEventListener('click', async () => {
      if (!confirm(`회사 시스템에서 [${fullLabel}] ${it.date} ${it.remote_hours}h 를 삭제할까요? (hours=0 으로 update)`)) return;
      delBtn.disabled = true;
      try {
        await apiPost('/api/actions/timesheet-push-one', {
          date: it.date,
          task_name: it.task_name,
          task_work_type: it.task_work_type || '',
          hours: 0,
        });
        toast('회사 시스템에서 삭제됨');
        row.remove();
      } catch (e) {
        delBtn.disabled = false;
        toast(`실패: ${e.message}`, 'fail');
      }
    });
    row.appendChild(delBtn);
    block.appendChild(row);
  }
}

document.getElementById('btn-timesheet').addEventListener('click', async () => {
  const target = document.getElementById('target').value;
  const body = target === 'today'
    ? { date: todayLocalIso(), dry_run: true }
    : { week_iso: currentWeek, dry_run: true };
  try {
    const preview = await apiPost('/api/actions/timesheet-submit', body);
    const summary = preview.items.map(
      (it) => `${it.date} [${it.status}] ${it.category} ${it.hours}h`
        + (it.project_name ? ` → ${it.project_name}` : '')
        + (it.task_name ? ` (task: ${it.task_name})` : ''),
    ).join('\n');
    if (preview.missing && preview.missing.length) {
      toast(`매핑 누락: ${preview.missing.join(', ')}`, 'fail');
      console.warn('preview:', preview);
      return;
    }
    if (!confirm(`다음 항목을 타임시트에 입력합니다:\n\n${summary}\n\n계속?`)) return;
    const real = await apiPost('/api/actions/timesheet-submit',
      { ...body, dry_run: false });
    toast(`타임시트 입력 완료 (${(real.results || []).length}건)`);
    // 입력 직후 회사 시스템과의 정합성을 즉시 badge 로 표시 (조용히 실행)
    try {
      await runTimesheetVerify();
    } catch (e) {
      toast(`자동 확인 실패: ${e.message}`, 'fail');
    }
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

document.getElementById('btn-excel').addEventListener('click', async () => {
  // 현재 주가 걸친 첫 달을 기준 (W18 = 4/27~5/1 같이 걸치면 4월 먼저)
  const months = monthsForWeek(currentWeek);
  const ym = months[0];
  try {
    const r = await fetch(`/api/timesheet/excel?year_month=${ym}`);
    if (!r.ok) {
      const text = await r.text();
      toast(`실패: ${r.status} ${text.slice(0, 200)}`, 'fail');
      return;
    }
    const blob = await r.blob();
    // 서버가 보낸 filename 추출
    const cd = r.headers.get('content-disposition') || '';
    let filename = `jobtime_${ym}.xlsx`;
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (m) filename = decodeURIComponent(m[1]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(`다운로드 완료: ${filename}`);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

// ─── 이번달 타임시트 미리보기 모달 ──────────────────

const KR_DAY_SHORT = ['일', '월', '화', '수', '목', '금', '토'];

function openMonthlyModal() {
  document.getElementById('monthly-modal').hidden = false;
}
function closeMonthlyModal() {
  document.getElementById('monthly-modal').hidden = true;
}
document.getElementById('monthly-modal-close').addEventListener('click', closeMonthlyModal);
document.querySelector('#monthly-modal .modal-backdrop').addEventListener('click', closeMonthlyModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.getElementById('monthly-modal').hidden) {
    closeMonthlyModal();
  }
});

function renderMonthlyGrid(data) {
  const body = document.getElementById('monthly-modal-body');
  document.getElementById('monthly-modal-title').textContent =
    `📊 ${data.year_month} 타임시트 (회사 시스템)`;

  const hasTasks = data.tasks && data.tasks.length > 0;
  const hasVacs = data.vacations && data.vacations.length > 0;
  if (!hasTasks && !hasVacs) {
    body.innerHTML = '<p class="muted">이번달 입력된 task / 휴가가 없습니다.</p>';
    return;
  }

  const [yStr, mStr] = data.year_month.split('-');
  const year = parseInt(yStr, 10);
  const month = parseInt(mStr, 10);
  const dim = data.days_in_month;

  const dayOfWeek = (d) => {
    const dt = new Date(Date.UTC(year, month - 1, d));
    return dt.getUTCDay();
  };

  // 공휴일 day 집합 (출근일 label 제외된 것만 서버가 보내줌)
  const holidayDays = new Map();  // day → label
  for (const h of (data.holidays || [])) {
    holidayDays.set(h.day, h.label);
  }

  const escMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };
  const esc = (s) => String(s || '').replace(/[&<>]/g, (c) => escMap[c]);

  // 일자 헤더의 클래스 — 휴일/주말 색칠 + 셀에도 동일 적용
  const dayClass = (d) => {
    const dow = dayOfWeek(d);
    if (holidayDays.has(d)) return 'hol';
    if (dow === 0) return 'sun';
    if (dow === 6) return 'sat';
    return '';
  };
  const dayLabel = (d) => {
    const dow = dayOfWeek(d);
    return KR_DAY_SHORT[dow];
  };

  // 히트맵 단계 — hours / 8 비율을 alpha 로. 8h+ 는 한 단계 더 진하게.
  // 0=투명, 1=옅음, 2=중간, 3=진함, 4=가장 진함 (overtime)
  const heatLevel = (h) => {
    if (!h || h <= 0) return 0;
    if (h <= 2) return 1;
    if (h <= 4) return 2;
    if (h <= 7) return 3;
    if (h <= 8) return 4;
    return 5;  // overtime
  };

  const cellClasses = (h, d, kind = 'task') => {
    const dow = dayOfWeek(d);
    const bg = holidayDays.has(d)
      ? 'bg-hol'
      : ((dow === 0 || dow === 6) ? 'bg-wknd' : '');
    const lvl = heatLevel(h);
    const prefix = kind === 'vac' ? 'vac-l' : 'task-l';
    return `cell ${bg} ${prefix}${lvl}`;
  };

  // 헤더
  let thead = '<thead><tr><th class="task-col">프로젝트(task)</th>';
  for (let d = 1; d <= dim; d += 1) {
    const cls = dayClass(d);
    const title = holidayDays.has(d) ? ` title="${esc(holidayDays.get(d))}"` : '';
    thead += `<th class="day-col ${cls}"${title}>${d}<br><small>${dayLabel(d)}</small></th>`;
  }
  thead += '<th class="total-col">합계</th></tr></thead>';

  // 셀 tooltip — hours + day 정보
  const cellTitle = (h, d) => {
    if (!h) return '';
    return ` title="${d}일: ${h}h"`;
  };

  // 본문 — task rows
  let tbody = '<tbody>';
  for (const t of data.tasks) {
    tbody += '<tr>';
    tbody += `<td class="task-col" title="${esc(t.task_name)}">${esc(t.task_name)}</td>`;
    for (let d = 1; d <= dim; d += 1) {
      const h = t.days[d] || 0;
      tbody += `<td class="${cellClasses(h, d, 'task')}"${cellTitle(h, d)}>${h || ''}</td>`;
    }
    tbody += `<td class="total-col"><b>${t.total}</b></td>`;
    tbody += '</tr>';
  }

  // 휴가 rows (있을 때만, 별도 그룹으로 시각 구분)
  if (hasVacs) {
    for (let i = 0; i < data.vacations.length; i += 1) {
      const v = data.vacations[i];
      const groupCls = i === 0 ? ' vac-row vac-first' : ' vac-row';
      tbody += `<tr class="${groupCls.trim()}">`;
      tbody += `<td class="task-col vac-label" title="휴가 — ${esc(v.label)}">🏖 휴가 — ${esc(v.label)}</td>`;
      for (let d = 1; d <= dim; d += 1) {
        const h = v.days[d] || 0;
        tbody += `<td class="${cellClasses(h, d, 'vac')}"${cellTitle(h, d)}>${h || ''}</td>`;
      }
      tbody += `<td class="total-col"><b>${v.total}</b></td>`;
      tbody += '</tr>';
    }
  }
  tbody += '</tbody>';

  // 합계 행
  let tfoot = '<tfoot><tr><td class="task-col"><b>일별 합계</b></td>';
  for (let d = 1; d <= dim; d += 1) {
    const h = data.daily_totals[d] || 0;
    tfoot += `<td class="${cellClasses(h, d, 'task')}"${cellTitle(h, d)}><b>${h || ''}</b></td>`;
  }
  tfoot += `<td class="total-col"><b>${data.month_total}</b></td>`;
  tfoot += '</tr></tfoot>';

  body.innerHTML = `<table class="monthly-grid">${thead}${tbody}${tfoot}</table>`;
}

document.getElementById('btn-monthly-preview').addEventListener('click', async () => {
  const ym = monthsForWeek(currentWeek)[0];  // 현재 주가 속한 월
  document.getElementById('monthly-modal-title').textContent =
    `📊 ${ym} 타임시트 (회사 시스템) — 로딩…`;
  document.getElementById('monthly-modal-body').innerHTML =
    '<p class="muted">회사 시스템에서 fetch 중… (몇 초 소요)</p>';
  openMonthlyModal();
  try {
    const data = await apiGet(`/api/timesheet/monthly-grid?year_month=${ym}`);
    renderMonthlyGrid(data);
  } catch (e) {
    document.getElementById('monthly-modal-body').innerHTML =
      `<p class="muted">실패: ${e.message}</p>`;
    toast(`미리보기 실패: ${e.message}`, 'fail');
  }
});

(async () => {
  await loadWeek();
})();

initHeader();
initOngoingSchedule();
