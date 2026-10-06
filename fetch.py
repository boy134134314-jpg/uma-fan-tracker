# -*- coding: utf-8 -*-
"""
GitHub Actions å®æ¶ä»»å¡ï¼æ¯2å°æ¶æåèµé©¬å¨ç¤¾å¢æåç²ä¸ â è¦çåå¥è¾è®¯ææ¡£å¨çº¿è¡¨æ ¼
æ°æ®æº: umamusume.space å¬å¼APIï¼åç»å½ï¼http://umamusume.space/uma/api/circles/110231887
åå¥: è¾è®¯ææ¡£ OpenAPI v3 æ¹éæ´æ° /openapi/spreadsheet/v3/files/{fileId}/batchUpdate
ç¯å¢åéï¼GitHub Secretsï¼:
  TD_CLIENT_ID     å¼æ¾å¹³å° client_idï¼åºç¨IDï¼
  TD_ACCESS_TOKEN  å¼æ¾å¹³å° access_tokenï¼30å¤©ææï¼å°æééç½®å¹¶æ´æ° Secretï¼
  TD_OPEN_ID       å¼æ¾å¹³å° open_id
  TD_BOOK_ID       å¨çº¿è¡¨æ ¼ fileIdï¼å« $ å·ï¼300000000$CbvczzLVABzrï¼
  TD_SHEET         å­è¡¨ IDï¼BB08J2ï¼
"""
import os
import json
import datetime
import urllib.request

API = "http://umamusume.space/uma/api/circles/110231887"
DOCS_BASE = "https://docs.qq.com"


def write_sheet(book_id, sheet_id, token, values):
    """v3 æ¹éæ´æ°ï¼å¨éè¦çåå¥æå®å­è¡¨ï¼ä»ç¬¬1è¡ç¬¬1åå¼å§"""
    rows = []
    for row in values:
        cells = [{"cellValue": {"text": "" if v is None else str(v)}} for v in row]
        rows.append({"values": cells})
    body = json.dumps({
        "requests": [{
            "updateRangeRequest": {
                "sheetId": sheet_id,
                "gridData": {
                    "startRow": 1,
                    "startColumn": 1,
                    "rows": rows,
                },
            }
        }]
    }).encode("utf-8")
    req = urllib.request.Request(
        DOCS_BASE + "/openapi/spreadsheet/v3/files/%s/batchUpdate" % book_id,
        data=body,
        headers={
            "Access-Token": token,
            "Client-Id": os.environ["TD_CLIENT_ID"],
            "Open-Id": os.environ["TD_OPEN_ID"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = resp.read().decode("utf-8")
    print("write resp:", out)
    parsed = json.loads(out)
    if parsed.get("code", 0) != 0:
        raise RuntimeError("åå¥å¤±è´¥ code=%s msg=%s" % (parsed.get("code"), parsed.get("message", "")))
    for r in parsed.get("data", {}).get("responses", []):
        if r.get("code", 0) != 0:
            raise RuntimeError("åå¥æä½å¤±è´¥: %s" % json.dumps(r, ensure_ascii=False))


def main():
    # 1. æç¤¾å¢æ¥å£
    with urllib.request.urlopen(API, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # æ´æ°æ¶é´ = ç½ç«æ°æ®æ¬èº«çæ´æ°æ¶é´ï¼ranking.updated_atï¼ï¼æ¥å£æ è¯¥å­æ®µæ¶ååºç¨è¿è¡æ¶é´
    try:
        now = datetime.datetime.fromisoformat(data["ranking"]["updated_at"]).strftime("%Y-%m-%d %H:%M")
    except Exception:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today()

    # 2. æé è¡¨æ ¼åå®¹ï¼6åï¼æ´æ°æ¶é´/ç¤¾å¢å½æç²ä¸/æå ä¸è¡ï¼è¡¨å¤´ä¸è¡ï¼30åæåï¼
    point = data["ranking"]["point"]
    values = [
        ["æ´æ°æ¶é´", now, "ç¤¾å¢å½æç²ä¸", point, "æå", data["ranking"]["rank"]],
        ["æå", "å½æç²ä¸", "ä»æ¥æ°å¢", "ç´¯è®¡ç²ä¸", "å½ææ¥ä¾", "å¨å¢å¤©æ°"],
    ]
    members = sorted(data["members"], key=lambda m: -m["month_fan"])
    for m in members:
        join_date = datetime.datetime.fromisoformat(m["join_time"]).date()
        month_start = datetime.date(today.year, today.month, 1)
        # å¨å¢å¤©æ° = æ¬æå·²è¿å¤©æ°ï¼10/1 åå¥å¢çä» 10/1 èµ·ç®ï¼æ¬æå¥å¢çä»å¥å¢æ¥èµ·ç®ï¼
        days = (today - max(join_date, month_start)).days + 1
        values.append([
            m["member_name"],
            m["month_fan"],
            m["today_delta"],
            m["fan"],
            round(m["month_fan"] / days),
            days,
        ])

    # 3. ç¨å¼æ¾å¹³å°åç access_token åå¥è¾è®¯ææ¡£
    token = os.environ["TD_ACCESS_TOKEN"]
    write_sheet(os.environ["TD_BOOK_ID"], os.environ["TD_SHEET"], token, values)

    print("ok, members=%d, point=%s, rank=%s" % (len(members), point, data["ranking"]["rank"]))


if __name__ == "__main__":
    main()
