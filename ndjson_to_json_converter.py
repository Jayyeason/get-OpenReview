#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import argparse
from typing import List, Dict, Any

def ndjson_to_json(ndjson_path: str, json_path: str, indent: int = 2) -> bool:
    """
    将NDJSON文件转换为标准JSON数组格式，并在同一forum内按时间（早→晚）排序
    
    Args:
        ndjson_path: NDJSON文件路径
        json_path: 输出JSON文件路径
        indent: JSON缩进级别
    
    Returns:
        bool: 转换是否成功
    """
    if not os.path.exists(ndjson_path):
        print(f"❌ NDJSON文件不存在: {ndjson_path}")
        return False
    
    try:
        data_list = []
        line_count = 0
        
        print(f"📖 读取NDJSON文件: {ndjson_path}")
        
        with open(ndjson_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                
                try:
                    data = json.loads(line)
                    data_list.append(data)
                    line_count += 1
                    
                    # 每1000行显示一次进度
                    if line_count % 1000 == 0:
                        print(f"  📊 已读取 {line_count} 条记录...")
                        
                except json.JSONDecodeError as e:
                    print(f"⚠️ 第{line_num}行JSON解析失败: {e}")
                    print(f"   问题行内容: {line[:100]}...")
                    continue
        
        print(f"✅ 成功读取 {line_count} 条记录")
        
        # 在同一forum下按时间（tcdate/cdate/odate/mdate）升序排序
        print("🧮 按forum分组并按时间排序（早→晚）")
        from typing import DefaultDict
        from collections import defaultdict
        import sys
        forum_groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        forum_order: List[str] = []
        
        def _ts(n: Dict[str, Any]) -> int:
            t = n.get("tcdate") or n.get("cdate") or n.get("odate") or n.get("mdate")
            try:
                return int(t) if t is not None else sys.maxsize
            except (TypeError, ValueError):
                return sys.maxsize
        
        for note in data_list:
            forum_id = note.get("forum") or note.get("id")
            if forum_id not in forum_groups:
                forum_order.append(forum_id)
            forum_groups[forum_id].append(note)
        
        for fid in forum_groups:
            forum_groups[fid].sort(key=_ts)
        
        # 按首次出现的forum顺序展开
        sorted_list: List[Dict[str, Any]] = []
        for fid in forum_order:
            sorted_list.extend(forum_groups[fid])
        print(f"   📚 论坛数量: {len(forum_groups)}")
        
        # 写入JSON文件
        print(f"💾 写入JSON文件: {json_path}")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sorted_list, f, ensure_ascii=False, indent=indent)
        
        print(f"🎉 转换完成！")
        print(f"   📄 输入: {ndjson_path} ({line_count} 条记录)")
        print(f"   📄 输出: {json_path}")
        
        # 显示文件大小对比
        ndjson_size = os.path.getsize(ndjson_path)
        json_size = os.path.getsize(json_path)
        print(f"   📊 文件大小: NDJSON {ndjson_size:,} bytes → JSON {json_size:,} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False

def convert_directory_ndjson(directory: str, ask_overwrite: bool = True) -> bool:
    """
    转换目录下所有NDJSON文件为JSON格式
    
    Args:
        directory: 目标目录
        ask_overwrite: 是否询问覆盖已存在的文件
    
    Returns:
        bool: 是否至少转换成功一个文件
    """
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在: {directory}")
        return False
    
    # 查找所有.ndjson文件
    ndjson_files = [f for f in os.listdir(directory) if f.endswith('.ndjson')]
    
    if not ndjson_files:
        print(f"❌ 目录中未找到任何.ndjson文件: {directory}")
        return False
    
    print(f"🔍 发现 {len(ndjson_files)} 个NDJSON文件:")
    for f in ndjson_files:
        size = os.path.getsize(os.path.join(directory, f))
        print(f"   • {f} ({size:,} bytes)")
    print()
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for ndjson_file in ndjson_files:
        ndjson_path = os.path.join(directory, ndjson_file)
        
        # 生成输出文件名：xxx.ndjson -> xxx_readable.json 或 xxx.json
        if ndjson_file.endswith('.ndjson'):
            base_name = ndjson_file[:-7]  # 去掉 .ndjson
            json_file = f"{base_name}_readable.json"
        else:
            json_file = ndjson_file + ".json"
        
        json_path = os.path.join(directory, json_file)
        
        # 检查是否已存在
        if os.path.exists(json_path) and ask_overwrite:
            response = input(f"⚠️ JSON文件已存在: {json_file}\n是否覆盖? (y/N/all): ")
            if response.lower() == 'all':
                ask_overwrite = False  # 后续不再询问
            elif response.lower() != 'y':
                print(f"⏭️ 跳过: {ndjson_file}\n")
                skipped_count += 1
                continue
        
        print(f"📄 转换: {ndjson_file}")
        if ndjson_to_json(ndjson_path, json_path):
            success_count += 1
        else:
            failed_count += 1
        print()
    
    # 总结
    print(f"{'='*60}")
    print(f"📊 转换完成:")
    print(f"   ✅ 成功: {success_count} 个文件")
    if failed_count > 0:
        print(f"   ❌ 失败: {failed_count} 个文件")
    if skipped_count > 0:
        print(f"   ⏭️ 跳过: {skipped_count} 个文件")
    print(f"{'='*60}")
    
    return success_count > 0

def batch_convert(base_dir: str) -> None:
    """
    批量转换目录树下的所有NDJSON文件（递归查找子目录）
    
    Args:
        base_dir: 基础目录
    """
    converted_dirs = []
    failed_dirs = []
    
    print(f"🔍 递归扫描目录: {base_dir}")
    
    # 收集所有包含.ndjson文件的目录
    dirs_with_ndjson = {}
    for root, dirs, files in os.walk(base_dir):
        ndjson_files = [f for f in files if f.endswith('.ndjson')]
        if ndjson_files:
            dirs_with_ndjson[root] = len(ndjson_files)
    
    if not dirs_with_ndjson:
        print(f"❌ 未找到任何包含.ndjson文件的目录")
        return
    
    print(f"📁 发现 {len(dirs_with_ndjson)} 个目录包含.ndjson文件\n")
    
    for idx, (dir_path, count) in enumerate(dirs_with_ndjson.items(), 1):
        print(f"{'='*60}")
        print(f"📂 [{idx}/{len(dirs_with_ndjson)}] {dir_path} ({count} 个文件)")
        print(f"{'='*60}")
        
        if convert_directory_ndjson(dir_path, ask_overwrite=False):
            converted_dirs.append(dir_path)
        else:
            failed_dirs.append(dir_path)
        print()
    
    print(f"\n{'='*60}")
    print(f"📊 批量转换完成:")
    print(f"   ✅ 成功: {len(converted_dirs)} 个目录")
    if failed_dirs:
        print(f"   ❌ 失败: {len(failed_dirs)} 个目录")
    print(f"{'='*60}")

def main():
    parser = argparse.ArgumentParser(
        description="将NDJSON文件转换为可读的JSON格式"
    )
    
    parser.add_argument(
        "--input", "-i",
        help="输入NDJSON文件路径"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="输出JSON文件路径"
    )
    
    parser.add_argument(
        "--dir", "-d",
        help="转换指定目录下的所有.ndjson文件"
    )
    
    parser.add_argument(
        "--batch", "-b",
        help="批量转换指定目录下的所有NDJSON文件"
    )
    
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON缩进级别（默认: 2）"
    )
    
    args = parser.parse_args()
    
    if args.batch:
        # 批量转换模式
        batch_convert(args.batch)
        
    elif args.dir:
        # 目录模式 - 转换目录下所有.ndjson文件
        if not convert_directory_ndjson(args.dir):
            exit(1)
            
    elif args.input and args.output:
        # 文件模式
        if not ndjson_to_json(args.input, args.output, args.indent):
            exit(1)
            
    else:
        # 交互模式
        print("🔧 NDJSON到JSON转换工具")
        print("=" * 40)
        
        # 检查当前目录
        current_dir = os.getcwd()
        ndjson_files = [f for f in os.listdir(current_dir) if f.endswith('.ndjson')]
        
        if ndjson_files:
            print(f"📁 当前目录发现NDJSON文件:")
            for i, filename in enumerate(ndjson_files, 1):
                size = os.path.getsize(filename)
                print(f"   {i}. {filename} ({size:,} bytes)")
            
            try:
                choice = int(input(f"\n选择要转换的文件 (1-{len(ndjson_files)}): "))
                if 1 <= choice <= len(ndjson_files):
                    input_file = ndjson_files[choice - 1]
                    output_file = input_file.replace('.ndjson', '_readable.json')
                    
                    if ndjson_to_json(input_file, output_file, args.indent):
                        print("✅ 转换成功！")
                    else:
                        print("❌ 转换失败！")
                        exit(1)
                else:
                    print("❌ 无效选择")
                    exit(1)
            except (ValueError, KeyboardInterrupt):
                print("\n❌ 操作取消")
                exit(1)
        else:
            print("❌ 当前目录未找到NDJSON文件")
            print("\n使用方法:")
            print("  python ndjson_to_json_converter.py --input file.ndjson --output file.json")
            print("  python ndjson_to_json_converter.py --dir ./history  # 转换目录下所有.ndjson")
            print("  python ndjson_to_json_converter.py --batch ./  # 递归查找子目录")

if __name__ == "__main__":
    main()