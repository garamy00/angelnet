"""기본 출력 템플릿 (Jinja2 문자열).

사용자가 settings 에서 override 하지 않으면 이 값이 사용된다.
포맷은 사용자 본인의 기존 일일보고 스타일을 그대로 따른다.

DEFAULT 가 변경될 때마다 이전 버전을 OBSOLETE_DEFAULTS 에 누적한다.
서버 시작 시 db.cleanup_obsolete_default_settings() 가 DB 의 저장된 값이 그 중
하나와 byte-identical 이면 "사용자가 커스터마이즈하지 않은 default 잔재" 로 보고
삭제 → 다음 read 때 새 DEFAULT 가 사용된다.
"""

from __future__ import annotations

# 팀장 보고 — 단일 날짜 또는 평탄화된 entries 리스트 컨텍스트.
# 자유 메모(week_notes) 는 컨텍스트에 주지 않아 자동으로 포함되지 않는다.
# separator 를 entry 시작 쪽에서 emit 하여 (UpNote 본문 패턴과 동일) body 가 비어도
# 빈 줄이 두 개 생기지 않게 한다.
DEFAULT_TEAM_REPORT = """\
{%- for entry in entries -%}
{%- if not loop.first %}

{% endif -%}
*) {{ entry.category }}
{%- if entry.body %}
{{ entry.body }}
{%- endif -%}
{%- endfor -%}
{%- if source_commit_label %}

*) 소스 Commit
 - {{ source_commit_label }}
{%- endif -%}
{%- if misc_note %}

*) 기타
 - {{ misc_note }}
{%- endif -%}"""


# UpNote 노트 제목 — 주 단위.
DEFAULT_UPNOTE_TITLE = "{{ yy }}년 W{{ ww }} ({{ week_start_mmdd }} ~ {{ week_end_mmdd }})"


# UpNote 노트 본문 — 그 주의 모든 날짜 + 자유 메모(있을 때).
# separator 를 entry/day 의 시작 쪽에서 명시적으로 출력하여
# Jinja2 의 {% if %} 라인 자체 newline 누적 문제를 회피한다.
# 결과: 카테고리 사이 빈 줄 1개, 날짜 블록 사이 빈 줄 2개.
DEFAULT_UPNOTE_BODY = """\
{%- for day in days -%}
{%- if not loop.first %}


{% endif -%}
{{ yy }}년 < {{ day.mm }}/{{ day.dd }}, {{ day.day_kr }} >
{% for entry in day.entries -%}
{%- if not loop.first %}

{% endif -%}
*) {{ entry.category }}
{%- if entry.body %}
{{ entry.body }}
{%- endif -%}
{%- endfor %}
{%- if day.source_commit_label %}

*) 소스 Commit
 - {{ day.source_commit_label }}
{%- endif -%}
{%- if day.misc_note %}

*) 기타
 - {{ day.misc_note }}
{%- endif -%}
{%- endfor %}
{%- if week_notes %}


───────────────────────────────
📝 메모

{{ week_notes }}
{%- endif %}"""


# ─── 과거 default 누적 ─────────────────────────────────
# DEFAULT_* 를 바꿀 때마다 *직전* default 를 이 dict 에 추가한다.
# 서버 시작 시 DB 에 저장된 사용자 설정이 여기 등장하는 값과 byte-identical 이면
# = "사용자가 별도로 편집한 적 없는 default 잔재" 로 보고 자동 삭제.

_OBSOLETE_TEAM_REPORT_V1 = """\
{%- for entry in entries -%}
*) {{ entry.category }}
{{ entry.body }}
{%- if not loop.last %}

{% endif -%}
{%- endfor -%}
{%- if source_commit_label %}

*) 소스 Commit
 - {{ source_commit_label }}
{%- endif -%}
{%- if misc_note %}

*) 기타
 - {{ misc_note }}
{%- endif -%}"""

_OBSOLETE_UPNOTE_BODY_V1 = """\
{%- for day in days -%}
{%- if not loop.first %}


{% endif -%}
{{ yy }}년 < {{ day.mm }}/{{ day.dd }}, {{ day.day_kr }} >
{% for entry in day.entries -%}
{%- if not loop.first %}

{% endif -%}
*) {{ entry.category }}
{{ entry.body }}
{%- endfor %}
{%- if day.source_commit_label %}

*) 소스 Commit
 - {{ day.source_commit_label }}
{%- endif -%}
{%- if day.misc_note %}

*) 기타
 - {{ day.misc_note }}
{%- endif -%}
{%- endfor %}
{%- if week_notes %}


───────────────────────────────
📝 메모

{{ week_notes }}
{%- endif %}"""


OBSOLETE_DEFAULTS: dict[str, list[str]] = {
    "team_report.template": [_OBSOLETE_TEAM_REPORT_V1],
    "upnote.body_template": [_OBSOLETE_UPNOTE_BODY_V1],
}
