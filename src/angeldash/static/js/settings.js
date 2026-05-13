import { apiGet, apiPut, apiPost, isoWeek, toast } from './api.js';

// text 필드들. join.auto_task_name 은 /projects.html 의 라디오로 이동.
const KEYS = {
  'notebook-id': 'upnote.notebook_id',
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
  'notion-projects-db-id': 'notion.projects_db_id',
  'notion-projects-prop-name': 'notion.projects_prop_name',
  'notion-projects-prop-worktype': 'notion.projects_prop_worktype',
  'notion-projects-prop-code': 'notion.projects_prop_code',
};
// select / checkbox (값은 'true' / 'false' 문자열로 저장)
const BOOL_KEYS = {
  'wrap-code': 'upnote.wrap_in_code_block',
  'upnote-markdown': 'upnote.markdown',
  'upnote-enabled': 'upnote.enabled',
  'notion-enabled': 'notion.enabled',
  'notion-week-enabled': 'notion.week_enabled',
  'notion-projects-enabled': 'notion.projects_enabled',
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
  await refreshNotionTokenStatus();
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

load();
