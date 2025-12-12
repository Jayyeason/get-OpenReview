#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从output/pdfs目录复制指定的PDF文件到目标目录
"""

import json
import os
import shutil
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple


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


def copy_single_pdf(args: Tuple) -> Tuple[str, bool, str]:
    """复制单个PDF文件"""
    forum_id, source_path, target_path = args
    
    try:
        # 检查源文件是否存在
        if not os.path.exists(source_path):
            return forum_id, False, "源文件不存在"
        
        # 检查目标文件是否已存在
        if os.path.exists(target_path):
            source_size = os.path.getsize(source_path)
            target_size = os.path.getsize(target_path)
            if source_size == target_size:
                return forum_id, True, f"文件已存在 ({target_size} bytes)"
        
        # 复制文件
        shutil.copy2(source_path, target_path)
        file_size = os.path.getsize(target_path)
        return forum_id, True, f"复制成功 ({file_size} bytes)"
        
    except Exception as e:
        return forum_id, False, f"复制失败: {str(e)}"


def create_progress_bar(completed: int, total: int, width: int = 30) -> str:
    """创建进度条"""
    percentage = completed / total if total > 0 else 0
    filled = int(width * percentage)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {completed}/{total} ({percentage:.1%})"


def main():
    parser = argparse.ArgumentParser(description="从output/pdfs目录复制PDF文件")
    parser.add_argument(
        "--json", 
        default="review_conversations_100.json",
        help="包含论文信息的JSON文件路径"
    )
    parser.add_argument(
        "--source", 
        default="/remote-home1/bwli/get_open_review/output/pdfs",
        help="源PDF目录"
    )
    parser.add_argument(
        "--output", 
        default="pdfs",
        help="PDF输出目录"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="并发复制线程数（默认: 4）"
    )
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}📁 PDF文件复制器{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    # 加载论文信息
    print(f"{Colors.BLUE}📖 正在加载论文信息...{Colors.RESET}")
    try:
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        forum_ids = list(data.keys())
        print(f"{Colors.GREEN}✅ 成功加载 {len(forum_ids)} 篇论文信息{Colors.RESET}\n")
    except Exception as e:
        print(f"{Colors.RED}❌ 加载JSON文件失败: {e}{Colors.RESET}")
        return 1
    
    # 准备复制任务
    copy_tasks = []
    for forum_id in forum_ids:
        source_path = os.path.join(args.source, f"{forum_id}.pdf")
        target_path = os.path.join(output_dir, f"{forum_id}.pdf")
        copy_tasks.append((forum_id, source_path, target_path))
    
    print(f"{Colors.BLUE}🚀 开始复制 {len(copy_tasks)} 个PDF文件...{Colors.RESET}")
    print(f"{Colors.BLUE}📂 源目录: {args.source}{Colors.RESET}")
    print(f"{Colors.BLUE}📁 输出目录: {output_dir}{Colors.RESET}")
    print(f"{Colors.BLUE}🔧 并发线程: {args.workers}{Colors.RESET}\n")
    
    # 执行复制
    completed = 0
    successful = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # 提交所有任务
        future_to_task = {
            executor.submit(copy_single_pdf, task): task 
            for task in copy_tasks
        }
        
        # 处理完成的任务
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            forum_id = task[0]
            
            try:
                forum_id, success, message = future.result()
                completed += 1
                
                if success:
                    successful += 1
                    print(f"{Colors.GREEN}✅ {forum_id}: {message}{Colors.RESET}")
                else:
                    failed += 1
                    print(f"{Colors.RED}❌ {forum_id}: {message}{Colors.RESET}")
                
                # 显示进度
                if completed % 10 == 0 or completed == len(copy_tasks):
                    progress_bar = create_progress_bar(completed, len(copy_tasks))
                    print(f"{Colors.CYAN}{progress_bar}{Colors.RESET}\n")
                
            except Exception as e:
                completed += 1
                failed += 1
                print(f"{Colors.RED}❌ {forum_id}: 处理异常 - {str(e)}{Colors.RESET}")
    
    # 显示最终统计
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}📊 复制完成统计{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.GREEN}✅ 成功: {successful}{Colors.RESET}")
    print(f"{Colors.RED}❌ 失败: {failed}{Colors.RESET}")
    print(f"{Colors.BLUE}📁 输出目录: {output_dir}{Colors.RESET}")
    
    if successful > 0:
        print(f"\n{Colors.GREEN}🎉 复制完成！成功复制了 {successful} 个PDF文件{Colors.RESET}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())