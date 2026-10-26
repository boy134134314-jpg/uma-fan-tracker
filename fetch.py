# -*- coding: utf-8 -*-
"""
赛马娘社团粉丝自动抓取
每小时由GitHub Actions触发，抓 umamusume.space 数据写腾讯文档
"""
import os
import json
import datetime
import urllib.request
import urllib.parse

API = "http://umamusume.space/uma/api/circles/110231887"
DOCS_BASE = "https://docs.qq.com"
FILE_ID = "300000000$CbvczzLVABzr"
SHEET = "BB08J2"

# 日供门槛（天）
MIN_STD = 3000000   # 最低日供300万
MAX_STD = 5000000   # 最高日供500万


def _cell(v):
    if isinstance(v, bool):
        return {"cellValue": {"text": str(v)}}
    if isinstance(v, (int, float)):
        return {"cellValue": {"number": v}}
    return {"cellValue": {"text": str(v)}}


def write_range(token, cid, oid, start_row, start_col, rows):
    body = {
        "requests": [{
            "updateRangeRequest": {
                "sheetId": SHEET,
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

    # G:K列：高于最低/最高（startRow=2, startColumn=6）
    lo = [m["member_name"] for m in members if m["month_fan"] < MIN_STD * days_map[m["member_name"]]]
    hi = [m["member_name"] for m in members if m["month_fan"] > MAX_STD * days_map[m["member_name"]]]
    gh_rows = [{"values": [
        _cell("高于最低"), _cell("高于最高"), _cell(""), _cell("不够最低的"), _cell("不够最高的")
    ]}]
    for i, m in enumerate(members):
        d = days_map[m["member_name"]]
        gh_rows.append({"values": [
            _cell(int(m["month_fan"]) - MIN_STD * d),
            _cell(int(m["month_fan"]) - MAX_STD * d),
            _cell(""),
            _cell(lo[i] if i < len(lo) else ""),
            _cell(hi[i] if i < len(hi) else ""),
        ]})

    # O列：入团时间（startRow=2, startColumn=14）
    join_rows = [{"values": [_cell("入团时间")]}]
    for m in members:
        join_rows.append({"values": [_cell(m["join_time"][:10])]})

    token = os.environ["TD_ACCESS_TOKEN"]
    cid = os.environ["TD_CLIENT_ID"]
    oid = os.environ["TD_OPEN_ID"]

    # 写B列主表
    main_rows = [{"values": [_cell(v) for v in row]} for row in values]
    write_range(token, cid, oid, 1, 1, main_rows)

    # 写G:K列
    write_range(token, cid, oid, 2, 6, gh_rows)

    # 写O列入团时间
    write_range(token, cid, oid, 2, 14, join_rows)

    print("ok, members=%d, point=%s, rank=%s, days=%d, join_written=%d" % (
        len(members), point, rank, days_elapsed, len(join_rows)))


if __name__ == "__main__":
    main()
