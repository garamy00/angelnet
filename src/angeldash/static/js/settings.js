import { apiGet, apiPut, apiPost, isoWeek, toast } from './api.js';

// text 필드들. join.auto_task_name 은 /projects.html 의 라디오로 이동.
const KEYS = {
  'notebook-id': 'upnote.notebook_id',
  'weekly-notebook-id': 'upnote.weekly_notebook_id',
  't-team-report': 'team_report.template',
  't-upnote-title': 'upnote.title_template',
  't-upnote-body': 'upnote.body_template',
  'holiday-exclude': 'misc.holiday_exclude_labels',  // 출근일로 취급할 공휴일 label
};
// select / checkbox (값은 'true' / 'false' 문자열로 저장)
const BOOL_KEYS = {
  'wrap-code': 'upnote.wrap_in_code_block',
  'upnote-markdown': 'upnote.markdown',
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

load();
