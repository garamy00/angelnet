"""calendar.js 에서 saveReservation 함수 본문 + createReservation 호출 인자 추출."""

import asyncio
import os
import re
import sys
from urllib.parse import urlencode

from angeldash.auth import KeychainStore
from angeldash.client import (
    TS_LOGIN, TS_REDIRECT_PARAMS, TS_REDIRECT_PATH, AngelNetClient,
)


async def main():
    # 사용자 ID 는 환경변수에서 읽음
    user_id = os.environ.get("ANGELNET_USER")
    if not user_id:
        raise SystemExit("ANGELNET_USER 환경변수를 설정하라")

    pwd = KeychainStore(account=user_id).get()
    if not pwd:
        raise SystemExit("no keychain pw")
    client = AngelNetClient(user_id=user_id)
    try:
        await client.login(pwd)
        rq = urlencode(TS_REDIRECT_PARAMS)
        await client._http.post(
            TS_LOGIN,
            data={"userId": user_id, "password": pwd,
                  "redirectUrl": f"{TS_REDIRECT_PATH}?{rq}"},
        )
        url = "https://timesheet.uangel.com/resources/js/meeting-room-calendar.js"
        text = (await client._http.get(url)).text

        # createReservation, updateReservation 호출 (인자 0~800자)
        print("=== createReservation/updateReservation API call sites ===")
        for m in re.finditer(r"\.(?:createReservation|updateReservation)\s*\(([\s\S]{0,800}?)\)", text):
            print("--- call ---")
            print(m.group(0)[:1000])
            print()

        # saveReservation / submitReservation / handleSave 함수 본문
        for fn in ("saveReservation", "submitReservation", "handleSave"):
            for m in re.finditer(rf"(?:async\s+)?{fn}\s*[=:]?\s*(?:async\s+)?\(([^)]*)\)\s*(?:=>)?\s*\{{", text):
                start = m.start()
                depth = 0
                end = start
                for i in range(m.end() - 1, len(text)):
                    if text[i] == "{": depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1; break
                body = text[start:end]
                if len(body) > 5000:
                    body = body[:5000] + "\n... (truncated)"
                print(f"--- {fn} ---")
                print(body)
                print()
    finally:
        await client.close()

asyncio.run(main())
