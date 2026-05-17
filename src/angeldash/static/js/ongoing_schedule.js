import { apiGet, apiPut, toast } from './api.js';

/** 페이지에 #ongoing-schedule-text + #btn-copy-schedule 가 있으면 핸들러 부착. */
export function initOngoingSchedule() {
  const ta = document.getElementById('ongoing-schedule-text');
  const btn = document.getElementById('btn-copy-schedule');
  if (!ta || !btn) return;  // 해당 영역 없는 페이지면 no-op

  (async () => {
    try {
      const settings = await apiGet('/api/settings');
      ta.value = settings.ongoing_schedule || '';
    } catch (e) {
      toast(`일정 로드 실패: ${e.message}`, 'fail');
    }
  })();

  ta.addEventListener('blur', async (e) => {
    try {
      await apiPut('/api/settings', { ongoing_schedule: e.target.value });
    } catch (err) {
      toast(`일정 저장 실패: ${err.message}`, 'fail');
    }
  });

  btn.addEventListener('click', async (e) => {
    // <summary> 안의 button 은 기본 동작이 details 토글이라 즉시 차단
    e.preventDefault();
    e.stopPropagation();
    const text = ta.value;
    if (!text) {
      toast('복사할 내용이 없습니다');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      toast('진행중인 일정 복사됨');
    } catch (err) {
      toast(`복사 실패: ${err.message}`, 'fail');
    }
  });
}
