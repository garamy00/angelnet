/**
 * 모든 페이지 헤더 우측 영역 초기화 — 사용자명 + 테마 토글 + 새로고침 버튼.
 *
 * 각 페이지의 main script 가 이 모듈을 import + initHeader() 호출.
 * 헤더 HTML 의 #user-name / #btn-refresh 가 존재해야 한다.
 * 테마 토글 버튼은 동적으로 #btn-refresh 옆에 삽입.
 */
import { apiGet } from './api.js';
import { icon, decorateButtons, decorateEmojis, decorateSubtitles, startEmojiAutoDecorate } from './icons.js';

const THEME_KEY = 'angeldash.theme';

// nav 항목 href 패턴 → 아이콘 이름 + 라벨
const NAV_ITEMS = [
  { href: '/',                 icon: 'calendar-days', label: '일일업무보고' },
  { href: '/weekly-report.html', icon: 'bar-chart-3', label: '주간업무보고' },
  { href: '/projects.html',    icon: 'folder',        label: '프로젝트' },
  { href: '/rooms.html',       icon: 'calendar',      label: '회의실예약' },
  { href: '/vacation.html',    icon: 'tent',          label: '휴가조회' },
  { href: '/logs.html',        icon: 'clipboard-list', label: '로그' },
  { href: '/settings.html',    icon: 'settings',      label: '설정' },
];

function renderBrand() {
  const header = document.querySelector('header');
  if (!header || header.querySelector('.brand')) return;
  const a = document.createElement('a');
  a.href = '/';
  a.className = 'brand';
  a.setAttribute('aria-label', 'Hey:log 홈으로');
  a.innerHTML = `
    <img class="brand-logo" src="/static/favicon.svg" alt="" width="22" height="22">
    <span class="brand-name">Hey<span class="brand-colon">:</span>log</span>
  `;
  header.insertBefore(a, header.firstElementChild);
}

function renderNav() {
  const nav = document.querySelector('header nav');
  if (!nav) return;
  const activeHref = (location.pathname === '/' || location.pathname === '')
    ? '/'
    : location.pathname;
  // 기존 anchor 의 텍스트와 href 를 유지하면서 이모지 제거 + SVG 아이콘으로 교체
  nav.innerHTML = NAV_ITEMS.map((it) => {
    const isActive = it.href === activeHref;
    const cls = isActive ? ' class="active"' : '';
    return `<a href="${it.href}"${cls}>${icon(it.icon)} <span>${it.label}</span></a>`;
  }).join('');
}

/** 페이지 첫 화면 깜빡임(FOUC) 방지를 위해 가능한 한 빨리 호출. */
export function applyStoredTheme() {
  const t = localStorage.getItem(THEME_KEY) || 'dark';
  document.documentElement.dataset.theme = t === 'light' ? 'light' : 'dark';
}

function toggleTheme() {
  const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  const next = cur === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
  updateThemeToggleLabel();
}

function updateThemeToggleLabel() {
  const btn = document.getElementById('btn-theme');
  if (!btn) return;
  const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  // 현재 테마와 반대 아이콘 (다음 상태) 표시 — 클릭 시 그 모드로 전환
  btn.innerHTML = icon(cur === 'light' ? 'moon' : 'sun');
  btn.title = cur === 'light' ? '다크 모드로' : '라이트 모드로';
  btn.setAttribute('aria-label', btn.title);
}

function injectThemeToggle() {
  const right = document.querySelector('header .header-right');
  if (!right || document.getElementById('btn-theme')) return;
  const btn = document.createElement('button');
  btn.id = 'btn-theme';
  btn.type = 'button';
  btn.classList.add('icon-only');
  btn.addEventListener('click', toggleTheme);
  // 새로고침 버튼 앞에 삽입 (있으면)
  const refresh = document.getElementById('btn-refresh');
  if (refresh) right.insertBefore(btn, refresh);
  else right.appendChild(btn);
  updateThemeToggleLabel();
}

function decorateRefresh() {
  const btn = document.getElementById('btn-refresh');
  if (!btn) return;
  btn.innerHTML = icon('refresh-cw');
  btn.classList.add('icon-only');
  btn.setAttribute('aria-label', btn.title || '새로고침');
}

export async function initHeader() {
  applyStoredTheme();
  renderBrand();
  renderNav();
  injectThemeToggle();
  decorateRefresh();
  // 페이지의 액션 버튼들 (id 매핑) 의 이모지 → SVG 일괄 교체
  decorateButtons();
  // 그 외 모든 헤딩/span/링크의 이모지도 자동 매핑 SVG 로 교체
  decorateEmojis();
  // 사이드바 헤더 / details summary / 메모 h3 같은 하위 타이틀 — selector 명시 (결정적)
  decorateSubtitles();
  // 이후 JS 렌더로 새로 추가되는 이모지도 자동 교체되도록 MutationObserver 가동
  startEmojiAutoDecorate();

  const nameEl = document.getElementById('user-name');
  const btn = document.getElementById('btn-refresh');

  // 새로고침 버튼 — 현재 페이지 reload
  if (btn) {
    btn.addEventListener('click', () => location.reload());
  }

  // 사용자명 — /api/me 의 name(user_id)
  if (nameEl) {
    try {
      const me = await apiGet('/api/me');
      nameEl.textContent = `${me.name}(${me.user_id})`;
    } catch (e) {
      nameEl.textContent = '(로그인 실패)';
    }
  }
}

// 모듈 로드 직후 즉시 테마 적용 (FOUC 회피 — initHeader 보다 먼저 실행됨)
applyStoredTheme();
