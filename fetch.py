# -*- coding: utf-8 -*-
"""
GitHub Actions 定时任务：每2小时抓取赛马娘社团成员粉丝 → 覆盖写入腾讯文档在线表格
数据源: umamusume.space 公开API（免登录）http://umamusume.space/uma/api/circles/110231887
写入: 腾讯文档 OpenAPI v3 批量更新 /openapi/spreadsheet/v3/files/{fileId}/batchUpdate
环境变量（GitHub Secrets）:
  TD_CLIENT_ID     开放平台 client_id（应用ID）
  TD_ACCESS_TOKEN  开放平台 access_token（30天有效，到期需重置并更新 Secret）
  TD_OPEN_ID       开放平台 open_id
  TD_BOOK_ID       在线表格 fileId，含 $ 号（300000000$CbvczzLVABzr）
  TD_SHEET         子表 ID（BB08J2）

写入布局：
  B2:F33  更新时间信息行 + 表头 + 成员数据（成员/当月粉丝/今日新增/当月日供/在团日期）
  G3:K33  自动更新：高于最低(月粉-最低标准x在团天数) / 高于最高(月粉-最高标准x在团天数)
          / 空列 / 不够最低的(月粉<最低标准x天数) / 不够最高的(月粉<最高标准x天数)
  标准值从文档 A 列读取（A3=日供最低粉丝、A6=日供最高粉丝），用户手改 A 列即可生效；
  读不到时回退默认 4000000 / 5000000
  在团天数口径同当月日供：20:00后入团从次日00:00起算，入团当天兜底1天
"""
import os
import json
import datetime
import urllib.request

API = "http://umamusume.space/uma/api/circles/110231887"
DOCS_BASE = "https://docs.qq.com"


def write_sheet(book_id, sheet_id, token, values, start_row, start_column):
    """v3 批量更新：全量覆盖写入指定子表，从 (start_row, start_column) 起（0 索引）"""
    rows = []
    for row in values:
        cells = [{"cellValue": {"text": "" if v is None else str(v)}} for v in row]
        rows.append({"values": cells})
    body = json.dumps({
        "requests": [{
            "updateRangeRequest": {
                "sheetId": sheet_id,
                "gridData": {
                    "startRow": start_row,
                    "startColumn": start_column,
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
        raise RuntimeError("写入失败 code=%s msg=%s" % (parsed.get("code"), parsed.get("message", "")))
    for r in parsed.get("data", {}).get("responses", []):
        if r.get("code", 0) != 0:
            raise RuntimeError("写入操作失败: %s" % json.dumps(r, ensure_ascii=False))


def read_range(book_id, sheet_id, token, range_name):
    """读取表格指定区域，返回二维列表（每格为字符串或数字或空）"""
    req = urllib.request.Request(
        DOCS_BASE + "/openapi/spreadsheet/v3/files/%s/%s/%s" % (book_id, sheet_id, range_name),
        headers={
            "Access-Token": token,
            "Client-Id": os.environ["TD_CLIENT_ID"],
            "Open-Id": os.environ["TD_OPEN_ID"],
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if out.get("code", 0) != 0:
        raise RuntimeError("读取失败 code=%s msg=%s" % (out.get("code"), out.get("message", "")))
    rows = out.get("gridData", {}).get("rows", [])
    result = []
    for row in rows:
        line = []
        for v in row.get("values", []):
            cv = v.get("cellValue") or {}
            if "text" in cv:
                line.append(cv["text"])
            elif "number" in cv:
                line.append(cv["number"])
            else:
                line.append("")
        result.append(line)
    return result


def read_standard(book_id, sheet_id, token):
    """从 A 列读取日供最低/最高标准（标签下一行的数值）；读不到时回退默认值"""
    min_std = 4000000
    max_std = 5000000
    try:
        rows = read_range(book_id, sheet_id, token, "A1:A10")
        for i in range(len(rows) - 1):
            label = str(rows[i][0] if rows[i] else "").strip()
            val_raw = rows[i + 1][0] if rows[i + 1] else ""
            if not label or val_raw == "":
                continue
            try:
                val = float(val_raw)
            except (TypeError, ValueError):
                continue
            if "最低" in label:
                min_std = val
            elif "最高" in label:
                max_std = val
    except Exception as e:
        print("read standard failed, use defaults:", e)
    print("标准值: 日供最低=%.0f 日供最高=%.0f" % (min_std, max_std))
    return min_std, max_std


def calc_days(join_dt, month_start_dt, today):
    """在团天数（口径同当月日供）：20:00后入团从次日00:00起算；10/1前入团从本月起算"""
    if join_dt.time() >= datetime.time(20, 0):
        start_dt = datetime.datetime.combine(
            join_dt.date() + datetime.timedelta(days=1), datetime.time(0, 0)
        )
    else:
        start_dt = join_dt
    start_dt = max(start_dt, month_start_dt)
    days = (today - start_dt.date()).days + 1
    return days, start_dt


def main():
    # 1. 抓社团接口
    with urllib.request.urlopen(API, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # 数据源 ranking 字段临时缺失时跳过本次写入（保留表格上次成功数据），下次定时任务自动重试
    if data.get("ranking") is None:
        raise RuntimeError("数据源 ranking 缺失，跳过本次写入（数据源临时故障），下次定时任务自动重试")

    # 更新时间 = 网站数据本身的更新时间（ranking.updated_at）；接口无该字段时兜底用运行时间
    try:
        now = datetime.datetime.fromisoformat(data["ranking"]["updated_at"]).strftime("%Y-%m-%d %H:%M")
    except Exception:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today()

    # 2. 构造 B2:F33 内容（第一行社团信息 6 列；表头与成员数据 5 列）
    point = data["ranking"]["point"]
    values = [
        ["更新时间", now, "社团当月粉丝", point, "排名", data["ranking"]["rank"]],
        ["成员", "当月粉丝", "今日新增", "当月日供", "在团日期"],
    ]
    # 本月起算基准 = 数据源的 month_start（含时分，如 10-01 05:00）
    month_start_dt = datetime.datetime.fromisoformat(data["month_start"]).replace(tzinfo=None)
    members = sorted(data["members"], key=lambda m: -m["month_fan"])
    days_map = {}
    for m in members:
        join_dt = datetime.datetime.fromisoformat(m["join_time"])
        days, start_dt = calc_days(join_dt, month_start_dt, today)
        days_map[m["member_name"]] = days
        values.append([
            m["member_name"],
            m["month_fan"],
            m["today_delta"],
            round(m["month_fan"] / max(days, 1)),
            start_dt.strftime("%m-%d %H:%M"),
        ])

    # 3. 读 A 列标准值（用户手改即可生效），构造 G3:K33（高于最低/高于最高/空列/不够最低的/不够最高的）
    token = os.environ["TD_ACCESS_TOKEN"]
    book_id = os.environ["TD_BOOK_ID"]
    sheet_id = os.environ["TD_SHEET"]
    min_std, max_std = read_standard(book_id, sheet_id, token)
    lo = [m["member_name"] for m in members if m["month_fan"] < min_std * days_map[m["member_name"]]]
    hi = [m["member_name"] for m in members if m["month_fan"] < max_std * days_map[m["member_name"]]]
    gh_values = [["高于最低", "高于最高", "", "不够最低的", "不够最高的"]]
    for i, m in enumerate(members):
        d = days_map[m["member_name"]]
        gh_values.append([
            int(m["month_fan"] - min_std * d),
            int(m["month_fan"] - max_std * d),
            "",
            lo[i] if i < len(lo) else "",
            hi[i] if i < len(hi) else "",
        ])

    # 4. 用开放平台发的 access_token 写入腾讯文档
    write_sheet(book_id, sheet_id, token, values, 1, 1)
    write_sheet(book_id, sheet_id, token, gh_values, 2, 6)

    print("ok, members=%d, point=%s, rank=%s, 不够最低=%d, 不够最高=%d"
          % (len(members), point, data["ranking"]["rank"], len(lo), len(hi)))


if __name__ == "__main__":
    main()
