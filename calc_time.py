import os
import re
from datetime import time,datetime, timezone, timedelta
from github import Github, Auth
from dotenv import load_dotenv
import logging

load_dotenv(override=True)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")

START_PATTERN = re.compile(r"(?:dev\s*begin|dev\s*start)(?:\s*(?:at|:|：)\s*(\d{1,2}:\d{2}))?", re.IGNORECASE)
END_PATTERN = re.compile(r"(?:dev\s*end|end)(?:\s*(?:at|:|：)\s*(\d{1,2}:\d{2}))?", re.IGNORECASE)
TZ_TW = timezone(timedelta(hours=8))
DEV_TIME_ERROR = "dev-time: error"
DEV_TIME_SETTLED = "dev-time: settled"

def calculate_working_hours(start_dt, end_dt):
    """
    1. 中間日：週一至週五，固定 6.0 小時
    2. 起始日：實算至當日 24:00 (隔日 00:00)
    3. 結束日：10:00 前結案計 (00:00~結束)，10:00 後結案計 (10:00~結束)
    """
    if end_dt < start_dt:
        return -1

    tz = start_dt.tzinfo
    total_hours = 0.0
    
    # --- 情況 A：當日完成 (規則 5) ---
    # 不限窗口，計算實際開始至結束
    if start_dt.date() == end_dt.date():
        if start_dt.weekday() < 5:
            total_hours = (end_dt - start_dt).total_seconds() / 3600
        return round(total_hours, 1)

    # --- 情況 B：跨日完成 ---
    curr_date = start_dt.date()
    end_date = end_dt.date()

    # 1. 起始日 (規則 4)
    # 不限窗口起點，但結束固定為 18:00
    if curr_date.weekday() < 5:
        next_day_midnight = datetime.combine(curr_date + timedelta(days=1), time.min, tzinfo=tz)
        if start_dt < next_day_midnight:
            total_hours += (next_day_midnight - start_dt).total_seconds() / 3600

    # 2. 中間日 (規則 3)
    # 固定計 6.0 小時
    check_date = curr_date + timedelta(days=1)
    while check_date < end_date:
        if check_date.weekday() < 5:
            total_hours += 6.0
        check_date += timedelta(days=1)

    # 3. 結束日 (規則 5)
    # 從 10:00 開始，不限窗口結束點
    if end_date.weekday() < 5:
        ten_am = datetime.combine(end_date, time(10, 0), tzinfo=tz)
        day_start = datetime.combine(end_date, time.min, tzinfo=tz)

        if end_dt <= ten_am:
            # 【凌晨邏輯】如果在 10:00 前就結案，計算從 00:00 到結束的時間
            total_hours += (end_dt - day_start).total_seconds() / 3600
        else:
            # 【標準邏輯】如果是 10:00 後結案，從 10:00 起算
            total_hours += (end_dt - ten_am).total_seconds() / 3600

    return round(total_hours, 1)

def process_closed_issues():
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(REPO_NAME)
    
    logging.info("啟動開發時間計算排程...")

    success_count = 0
    error_count = 0

    query = f"repo:{repo.full_name} is:issue is:closed created:>=2026-01-01 -label:\"{DEV_TIME_SETTLED}\""
    unprocessed_issues = g.search_issues(query, sort='updated', order='desc')
    
    for issue in unprocessed_issues:
        comments = list(issue.get_comments())
        
        start_time = None
        end_time = None
        
        texts_to_scan = [(issue.created_at, issue.body or "")]
        for comment in comments:
            texts_to_scan.append((comment.created_at, comment.body or ""))


        for base_time, text in texts_to_scan:
            base_time = base_time.astimezone(TZ_TW)
            
            start_match = START_PATTERN.search(text)
            if start_match:
                if start_match.group(1):
                    hh, mm = map(int, start_match.group(1).split(':'))
                    start_time = base_time.replace(hour=hh, minute=mm, second=0)
                else:
                    start_time = base_time
                    
            end_match = END_PATTERN.search(text)
            if end_match:
                if end_match.group(1):
                    hh, mm = map(int, end_match.group(1).split(':'))
                    end_time = base_time.replace(hour=hh, minute=mm, second=0)
                else:
                    end_time = base_time

        if not start_time:
            logging.warning(f"Issue #{issue.number}: 找不到 dev start，判定為異常。")
            total_hours = -1

        else:
            if not end_time:
                end_time = issue.closed_at.astimezone(TZ_TW)
            
            total_hours = calculate_working_hours(start_time, end_time)
        
        current_labels = [label.name for label in issue.labels]

        if total_hours < 0:
            if DEV_TIME_ERROR not in current_labels:
                issue.add_to_labels(DEV_TIME_ERROR) 
                error_msg = f"Hi @{issue.user.login}，偵測到開發時間紀錄格式有誤，請檢查後重新填寫。"
                issue.create_comment(error_msg)
                logging.error(f"Issue #{issue.number}: 週期計算異常 (<0)，已貼上標籤。")
            error_count += 1
            continue

        if DEV_TIME_ERROR in current_labels:
            issue.remove_from_labels(DEV_TIME_ERROR)
            logging.info(f"Issue #{issue.number}: 異常已修復，自動拔除標籤。")

        success_count += 1

        comment_body = (
            f"**自動統計開發時間** \n\n"
            f"- **開始時間:** `{start_time.strftime('%Y-%m-%d %H:%M')}`\n"
            f"- **結束時間:** `{end_time.strftime('%Y-%m-%d %H:%M')}`\n"
            f"- **總計開發時間:** **{total_hours} 小時**"
        )

        issue.create_comment(comment_body)
        issue.add_to_labels(DEV_TIME_SETTLED)  
    
    logging.info(f"排程結束。本次成功計算: {success_count} 筆，異常: {error_count} 筆。")

if __name__ == "__main__":
    if not GITHUB_TOKEN or not REPO_NAME:
        print("請確認 .env 檔案中有設定 GITHUB_TOKEN 與 GITHUB_REPOSITORY！")
    else:
        process_closed_issues()