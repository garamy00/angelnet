# Ko-fi 영감 디자인 가이드 (AngelDash Light Theme)

> Ko-fi (https://ko-fi.com/) 의 친근하고 밝은 톤을 참고한 라이트 모드 디자인.
> AngelDash 의 light 테마는 이 문서의 토큰을 따른다. 다크는 별개 톤.

---

## 1. 디자인 철학

Ko-fi 의 특징:
- **친근함** — 둥근 모서리, 부드러운 그림자, 풍부한 공백
- **밝은 명도** — 흰 surface 위에 옅은 블루 강조
- **선명한 액센트** — 다른 부분은 차분하고, primary 만 비비드하게 도드라짐
- **타이포 중심** — 헤딩이 굵고 크며, 본문은 가독성 좋은 sans-serif
- **장식 최소화** — 채워진(filled) 이모지 대신 얇은 stroke 라인 아이콘

이 톤을 AngelDash 에 적용할 때:
- 메인 표면(Surface Bright) 은 흰색
- 페이지 배경(Surface) 은 옅은 블루(`#f7f9ff`) — 카드가 떠 보이도록
- 카드/패널은 흰색 + 옅은 그림자
- 액션 버튼은 pill shape (둥근 full radius)
- 아이콘은 stroke 1.5 ~ 2 SVG (Lucide / Heroicons outline 스타일)

---

## 2. 색상 토큰

### 2.1 Primary

| 토큰 | HEX | 용도 |
|---|---|---|
| `--ko-primary` | `#13c3ff` | CTA 버튼, 링크, 활성 nav 텍스트, 액센트 stripe |
| `--ko-primary-hover` | `#00b1f5` | hover 시 약간 진하게 |
| `--ko-primary-container` | `#e0f7ff` | 옅은 액센트 배경 (today 박스, 칩 등) |
| `--ko-on-primary` | `#ffffff` | primary 위 텍스트 |

### 2.2 Surface / Background

| 토큰 | HEX | 용도 |
|---|---|---|
| `--ko-background` | `#f7f9ff` | 페이지 전체 배경 (옅은 블루 틴트) |
| `--ko-surface` | `#ffffff` | 카드/패널/모달 배경 |
| `--ko-surface-container` | `#eef4ff` | nested surface (hover, 강조 셀, 헤더 배경) |
| `--ko-surface-elevated` | `#ffffff` | 떠 있는 요소 (모달, dropdown) — surface + shadow |

### 2.3 텍스트

| 토큰 | HEX | 용도 |
|---|---|---|
| `--ko-text` | `#1a1d23` | 본문 (검정에 가까운 슬레이트) |
| `--ko-text-secondary` | `#5b6478` | 부가 정보 (placeholder, caption) |
| `--ko-text-tertiary` | `#9ba3ad` | 비활성 / disabled |

### 2.4 Outline & Divider

| 토큰 | HEX | 용도 |
|---|---|---|
| `--ko-outline` | `#d1dbea` | 카드 / 인풋 테두리 |
| `--ko-outline-soft` | `#e7edf6` | 표 row 구분선, divider |

### 2.5 Semantic

| 토큰 | HEX | 용도 |
|---|---|---|
| `--ko-success` | `#4caf50` | 성공 토스트 / 합계 OK |
| `--ko-warn` | `#d97706` | 경고 / 휴가 태그 |
| `--ko-danger` | `#f44336` | 에러 / 공휴일 / 삭제 |

### 2.6 Shadow

Ko-fi 는 그림자가 진하지 않다. 옅게 띄우는 정도.

```css
--ko-shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
--ko-shadow-md: 0 4px 12px rgba(15, 23, 42, 0.06);
--ko-shadow-lg: 0 12px 32px rgba(15, 23, 42, 0.08);
--ko-shadow-modal: 0 20px 60px rgba(15, 23, 42, 0.10);
```

---

## 3. 타이포그래피

### 3.1 Font Family

**Primary:** `Plus Jakarta Sans`, 둥근 가독성 좋은 sans-serif

```css
font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont,
             "Apple SD Gothic Neo", "Pretendard", "Segoe UI", Roboto, sans-serif;
```

한글 폴백: Apple SD Gothic Neo (macOS) → Pretendard (사내 표준) → 시스템 sans.

### 3.2 Scale

| 토큰 | 크기 / 행간 | 굵기 | 용도 |
|---|---|---|---|
| Display | 40px / 48px | 700 | 페이지 메인 헤딩 (거의 미사용) |
| Headline Large | 32px / 40px | 700 | 페이지 타이틀 (`<h1>`) |
| Headline Medium | 24px / 32px | 700 | 섹션 제목 (`<h2>`) |
| Title | 18px / 24px | 600 | 카드 제목 (`<h3>`) |
| Body Large | 16px / 24px | 400 | 기본 본문 |
| Body | 14px / 20px | 400 | 보조 본문 / 라벨 |
| Caption | 12px / 16px | 500 | muted 설명 |
| Label | 14px / 20px | 500 | 버튼 텍스트 |

---

## 4. 공간 시스템

### 4.1 Base Unit

기본 `4px`. 모든 패딩/마진/갭은 4 의 배수.

| 토큰 | 값 |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-12` | 48px |

### 4.2 Radius

Ko-fi 는 강하게 둥글다. AngelDash 에서:

| 토큰 | 값 | 용도 |
|---|---|---|
| `--radius-sm` | 6px | 작은 입력 / 배지 |
| `--radius-md` | 8px | 카드 (default) |
| `--radius-lg` | 16px | 큰 카드 / 모달 |
| `--radius-full` | 9999px | pill 버튼 / 칩 |

### 4.3 Layout

- **컨테이너 최대 폭** — 일반 페이지 `1200px`, 설정 페이지 `820px`
- **본문 좌우 패딩** — 모바일 16px, 데스크탑 24-32px
- **카드 내부 패딩** — 16-24px

---

## 5. 컴포넌트

### 5.1 Button

Ko-fi 의 시그니처 — **pill shape**, 굵은 라벨.

#### Primary Button
```css
background: var(--ko-primary);
color: var(--ko-on-primary);
border-radius: var(--radius-full);
padding: 10px 20px;
font-weight: 600;
font-size: 14px;
border: none;
box-shadow: var(--ko-shadow-sm);
transition: filter 120ms, transform 80ms;
```
hover: `filter: brightness(1.05); box-shadow: var(--ko-shadow-md);`
active: `transform: translateY(1px);`

#### Secondary / Outline Button
```css
background: var(--ko-surface);
color: var(--ko-primary);
border: 1.5px solid var(--ko-outline);
border-radius: var(--radius-full);
padding: 9px 19px;  /* border 차감 */
font-weight: 600;
```
hover: `border-color: var(--ko-primary); background: var(--ko-primary-container);`

#### Ghost / Text Button
배경 없음, primary 색 텍스트만. 작은 동작 (X 닫기, 새로고침 등)

### 5.2 Card

```css
background: var(--ko-surface);
border: 1px solid var(--ko-outline-soft);
border-radius: var(--radius-md);
padding: 20px 24px;
box-shadow: var(--ko-shadow-sm);
```
hover (interactive 카드): `box-shadow: var(--ko-shadow-md); transform: translateY(-1px);`

### 5.3 Input

```css
background: var(--ko-surface);
border: 1.5px solid var(--ko-outline);
border-radius: var(--radius-sm);
padding: 8px 12px;
font-size: 14px;
color: var(--ko-text);
```
focus: `border-color: var(--ko-primary); outline: 2px solid rgba(19, 195, 255, 0.2); outline-offset: 0;`

### 5.4 Chip / Badge / Tag

```css
display: inline-flex;
align-items: center;
gap: 4px;
padding: 4px 10px;
border-radius: var(--radius-full);
background: var(--ko-primary-container);
color: var(--ko-primary-hover);
font-size: 12px;
font-weight: 600;
```

### 5.5 Navigation (Top App Bar)

- 흰 배경(`var(--ko-surface)`) + 하단 1px outline-soft
- 좌측: 브랜드 (텍스트 또는 미니 로고)
- 중앙/좌: nav 항목 (텍스트 + 16px stroke icon, 간격 8px)
- 우측: 사용자명 + 테마 토글 + 새로고침
- 활성 항목: primary 색 텍스트 + 하단 2px primary underline (또는 옅은 container 배경)

### 5.6 Modal

```css
background: var(--ko-surface);
border-radius: var(--radius-lg);  /* 16px — 강하게 둥글게 */
padding: 24px;
box-shadow: var(--ko-shadow-modal);
```
backdrop: `rgba(15, 23, 42, 0.35)` — 진하지 않게.

---

## 6. 아이콘 가이드

### 6.1 원칙

- **stroke 라인 스타일** (filled 이모지 절대 X)
- 1.5 ~ 2px stroke-width
- 16-20px 크기 (텍스트 옆), 24px (단독 액션)
- `currentColor` 로 stroke 지정 — 부모 색 상속
- Lucide / Heroicons (outline) / Tabler 셋 중 하나로 통일

### 6.2 권장 라이브러리

**Lucide** (https://lucide.dev) — 가볍고 라이센스 자유 (ISC). MIT 의 Feather 기반.

또는 **Heroicons outline** (https://heroicons.com) — Tailwind 팀 제작, MIT.

이 도구는 의존성 추가 없이 인라인 SVG 만 사용.

### 6.3 아이콘 매핑 (이모지 → Lucide)

| 기존 | 의미 | 교체 (Lucide) |
|---|---|---|
| 📅 | daily report | `calendar-days` |
| 📈 | weekly report | `bar-chart-3` |
| 🗂 | projects | `folder` |
| 🗓 | rooms | `calendar` |
| 🏖 | vacation | `palmtree` |
| 📋 | logs / copy | `clipboard-list` / `copy` |
| ⚙️ | settings | `settings` (또는 `cog`) |
| 📤 | submit / send | `send` |
| 🔄 | sync / refresh | `refresh-cw` |
| 📊 | preview | `table` |
| 🔍 | verify / search | `search` |
| 📥 | download | `download` |
| 📌 | pin | `pin` |
| 🌙 | dark mode | `moon` |
| ☀️ | light mode | `sun` |
| 🎌 | holiday | `flag` |
| ▶ ◀ | nav | `chevron-right` / `chevron-left` |

---

## 7. 상호작용 / 모션

- **Transition duration:** 120-200ms
- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` (Material standard)
- 버튼 hover: filter brightness 1.05 + shadow 한 단계 up
- 버튼 active: `translateY(1px)`
- 카드 hover (interactive): `translateY(-1px)` + shadow up
- 모달 등장: `scale(0.96) → scale(1)` + opacity 0 → 1, 180ms

---

## 8. 다크 모드와의 관계

라이트 = Ko-fi 톤 / 다크 = 자체 톤 (회사 사내 시스템 색 정합성 위해 유지).

다크는 별도 팔레트:
- `--color-bg: #0f1115`
- `--color-surface: #1a1d23`
- `--color-accent: #4a90e2`

라이트와 동일한 **변수명** 을 공유하므로 같은 CSS 룰이 두 테마 모두에서 동작.

---

## 9. 미적용 / 추후 TODO

- Plus Jakarta Sans 웹폰트 import (현재 system fallback 사용)
- Lucide SVG sprite 또는 inline 컴포넌트 도입
- 모든 이모지 아이콘 → SVG 교체
- 버튼을 pill shape 로 일괄 변경 (현재 6-8px radius)
- 카드 그림자 톤 정렬 (현재 일부 다크 톤 잔여)
