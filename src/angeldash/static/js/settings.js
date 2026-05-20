import { apiGet, apiPut, apiPost, isoWeek, toast } from './api.js';
import { initHeader } from './header.js';

// text 필드들. join.auto_task_name 은 /projects.html 의 라디오로 이동.
const KEYS = {
  'notebook-id': 'upnote.notebook_id',
  'weekly-notebook-id': 'upnote.weekly_notebook_id',
  'weekly-title-template': 'upnote.weekly_title_template',
  't-team-report': 'team_report.template',
  't-upnote-title': 'upnote.title_template',
  't-upnote-body': 'upnote.body_template',
  'holiday-exclude': 'misc.holiday_exclude_labels',  // 출근일로 취급할 공휴일 label
  'notion-database-id': 'notion.database_id',
  'notion-prop-title': 'notion.prop_title',
  'notion-prop-date': 'notion.prop_date',
  'notion-prop-project': 'notion.prop_project',
  'notion-prop-worktype': 'notion.prop_worktype',
  'notion-prop-hours': 'notion.prop_hours',
  'notion-prop-category': 'notion.prop_category',
  'notion-week-db-id': 'notion.week_db_id',
  'notion-week-prop-title': 'notion.week_prop_title',
  'notion-week-prop-date': 'notion.week_prop_date',
  'notion-weekly-report-db-id': 'notion.weekly_report_db_id',
  'notion-weekly-report-prop-title': 'notion.weekly_report_prop_title',
  'notion-weekly-report-prop-date': 'notion.weekly_report_prop_date',
  'notion-projects-db-id': 'notion.projects_db_id',
  'notion-projects-prop-name': 'notion.projects_prop_name',
  'notion-projects-prop-worktype': 'notion.projects_prop_worktype',
  'notion-projects-prop-code': 'notion.projects_prop_code',
  'report-author-name': 'report.author_name',        // 주간업무보고 휴가 행 표시명
  'email-to': 'email.to',
  'email-cc': 'email.cc',
  'email-subject': 'email.subject_template',
  'email-greeting': 'email.greeting',
  'email-closing': 'email.closing',
  'email-signature': 'email.signature_html',
  'email-smtp-host': 'email.smtp_host',
  'email-smtp-port': 'email.smtp_port',
  'email-username': 'email.username',
  'email-from': 'email.from',
};
// select / checkbox (값은 'true' / 'false' 문자열로 저장)
const BOOL_KEYS = {
  'wrap-code': 'upnote.wrap_in_code_block',
  'upnote-markdown': 'upnote.markdown',
  'upnote-enabled': 'upnote.enabled',
  'notion-enabled': 'notion.enabled',
  'notion-week-enabled': 'notion.week_enabled',
  'notion-projects-enabled': 'notion.projects_enabled',
  'notion-weekly-report-enabled': 'notion.weekly_report_enabled',
  'email-enabled': 'email.enabled',
  'email-smtp-tls': 'email.smtp_tls',
  'cb-team-report-source-commit': 'team_report.include_source_commit',
};

let defaults = {};

async function load() {
  const s = await apiGet('/api/settings');
  defaults = { ...s };
  for (const [elId, key] of Object.entries(KEYS)) {
    document.getElementById(elId).value = s[key] ?? '';
  }
  for (const [elId, key] of Object.entries(BOOL_KEYS)) {
    const el = document.getElementById(elId);
    const val = (s[key] ?? 'false').toString().toLowerCase() === 'true';
    if (el.type === 'checkbox') el.checked = val;
    else el.value = val ? 'true' : 'false';
  }
  setupEnableToggles();
  await refreshNotionTokenStatus();
}

/**
 * data-enable="checkboxId" 가 붙은 그룹 토글.
 * 체크 해제 시 자식 element 에 .is-collapsed (display:none) 부여.
 * 단 타이틀과 첫 안내 문단(첫 p.muted) 은 항상 보이게 유지 — 사용자가
 * 비활성 상태에서도 섹션 설명을 읽을 수 있도록.
 */
function applyCollapseState(container) {
  const cb = document.getElementById(container.dataset.enable);
  if (!cb) return;
  const collapsed = !cb.checked;

  let kids;
  if (container.tagName === 'SECTION') {
    kids = Array.from(container.children).filter(
      (c) => !c.classList.contains('section-title'),
    );
  } else {
    // subsection-title — 다음 .subsection-title 직전까지 형제
    kids = [];
    let cur = container.nextElementSibling;
    while (cur && !cur.classList.contains('subsection-title')) {
      kids.push(cur);
      cur = cur.nextElementSibling;
    }
  }

  // 첫 안내 문단 (p.muted) 은 항상 visible
  let descShown = false;
  for (const el of kids) {
    if (!descShown && el.tagName === 'P' && el.classList.contains('muted')) {
      el.classList.remove('is-collapsed');
      descShown = true;
      continue;
    }
    el.classList.toggle('is-collapsed', collapsed);
  }

  // 서브섹션 재귀는 부모 section 이 활성일 때만 — 부모가 비활성이면
  // 서브섹션 콘텐츠도 위 loop 에서 이미 collapsed 처리됨. 여기서 재귀하면
  // 서브섹션 자체 토글이 켜져 있을 때 다시 unhide 되어 버그.
  if (container.tagName === 'SECTION' && !collapsed) {
    for (const sub of container.querySelectorAll('.subsection-title[data-enable]')) {
      applyCollapseState(sub);
    }
  }
}

function setupEnableToggles() {
  // 변경 시 section 부터 top-down 재계산 — 부모가 disabled 면 자식 토글 무시
  function recompute() {
    for (const section of document.querySelectorAll('section[data-enable]')) {
      applyCollapseState(section);
    }
  }
  for (const container of document.querySelectorAll('[data-enable]')) {
    const cb = document.getElementById(container.dataset.enable);
    if (!cb) continue;
    cb.addEventListener('change', recompute);
  }
  recompute();
}

async function refreshNotionTokenStatus() {
  try {
    const r = await apiGet('/api/settings/notion-token-status');
    const el = document.getElementById('notion-token-status');
    el.textContent = r.present
      ? '✅ 토큰이 키체인에 저장되어 있습니다 (변경하려면 새 토큰을 입력 후 저장).'
      : '⚠️ 토큰이 저장되어 있지 않습니다.';
  } catch (e) {
    console.error('notion token status failed', e);
  }
}

document.getElementById('save').addEventListener('click', async () => {
  const payload = {};
  for (const [elId, key] of Object.entries(KEYS)) {
    payload[key] = document.getElementById(elId).value;
  }
  for (const [elId, key] of Object.entries(BOOL_KEYS)) {
    const el = document.getElementById(elId);
    const val = el.type === 'checkbox' ? el.checked : el.value === 'true';
    payload[key] = val ? 'true' : 'false';
  }
  try {
    await apiPut('/api/settings', payload);
    // Notion 토큰: 값이 입력된 경우에만 키체인 저장 (빈 입력은 무시,
    // 키체인을 비우려면 사용자가 명시적으로 spec 한 빈 값을 보내야 한다는 점은
    // 향후 별도 버튼으로 분리)
    const tokenEl = document.getElementById('notion-token');
    if (tokenEl && tokenEl.value.trim()) {
      await apiPut('/api/settings/notion-token', { token: tokenEl.value.trim() });
      tokenEl.value = '';
      await refreshNotionTokenStatus();
    }
    toast('저장됨');
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'fail');
  }
});

for (const btn of document.querySelectorAll('button[data-preview]')) {
  btn.addEventListener('click', async () => {
    const kind = btn.dataset.preview;
    const elId = kind === 'team_report'
      ? 't-team-report'
      : kind === 'upnote_title' ? 't-upnote-title' : 't-upnote-body';
    const template = document.getElementById(elId).value;
    const previewEl = document.getElementById(
      kind === 'team_report' ? 'preview-team-report'
        : kind === 'upnote_title' ? 'preview-upnote-title'
          : 'preview-upnote-body',
    );
    try {
      const body = { kind, template, week_iso: isoWeek(new Date()) };
      const r = await apiPost('/api/settings/preview', body);
      previewEl.textContent = r.text;
    } catch (e) {
      previewEl.textContent = `[ERROR] ${e.message}`;
    }
  });
}

for (const btn of document.querySelectorAll('button[data-reset]')) {
  btn.addEventListener('click', () => {
    const key = btn.dataset.reset;
    const elId = Object.entries(KEYS).find(([, k]) => k === key)[0];
    document.getElementById(elId).value = defaults[key] ?? '';
    toast('기본값으로 복원 (저장 버튼을 눌러 적용)');
  });
}

// ─── 이메일 password (Keychain) + Test ────────────────

async function refreshEmailPasswordStatus() {
  const statusEl = document.getElementById('email-password-status');
  if (!statusEl) return;
  try {
    const s = await apiGet('/api/settings/email-password-status');
    if (s.has_password) {
      statusEl.textContent = `(Keychain 에 저장됨: ${s.username})`;
    } else if (s.username) {
      statusEl.textContent = `(미저장: ${s.username} 의 password 를 입력 후 저장)`;
    } else {
      statusEl.textContent = '(Username 먼저 입력 후 저장)';
    }
  } catch (e) {
    statusEl.textContent = `(상태 조회 실패: ${e.message})`;
  }
}

// 일반 settings 저장 후 password 가 있으면 별도 endpoint 로 Keychain 저장.
// 빈 값이면 변경 의도 없음으로 해석 — 기존 Keychain 항목 유지.
async function savePasswordIfChanged() {
  const pwEl = document.getElementById('email-password');
  const pw = pwEl ? pwEl.value : '';
  if (!pw) return;
  await apiPut('/api/settings/email-password', { password: pw });
  pwEl.value = '';  // 화면에서 즉시 지움 (재노출 방지)
}

const testBtn = document.getElementById('email-test');
if (testBtn) {
  testBtn.addEventListener('click', async () => {
    const resultEl = document.getElementById('email-test-result');
    resultEl.textContent = '...';
    testBtn.disabled = true;
    try {
      await apiPost('/api/actions/email-test', {});
      resultEl.textContent = '✅ SMTP 연결/인증 OK';
      toast('SMTP 연결 OK');
    } catch (e) {
      resultEl.textContent = `❌ ${e.message}`;
      toast(`SMTP 실패: ${e.message}`, 'fail');
    } finally {
      testBtn.disabled = false;
    }
  });
}

// 저장 버튼 click 핸들러는 위에서 등록됨 — Keychain password 저장을
// 그 핸들러 안에서 추가로 호출하도록 wrap.
const saveBtn = document.getElementById('save');
const origOnClick = saveBtn.onclick;
saveBtn.addEventListener('click', async () => {
  try {
    await savePasswordIfChanged();
    await refreshEmailPasswordStatus();
  } catch (e) {
    toast(`Password 저장 실패: ${e.message}`, 'fail');
  }
});

load();
refreshEmailPasswordStatus();
initHeader();
