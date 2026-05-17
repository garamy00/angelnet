/**
 * Lucide CDN 기반 아이콘 시스템.
 *
 * 각 HTML 페이지의 <head> 에서 https://unpkg.com/lucide@latest UMD 스크립트를
 * 로드하면 window.lucide 가 노출된다. 이 모듈은 그 위의 얇은 래퍼:
 *
 *   - icon(name)           — '<i data-lucide="name"></i>' placeholder 반환
 *   - refreshIcons()       — placeholder 들을 즉시 SVG 로 변환
 *   - startLucideAutoRender() — 새 placeholder 가 DOM 에 추가될 때마다 자동 변환
 *
 * 이모지 → Lucide 매핑 + 버튼 ID → Lucide 매핑 + 하위 타이틀 selector 매핑은
 * 이전 로직과 동일.
 */

/** placeholder 생성. 실제 SVG 는 lucide.createIcons() 호출 시 교체됨. */
export function icon(name) {
  return `<i data-lucide="${name}"></i>`;
}

/** DOM 노드 반환 — appendChild 용. */
export function iconNode(name) {
  const wrap = document.createElement('span');
  wrap.innerHTML = icon(name);
  return wrap.firstChild;
}

/** placeholder 들을 즉시 SVG 로 처리 (lucide.createIcons 호출). */
export function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    try { window.lucide.createIcons(); } catch (e) { /* swallow */ }
  }
}

/* ─── 이모지 ↔ Lucide 매핑 ─────────────────────────────── */
const EMOJI_TO_ICON = {
  '📅': 'calendar-days',
  '📈': 'bar-chart-3',
  '🗂': 'folder',
  '🗓': 'calendar',
  '🏖': 'tent',
  '📋': 'clipboard-list',
  '⚙️': 'settings',
  '⚙': 'settings',
  '📤': 'send',
  '🔄': 'refresh-cw',
  '📊': 'table',
  '🔍': 'search',
  '📥': 'download',
  '📌': 'pin',
  '📝': 'file-text',
  '🎌': 'flag',
  '✉️': 'mail',
  '✉': 'mail',
  '🌙': 'moon',
  '☀️': 'sun',
  '☀': 'sun',
  '📂': 'folder',
};

const BUTTON_ICON_MAP = {
  'btn-refresh': 'refresh-cw',
  'btn-copy-schedule': 'copy',
  'btn-excel': 'download',
  'btn-timesheet': 'send',
  'btn-verify': 'search',
  'btn-monthly-preview': 'table',
  'btn-upnote': 'refresh-cw',
  'btn-notion': 'refresh-cw',
  'btn-notion-projects': 'refresh-cw',
  'btn-upnote-weekly': 'send',
  'btn-notion-weekly': 'refresh-cw',
  'btn-generate-initial': 'download',
  'btn-regenerate': 'refresh-cw',
  'btn-preview-email': 'mail',
  'btn-send-email': 'send',
  'preview-modal-copy': 'copy',
  'save': 'check',
};

// 이모지 / 변이 셀렉터 제거 패턴 (광범위)
const EMOJI_RE = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F100}-\u{1F1FF}]️?\s*/gu;
const _LEADING_EMOJI_RE = /^[\s\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}️]+/u;

/** 버튼 id → 아이콘 매핑으로 일괄 SVG 화. 기존 텍스트의 이모지는 strip. */
export function decorateButtons() {
  for (const [id, name] of Object.entries(BUTTON_ICON_MAP)) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (el.querySelector('i[data-lucide], svg')) continue;
    const txt = (el.textContent || '').replace(EMOJI_RE, '').trim();
    el.innerHTML = `${icon(name)}${txt ? ` <span>${txt}</span>` : ''}`;
  }
  refreshIcons();
}

/** 특정 selector 에 명시적으로 아이콘 prefix (하위 타이틀용). */
const SUBTITLE_ICONS = [
  { sel: '.week-sidebar-header', icon: 'folder' },
  { sel: '#ongoing-schedule > summary > span:not(.icon-wrap)', icon: 'pin' },
  { sel: '.week-notes h3', icon: 'file-text' },
];

export function decorateSubtitles(root = document.body) {
  for (const { sel, icon: name } of SUBTITLE_ICONS) {
    for (const el of root.querySelectorAll(sel)) {
      if (el.querySelector('i[data-lucide], svg')) continue;
      const text = (el.textContent || '').replace(_LEADING_EMOJI_RE, '').trim();
      el.innerHTML = `${icon(name)}<span>${text}</span>`;
    }
  }
  refreshIcons();
}

/** 일반 텍스트 element 안의 이모지를 selector 별로 일괄 교체. */
export function decorateEmojis(root = document.body) {
  const selectors = 'a, button, h1, h2, h3, span, strong, summary, td, li,'
    + ' .week-sidebar-header, .group-label, .vacation-tag, .holiday-tag';
  for (const el of root.querySelectorAll(selectors)) {
    let html = el.innerHTML;
    let changed = false;
    for (const [emoji, name] of Object.entries(EMOJI_TO_ICON)) {
      if (html.includes(emoji)) {
        html = html.split(emoji).join(icon(name));
        changed = true;
      }
    }
    if (changed) el.innerHTML = html;
  }
  refreshIcons();
}

/* ─── MutationObserver 자동 처리 ────────────────────────── */

let _scheduled = false;
function schedule() {
  if (_scheduled) return;
  _scheduled = true;
  requestAnimationFrame(() => {
    _scheduled = false;
    refreshIcons();
  });
}

let _emojiObserver = null;
export function startEmojiAutoDecorate() {
  if (_emojiObserver) return;
  const emojiKeys = Object.keys(EMOJI_TO_ICON);
  const hasEmoji = (text) => emojiKeys.some((e) => text.includes(e));

  _emojiObserver = new MutationObserver((mutations) => {
    let needs = false;
    let needsLucide = false;
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType === Node.TEXT_NODE && hasEmoji(node.nodeValue || '')) {
          needs = true;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.tagName === 'SVG' || node.tagName === 'svg') continue;
          if (hasEmoji(node.textContent || '')) needs = true;
          if (node.matches?.('i[data-lucide]') ||
              node.querySelector?.('i[data-lucide]')) {
            needsLucide = true;
          }
        }
      }
    }
    if (needs) requestAnimationFrame(() => decorateEmojis());
    else if (needsLucide) schedule();
  });
  _emojiObserver.observe(document.body, { childList: true, subtree: true });
}
