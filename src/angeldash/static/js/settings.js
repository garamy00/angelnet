import { apiGet, apiPut, apiPost, isoWeek, toast } from './api.js';

// text 필드들. join.auto_task_name 은 /projects.html 의 라디오로 이동.
const KEYS = {
  'notebook-id': 'upnote.notebook_id',
  'weekly-notebook-id': 'upnote.weekly_notebook_id',
  'weekly-title-template': 'upnote.weekly_title_template',
  't-team-report': 'team_report.template',
  't-upnote-title': 'upnote.title_template',
  't-upnote-body': 'upnote.body_template',
  'holiday-exclude': 'misc.holiday_exclude_labels',  // 출근일로 취급할 공휴일 label
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
  'email-enabled': 'email.enabled',
  'email-smtp-tls': 'email.smtp_tls',
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
