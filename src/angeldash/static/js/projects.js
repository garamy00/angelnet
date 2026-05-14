import { apiGet, apiPost, apiPut, apiDelete, toast } from './api.js';
import { initHeader } from './header.js';

const AUTO_TASK_OPTIONS = ['개발', '시험/지원', '영업'];
const AUTO_TASK_DEFAULT = '개발';

function escapeHtml(s) {
  return String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

// 프로젝트 표시 라벨: 이름 + [work_type] 태그. work_type 이 비어있으면 이름만.
function projectLabel(p) {
  const name = escapeHtml(p.name);
  const wt = (p.work_type || '').trim();
  return wt
    ? `${name} <span class="work-type-tag">[${escapeHtml(wt)}]</span>`
    : name;
}
function projectLabelPlain(p) {
  const wt = (p.work_type || '').trim();
  return wt ? `${p.name} [${wt}]` : p.name;
}

// ─── 자동 가입 task 라디오 (settings.join.auto_task_name 와 동기화) ───
async function loadAutoTaskRadios() {
  const settings = await apiGet('/api/settings');
  let current = settings['join.auto_task_name'] || AUTO_TASK_DEFAULT;
  if (!AUTO_TASK_OPTIONS.includes(current)) current = AUTO_TASK_DEFAULT;
  const container = document.getElementById('auto-task-radios');
  container.innerHTML = AUTO_TASK_OPTIONS.map((name, i) => `
    <label style="margin-right:12px">
      <input type="radio" name="auto-task" value="${escapeHtml(name)}"
        ${name === current ? 'checked' : ''}> ${escapeHtml(name)}
    </label>
  `).join('');
  container.querySelectorAll('input[name="auto-task"]').forEach((r) => {
    r.addEventListener('change', async () => {
      try {
        await apiPut('/api/settings', { 'join.auto_task_name': r.value });
        toast(`자동 가입 task: ${r.value}`);
      } catch (e) {
        toast(`실패: ${e.message}`, 'fail');
      }
    });
  });
}

// ─── 등록된 프로젝트 ───
async function loadProjects() {
  const items = await apiGet('/api/projects');
  const tbody = document.querySelector('#projects-table tbody');
  tbody.innerHTML = '';
  for (const p of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${projectLabel(p)}</td>
      <td>${p.active ? '활성' : '<span class="muted">비활성</span>'}</td>
      <td><button class="row-delete" title="삭제">×</button></td>
    `;
    const label = projectLabelPlain(p);
    tr.querySelector('.row-delete').addEventListener('click', async () => {
      if (!confirm(`'${label}' 프로젝트를 삭제하시겠습니까?`)) return;
      try {
        await apiDelete(`/api/projects/${p.id}`);
        toast(`삭제됨: ${label}`);
        await refreshAll();
      } catch (e) {
        // 매핑 사용 중이면 서버가 409 + JSON detail 반환
        if (e.detail && typeof e.detail === 'object') {
          const c = e.detail.category_mappings || 0;
          const m = e.detail.pattern_mappings || 0;
          toast(
            `'${label}' 삭제 불가 — 카테고리 매핑 ${c}건, 패턴 매핑 ${m}건에서 사용 중. 먼저 매핑을 해제하세요.`,
            'fail',
          );
        } else {
          toast(`실패: ${e.message}`, 'fail');
        }
      }
    });
    tbody.appendChild(tr);
  }
  return items;
}

// ─── 카테고리 매핑 ───
async function loadMappings(projects) {
  const items = await apiGet('/api/mappings');
  const tbody = document.querySelector('#mappings-table tbody');
  tbody.innerHTML = '';
  const opts = ['<option value="">(미매핑)</option>']
    .concat(projects.map(
      (p) => `<option value="${p.id}">${escapeHtml(projectLabelPlain(p))}</option>`,
    ))
    .join('');
  for (const m of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(m.category)}</td>
      <td><select class="project-select">${opts}</select></td>
      <td><input type="text" class="weekly-name" value="${escapeHtml(m.weekly_project_name || '')}" placeholder="(없으면 타임시트 프로젝트명)" style="width:100%"></td>
      <td><input type="checkbox" class="excluded" ${m.excluded ? 'checked' : ''}></td>
      <td><button class="row-delete" title="이 매핑 행 삭제">×</button></td>
    `;
    const sel = tr.querySelector('.project-select');
    if (m.project_id) sel.value = String(m.project_id);
    const weeklyInput = tr.querySelector('.weekly-name');
    const exc = tr.querySelector('.excluded');
    const save = async () => {
      try {
        await apiPut(
          `/api/mappings/${encodeURIComponent(m.category)}`,
          {
            project_id: sel.value ? parseInt(sel.value, 10) : null,
            excluded: exc.checked,
            weekly_project_name: weeklyInput.value.trim() || null,
          },
        );
        toast('매핑 저장됨');
      } catch (e) {
        toast(`실패: ${e.message}`, 'fail');
      }
    };
    sel.addEventListener('change', save);
    weeklyInput.addEventListener('blur', save);
    exc.addEventListener('change', save);
    tr.querySelector('.row-delete').addEventListener('click', async () => {
      if (!confirm(`카테고리 '${m.category}' 의 매핑 행을 삭제하시겠습니까?\n(보고서의 카테고리 자체는 유지됨)`)) return;
      try {
        await apiDelete(`/api/mappings/${encodeURIComponent(m.category)}`);
        toast(`매핑 삭제됨: ${m.category}`);
        await refreshAll();
      } catch (e) {
        toast(`실패: ${e.message}`, 'fail');
      }
    });
    tbody.appendChild(tr);
  }
}

// ─── 본문 패턴 매핑 ───
async function loadPatternMappings(projects) {
  const items = await apiGet('/api/pattern-mappings');
  const tbody = document.querySelector('#patterns-table tbody');
  tbody.innerHTML = '';
  for (const p of items) {
    const tr = document.createElement('tr');
    const projDisplay = p.project_name
      ? projectLabel({ name: p.project_name, work_type: p.project_work_type })
      : '<span class="muted">(없음)</span>';
    tr.innerHTML = `
      <td><code>${escapeHtml(p.pattern)}</code></td>
      <td>${projDisplay}</td>
      <td>${p.excluded ? '✓' : ''}</td>
      <td><button class="row-delete" title="삭제">×</button></td>
    `;
    tr.querySelector('.row-delete').addEventListener('click', async () => {
      if (!confirm(`패턴 '${p.pattern}' 을 삭제하시겠습니까?`)) return;
      try {
        await apiDelete(`/api/pattern-mappings/${p.id}`);
        toast(`패턴 삭제됨: ${p.pattern}`);
        await loadPatternMappings(projects);
      } catch (e) {
        toast(`실패: ${e.message}`, 'fail');
      }
    });
    tbody.appendChild(tr);
  }

  // 새 패턴 추가용 드롭다운 — [work_type] 까지 보여 동일 이름 구분 가능
  const sel = document.getElementById('new-pattern-project');
  sel.innerHTML = projects.map(
    (p) => `<option value="${p.id}">${escapeHtml(projectLabelPlain(p))}</option>`,
  ).join('');
}

// 프로젝트 → 매핑/패턴 매핑 의존성. 어디서 변경되든 한 곳에서 동기화.
async function refreshAll() {
  const ps = await loadProjects();
  await loadMappings(ps);
  await loadPatternMappings(ps);
  return ps;
}

// ─── 회사 검색/가입 ───
async function searchJoinable(keyword) {
  const res = await apiGet(
    `/api/timesheet/projects/search?keyword=${encodeURIComponent(keyword)}`,
  );
  const tbody = document.querySelector('#joinable-table tbody');
  tbody.innerHTML = '';
  for (const p of res.rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="checkbox" class="join-toggle" ${p.joined ? 'checked' : ''}></td>
      <td>${escapeHtml(p.project_id)}</td>
      <td><code>${escapeHtml(p.code)}</code></td>
      <td>${escapeHtml(p.name)}</td>
    `;
    const cb = tr.querySelector('.join-toggle');
    cb.addEventListener('change', async () => {
      cb.disabled = true;
      const newState = cb.checked;
      const verb = newState ? '가입' : '탈퇴';
      if (!confirm(`'${p.name}' 에 ${verb} 하시겠습니까?`)) {
        cb.checked = !newState;
        cb.disabled = false;
        return;
      }
      try {
        await apiPost('/api/timesheet/projects/join', {
          project_id: p.project_id, joined: newState,
        });
        toast(`'${p.name}' ${verb} 완료`);
      } catch (e) {
        cb.checked = !newState;
        toast(`실패: ${e.message}`, 'fail');
      } finally {
        cb.disabled = false;
      }
    });
    tbody.appendChild(tr);
  }
  document.getElementById('joinable-table').style.display = res.rows.length ? '' : 'none';
  document.getElementById('join-summary').textContent =
    res.total ? `총 ${res.total}건 중 ${res.rows.length}건 표시` : '검색 결과 없음';
}

document.getElementById('join-search').addEventListener('click', async () => {
  const kw = document.getElementById('join-keyword').value.trim();
  try {
    await searchJoinable(kw);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});
document.getElementById('join-keyword').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('join-search').click();
});

// ─── 보고서 프로젝트 등록 (타임시트 task → 로컬 프로젝트) ───
const ymInput = document.getElementById('ym-input');
const today = new Date();
ymInput.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;

document.getElementById('load-remote').addEventListener('click', async () => {
  const ym = ymInput.value;
  const url = ym ? `/api/timesheet/tasks?year_month=${ym}` : '/api/timesheet/tasks';
  try {
    const tasks = await apiGet(url);
    renderRemoteTasks(tasks);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

function renderRemoteTasks(tasks) {
  const ul = document.getElementById('remote-tasks');
  ul.innerHTML = '';
  for (const t of tasks) {
    const li = document.createElement('li');
    const wt = (t.work_type || '').trim();
    const wtTag = wt ? `<span class="work-type-tag">[${escapeHtml(wt)}]</span>` : '';
    const meta = `<span class="muted">task_id=${t.task_id}</span>`;
    const labelPlain = wt ? `${t.name} [${wt}]` : t.name;
    if (t.already_registered) {
      li.innerHTML = `<span>${escapeHtml(t.name)}</span> ${wtTag} ${meta} <span class="muted">✓ 등록됨</span>`;
    } else {
      li.innerHTML = `<span>${escapeHtml(t.name)}</span> ${wtTag} ${meta} `;
      const btn = document.createElement('button');
      btn.textContent = '+ 프로젝트로 추가';
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        try {
          await apiPost('/api/projects', {
            name: t.name, remote_id: t.name, work_type: wt,
          });
          toast(`등록됨: ${labelPlain}`);
          li.innerHTML = `<span>${escapeHtml(t.name)}</span> ${wtTag} ${meta} <span class="muted">✓ 등록됨</span>`;
          await refreshAll();
        } catch (err) {
          btn.disabled = false;
          toast(`실패: ${err.message}`, 'fail');
        }
      });
      li.appendChild(btn);
    }
    ul.appendChild(li);
  }
}

// 패턴 추가
document.getElementById('add-pattern').addEventListener('click', async () => {
  const input = document.getElementById('new-pattern');
  const sel = document.getElementById('new-pattern-project');
  const pattern = input.value.trim();
  if (!pattern || !sel.value) return;
  try {
    await apiPost('/api/pattern-mappings', {
      pattern,
      project_id: parseInt(sel.value, 10),
      excluded: false,
    });
    input.value = '';
    await refreshAll();
    toast(`패턴 추가됨: ${pattern}`);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

// 초기 로드
(async () => {
  await loadAutoTaskRadios();
  await refreshAll();
})();
initHeader();
