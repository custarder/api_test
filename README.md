# Auto Calculate Dev Time

**Auto Calculate Dev Time** 是一款專為 GitHub Issues 設計的自動化工時計算 Action。
當開發者在 Issue 中透過留言標記開始與結束時間，此 Action 會在 Issue 關閉時自動計算總開發工時，並將結果回覆在留言區，讓專案進度與工時追蹤變得自動且透明！

## 核心功能

* **自動化回覆：** Issue 關閉時自動結算，並以機器人留言回報總工時。
* **靈活的時間標記：** 支援直接抓取留言時間，或手動指定特定時間（例如 `dev start at 14:00`）。
* **智能跨日運算：** 內建進階的跨日與週末排除邏輯，精準貼合實際工作狀態。
* **自動標籤管理：** 計算成功自動貼上 `dev-time: settled` 標籤；若格式有誤則標記 `dev-time: error` 並提醒開發者修正。

---

## 快速開始 (Quick Start)

請在你的 Repository 中建立一個檔案：`.github/workflows/auto-calc-time.yml`，並貼上以下內容：

```yaml
name: Auto Calculate Dev Time

on:
  issues:
    types: [closed]
  issue_comment:
    types: [created, edited]
  workflow_dispatch:

permissions:
  issues: write    # 必須開啟寫入權限，才能讓 Action 留言與貼標籤
  contents: read

jobs:
  calculate-time:
    runs-on: ubuntu-latest
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.issue.state == 'closed' }}
    
    # 避免短時間內重複觸發
    concurrency:
      group: calculate-time-group
      cancel-in-progress: false

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Calculate Dev Time
        uses: 你的帳號/你的Repo名稱@v1 # 👈 請替換為你實際發布的版本號
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 留言語法規則 (Syntax)

開發者可以在 Issue 的「本文」或「任何留言」中輸入以下關鍵字來記錄時間（不分大小寫）：

### 開始開發 (Start)
* 預設使用留言當下的時間：`dev start` 或 `dev begin`
* 手動指定特定時間：`dev start at 09:30` 或 `dev start: 09:30`

### 結束開發 (End)
* 預設使用留言當下的時間：`dev end` 或 `end`
* 手動指定特定時間：`dev end at 18:00` 或 `dev end: 18:00`

> **💡 提示：** 系統會掃描 Issue 內的所有留言。如果忘記標記結束時間，系統會預設以「Issue 關閉 (Closed) 的時間」作為結束時間。

---

## ⚙️ 內建工時計算邏輯 (Calculation Rules)

本 Action 內建了貼近實務的企業工時邏輯（時區為 UTC+8 台灣時間）：

1.  **當日完成：** 實算開始至結束的時間。
2.  **跨日完成 (起始日)：** 實算開始時間至當日 24:00 (隔日 00:00)。
3.  **跨日完成 (中間日)：** 遇到週一至週五，每日固定採計 **6.0 小時**；週末不計時。
4.  **跨日完成 (結束日)：** * 若在 10:00 前結案：計算 00:00 至結束的時間。
    * 若在 10:00 後結案：自 10:00 起算至結束的時間。

---

## 輸入參數 (Inputs)

| 參數名稱 | 必填 | 預設值 | 說明 |
| :--- | :---: | :--- | :--- |
| `github-token` | ✅ | `無` | 用來操作 Issue 留言與標籤的 Token，請帶入 `${{ secrets.GITHUB_TOKEN }}` |

---
