import { apiGet, apiPut, apiPost, isoWeek, weekDates, toast } from './api.js';
import { initOngoingSchedule } from './ongoing_schedule.js';

const COL_KEYS = ['last_week', 'this_week', 'next_week', 'note'];
const COL_HEADERS = ['프로젝트', '지난주 한 일', '이번주 한 일/할 일', '다음주 할 일', '비고'];
// 자동 생성되는 휴가 행. 사용자가 직접 옮기거나 영구 삭제할 수 없게 ▲▼/🗑 숨김.
// 프로젝트 컬럼 표시는 '기타' (셀 본문 prefix 는 '*) 휴가' 로 별개).
const VACATION_PROJECT_NAME = '기타';

function isVacationRow(row) {
  return !!row && row.project_name === VACATION_PROJECT_NAME;
}

let currentWeek = new URLSearchParams(location.search).get('week') || isoWeek(new Date());
let currentRows = [];
// 설정 캐시 — 이메일/UpNote 액션 시 사용
const cachedSettings = {
  weeklyNotebookId: '',
  emailTo: '',
  emailCc: '',
  emailSubjectTemplate: '',
  emailGreeting: '',
  emailClosing: '',
};

async function loadCachedSettings() {
  try {
    const s = await apiGet('/api/settings');
    cachedSettings.weeklyNotebookId = (s['upnote.weekly_notebook_id'] || '').trim();
    cachedSettings.emailTo = (s['email.to'] || '').trim();
    cachedSettings.emailCc = (s['email.cc'] || '').trim();
    cachedSettings.emailSubjectTemplate = s['email.subject_template'] || '';
    cachedSettings.emailGreeting = s['email.greeting'] || '';
    cachedSettings.emailClosing = s['email.closing'] || '';
  } catch (e) {
    // 설정 로드 실패 — 캐시는 빈 채로 유지. 액션 시 toast 로 안내.
  }
}

function shiftWeek(weekIso, delta) {
  // weekDates(weekIso)[0] = 월요일 'YYYY-MM-DD'
  const monday = new Date(weekDates(weekIso)[0] + 'T00:00:00');
  monday.setDate(monday.getDate() + delta * 7);
  return isoWeek(monday);
}

function setWeekLabel() {
  // daily report 와 동일한 표기 — 'YYYY-Www'
  document.getElementById('week-label').textContent = currentWeek;
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
  // 휴가 행이 있으면 일반 행의 마지막 idx 가 그 직전. ▼ 가 휴가 행을 넘어가지 않도록.
  const vacIdx = currentRows.findIndex(isVacationRow);
  const normalMaxIdx = vacIdx === -1 ? currentRows.length - 1 : vacIdx - 1;
  for (let i = 0; i < currentRows.length; i += 1) {
    tbody.appendChild(renderRow(i, normalMaxIdx));
  }
}

async function moveRow(idx, delta) {
  // 일반 행끼리만 swap. 휴가 행과 자리바꿈 금지.
  const target = idx + delta;
  if (target < 0 || target >= currentRows.length) return;
  if (isVacationRow(currentRows[target])) return;
  const [item] = currentRows.splice(idx, 1);
  currentRows.splice(target, 0, item);
  await saveAll();
  renderRows();
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = (ta.scrollHeight + 2) + 'px';
}

function renderRow(idx, normalMaxIdx) {
  const row = currentRows[idx];
  const isVac = isVacationRow(row);
  const tr = document.createElement('tr');
  if (isVac) tr.classList.add('row-vacation');

  // 프로젝트명 input — 휴가 행은 readonly (자동 관리)
  const tdName = document.createElement('td');
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'cell-project';
  nameInput.value = row.project_name || '';
  if (isVac) {
    nameInput.readOnly = true;
    nameInput.title = '휴가 행은 자동 관리됩니다';
  } else {
    nameInput.addEventListener('blur', () => {
      currentRows[idx].project_name = nameInput.value;
      saveAll();
    });
  }
  tdName.appendChild(nameInput);
  tr.appendChild(tdName);

  // 4개 텍스트 셀 (편집은 일반/휴가 행 모두 가능 — 휴가 행은 다음 재생성 때 덮어쓰기)
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

  // 액션 td: 휴가 행은 '자동' 라벨, 일반 행은 ▲ ▼ 🗑
  const tdActions = document.createElement('td');
  tdActions.className = 'row-actions';
  if (isVac) {
    const lock = document.createElement('span');
    lock.className = 'muted';
    lock.textContent = '자동';
    lock.title = '휴가 행은 재생성마다 자동 갱신됩니다';
    tdActions.appendChild(lock);
  } else {
    const upBtn = document.createElement('button');
    upBtn.className = 'row-move';
    upBtn.textContent = '▲';
    upBtn.title = '위로';
    upBtn.disabled = idx === 0;
    upBtn.addEventListener('click', () => moveRow(idx, -1));

    const dnBtn = document.createElement('button');
    dnBtn.className = 'row-move';
    dnBtn.textContent = '▼';
    dnBtn.title = '아래로';
    dnBtn.disabled = idx >= normalMaxIdx;
    dnBtn.addEventListener('click', () => moveRow(idx, +1));

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

    tdActions.append(upBtn, dnBtn, delBtn);
  }
  tr.appendChild(tdActions);

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

function syncUrlToCurrentWeek() {
  // 사용자가 현재 주차를 북마크할 수 있도록 URL ?week= 갱신
  const url = new URL(location.href);
  url.searchParams.set('week', currentWeek);
  history.replaceState(null, '', url.toString());
}

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
  syncUrlToCurrentWeek();
  loadWeek();
});
document.getElementById('prev-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, -1);
  syncUrlToCurrentWeek();
  loadWeek();
});
document.getElementById('next-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, +1);
  syncUrlToCurrentWeek();
  loadWeek();
});

// ─── 본문 빌더 (HTML / 마크다운 / 이메일 전체) ────

const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };
const esc = (s) => (s || '').replace(/[&<>]/g, (c) => ESC_MAP[c]);

// 셀 안의 줄바꿈/들여쓰기 보존 — Outlook 일부 버전이 white-space:pre-wrap 을
// 무시하므로 \n → <br>, 줄 시작 spaces → &nbsp; 로 명시적 변환.
// 추가: '*) ' 로 시작하는 카테고리 헤더 라인은 <strong> 으로 강조.
function escPreserveWhitespace(s) {
  if (!s) return '';
  return s.split('\n').map((line) => {
    const stripped = line.replace(/^ +/, '');
    const indent = line.length - stripped.length;
    let escaped = esc(stripped);
    if (stripped.startsWith('*)')) escaped = `<strong>${escaped}</strong>`;
    return '&nbsp;'.repeat(indent) + escaped;
  }).join('<br>');
}

function buildHtmlTable(rows) {
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
      cells.push(`<td style="${tdBody}">${escPreserveWhitespace(r[key])}</td>`);
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
  // '*) ' 로 시작하는 카테고리 헤더 라인을 markdown `**\*)...**` 로 감쌈.
  // `*` 를 escape 해서 `**` + `*` 충돌 방지.
  const boldHeader = (line) => {
    const stripped = line.replace(/^ +/, '');
    if (!stripped.startsWith('*)')) return line;
    const indent = line.slice(0, line.length - stripped.length);
    const body = '\\*' + stripped.slice(1);
    return `${indent}**${body}**`;
  };
  const cell = (s) => {
    if (!s) return '';
    return s.split('\n')
      .map(boldHeader)
      .map((ln) => ln.replace(/\|/g, '\\|'))
      .join('<br>');
  };
  const lines = [];
  lines.push('| ' + COL_HEADERS.join(' | ') + ' |');
  lines.push('| ' + COL_HEADERS.map(() => '---').join(' | ') + ' |');
  for (const r of rows) {
    const cells = [r.project_name, r.last_week, r.this_week, r.next_week, r.note];
    lines.push('| ' + cells.map(cell).join(' | ') + ' |');
  }
  return lines.join('\n');
}

// ─── 이메일 본문 빌더 (client-side 미리보기용) ─────
// 서버 발송 시는 서버가 weekly_table.render_email_* 로 동일 형식을 빌드.

function plainToHtmlParagraphs(text) {
  if (!text) return '';
  return text.split('\n\n')
    .filter((p) => p.trim())
    .map((p) => '<p>' + esc(p).replace(/\n/g, '<br>') + '</p>')
    .join('');
}

function buildEmailHtml(rows, greeting, closing, signatureHtml) {
  const parts = [];
  parts.push("<div style=\"font-family: '맑은 고딕', sans-serif; font-size:13px;\">");
  if (greeting) parts.push(plainToHtmlParagraphs(greeting));
  parts.push(buildHtmlTable(rows));
  if (closing) parts.push(plainToHtmlParagraphs(closing));
  if (signatureHtml && signatureHtml.trim()) {
    parts.push('<br>' + signatureHtml);
  }
  parts.push('</div>');
  return parts.join('');
}

function buildEmailPlain(rows, greeting, closing) {
  const chunks = [];
  if (greeting) chunks.push(greeting.replace(/\s+$/, ''));
  chunks.push(buildMarkdownTable(rows));
  if (closing) chunks.push(closing.replace(/\s+$/, ''));
  return chunks.join('\n\n');
}

// ─── 미리보기 모달 ───────────────────────────────

function openPreviewModal({ title, htmlForPreview, htmlForCopy, plainForCopy }) {
  const modal = document.getElementById('preview-modal');
  document.getElementById('preview-modal-title').textContent = title;
  // 미리보기 영역에는 결과 HTML 을 그대로 렌더 (sandbox 효과를 위해 iframe 사용 권장)
  // 단순화를 위해 직접 innerHTML — 본문은 사용자 본인이 작성한 것이라 XSS 위험 낮음.
  document.getElementById('preview-modal-body').innerHTML = htmlForPreview;
  const copyBtn = document.getElementById('preview-modal-copy');
  // 이전 핸들러 제거를 위해 cloneNode 트릭
  const newCopy = copyBtn.cloneNode(true);
  copyBtn.parentNode.replaceChild(newCopy, copyBtn);
  newCopy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([htmlForCopy], { type: 'text/html' }),
          'text/plain': new Blob([plainForCopy], { type: 'text/plain' }),
        }),
      ]);
      toast('클립보드에 복사됨');
    } catch (e) {
      try {
        await navigator.clipboard.writeText(plainForCopy);
        toast('HTML 미지원 — plain 만 복사됨');
      } catch (err) {
        toast(`복사 실패: ${err.message}`, 'fail');
      }
    }
  });
  modal.hidden = false;
}

function closePreviewModal() {
  document.getElementById('preview-modal').hidden = true;
}

document.getElementById('preview-modal-close').addEventListener('click', closePreviewModal);
document.querySelector('#preview-modal .modal-backdrop').addEventListener('click', closePreviewModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.getElementById('preview-modal').hidden) {
    closePreviewModal();
  }
});

// ─── 미리보기 핸들러 ─────────────────────────────

document.getElementById('btn-preview-email').addEventListener('click', () => {
  if (currentRows.length === 0) { toast('미리보기 할 보고서가 없습니다'); return; }
  const html = buildEmailHtml(
    currentRows,
    cachedSettings.emailGreeting,
    cachedSettings.emailClosing,
    '',  // 미리보기 영역은 서명 raw HTML 을 그대로 보여주지 않음 (이미지 등 깨질 수 있어)
  );
  // 복사용에는 서명 포함
  const htmlForCopy = buildEmailHtml(
    currentRows,
    cachedSettings.emailGreeting,
    cachedSettings.emailClosing,
    '',
  );
  const plainForCopy = buildEmailPlain(
    currentRows,
    cachedSettings.emailGreeting,
    cachedSettings.emailClosing,
  );
  openPreviewModal({
    title: '📧 이메일 미리보기',
    htmlForPreview: html,
    htmlForCopy,
    plainForCopy,
  });
});

document.getElementById('btn-preview-upnote').addEventListener('click', () => {
  if (currentRows.length === 0) { toast('미리보기 할 보고서가 없습니다'); return; }
  const html = buildHtmlTable(currentRows);
  const md = buildMarkdownTable(currentRows);
  openPreviewModal({
    title: '📝 UpNote 미리보기 (표만 저장)',
    htmlForPreview: html,
    htmlForCopy: html,
    plainForCopy: md,
  });
});

// ─── 이메일 보내기 (서버 SMTP) ──────────────────

document.getElementById('btn-send-email').addEventListener('click', async () => {
  if (currentRows.length === 0) { toast('발송할 보고서가 없습니다'); return; }

  // 받는사람 확인 — 설정값이 default, 사용자가 즉시 수정 가능
  const defaultTo = cachedSettings.emailTo;
  const defaultCc = cachedSettings.emailCc;
  const to = prompt('받는사람 (To, 콤마 구분)', defaultTo);
  if (to === null) return;  // 취소
  const cc = prompt('참조 (Cc, 콤마 구분) — 없으면 빈 칸', defaultCc);
  if (cc === null) return;
  if (!to.trim()) { toast('받는사람이 비어있습니다', 'fail'); return; }
  if (!confirm(`정말 발송할까요?\n\nTo: ${to}\nCc: ${cc || '(없음)'}`)) return;

  try {
    const r = await apiPost('/api/actions/email-send-weekly', {
      week_iso: currentWeek,
      override_to: to,
      override_cc: cc,
    });
    toast(`이메일 발송됨 — ${r.subject}`);
  } catch (e) {
    toast(`발송 실패: ${e.message}`, 'fail');
  }
});

// ─── UpNote 저장 ─────────────────────────────────

document.getElementById('btn-upnote-weekly').addEventListener('click', async () => {
  if (currentRows.length === 0) {
    toast('보고서가 비어있습니다');
    return;
  }
  if (!cachedSettings.weeklyNotebookId) {
    toast('주간업무보고 노트북 ID 를 설정 페이지에서 먼저 등록하세요');
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
loadCachedSettings();
initOngoingSchedule();
