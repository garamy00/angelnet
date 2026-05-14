import { apiGet } from './api.js';
import { initHeader } from './header.js';

async function load() {
  const items = await apiGet('/api/logs');
  const tbody = document.getElementById('logs-tbody');
  tbody.innerHTML = '';
  for (const log of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${log.created_at}</td>
      <td>${log.action_type}</td>
      <td>${log.target_range}</td>
      <td>${log.status === 'ok' ? '✓' : '✗'}</td>
      <td>${log.message ?? ''}</td>
    `;
    tbody.appendChild(tr);
  }
}

load();
initHeader();
