#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import sys
import time
import pickle
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Set
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

RATE_LIMIT_SEC = 0.5  # 请求间隔，避免被限速（更保守的设置）

# ANSI 颜色代码，用于增强控制台输出效果
class Colors:
    GREEN = '\033[92m'      # 绿色 - 成功
    RED = '\033[91m'        # 红色 - 失败
    YELLOW = '\033[93m'     # 黄色 - 警告
    BLUE = '\033[94m'       # 蓝色 - 信息
    MAGENTA = '\033[95m'    # 紫色 - 重要
    CYAN = '\033[96m'       # 青色 - 进度
    BOLD = '\033[1m'        # 粗体
    UNDERLINE = '\033[4m'   # 下划线
    RESET = '\033[0m'       # 重置颜色
    
    # 背景色
    BG_GREEN = '\033[102m'  # 绿色背景
    BG_RED = '\033[101m'    # 红色背景

class PDFDownloadWorker:
    """异步PDF下载工作器，避免阻塞主流程"""
    
    def __init__(self, downloader, pdf_output_dir, max_workers=3):
        self.downloader = downloader
        self.pdf_output_dir = pdf_output_dir
        self.max_workers = max_workers
        self.download_queue = Queue()
        self.workers = []
        self.running = False
        # 进度统计
        self.total_pdfs = 0
        self.completed_pdfs = 0
        self.failed_pdfs = 0
        self.total_submissions = 0  # 新增：总论文数量
        self.progress_lock = threading.Lock()
        
    def set_total_submissions(self, total):
        """设置总论文数量"""
        with self.progress_lock:
            self.total_submissions = total
    
    def start(self):
        """启动下载工作线程"""
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def stop(self):
        """停止下载工作线程"""
        self.running = False
        # 添加停止信号到队列
        for _ in range(self.max_workers):
            self.download_queue.put(None)
    
    def add_download_task(self, forum_id, pdf_url):
        """添加PDF下载任务到队列"""
        if not self.downloader.is_pdf_downloaded(forum_id):
            self.download_queue.put((forum_id, pdf_url))
            with self.progress_lock:
                self.total_pdfs += 1
    
    def get_progress_info(self):
        """获取当前下载进度信息"""
        with self.progress_lock:
            return {
                'total': self.total_pdfs,
                'completed': self.completed_pdfs,
                'failed': self.failed_pdfs,
                'remaining': self.total_pdfs - self.completed_pdfs - self.failed_pdfs
            }
    
    def _worker(self):
        """工作线程函数"""
        while self.running:
            try:
                task = self.download_queue.get(timeout=1)
                if task is None:  # 停止信号
                    break
                    
                forum_id, pdf_url = task
                if not self.downloader.is_pdf_downloaded(forum_id):
                    pdf_filename = f"{forum_id}.pdf"
                    pdf_path = os.path.join(self.pdf_output_dir, pdf_filename)
                    
                    if download_pdf(pdf_url, pdf_path):
                        self.downloader.mark_pdf_downloaded(forum_id)
                        with self.progress_lock:
                            self.completed_pdfs += 1
                        
                        # 获取当前进度 - 使用总论文数量而不是总PDF数量
                        total_downloaded = len(self.downloader.progress.get('downloaded_pdfs', set()))
                        progress_bar = self._create_progress_bar(total_downloaded, self.total_submissions)
                        
                        # 增强的成功提示 - 使用颜色和更醒目的图标
                        print(f"    {Colors.GREEN}{Colors.BOLD}🎉 PDF下载成功!{Colors.RESET} {Colors.CYAN}{pdf_filename}{Colors.RESET}")
                        print(f"    {Colors.GREEN}📁 保存位置: {pdf_path}{Colors.RESET}")
                        print(f"    {Colors.CYAN}📊 进度: {progress_bar} {total_downloaded}/{self.total_submissions}{Colors.RESET}")
                    else:
                        with self.progress_lock:
                            self.failed_pdfs += 1
                        
                        # 获取当前进度
                        total_downloaded = len(self.downloader.progress.get('downloaded_pdfs', set()))
                        
                        # 增强的失败提示
                        print(f"    {Colors.RED}{Colors.BOLD}💥 PDF下载失败!{Colors.RESET} {Colors.YELLOW}{pdf_filename}{Colors.RESET}")
                        print(f"    {Colors.RED}🔗 URL: {pdf_url}{Colors.RESET}")
                        print(f"    {Colors.CYAN}📊 进度: {total_downloaded}/{self.total_submissions} (失败: {self.failed_pdfs}){Colors.RESET}")
                        
                self.download_queue.task_done()
            except:
                continue
    
    def _create_progress_bar(self, completed, total, width=20):
        """创建进度条"""
        if total == 0:
            return "█" * width
        
        filled = int(width * completed / total)
        bar = "█" * filled + "░" * (width - filled)
        percentage = (completed / total) * 100
        return f"{Colors.GREEN}{bar}{Colors.RESET} {percentage:.1f}%"

class ResumeDownloader:
    """支持断点续传的OpenReview下载器"""
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        # 将断点文件存储到输出目录下的.download文件夹
        self.download_dir = os.path.join(output_dir, ".download")
        os.makedirs(self.download_dir, exist_ok=True)
        self.progress_file = os.path.join(self.download_dir, ".download_progress.pkl")
        self.state_file = os.path.join(self.download_dir, ".download_state.json")
        self.progress = self.load_progress()
        
    def load_progress(self) -> Dict[str, Any]:
        """加载下载进度"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'rb') as f:
                    progress = pickle.load(f)
                print(f"📂 发现断点文件，已处理 {progress.get('processed_submissions', 0)} 篇投稿")
                return progress
            except Exception as e:
                print(f"⚠️ 无法加载断点文件: {e}")
        
        return {
            'processed_submissions': 0,
            'processed_forums': set(),
            'processed_notes': set(),
            'downloaded_pdfs': set(),  # 新增：已下载的PDF集合
            'total_submissions': 0,
            'start_time': None,
            'last_update': None,
            'venue': None,
            'args': None
        }
    
    def save_progress(self):
        """保存下载进度"""
        self.progress['last_update'] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'wb') as f:
                pickle.dump(self.progress, f)
            
            # 同时保存可读的状态文件
            readable_state = {
                'processed_submissions': self.progress['processed_submissions'],
                'total_submissions': self.progress['total_submissions'],
                'processed_forums_count': len(self.progress['processed_forums']),
                'processed_notes_count': len(self.progress['processed_notes']),
                'downloaded_pdfs_count': len(self.progress.get('downloaded_pdfs', set())),  # 新增
                'progress_percentage': (self.progress['processed_submissions'] / max(1, self.progress['total_submissions'])) * 100,
                'start_time': self.progress['start_time'],
                'last_update': self.progress['last_update'],
                'venue': self.progress['venue']
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(readable_state, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"⚠️ 保存进度失败: {e}")
    
    def is_forum_processed(self, forum_id: str) -> bool:
        """检查论坛是否已处理"""
        return forum_id in self.progress['processed_forums']
    
    def is_note_processed(self, note_id: str) -> bool:
        """检查note是否已处理"""
        return note_id in self.progress['processed_notes']
    
    def mark_forum_processed(self, forum_id: str):
        """标记论坛为已处理"""
        self.progress['processed_forums'].add(forum_id)
        self.progress['processed_submissions'] += 1
    
    def mark_note_processed(self, note_id: str):
        """标记note为已处理"""
        self.progress['processed_notes'].add(note_id)
    
    def is_pdf_downloaded(self, forum_id: str) -> bool:
        """检查PDF是否已下载"""
        return forum_id in self.progress.get('downloaded_pdfs', set())
    
    def mark_pdf_downloaded(self, forum_id: str):
        """标记PDF为已下载"""
        if 'downloaded_pdfs' not in self.progress:
            self.progress['downloaded_pdfs'] = set()
        self.progress['downloaded_pdfs'].add(forum_id)
    
    def get_resume_info(self) -> str:
        """获取续传信息"""
        if self.progress['processed_submissions'] == 0:
            return "开始新的下载任务"
        
        percentage = (self.progress['processed_submissions'] / max(1, self.progress['total_submissions'])) * 100
        return f"从第 {self.progress['processed_submissions'] + 1} 篇投稿继续下载 ({percentage:.1f}% 已完成)"

def mk_out(path: str):
    os.makedirs(path, exist_ok=True)

def is_review_invitation(inv: str) -> bool:
    suffixes = [
        "/Official_Review", "/Review", "/Meta_Review",
        "/Decision", "/Public_Comment", "/Comment", "/Author_Response"
    ]
    return any(inv.endswith(suf) for suf in suffixes)

def extract_reviewish_row(note: Dict[str, Any]) -> Dict[str, Any]:
    content = note.get("content", {}) or {}
    inv = note.get("invitation", "")
    row = {
        "forum": note.get("forum"),
        "note_id": note.get("id"),
        "invitation": inv,
        "signatures_0": (note.get("signatures") or [None])[0],
        "readers": ",".join(note.get("readers") or []),
        "tcdate": note.get("tcdate") or note.get("cdate"),
        "rating": content.get("rating") or content.get("recommendation"),
        "confidence": content.get("confidence"),
        "review_text": content.get("review") or content.get("summary_of_review") \
                       or content.get("comment") or content.get("reply") \
                       or content.get("metareview") or content.get("decision_comment"),
        "decision": content.get("decision"),
    }
    return row


def normalize_pdf(pdf_value: Any, base: str = "https://openreview.net") -> Any:
    """
    Normalize OpenReview 'content.pdf' to a dict format {"value": URL}.
    - Accepts either a dict with 'value' or a raw string.
    - Returns {"value": full_url} if possible, else {"value": "null"}.
    """
    if pdf_value is None:
        return {"value": "null"}
    
    val = pdf_value
    if isinstance(pdf_value, dict):
        val = pdf_value.get("value")
    if not val:
        return {"value": "null"}
    if isinstance(val, str):
        v = val.strip()
        if v.startswith("http://") or v.startswith("https://"):
            return {"value": v}
        if v.startswith("/"):
            return {"value": f"{base}{v}"}
        return {"value": f"{base}/{v}"}
    return {"value": "null"}

def download_pdf(pdf_url: str, output_path: str, timeout: int = 30) -> bool:
    """
    下载PDF文件
    
    Args:
        pdf_url: PDF文件的URL
        output_path: 保存路径
        timeout: 超时时间（秒）
    
    Returns:
        bool: 下载是否成功
    """
    try:
        # 创建目录（如果不存在）
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 如果文件已存在且大小大于0，跳过下载
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        
        # 设置请求头，模拟浏览器访问
        req = urllib.request.Request(
            pdf_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        
        # 下载文件
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.read())
                return True
            else:
                print(f"    ❌ HTTP错误 {response.status}: {pdf_url}")
                return False
                
    except urllib.error.URLError as e:
        print(f"    ❌ URL错误: {e}")
        return False
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        return False

def load_existing_data(file_path: str, file_type: str) -> tuple:
    """加载已存在的数据文件"""
    existing_data = []
    existing_ids = set()
    
    if not os.path.exists(file_path):
        return existing_data, existing_ids
    
    try:
        if file_type == 'ndjson':
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        existing_data.append(data)
                        if 'id' in data:
                            existing_ids.add(data['id'])
        
        elif file_type == 'json':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_data = data
                    existing_ids = {item.get('id') for item in data if 'id' in item}
        
        elif file_type == 'csv':
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_data.append(row)
                    if 'note_id' in row:
                        existing_ids.add(row['note_id'])
                    elif 'forum' in row:
                        existing_ids.add(row['forum'])
        
        print(f"📂 加载已存在的 {file_type.upper()} 数据: {len(existing_data)} 条记录")
        
    except Exception as e:
        print(f"⚠️ 加载 {file_path} 失败: {e}")
        return [], set()
    
    return existing_data, existing_ids

def main():
    # 在进入主逻辑前再尝试导入 openreview（确保日志重定向后能捕获错误输出）
    try:
        import openreview
    except ImportError:
        print("Please: pip install openreview-py", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(
        description="Pull all OpenReview notes with resume capability. Outputs compact NDJSON format for efficient storage and processing."
    )
    ap.add_argument("--venue", required=True,
                    help='Venue ID, e.g. "ICLR.cc/2025/Conference" or "TMLR"')
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--baseurl", default="https://api2.openreview.net",
                    help="OpenReview API baseurl")
    ap.add_argument("--username", default=None, help="OpenReview username (if needed)")
    ap.add_argument("--password", default=None, help="OpenReview password (if needed)")
    ap.add_argument("--sleep", type=float, default=RATE_LIMIT_SEC,
                    help="Sleep seconds between requests")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit number of submissions to fetch (for testing)")
    ap.add_argument("--pdf-workers", type=int, default=3,
                    help="Number of concurrent PDF download workers")
    ap.add_argument("--no-pdf", action="store_true",
                    help="Skip PDF downloads to speed up data collection")

    ap.add_argument("--clean-start", action="store_true",
                    help="忽略断点文件，重新开始下载")
    ap.add_argument("--progress-interval", type=int, default=10,
                    help="每处理多少个论坛保存一次进度")
    
    args = ap.parse_args()

    mk_out(args.out)
    
    # 创建PDF输出目录
    pdf_output_dir = os.path.join(args.out, "pdfs")
    mk_out(pdf_output_dir)
    
    # 初始化断点下载器
    downloader = ResumeDownloader(args.out)
    
    # 初始化PDF下载工作器（如果启用PDF下载）
    pdf_worker = None
    if not args.no_pdf:
        pdf_worker = PDFDownloadWorker(downloader, pdf_output_dir, args.pdf_workers)
        pdf_worker.start()
        print(f"🚀 启动 {args.pdf_workers} 个PDF下载工作线程")
    else:
        print("⚠️ 跳过PDF下载以提高速度")
    
    if args.clean_start:
        print("🔄 清理断点文件，重新开始下载")
        if os.path.exists(downloader.progress_file):
            os.remove(downloader.progress_file)
        if os.path.exists(downloader.state_file):
            os.remove(downloader.state_file)
        downloader.progress = downloader.load_progress()

    # 初始化客户端
    if args.username and args.password:
        client = openreview.api.OpenReviewClient(
            baseurl=args.baseurl, username=args.username, password=args.password
        )
    else:
        client = openreview.api.OpenReviewClient(baseurl=args.baseurl)

    venue = args.venue.rstrip("/")
    print(f"📘 Fetching venue: {venue}")
    
    # 保存任务参数
    downloader.progress['venue'] = venue
    downloader.progress['args'] = vars(args)
    if not downloader.progress['start_time']:
        downloader.progress['start_time'] = datetime.now().isoformat()

    # Step 1. 获取投稿
    print(f"[1/3] Fetching submissions ...")
    submissions_inv = f"{venue}/-/Submission"
    
    # 检查是否需要重新获取投稿列表
    submissions_csv = os.path.join(args.out, "submissions.csv")
    if downloader.progress['processed_submissions'] == 0 or not os.path.exists(submissions_csv):
        print("📥 获取投稿列表...")
        submissions = client.get_all_notes(invitation=submissions_inv)
        time.sleep(args.sleep)
        
        if args.limit:
            submissions = submissions[:args.limit]
            print(f"⚙️ Limiting to first {args.limit} submissions for testing")
        
        downloader.progress['total_submissions'] = len(submissions)
        print(f"Total submissions: {len(submissions)}")
        
        # 保存投稿列表
        with open(submissions_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "forum", "note_id", "number", "title", "authors",
                "abstract", "pdf", "readers", "signatures_0", "tcdate"
            ])
            writer.writeheader()
            for s in submissions:
                s_dict = s.to_json() if hasattr(s, "to_json") else s
                content = s_dict.get("content", {}) or {}
                pdf_dict = normalize_pdf(content.get("pdf"))
                # 对于 CSV，我们将字典转换为字符串表示
                pdf_for_csv = json.dumps(pdf_dict, ensure_ascii=False) if pdf_dict else None
                writer.writerow({
                    "forum": s_dict.get("forum") or s_dict.get("id"),
                    "note_id": s_dict.get("id"),
                    "number": content.get("number") or s_dict.get("number"),
                    "title": content.get("title"),
                    "authors": "; ".join(content.get("authors", [])) if isinstance(content.get("authors"), list) else content.get("authors"),
                    "abstract": content.get("abstract"),
                    "pdf": pdf_for_csv,
                    "readers": ",".join(s_dict.get("readers") or []),
                    "signatures_0": (s_dict.get("signatures") or [None])[0],
                    "tcdate": s_dict.get("tcdate") or s_dict.get("cdate"),
                })
        print(f"✅ Saved submissions -> {submissions_csv}")
    else:
        print("📂 从已保存的投稿列表继续...")
        # 从CSV文件重新加载投稿列表
        submissions = []
        with open(submissions_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 创建简化的投稿对象
                submission = {
                    'id': row['note_id'],
                    'forum': row['forum']
                }
                submissions.append(submission)
        
        if not downloader.progress['total_submissions']:
            downloader.progress['total_submissions'] = len(submissions)
    
    # 设置PDF工作器的总论文数量
    if pdf_worker:
        pdf_worker.set_total_submissions(downloader.progress['total_submissions'])

    print(f"📊 {downloader.get_resume_info()}")

    # Step 2. 拉取每篇论文的所有 notes
    ndjson_path = os.path.join(args.out, "all_notes.ndjson")
    reviews_csv = os.path.join(args.out, "reviews.csv")
    
    # 加载已存在的数据
    existing_notes_ndjson, existing_note_ids_ndjson = load_existing_data(ndjson_path, 'ndjson')
    existing_reviews, existing_review_ids = load_existing_data(reviews_csv, 'csv')
    
    review_rows = existing_reviews.copy()

    print(f"[2/3] Fetching all notes from {len(submissions)} forums ...")
    
    # 创建NDJSON文件用于逐条写入
    ndjson_file = open(ndjson_path, "a", encoding="utf-8")  # 追加模式
    
    try:
        processed_count = 0
        for idx, s in enumerate(submissions, 1):
            s_dict = s if isinstance(s, dict) else (s.to_json() if hasattr(s, "to_json") else s)
            forum_id = s_dict.get("forum") or s_dict.get("id")
            
            # 检查是否已处理过这个论坛
            if downloader.is_forum_processed(forum_id):
                continue
            
            # 跳过已处理的投稿
            if idx <= downloader.progress['processed_submissions']:
                continue
            
            print(f"  🔄 处理论坛 {idx}/{len(submissions)}: {forum_id}")
            
            try:
                notes_in_forum = client.get_all_notes(forum=forum_id)
                time.sleep(args.sleep)
                
                # 检查是否成功获取到notes
                if notes_in_forum is None:
                    print(f"    ⚠️ 无法获取论坛 {forum_id} 的notes (可能已撤回或无权限)")
                    downloader.mark_forum_processed(forum_id)
                    continue
                
                new_notes_count = 0
                for n in notes_in_forum:
                    # 检查note对象是否有效
                    if n is None:
                        continue
                        
                    n_dict = n.to_json() if hasattr(n, "to_json") else n
                    
                    # 检查n_dict是否有效
                    if n_dict is None:
                        continue
                        
                    note_id = n_dict.get('id')
                    
                    # 检查是否已处理过这个note
                    if (note_id in existing_note_ids_ndjson or 
                        downloader.is_note_processed(note_id)):
                        continue
                    
                    new_notes_count += 1
                    
                    # 仅对投稿 note（id == forum）处理 pdf 字段；非投稿 note 移除 pdf
                    c = n_dict.get("content") or {}
                    is_submission_note = (n_dict.get("id") == n_dict.get("forum"))
                    if is_submission_note:
                        c_pdf_dict = normalize_pdf(c.get("pdf"))
                        c["pdf"] = c_pdf_dict  # 现在总是返回字典格式
                        
                        # 异步下载PDF文件（如果启用且PDF URL有效）
                        if pdf_worker and not args.no_pdf:
                            pdf_url = c_pdf_dict.get("value")
                            if pdf_url and pdf_url != "null":
                                pdf_worker.add_download_task(forum_id, pdf_url)
                    else:
                        if "pdf" in c:
                            c.pop("pdf", None)
                    n_dict["content"] = c

                    # 写入NDJSON（断点友好）
                    ndjson_file.write(json.dumps(n_dict, ensure_ascii=False, separators=(',', ':')) + "\n")
                    ndjson_file.flush()  # 立即写入磁盘
                    
                    inv = n_dict.get("invitation", "")
                    if is_review_invitation(inv):
                        review_row = extract_reviewish_row(n_dict)
                        if review_row.get('note_id') not in existing_review_ids:
                            review_rows.append(review_row)
                    
                    downloader.mark_note_processed(note_id)
                
                downloader.mark_forum_processed(forum_id)
                processed_count += 1
                
                if new_notes_count > 0:
                    print(f"    ✅ 新增 {new_notes_count} 条notes")
                else:
                    print(f"    ⏭️ 无新notes (可能已存在)")
                
                # 定期保存进度
                if processed_count % args.progress_interval == 0:
                    downloader.save_progress()
                    print(f"    💾 已保存进度 ({processed_count} 个论坛)")
                
            except Exception as e:
                print(f"    ❌ 处理论坛 {forum_id} 失败: {e}")
                continue
                
    except KeyboardInterrupt:
        print(f"\n⚠️ 用户中断下载，已保存进度")
        downloader.save_progress()
        if pdf_worker:
            pdf_worker.stop()
        return
    finally:
        if 'ndjson_file' in locals() and ndjson_file:
            ndjson_file.close()
        if pdf_worker:
            print("🔄 等待PDF下载完成...")
            pdf_worker.stop()
            print("✅ PDF下载工作线程已停止")
    
    print(f"[3/3] Processing review data and generating outputs ...")

    # 输出文件信息
    print(f"✅ Saved all notes (compact NDJSON) -> {ndjson_path}")

    # Step 3. 导出评审类数据
    if review_rows:
        cols = sorted({k for r in review_rows for k in r.keys()})
        with open(reviews_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in review_rows:
                w.writerow(r)
        print(f"✅ Saved reviews/meta/decision -> {reviews_csv}")
    else:
        print("⚠️ No review-like notes detected (check invitation suffix rules).")

    # 保存最终进度并清理断点文件
    downloader.save_progress()
    
    # 下载完成后可以选择清理断点文件
    completion_percentage = (downloader.progress['processed_submissions'] / max(1, downloader.progress['total_submissions'])) * 100
    if completion_percentage >= 100:
        print("🎉 下载完成！清理断点文件...")
        try:
            if os.path.exists(downloader.progress_file):
                os.remove(downloader.progress_file)
        except:
            pass

    print(f"\n🎉 All exports complete. 处理了 {downloader.progress['processed_submissions']}/{downloader.progress['total_submissions']} 篇投稿")

    # 统计摘要输出到日志
    try:
        ndjson_path = os.path.join(args.out, "all_notes.ndjson")

        # 统计总 notes 数量（从 NDJSON 行数）
        total_notes = None
        if os.path.exists(ndjson_path):
            try:
                with open(ndjson_path, 'r', encoding='utf-8') as f:
                    total_notes = sum(1 for line in f if line.strip())
            except Exception:
                pass

        processed_forums_count = len(downloader.progress.get('processed_forums', set()))
        processed_notes_count = len(downloader.progress.get('processed_notes', set()))
        downloaded_pdfs_count = len(downloader.progress.get('downloaded_pdfs', set()))
        total_submissions = downloader.progress.get('total_submissions', 0)
        processed_submissions = downloader.progress.get('processed_submissions', 0)
        percentage = (processed_submissions / max(1, total_submissions)) * 100

        print(f"\n{Colors.MAGENTA}{Colors.BOLD}📊 下载统计摘要{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*50}{Colors.RESET}")
        print(f"  📝 总投稿数: {Colors.BOLD}{total_submissions}{Colors.RESET}")
        print(f"  ✅ 已处理投稿数: {Colors.GREEN}{Colors.BOLD}{processed_submissions}{Colors.RESET} ({Colors.YELLOW}{percentage:.2f}%{Colors.RESET})")
        print(f"  🏛️  已处理论坛数: {Colors.BLUE}{processed_forums_count}{Colors.RESET}")
        print(f"  📄 本次新增 notes 数: {Colors.CYAN}{processed_notes_count}{Colors.RESET}")
        
        # 突出显示PDF下载数量
        if downloaded_pdfs_count > 0:
            print(f"  {Colors.BG_GREEN}{Colors.BOLD} 📁 已下载PDF数: {downloaded_pdfs_count} {Colors.RESET} {Colors.GREEN}🎉{Colors.RESET}")
        else:
            print(f"  📁 已下载PDF数: {Colors.YELLOW}{downloaded_pdfs_count}{Colors.RESET} {Colors.YELLOW}(无PDF下载){Colors.RESET}")
        
        if total_notes is not None:
            print(f"  📊 输出中 notes 总数: {Colors.MAGENTA}{total_notes}{Colors.RESET}")
        else:
            print(f"  📊 输出中 notes 总数: {Colors.RED}未能确定（文件可能未生成或解析失败）{Colors.RESET}")
        
        print(f"{Colors.CYAN}{'='*50}{Colors.RESET}")
    except Exception as e:
        print(f"⚠️ 统计摘要生成失败: {e}")

if __name__ == "__main__":
    main()