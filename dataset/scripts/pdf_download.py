#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的 PDF 下载脚本
支持断点续传和多线程下载
"""

import argparse
import csv
import json
import os
import pickle
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Set, Tuple


# ANSI 颜色代码
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    BG_GREEN = '\033[102m'
    BG_RED = '\033[101m'


class PDFDownloadProgress:
    """PDF下载进度管理器"""
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.progress_file = os.path.join(output_dir, ".pdf_download_progress.pkl")
        self.state_file = os.path.join(output_dir, ".pdf_download_state.json")
        self.progress = self.load_progress()
    
    def load_progress(self) -> Dict:
        """加载下载进度"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'rb') as f:
                    progress = pickle.load(f)
                print(f"{Colors.CYAN}📂 发现断点文件，已下载 {len(progress.get('downloaded_pdfs', set()))} 个PDF{Colors.RESET}")
                return progress
            except Exception as e:
                print(f"{Colors.YELLOW}⚠️ 无法加载断点文件: {e}{Colors.RESET}")
        
        return {
            'downloaded_pdfs': set(),  # 已下载的forum_id集合
            'failed_pdfs': set(),      # 下载失败的forum_id集合
            'total_pdfs': 0,
            'start_time': None,
            'last_update': None,
        }
    
    def save_progress(self):
        """保存下载进度"""
        self.progress['last_update'] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'wb') as f:
                pickle.dump(self.progress, f)
            
            # 保存可读的状态文件
            readable_state = {
                'downloaded_count': len(self.progress['downloaded_pdfs']),
                'failed_count': len(self.progress['failed_pdfs']),
                'total_pdfs': self.progress['total_pdfs'],
                'progress_percentage': (len(self.progress['downloaded_pdfs']) / max(1, self.progress['total_pdfs'])) * 100,
                'start_time': self.progress['start_time'],
                'last_update': self.progress['last_update'],
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(readable_state, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"{Colors.RED}⚠️ 保存进度失败: {e}{Colors.RESET}")
    
    def is_downloaded(self, forum_id: str) -> bool:
        """检查PDF是否已下载"""
        return forum_id in self.progress['downloaded_pdfs']
    
    def mark_downloaded(self, forum_id: str):
        """标记PDF为已下载"""
        self.progress['downloaded_pdfs'].add(forum_id)
    
    def mark_failed(self, forum_id: str):
        """标记PDF下载失败"""
        self.progress['failed_pdfs'].add(forum_id)
    
    def is_failed(self, forum_id: str) -> bool:
        """检查PDF是否下载失败过"""
        return forum_id in self.progress['failed_pdfs']


def download_pdf(pdf_url: str, output_path: str, timeout: int = 30, max_retries: int = 3) -> bool:
    """
    下载PDF文件
    
    Args:
        pdf_url: PDF文件的URL
        output_path: 保存路径
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
    
    Returns:
        bool: 下载是否成功
    """
    import time
    import random
    
    # 如果文件已存在且大小大于0，跳过下载
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return True
    
    for attempt in range(max_retries + 1):
        try:
            # 添加随机延迟，避免并发请求过于集中
            if attempt > 0:
                delay = random.uniform(1, 3) * attempt  # 递增延迟
                time.sleep(delay)
            
            # 设置请求头，模拟浏览器访问
            req = urllib.request.Request(
                pdf_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/pdf,*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive'
                }
            )
            
            # 下载文件
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(response.read())
                    return True
                else:
                    print(f"{Colors.RED}❌ HTTP错误 {response.status}: {pdf_url}{Colors.RESET}")
                    if response.status == 404:
                        # 404错误不需要重试
                        return False
                    # 其他HTTP错误可以重试
                    continue
                    
        except urllib.error.URLError as e:
            error_msg = str(e)
            if "Temporary failure in name resolution" in error_msg:
                if attempt < max_retries:
                    print(f"{Colors.YELLOW}⚠️ DNS解析失败，第{attempt+1}次重试 ({output_path}){Colors.RESET}")
                    continue
                else:
                    print(f"{Colors.RED}❌ DNS解析失败，已达最大重试次数 ({output_path}): {e}{Colors.RESET}")
            else:
                print(f"{Colors.RED}❌ URL错误 ({output_path}): {e}{Colors.RESET}")
            
            if attempt == max_retries:
                return False
                
        except Exception as e:
            if attempt < max_retries:
                print(f"{Colors.YELLOW}⚠️ 下载失败，第{attempt+1}次重试 ({output_path}): {e}{Colors.RESET}")
                continue
            else:
                print(f"{Colors.RED}❌ 下载失败 ({output_path}): {e}{Colors.RESET}")
                return False
    
    return False


def create_progress_bar(completed: int, total: int, width: int = 30) -> str:
    """创建进度条"""
    if total == 0:
        return "█" * width
    
    filled = int(width * completed / total)
    bar = "█" * filled + "░" * (width - filled)
    percentage = (completed / total) * 100
    return f"{Colors.GREEN}{bar}{Colors.RESET} {percentage:.1f}%"


def load_pdf_list_from_csv(csv_path: str) -> list:
    """
    从 submissions.csv 加载PDF列表
    
    Returns:
        list: [(forum_id, pdf_url, title), ...]
    """
    pdf_list = []
    
    if not os.path.exists(csv_path):
        print(f"{Colors.RED}❌ 找不到文件: {csv_path}{Colors.RESET}")
        return pdf_list
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                forum_id = row.get('forum') or row.get('note_id')
                pdf_field = row.get('pdf', '')
                title = row.get('title', 'Unknown')
                
                if not forum_id:
                    continue
                
                # 解析PDF字段（可能是JSON格式）
                pdf_url = None
                if pdf_field:
                    try:
                        # 尝试解析为JSON
                        pdf_data = json.loads(pdf_field)
                        if isinstance(pdf_data, dict):
                            pdf_url = pdf_data.get('value')
                    except json.JSONDecodeError:
                        # 如果不是JSON，直接当作URL
                        pdf_url = pdf_field
                
                # 跳过无效的PDF URL
                if pdf_url and pdf_url != "null" and pdf_url.startswith('http'):
                    pdf_list.append((forum_id, pdf_url, title))
        
        print(f"{Colors.GREEN}✅ 从 CSV 加载了 {len(pdf_list)} 个PDF链接{Colors.RESET}")
        
    except Exception as e:
        print(f"{Colors.RED}❌ 读取CSV文件失败: {e}{Colors.RESET}")
    
    return pdf_list


def download_single_pdf(args: Tuple) -> Tuple[str, bool, str]:
    """
    下载单个PDF（用于多线程）
    
    Args:
        args: (forum_id, pdf_url, output_dir, title)
    
    Returns:
        (forum_id, success, message)
    """
    forum_id, pdf_url, output_dir, title = args
    
    pdf_filename = f"{forum_id}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    # 检查文件是否已存在
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        return (forum_id, True, f"已存在: {pdf_filename}")
    
    # 下载PDF
    success = download_pdf(pdf_url, pdf_path)
    
    if success:
        return (forum_id, True, f"成功: {pdf_filename}")
    else:
        return (forum_id, False, f"失败: {pdf_filename} ({pdf_url})")


def main():
    parser = argparse.ArgumentParser(
        description="独立的PDF下载器，支持断点续传"
    )
    parser.add_argument(
        "--dir", 
        default="/remote-home1/bwli/get_open_review/dataset/paper/iclr2026/pdf",
        help="PDF输出目录"
    )
    parser.add_argument(
        "--csv",
        default="/remote-home1/bwli/get_open_review/dataset/scripts/submissions.csv",
        help="submissions.csv 文件路径（默认: <dir>/../submissions.csv）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="并发下载线程数（默认: 3，建议不超过5以避免DNS解析问题）"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="重新下载之前失败的PDF"
    )
    parser.add_argument(
        "--clean-start",
        action="store_true",
        help="忽略断点文件，重新开始下载"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="下载超时时间（秒，默认: 30）"
    )
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = os.path.abspath(args.dir)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}📥 OpenReview PDF 下载器{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    # 确定CSV文件路径
    if args.csv:
        csv_path = args.csv
    else:
        # 默认查找 <output_dir>/../submissions.csv
        csv_path = os.path.join(os.path.dirname(output_dir), "submissions.csv")
    
    csv_path = os.path.abspath(csv_path)
    
    if not os.path.exists(csv_path):
        print(f"{Colors.RED}❌ 错误: 找不到 submissions.csv 文件: {csv_path}{Colors.RESET}")
        print(f"{Colors.YELLOW}💡 提示: 使用 --csv 参数指定 CSV 文件路径{Colors.RESET}")
        return 1
    
    print(f"{Colors.BLUE}📄 CSV 文件: {csv_path}{Colors.RESET}")
    print(f"{Colors.BLUE}📁 输出目录: {output_dir}{Colors.RESET}")
    print(f"{Colors.BLUE}🔧 并发线程: {args.workers}{Colors.RESET}\n")
    
    # 初始化进度管理器
    progress_mgr = PDFDownloadProgress(output_dir)
    
    if args.clean_start:
        print(f"{Colors.YELLOW}🔄 清理断点文件，重新开始下载{Colors.RESET}")
        if os.path.exists(progress_mgr.progress_file):
            os.remove(progress_mgr.progress_file)
        if os.path.exists(progress_mgr.state_file):
            os.remove(progress_mgr.state_file)
        progress_mgr.progress = progress_mgr.load_progress()
    
    # 加载PDF列表
    pdf_list = load_pdf_list_from_csv(csv_path)
    
    if not pdf_list:
        print(f"{Colors.RED}❌ 没有找到可下载的PDF{Colors.RESET}")
        return 1
    
    # 设置总数
    progress_mgr.progress['total_pdfs'] = len(pdf_list)
    if not progress_mgr.progress['start_time']:
        progress_mgr.progress['start_time'] = datetime.now().isoformat()
    
    # 过滤已下载的PDF
    download_tasks = []
    for forum_id, pdf_url, title in pdf_list:
        # 跳过已下载的
        if progress_mgr.is_downloaded(forum_id):
            continue
        
        # 跳过失败的（除非指定重试）
        if progress_mgr.is_failed(forum_id) and not args.retry_failed:
            continue
        
        download_tasks.append((forum_id, pdf_url, output_dir, title))
    
    total_pdfs = len(pdf_list)
    already_downloaded = len(progress_mgr.progress['downloaded_pdfs'])
    to_download = len(download_tasks)
    
    print(f"{Colors.CYAN}📊 统计信息:{Colors.RESET}")
    print(f"  总PDF数: {Colors.BOLD}{total_pdfs}{Colors.RESET}")
    print(f"  已下载: {Colors.GREEN}{already_downloaded}{Colors.RESET}")
    print(f"  待下载: {Colors.YELLOW}{to_download}{Colors.RESET}")
    print(f"  并发数: {Colors.BLUE}{args.workers}{Colors.RESET}")
    
    if progress_mgr.progress['failed_pdfs']:
        print(f"  失败数: {Colors.RED}{len(progress_mgr.progress['failed_pdfs'])}{Colors.RESET}")
    
    print()
    
    if to_download == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 所有PDF已下载完成！{Colors.RESET}")
        return 0
    
    # 网络连接测试
    print(f"{Colors.CYAN}🔍 网络连接测试...{Colors.RESET}")
    try:
        import urllib.request
        req = urllib.request.Request('https://openreview.net', headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        print(f"{Colors.GREEN}✅ OpenReview.net 连接正常{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}❌ 网络连接测试失败: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠️ 建议检查网络连接后重试{Colors.RESET}")
        return 1
    
    print()
    
    # 开始下载
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}🚀 开始下载 PDF...{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    successful = 0
    failed = 0
    
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # 提交所有任务
            futures = {
                executor.submit(download_single_pdf, task): task 
                for task in download_tasks
            }
            
            # 处理完成的任务
            for future in as_completed(futures):
                forum_id, success, message = future.result()
                
                if success:
                    progress_mgr.mark_downloaded(forum_id)
                    successful += 1
                    current_total = already_downloaded + successful
                    progress_bar = create_progress_bar(current_total, total_pdfs)
                    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
                    print(f"   {progress_bar} {current_total}/{total_pdfs}")
                else:
                    progress_mgr.mark_failed(forum_id)
                    failed += 1
                    print(f"{Colors.RED}❌ {message}{Colors.RESET}")
                
                # 每10个保存一次进度
                if (successful + failed) % 10 == 0:
                    progress_mgr.save_progress()
                    
                # 添加小延迟，避免过于频繁的并发请求
                time.sleep(0.1)
        
        # 保存最终进度
        progress_mgr.save_progress()
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️ 用户中断下载，已保存进度{Colors.RESET}")
        progress_mgr.save_progress()
        return 1
    
    # 输出最终统计
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}📊 下载完成统计{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"  {Colors.GREEN}✅ 成功: {successful}{Colors.RESET}")
    if failed > 0:
        print(f"  {Colors.RED}❌ 失败: {failed}{Colors.RESET}")
    print(f"  {Colors.CYAN}📁 总计已下载: {len(progress_mgr.progress['downloaded_pdfs'])}/{total_pdfs}{Colors.RESET}")
    
    completion = (len(progress_mgr.progress['downloaded_pdfs']) / total_pdfs) * 100
    print(f"  {Colors.YELLOW}📊 完成度: {completion:.1f}%{Colors.RESET}")
    
    # 显示失败的PDF信息
    if failed > 0:
        print(f"\n{Colors.YELLOW}📋 失败的PDF列表:{Colors.RESET}")
        failed_count = 0
        for forum_id in progress_mgr.progress['failed_pdfs']:
            if failed_count < 10:  # 只显示前10个
                print(f"  - {forum_id}")
                failed_count += 1
            else:
                remaining = len(progress_mgr.progress['failed_pdfs']) - 10
                print(f"  ... 还有 {remaining} 个失败的PDF")
                break
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    if failed > 0:
        print(f"{Colors.YELLOW}💡 提示: 使用 --retry-failed 重新下载失败的PDF{Colors.RESET}")
        print(f"{Colors.YELLOW}💡 提示: 如果DNS解析失败较多，可以降低 --workers 参数{Colors.RESET}")
    
    # 清理断点文件（如果100%完成）
    if completion >= 100 and failed == 0:
        print(f"{Colors.GREEN}🎉 所有PDF下载完成！清理断点文件...{Colors.RESET}")
        try:
            if os.path.exists(progress_mgr.progress_file):
                os.remove(progress_mgr.progress_file)
        except:
            pass
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

