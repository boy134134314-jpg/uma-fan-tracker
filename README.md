# uma-fan-tracker

GitHub Actions 定时抓取赛马娘社团 110231887（umamusume.space）粉丝数据，写入腾讯文档在线表格。

- 数据源：`http://umamusume.space/uma/api/circles/110231887`（公开 API，免登录，每小时快照）
- 频率：每 2 小时（GitHub Actions schedule，UTC 每 2 小时整点）
- 写入：腾讯文档表格 fileId `300000000$CbvczzLVABzr`，子表 `BB08J2`，覆盖写 B2:G33

## 所需 Secrets

| Secret | 说明 |
|---|---|
| TD_CLIENT_ID | 腾讯文档开放平台应用 ID |
| TD_ACCESS_TOKEN | 开放平台 access_token（30 天有效，到期需重置并更新） |
| TD_OPEN_ID | 开放平台 open_id |
| TD_BOOK_ID | 表格 fileId（`300000000$CbvczzLVABzr`） |
| TD_SHEET | 子表 ID（`BB08J2`） |

## 手动触发

Actions → fetch-fans → Run workflow。

## 注意事项

- access_token 有效期至 2026/10/30 22:00，到期前 1 天去腾讯文档开放平台点「重置」并更新 Secret。
- 免费：公共仓库 Actions 无限分钟。
