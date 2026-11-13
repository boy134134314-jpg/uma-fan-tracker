# -*- coding: utf-8 -*-
"""
赛马娘社团粉丝自动抓取
每小时由GitHub Actions触发，抓 umamusume.space 数据写腾讯文档
"""
import os
import re
import json
import datetime
import urllib.request
import urllib.parse

API = "http://umamusume.space/uma/api/circles/110231887"
DOCS_BASE = "https://docs.qq.com"
FILE_ID = "300000000$CbvczzLVABzr"
SHEET = "BB08J2"            # 主表 工作表1
SHEET_MONTHLY = "z4hWf9"    # 月供总表
SHEET_HISTORY = "MMDFno"    # 历史记录

# 日供门槛（天）
MIN_STD = 3000000   # 最低日供300万
MAX_STD = 7000000   # 最高日供700万（主表已不用，仅保留）


def _cell(v):
    if isinstance(v, bool):
        return {"cellValue": {"text": str(v)}}
    if isinstance(v, (int, float)):
        return {"cellValue": {"number": v}}
    return {"cellValue": {"text": str(v)}}


def write_range(token, cid, oid, start_row, start_col, rows, sheet_id=SHEET):
    body = {
        "requests": [{
            "updateRangeRequest": {
                "sheetId": sheet_id,
                "gridData": {
                    "startRow": start_row,
                    "startColumn": start_col,
                    "rows": rows,
                },
            }
        }]
    }
    data = json.dumps(body).encode("utf-8")
    url = DOCS_BASE + "/openapi/spreadsheet/v3/files/%s/batchUpdate" % urllib.parse.quote(FILE_ID, safe="")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Access-Token": token,
            "Client-Id": cid,
            "Open-Id": oid,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("write resp:", resp.read().decode("utf-8"))


def _cell_text(c):
    cv = (c or {}).get("cellValue") or {}
    if "number" in cv and cv["number"] is not None:
        return cv["number"]
    return cv.get("text", "")


def read_range(token, cid, oid, sheet_id, rng):
    url = DOCS_BASE + "/openapi/spreadsheet/v3/files/%s/%s/%s" % (
        urllib.parse.quote(FILE_ID, safe=""),
        sheet_id,
        urllib.parse.quote(rng, safe=""),
    )
    req = urllib.request.Request(
        url, headers={
            "Access-Token": token,
            "Client-Id": cid,
            "Open-Id": oid,
            "Accept": "application/json",
        }, method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    rows = (body.get("data") or {}).get("gridData", {}).get("rows", [])
    out = []
    for row in rows:
        out.append([_cell_text(c) for c in (row.get("values") or [])])
    return out


def _norm(name):
    # 成员名归一化：去空白与常见全/半角标点，便于跨表匹配
    return re.sub(r"[\s，,．.。・·!！?？]", "", str(name or ""))


def main():
    with urllib.request.urlopen(API, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    bj = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    now = bj.strftime("%Y-%m-%d %H:%M")
    today = bj.date()
    month_start = datetime.date(today.year, today.month, 1)
    days_elapsed = (today - month_start).days + 1

    # ranking字段可能为None，从month_point_history最后一条取
    mp_last = data["month_point_history"][-1] if data.get("month_point_history") else {}
    point = mp_last.get("point", 0)
    rank = mp_last.get("rank", 0)

    values = [
        ["更新时间", now, "社团当月粉丝", point, "排名", rank],
        ["成员", "当月粉丝", "今日新增", "累计粉丝", "当月日供", "在团天数"],
    ]

    members = sorted(data["members"], key=lambda m: -m["month_fan"])

    # 计算每个成员的在团天数
    days_map = {}
    for m in members:
        join_date = datetime.datetime.fromisoformat(m["join_time"]).date()
        if join_date <= month_start:
            days = days_elapsed
        else:
            days = (today - join_date).days + 1
        days = max(days, 1)
        days_map[m["member_name"]] = days
        values.append([
            m["member_name"],
            m["month_fan"],
            m["today_delta"],
            m["fan"],
            round(m["month_fan"] / days),
            days,
        ])

    # G:K列：总日供差 + 日供不达标名单（startRow=2, startColumn=6）
    lo = [m["member_name"] for m in members if m["month_fan"] < MIN_STD * days_map[m["member_name"]]]
    gh_rows = [{"values": [
        _cell("总日供差"), _cell(""), _cell("日供不达标的成员"), _cell(""), _cell("")
    ]}]
    for i, m in enumerate(members):
        d = days_map[m["member_name"]]
        gh_rows.append({"values": [
            _cell(int(m["month_fan"]) - MIN_STD * d),
            _cell(""),
            _cell(lo[i] if i < len(lo) else ""),
            _cell(""),
            _cell(""),
        ]})

    # O列：入团时间（startRow=2, startColumn=14）
    join_rows = [{"values": [_cell("入团时间")]}]
    for m in members:
        join_rows.append({"values": [_cell(m["join_time"][:10])]})

    token = os.environ["TD_ACCESS_TOKEN"]
    cid = os.environ["TD_CLIENT_ID"]
    oid = os.environ["TD_OPEN_ID"]

    # 写B列主表（末尾补5行空，清掉退团成员的残留旧数据）
    main_rows = [{"values": [_cell(v) for v in row]} for row in values]
    for _ in range(5):
        main_rows.append({"values": [_cell("") for _ in range(6)]})
    write_range(token, cid, oid, 1, 1, main_rows)

    # 写G:K列（末尾补5行空）
    for _ in range(5):
        gh_rows.append({"values": [_cell("") for _ in range(5)]})
    write_range(token, cid, oid, 2, 6, gh_rows)

    # 写O列入团时间（末尾补5行空）
    for _ in range(5):
        join_rows.append({"values": [_cell("")]})
    write_range(token, cid, oid, 2, 14, join_rows)

    # ---- 月供总表：上月整月结算定格 ----
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1
    prev_first = datetime.date(prev_year, prev_month, 1)
    prev_last = month_start - datetime.timedelta(days=1)
    prev_days = (month_start - prev_first).days

    fhist = data.get("members_fan_history", {})

    def snap(vid, prefix):
        h = fhist.get(str(vid), {}).get("history", [])
        for p in h:
            if p["captured_at"].startswith(prefix):
                return p["fan"]
        return None

    # 读历史记录表，定位“上月初粉丝”列，建 归一化名->月初累计 基线
    hist_rows = read_range(token, cid, oid, SHEET_HISTORY, "A1:G40")
    header = hist_rows[1] if len(hist_rows) > 1 else []
    label = "%d月初粉丝" % prev_month
    col_idx = next((i for i, h in enumerate(header) if str(h).strip() == label), None)
    baseline = {}
    for r in hist_rows[2:]:
        if r and str(r[0]).strip():
            v = r[col_idx] if col_idx is not None and len(r) > col_idx else ""
            baseline[_norm(r[0])] = v
    print("history header:", header, "| baseline col:", col_idx, "| baseline n:", len(baseline))

    month_prefix = month_start.strftime("%Y-%m-%dT00:00:00")
    monthly_rows = []
    for m in members:
        name = m["member_name"]
        join = datetime.datetime.fromisoformat(m["join_time"]).date()
        f_end = snap(m["viewer_id"], month_prefix)
        f_start = baseline.get(_norm(name))
        if join > prev_last:
            # 本月新入团，上月不在团：只留名字，数值留空
            monthly_rows.append({"values": [_cell(name), _cell(""), _cell(""), _cell(""), _cell("")]})
            continue
        if join <= prev_first:
            hdays = prev_days
        else:
            hdays = (prev_last - join).days + 1
        hdays = max(hdays, 1)
        e_val = f_start if f_start not in ("", None) else ""
        f_val = f_end if f_end is not None else ""
        if isinstance(e_val, (int, float)) and isinstance(f_end, (int, float)):
            daily = round((f_end - e_val) / hdays)
        else:
            daily = ""
        monthly_rows.append({"values": [
            _cell(name), _cell(e_val), _cell(f_val), _cell(daily), _cell(hdays),
        ]})

    # 写月供总表：C2结算月份；D3起成员数据（末尾补5行空）
    month_row = [{"values": [_cell("%d-%02d" % (prev_year, prev_month))]}]
    write_range(token, cid, oid, 1, 2, month_row, sheet_id=SHEET_MONTHLY)
    for _ in range(5):
        monthly_rows.append({"values": [_cell("") for _ in range(5)]})
    write_range(token, cid, oid, 2, 3, monthly_rows, sheet_id=SHEET_MONTHLY)

    print("ok, members=%d, point=%s, rank=%s, days=%d, join_written=%d" % (
        len(members), point, rank, days_elapsed, len(join_rows)))


if __name__ == "__main__":
    main()
