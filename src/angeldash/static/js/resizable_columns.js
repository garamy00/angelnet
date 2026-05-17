/**
 * 표의 column 폭을 mousedown 드래그로 조절하는 모듈.
 *
 * 사용법:
 *   <table class="resizable-table">
 *     <colgroup>
 *       <col style="width: 160px">
 *       <col>  <!-- 가변 -->
 *       ...
 *     </colgroup>
 *     <thead><tr><th>...</th></tr></thead>
 *     ...
 *   </table>
 *
 *   enableColumnResize(tableEl)
 *
 * 동작:
 *   각 thead th 의 우측 끝에 grip handle 을 추가. handle 을 mousedown 한 채
 *   드래그하면 같은 index 의 <col> width 가 갱신된다.
 *   <colgroup> 이 없는 표면 enableColumnResize 가 no-op.
 */

const MIN_COL_WIDTH = 40;

export function enableColumnResize(table) {
  if (!table) return;
  const cols = table.querySelectorAll('colgroup col');
  const ths = table.querySelectorAll('thead th');
  if (!cols.length || !ths.length) return;

  ths.forEach((th, i) => {
    if (i >= cols.length) return;
    // 기존 handle 제거 (재호출 안전)
    th.querySelector('.col-resize-handle')?.remove();

    const handle = document.createElement('span');
    handle.className = 'col-resize-handle';
    // th 가 position:relative 이어야 absolute 자식이 우측 끝에 자리잡음.
    // 페이지 CSS 가 .resizable-table th 에 적용 — JS 가 매번 set 할 필요 없음.

    handle.addEventListener('mousedown', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();  // th 의 다른 click(예: sort) 와 충돌 방지
      const col = cols[i];
      const startX = ev.clientX;
      // 현재 폭 — col width 가 px 또는 빈 값일 수 있어 실측치 사용
      const startWidth = col.getBoundingClientRect().width
        || th.getBoundingClientRect().width || 100;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      function onMove(e) {
        const delta = e.clientX - startX;
        const newWidth = Math.max(MIN_COL_WIDTH, Math.round(startWidth + delta));
        col.style.width = `${newWidth}px`;
      }
      function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    th.appendChild(handle);
  });
}
