import os
import re
from datetime import datetime, timezone
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")

START_PATTERN = re.compile(r"(?:dev\s*begin|dev\s*start)(?:\s*(?:at|:|：)\s*(\d{1,2}:\d{2}))?", re.IGNORECASE)
END_PATTERN = re.compile(r"(?:dev\s*end|end)(?:\s*(?:at|:|：)\s*(\d{1,2}:\d{2}))?", re.IGNORECASE)

def process_closed_issues():
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(REPO_NAME)

    # 1. 修改 Search Query：只排除「工時已結算」。
    # 這代表「完全沒處理過」和「工時異常」的票都會被抓出來巡視！
    query = f"repo:{repo.full_name} is:issue is:closed -label:工時已結算"
    
    print(f"🔍 使用 Search API 尋找待處理的 Issue...")
    unprocessed_issues = g.search_issues(query, sort='updated', order='desc')
    
    for issue in unprocessed_issues:
        print(f"\n⚡ 正在處理 Issue #{issue.number}...")
        
        # 讀取留言存入記憶體
        comments = list(issue.get_comments())
        
        start_time = None
        end_time = None
        
        texts_to_scan = [(issue.created_at, issue.body or "")]
        for comment in comments:
            texts_to_scan.append((comment.created_at, comment.body or ""))

        # --- 掃描 Start 與 End 的 Regex 邏輯 (保持不變) ---
        for base_time, text in texts_to_scan:
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
            start_time = issue.created_at
        if not end_time:
            end_time = issue.closed_at

        try:
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)

            duration = end_time - start_time
            total_hours = round(duration.total_seconds() / 3600, 2)
            
            # 讀取這張票目前的標籤
            current_labels = [label.name for label in issue.labels]

            # ==========================================
            # 狀態分流機制：異常 vs 成功
            # ==========================================
            if total_hours < 0:
                # 只有當它身上還沒有異常標籤時，才發送 API 貼標籤，節省資源
                if "工時異常" not in current_labels:
                    print(f"❌ Issue #{issue.number} 工時異常 ({total_hours} 小時)，貼上標籤。")
                    issue.add_to_labels("工時異常") 
                else:
                    print(f"⚠️ Issue #{issue.number} 仍是異常狀態，略過。")
                continue

            # ==========================================
            # 正常處理：如果原本是異常的，現在算對了，就自動拔掉！
            # ==========================================
            if "工時異常" in current_labels:
                issue.remove_from_labels("工時異常")
                print(f"🔧 Issue #{issue.number} 發現資料已修正！已自動拔除異常標籤。")

            # 回寫成功留言並貼上「已結算」標籤
            comment_body = (
                f"🤖 **自動統計總工時** ✅\n\n"
                f"- **開始時間:** `{start_time.strftime('%Y-%m-%d %H:%M')}`\n"
                f"- **結束時間:** `{end_time.strftime('%Y-%m-%d %H:%M')}`\n"
                f"- **總計耗時:** **{total_hours} 小時**"
            )
            issue.create_comment(comment_body)
            issue.add_to_labels("工時已結算")  
            
            print(f"✅ Issue #{issue.number} 計算完成: {total_hours} 小時，已結算！")

        except Exception as e:
            print(f"❌ Issue #{issue.number} 發生未預期錯誤: {e}")

if __name__ == "__main__":
    if not GITHUB_TOKEN or not REPO_NAME:
        print("請確認 .env 檔案中有設定 GITHUB_TOKEN 與 GITHUB_REPOSITORY！")
    else:
        process_closed_issues()