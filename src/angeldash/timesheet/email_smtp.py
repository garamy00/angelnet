"""SMTP 이메일 발송 (주간업무보고 외부 발송용).

smtplib 표준 라이브러리만 사용. HTML + plain text alternative 본문 지원.
host/port/TLS/auth 정보는 caller 가 전달 — 모듈 자체는 설정 저장소를 모른다.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)

# 외부 발송은 시간이 오래 걸릴 수 있어 명시적 timeout. 30초면 office365 환경에서도 충분.
SMTP_TIMEOUT_SECONDS = 30


@dataclass
class SmtpConfig:
    """SMTP 발송에 필요한 인증/연결 파라미터."""
    host: str
    port: int
    use_tls: bool      # True → STARTTLS (587), False → SMTPS (465) or plain
    username: str
    password: str


@dataclass
class EmailMessageSpec:
    """발송할 메일 한 통의 헤더 + 본문."""
    from_addr: str
    to: list[str]      # 빈 리스트면 ValueError
    cc: list[str]
    subject: str
    html_body: str     # 비어있어도 OK (그 경우 plain 만)
    plain_body: str    # alternative — HTML 미지원 클라이언트용


class SmtpError(Exception):
    """SMTP 연결/인증/발송 실패. message 는 사용자에게 표시 가능한 한국어."""


def _split_recipients(raw: str) -> list[str]:
    """콤마 또는 세미콜론 구분된 주소 문자열을 리스트로. 빈 값 제거."""
    if not raw:
        return []
    parts = raw.replace(";", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def parse_recipients(to_raw: str, cc_raw: str) -> tuple[list[str], list[str]]:
    """설정 문자열에서 to/cc 리스트로. 외부에서 사용."""
    return _split_recipients(to_raw), _split_recipients(cc_raw)


def _build_message(spec: EmailMessageSpec) -> EmailMessage:
    """EmailMessage 객체 빌드 (multipart/alternative — html + plain)."""
    msg = EmailMessage()
    msg["From"] = spec.from_addr
    msg["To"] = ", ".join(spec.to)
    if spec.cc:
        msg["Cc"] = ", ".join(spec.cc)
    msg["Subject"] = spec.subject

    if spec.html_body:
        # plain 을 fallback 으로 먼저 set 한 뒤 html 을 alternative 로 추가
        msg.set_content(spec.plain_body or "")
        msg.add_alternative(spec.html_body, subtype="html")
    else:
        msg.set_content(spec.plain_body or "")
    return msg


def _connect(cfg: SmtpConfig) -> smtplib.SMTP:
    """SMTP 연결 + (필요 시) STARTTLS. 인증은 별도 step.

    port 465 는 SMTPS 전용이므로 use_tls(STARTTLS) 옵션과 충돌. 명확한 에러로 막는다.
    """
    if cfg.port == 465 and cfg.use_tls:
        raise SmtpError(
            "포트 465 는 SMTPS 전용이라 STARTTLS 와 함께 쓸 수 없습니다. "
            "포트 587 (STARTTLS=on) 또는 465 (STARTTLS=off) 중 선택하세요.",
        )
    if cfg.use_tls:
        # STARTTLS — port 587 (또는 25) 의 일반적 패턴
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=SMTP_TIMEOUT_SECONDS)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    elif cfg.port == 465:
        # SMTPS — 처음부터 TLS
        server = smtplib.SMTP_SSL(
            cfg.host, cfg.port,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        # plain SMTP — 운영에서 흔치 않지만 테스트/사내망용
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=SMTP_TIMEOUT_SECONDS)
    return server


def verify_connection(cfg: SmtpConfig) -> None:
    """연결 + AUTH 만 검증 (실제 발송 없음). Test 버튼이 호출.

    실패 시 SmtpError. 성공 시 None.
    """
    try:
        server = _connect(cfg)
    except (OSError, smtplib.SMTPException) as exc:
        raise SmtpError(f"SMTP 연결 실패: {exc}") from exc

    try:
        server.login(cfg.username, cfg.password)
    except smtplib.SMTPAuthenticationError as exc:
        server.close()
        raise SmtpError(f"SMTP 인증 실패: {exc.smtp_code} {exc.smtp_error!r}") from exc
    except smtplib.SMTPException as exc:
        server.close()
        raise SmtpError(f"SMTP 로그인 오류: {exc}") from exc

    try:
        server.quit()
    except smtplib.SMTPException:
        # quit 실패는 검증 결과에 영향 없음 (이미 인증 OK)
        pass

    logger.info(
        "SMTP verify ok host=%s port=%d user=%s",
        cfg.host, cfg.port, cfg.username,
    )


def send_email(cfg: SmtpConfig, spec: EmailMessageSpec) -> None:
    """메일 한 통 발송. 실패 시 SmtpError."""
    if not spec.to:
        raise SmtpError("받는사람(To) 이 비어있습니다")
    if not spec.from_addr:
        raise SmtpError("보내는사람(From) 이 비어있습니다")

    msg = _build_message(spec)

    try:
        server = _connect(cfg)
    except (OSError, smtplib.SMTPException) as exc:
        raise SmtpError(f"SMTP 연결 실패: {exc}") from exc

    try:
        server.login(cfg.username, cfg.password)
    except smtplib.SMTPAuthenticationError as exc:
        server.close()
        raise SmtpError(f"SMTP 인증 실패: {exc.smtp_code} {exc.smtp_error!r}") from exc
    except smtplib.SMTPException as exc:
        server.close()
        raise SmtpError(f"SMTP 로그인 오류: {exc}") from exc

    try:
        # to + cc 모두 전송 대상에 포함. BCC 는 현재 미지원.
        server.send_message(msg, to_addrs=spec.to + spec.cc)
    except smtplib.SMTPException as exc:
        server.close()
        raise SmtpError(f"메일 전송 실패: {exc}") from exc
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass

    logger.info(
        "email sent from=%s to=%s cc=%s subject=%s",
        spec.from_addr, spec.to, spec.cc, spec.subject,
    )
