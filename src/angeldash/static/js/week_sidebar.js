/**
 * 주차 리스트 사이드바 — 저장된 데이터의 주차 한 줄씩 표시.
 *
 * 일일/주간업무보고 공용. 페이지가 사이드바 안 DOM 컨테이너 (#week-sidebar-list)
 * 를 제공하면 이 모듈이 API 에서 list 를 fetch 해서 채우고 클릭 시 navigate.
 *
 * 옵션:
 *   indexUrl    : 사이드바에 보여줄 list 를 가져오는 API 경로
 *   navigate(weekIso): 항목 클릭 시 실행되는 콜백 (페이지가 그 주차로 이동)
 *   currentWeek : 현재 보고 있는 주차 — highlight 용
 */
import { apiGet, isoWeek, weekDates } from './api.js';

function formatLabel(weekIso) {
  // '2026-W20 (05/11 ~ 05/15)'
  const dates = weekDates(weekIso);
  if (!dates || dates.length < 5) return weekIso;
  const start = dates[0].slice(5);
  const end = dates[4].slice(5);
  return `${weekIso} (${start} ~ ${end})`;
}

// 오늘 기준 이전주/이번주/다음주 ISO 라벨 매핑.
function relativeWeekTags() {
  const today = new Date();
  const thisIso = isoWeek(today);
  const prev = new Date(today); prev.setDate(today.getDate() - 7);
  const next = new Date(today); next.setDate(today.getDate() + 7);
  return {
    [isoWeek(prev)]: '지난 주',
    [thisIso]: '이번 주',
    [isoWeek(next)]: '다음 주',
  };
}

export async function loadWeekSidebar({ indexUrl, navigate, currentWeek }) {
  const list = document.getElementById('week-sidebar-list');
  if (!list) return;
  list.innerHTML = '<div class="muted">로딩…</div>';
  let items;
  try {
    items = await apiGet(indexUrl);
  } catch (e) {
    list.innerHTML = `<div class="muted">로드 실패: ${e.message}</div>`;
    return;
  }
  if (!items.length) {
    list.innerHTML = '<div class="muted">저장된 항목 없음</div>';
    return;
  }
  list.innerHTML = '';
  const tags = relativeWeekTags();
  for (const it of items) {
    const btn = document.createElement('button');
    btn.className = 'week-sidebar-item';
    if (it.week_iso === currentWeek) btn.classList.add('active');
    btn.dataset.weekIso = it.week_iso;
    const tag = tags[it.week_iso];
    if (tag === '이번 주') {
      btn.classList.add('this-week');
      btn.innerHTML = `<span class="week-label">${formatLabel(it.week_iso)}</span><span class="week-tag">이번 주</span>`;
    } else {
      btn.innerHTML = `<span class="week-label">${formatLabel(it.week_iso)}</span>`;
    }
    btn.title = it.week_iso;
    btn.addEventListener('click', () => navigate(it.week_iso));
    list.appendChild(btn);
  }
}

/** 현재 활성 항목만 빠르게 갱신 — 전체 reload 안 함. */
export function highlightCurrent(weekIso) {
  const list = document.getElementById('week-sidebar-list');
  if (!list) return;
  for (const el of list.querySelectorAll('.week-sidebar-item')) {
    el.classList.toggle('active', el.dataset.weekIso === weekIso);
  }
}
