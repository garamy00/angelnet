import { apiGet, apiPut, apiPost, isoWeek, weekDates, toast } from './api.js';

const COL_KEYS = ['last_week', 'this_week', 'next_week', 'note'];
const COL_HEADERS = ['프로젝트', '지난주 한 일', '이번주 한 일/할 일', '다음주 할 일', '비고'];

let currentWeek = new URLSearchParams(location.search).get('week') || isoWeek(new Date());
let currentRows = [];

function shiftWeek(weekIso, delta) {
  // weekDates(weekIso)[0] = 월요일 'YYYY-MM-DD'
  const monday = new Date(weekDates(weekIso)[0] + 'T00:00:00');
  monday.setDate(monday.getDate() + delta * 7);
  return isoWeek(monday);
}

function setWeekLabel() {
  const dates = weekDates(currentWeek);
  const start = dates[0].slice(5); // MM-DD
  const end = dates[6].slice(5);
  document.getElementById('week-label').textContent =
    `${currentWeek} (${start} ~ ${end})`;
}

async function loadWeek() {
  setWeekLabel();
  try {
    const data = await apiGet(`/api/weekly-reports/${currentWeek}`);
    currentRows = data.rows || [];
    renderRows();
  } catch (e) {
    toast(`로드 실패: ${e.message}`, 'fail');
  }
}

function renderRows() {
  const tbody = document.getElementById('weekly-rows');
  const empty = document.getElementById('weekly-empty');
  const wrap = document.getElementById('weekly-table-wrap');
  tbody.innerHTML = '';
  if (currentRows.length === 0) {
    wrap.hidden = true;
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  wrap.hidden = false;
  for (let i = 0; i < currentRows.length; i += 1) {
    tbody.appendChild(renderRow(i));
  }
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = (ta.scrollHeight + 2) + 'px';
}

function renderRow(idx) {
  const row = currentRows[idx];
  const tr = document.createElement('tr');

  // 프로젝트명 input
  const tdName = document.createElement('td');
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'cell-project';
  nameInput.value = row.project_name || '';
  nameInput.addEventListener('blur', () => {
    currentRows[idx].project_name = nameInput.value;
    saveAll();
  });
  tdName.appendChild(nameInput);
  tr.appendChild(tdName);

  // 4개 텍스트 셀
  for (const key of COL_KEYS) {
    const td = document.createElement('td');
    const ta = document.createElement('textarea');
    ta.className = 'cell-text';
    ta.value = row[key] || '';
    ta.rows = 3;
    ta.addEventListener('input', () => autoResize(ta));
    ta.addEventListener('blur', () => {
      currentRows[idx][key] = ta.value;
      saveAll();
    });
    td.appendChild(ta);
    tr.appendChild(td);
    queueMicrotask(() => autoResize(ta));
  }

  // 삭제 버튼
  const tdDel = document.createElement('td');
  const delBtn = document.createElement('button');
  delBtn.className = 'row-del';
  delBtn.textContent = '🗑';
  delBtn.title = '이 행 삭제';
  delBtn.addEventListener('click', async () => {
    if (!confirm(`'${currentRows[idx].project_name || '(이름 없음)'}' 행을 삭제할까요?`)) return;
    currentRows.splice(idx, 1);
    await saveAll();
    renderRows();
  });
  tdDel.appendChild(delBtn);
  tr.appendChild(tdDel);

  return tr;
}

async function saveAll() {
  try {
    await apiPut(`/api/weekly-reports/${currentWeek}`,
      { rows: currentRows });
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'fail');
  }
}

// ─── 액션 핸들러 ──────────────────────────────────

document.getElementById('btn-generate-initial').addEventListener('click', async () => {
  try {
    const r = await apiPost(
      `/api/weekly-reports/${currentWeek}/generate`,
      { preserve_manual: true },
    );
    currentRows = r.rows || [];
    renderRows();
    if (currentRows.length === 0) {
      toast('이 주에는 daily entries 가 없습니다');
    } else {
      toast(`보고서 생성됨 (${currentRows.length} 행)`);
    }
  } catch (e) {
    toast(`생성 실패: ${e.message}`, 'fail');
  }
});

document.getElementById('btn-regenerate').addEventListener('click', async () => {
  if (!confirm('지난주 한 일 / 이번주 한 일/할 일 셀을 daily entries 로 다시 채웁니다. (다음주/비고는 보존). 계속?')) {
    return;
  }
  try {
    const r = await apiPost(
      `/api/weekly-reports/${currentWeek}/generate`,
      { preserve_manual: true },
    );
    currentRows = r.rows || [];
    renderRows();
    toast('재생성됨');
  } catch (e) {
    toast(`재생성 실패: ${e.message}`, 'fail');
  }
});

document.getElementById('btn-add-row').addEventListener('click', async () => {
  currentRows.push({
    project_name: '', last_week: '', this_week: '', next_week: '', note: '',
  });
  await saveAll();
  renderRows();
  const lastTr = document.getElementById('weekly-rows').lastElementChild;
  if (lastTr) lastTr.querySelector('.cell-project').focus();
});

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

// ─── HTML 표 복사 ────────────────────────────────

function buildHtmlTable(rows) {
  const escMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };
  const esc = (s) => (s || '').replace(/[&<>]/g, (c) => escMap[c]);
  const thStyle = 'border:1px solid #888; padding:6px;';
  const tdProj = 'border:1px solid #888; padding:6px; vertical-align:top;';
  const tdBody = (
    "border:1px solid #888; padding:6px; vertical-align:top; "
    + "white-space:pre-wrap; font-family: 'SF Mono', Menlo, Consolas, monospace; "
    + "font-size:12px;"
  );
  const headRow = COL_HEADERS.map((h) => `<th style="${thStyle}">${esc(h)}</th>`).join('');
  const bodyRows = rows.map((r) => {
    const cells = [
      `<td style="${tdProj}"><b>${esc(r.project_name)}</b></td>`,
    ];
    for (const key of COL_KEYS) {
      cells.push(`<td style="${tdBody}">${esc(r[key])}</td>`);
    }
    return `<tr>${cells.join('')}</tr>`;
  }).join('');
  return (
    '<table cellpadding="6" cellspacing="0" '
    + 'style="border-collapse:collapse; '
    + "font-family: '맑은 고딕', sans-serif; font-size:13px;\">"
    + `<thead><tr style="background:#e8e8e8;">${headRow}</tr></thead>`
    + `<tbody>${bodyRows}</tbody>`
    + '</table>'
  );
}

function buildMarkdownTable(rows) {
  const cell = (s) => (s || '').replace(/\|/g, '\\|').replace(/\n/g, '<br>');
  const lines = [];
  lines.push('| ' + COL_HEADERS.join(' | ') + ' |');
  lines.push('| ' + COL_HEADERS.map(() => '---').join(' | ') + ' |');
  for (const r of rows) {
    const cells = [r.project_name, r.last_week, r.this_week, r.next_week, r.note];
    lines.push('| ' + cells.map(cell).join(' | ') + ' |');
  }
  return lines.join('\n');
}

document.getElementById('btn-copy-html').addEventListener('click', async () => {
  if (currentRows.length === 0) {
    toast('복사할 보고서가 없습니다');
    return;
  }
  const html = buildHtmlTable(currentRows);
  const plain = buildMarkdownTable(currentRows);
  try {
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([plain], { type: 'text/plain' }),
      }),
    ]);
    toast('주간업무보고 HTML 표 복사됨');
  } catch (e) {
    try {
      await navigator.clipboard.writeText(plain);
      toast('HTML 미지원 — 마크다운 표만 복사됨');
    } catch (err) {
      toast(`복사 실패: ${err.message}`, 'fail');
    }
  }
});

// ─── UpNote 저장 ─────────────────────────────────

document.getElementById('btn-upnote-weekly').addEventListener('click', async () => {
  if (currentRows.length === 0) {
    toast('보고서가 비어있습니다');
    return;
  }
  try {
    await apiPost('/api/actions/weekly-report-upnote',
      { week_iso: currentWeek });
    toast('UpNote 에 노트가 생성되었습니다');
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

// ─── 초기 로드 ───────────────────────────────────

loadWeek();
