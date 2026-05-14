import { apiGet } from './api.js';
import { initHeader } from './header.js';
import { enableColumnResize } from './resizable_columns.js';

let logs = [];                                  // 서버에서 받은 원본
let sortState = { key: 'ts', dir: 'desc' };     // 기본: 시각 내림차순 (최신부터)

// 정렬 키 → log 객체의 실제 필드 접근자
const SORT_ACCESSORS = {
  ts: (l) => l.created_at || '',
  kind: (l) => l.action_type || '',
  target: (l) => l.target_range || '',
  status: (l) => l.status || '',
  message: (l) => l.message || '',
};

function sortedLogs() {
  const get = SORT_ACCESSORS[sortState.key] || ((l) => '');
  const sign = sortState.dir === 'asc' ? 1 : -1;
  return [...logs].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (av < bv) return -1 * sign;
    if (av > bv) return 1 * sign;
    return 0;
  });
}

function escapeHtml(s) {
  return String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function render() {
  const tbody = document.getElementById('logs-tbody');
  tbody.innerHTML = '';
  for (const log of sortedLogs()) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(log.created_at)}</td>
      <td>${escapeHtml(log.action_type)}</td>
      <td>${escapeHtml(log.target_range)}</td>
      <td>${log.status === 'ok' ? '✓' : '✗'}</td>
      <td>${escapeHtml(log.message ?? '')}</td>
    `;
    tbody.appendChild(tr);
  }
  updateSortIndicators();
}

function updateSortIndicators() {
  const thead = document.querySelector('#logs-table thead');
  if (!thead) return;
  for (const th of thead.querySelectorAll('th[data-sort-key]')) {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sortKey === sortState.key) {
      th.classList.add(sortState.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  }
}

function attachSortHandlers() {
  const thead = document.querySelector('#logs-table thead');
  if (!thead) return;
  for (const th of thead.querySelectorAll('th[data-sort-key]')) {
    th.addEventListener('click', (ev) => {
      // resize handle 클릭은 sort 와 무관 — 모듈이 stopPropagation 함
      if (ev.target.classList.contains('col-resize-handle')) return;
      const key = th.dataset.sortKey;
      if (sortState.key === key) {
        sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
      } else {
        sortState = { key, dir: 'asc' };
      }
      render();
    });
  }
}

async function load() {
  logs = await apiGet('/api/logs');
  render();
}

attachSortHandlers();
enableColumnResize(document.getElementById('logs-table'));
load();
initHeader();
