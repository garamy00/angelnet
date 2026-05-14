/**
 * 모든 페이지 헤더 우측 영역 초기화 — 사용자명 + 새로고침 버튼.
 *
 * 각 페이지의 main script 가 이 모듈을 import + initHeader() 호출.
 * 헤더 HTML 의 #user-name / #btn-refresh 가 존재해야 한다.
 */
import { apiGet } from './api.js';

export async function initHeader() {
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
