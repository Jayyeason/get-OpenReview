#!/usr/bin/env python3
"""
完整的转换脚本：将 all_notes_readable.json 转换为 structured_review_conversations.json

使用方法:
python convert_to_structured.py --dir output
python convert_to_structured.py --dir /path/to/your/data

参数说明:
--dir: 指定包含输入文件的目录路径，默认为 'output'

输入文件: <指定目录>/all_notes_readable.json
输出文件: <指定目录>/structured_review_conversations.json
"""

import json
import re
import argparse
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional


def get_timestamp(note: Dict[str, Any]) -> int:
    """从note中提取时间戳"""
    return note.get('cdate', 0)


def format_timestamp(timestamp_ms: int) -> str:
    """将毫秒时间戳转换为yyyy/mm/dd hh:mm:ss格式"""
    if timestamp_ms == 0:
        return ""
    
    # 转换毫秒时间戳为秒
    timestamp_s = timestamp_ms / 1000
    dt = datetime.fromtimestamp(timestamp_s)
    return dt.strftime("%Y/%m/%d %H:%M:%S")


def extract_full_content(note: Dict[str, Any]) -> Dict[str, Any]:
    """提取note的完整内容结构"""
    content = note.get('content', {})
    
    # 定义要提取的字段，按优先级排序
    priority_fields = [
        'title', 'abstract', 'summary', 'strengths', 'weaknesses', 
        'questions', 'comment', 'decision', 'rating', 'confidence',
        'soundness', 'presentation', 'contribution', 'flag_for_ethics_review',
        'code_of_conduct'
    ]
    
    extracted_content = {}
    
    # 提取优先级字段
    for field in priority_fields:
        if field in content:
            field_value = content[field]
            if isinstance(field_value, dict) and 'value' in field_value:
                extracted_content[field] = field_value
            elif field_value is not None:
                extracted_content[field] = {'value': field_value}
    
    # 提取其他字段
    for key, value in content.items():
        if key not in priority_fields and value is not None:
            if isinstance(value, dict) and 'value' in value:
                extracted_content[key] = value
            else:
                extracted_content[key] = {'value': value}
    
    return extracted_content


def is_review_note(note: Dict[str, Any]) -> bool:
    """判断是否为评审note"""
    invitations = note.get('invitations', [])
    return any('Official_Review' in inv for inv in invitations)


def is_author_response(note: Dict[str, Any]) -> bool:
    """判断是否为作者回复"""
    signatures = note.get('signatures', [])
    return any('Authors' in sig for sig in signatures)


def is_meta_review_note(note: Dict[str, Any]) -> bool:
    """判断是否为Meta_Review note"""
    invitations = note.get('invitations', [])
    return any('Meta_Review' in inv for inv in invitations)


def is_decision_note(note: Dict[str, Any]) -> bool:
    """判断是否为Decision note"""
    invitations = note.get('invitations', [])
    return any('Decision' in inv for inv in invitations)


def is_desk_rejection_note(note: Dict[str, Any]) -> bool:
    """判断是否为Desk_Rejection note"""
    invitations = note.get('invitations', [])
    return any('Desk_Rejection' in inv for inv in invitations)


def is_public_comment_note(note: Dict[str, Any]) -> bool:
    """判断是否为Public_Comment note"""
    invitations = note.get('invitations', [])
    return any('Public_Comment' in inv for inv in invitations)


def is_official_comment_note(note: Dict[str, Any]) -> bool:
    """判断是否为Official_Comment note"""
    invitations = note.get('invitations', [])
    return any('Official_Comment' in inv for inv in invitations)


def extract_paper_info(notes: List[Dict[str, Any]], forum_id: str) -> Dict[str, Any]:
    """从给定forum的notes中提取论文信息"""
    paper_info = {
        'title': None,
        'keywords': None,
        'abstract': None,
        'primary_area': None,
        'pdf_url': None,
        'meta_review': None,
        'decision': None,
        'desk_rejection': None
    }
    
    # 查找submission note (通常是forum_id对应的note)
    submission_note = None
    for note in notes:
        if note.get('id') == forum_id:
            submission_note = note
            break
    
    if not submission_note:
        return paper_info
    
    content = submission_note.get('content', {})
    
    # 提取各个字段
    for field in ['title', 'keywords', 'abstract', 'primary_area', 'pdf']:
        if field in content:
            field_data = content[field]
            if isinstance(field_data, dict) and 'value' in field_data:
                if field == 'pdf':
                    paper_info['pdf_url'] = field_data['value']
                else:
                    paper_info[field] = field_data['value']
    
    # 提取Meta_Review、Decision、Desk_Rejection notes
    for note in notes:
        if is_meta_review_note(note):
            paper_info['meta_review'] = {
                'id': note.get('id'),
                'timestamp': format_timestamp(get_timestamp(note)),
                'signatures': note.get('signatures', []),
                'content': extract_full_content(note)
            }
        elif is_decision_note(note):
            paper_info['decision'] = {
                'id': note.get('id'),
                'timestamp': format_timestamp(get_timestamp(note)),
                'signatures': note.get('signatures', []),
                'content': extract_full_content(note)
            }
        elif is_desk_rejection_note(note):
            paper_info['desk_rejection'] = {
                'id': note.get('id'),
                'timestamp': format_timestamp(get_timestamp(note)),
                'signatures': note.get('signatures', []),
                'content': extract_full_content(note)
            }
    
    return paper_info


def extract_result_info(notes: List[Dict[str, Any]], forum_id: str) -> Dict[str, Any]:
    """从给定forum的notes中提取论文结果信息"""
    result_info = {
        'state': None
    }
    
    # 查找submission note (通常是forum_id对应的note)
    submission_note = None
    for note in notes:
        if note.get('id') == forum_id:
            submission_note = note
            break
    
    if not submission_note:
        return result_info
    
    # 获取venueid字段，首先从content中查找
    content = submission_note.get('content', {})
    venueid_field = content.get('venueid', {})
    
    if isinstance(venueid_field, dict) and 'value' in venueid_field:
        venueid = venueid_field['value']
    else:
        # 如果content中没有，尝试从顶层获取
        venueid_field = submission_note.get('venueid', {})
        if isinstance(venueid_field, dict) and 'value' in venueid_field:
            venueid = venueid_field['value']
        else:
            venueid = venueid_field or ''
    
    # 根据venueid判断论文状态
    if 'Withdrawn_Submission' in venueid:
        result_info['state'] = 'withdrawn'
    elif 'Rejected_Submission' in venueid or 'Desk_Rejected_Submission' in venueid:
        result_info['state'] = 'reject'
    elif 'ICLR.cc/2025/Conference' in venueid and 'Submission' not in venueid:
        # 如果是ICLR.cc/2025/Conference但不包含Submission，说明是接受的
        result_info['state'] = 'accept'
    else:
        # 其他情况暂时设为None，可能是审查中或其他状态
        result_info['state'] = None
    
    return result_info


def add_replies(note: Dict[str, Any], all_notes: List[Dict[str, Any]], 
               processed_ids: set) -> Dict[str, Any]:
    """递归构建对话链，添加回复"""
    note_id = note['id']
    
    if note_id in processed_ids:
        return None
    
    processed_ids.add(note_id)
    
    # 构建当前note的结构
    node = {
        'id': note_id,
        'signatures': note.get('signatures', []),
        'replyto': note.get('replyto'),  # 保留replyto信息用于合并判断,
        'invitations': note.get('invitations', []),  # 保留原始的invitations字段
        'timestamp': format_timestamp(get_timestamp(note)),
        'content': extract_full_content(note)
    }
    
    # 查找所有回复此note的notes
    replies = []
    for other_note in all_notes:
        if (other_note.get('replyto') == note_id and 
            other_note['id'] not in processed_ids):
            reply_node = add_replies(other_note, all_notes, processed_ids)
            if reply_node:
                replies.append(reply_node)
    
    # 不需要排序，数据已经在ndjson_to_json_converter.py中按时间戳排序过了
    
    if replies:
        node['replies'] = replies
    
    return node


def build_conversation_chains(forum_notes: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """为一个forum构建所有对话链"""
    # 找到所有评审notes、公开评论notes和官方评论notes（作为对话链的起点）
    review_notes = [note for note in forum_notes if is_review_note(note)]
    public_comment_notes = [note for note in forum_notes if is_public_comment_note(note)]
    official_comment_notes = [note for note in forum_notes if is_official_comment_note(note)]
    
    # 合并所有可以作为对话链起点的notes
    starting_notes = review_notes + public_comment_notes + official_comment_notes
    
    if not starting_notes:
        return []
    
    # 不需要排序，数据已经在ndjson_to_json_converter.py中按时间戳排序过了
    
    conversations = []
    processed_ids = set()
    
    # 首先处理所有没有replyto的起始notes（真正的对话链起点）
    root_notes = [note for note in starting_notes if not note.get('replyto')]
    
    for root_note in root_notes:
        if root_note['id'] not in processed_ids:
            # 构建以此note为起点的对话链
            conversation_tree = add_replies(root_note, forum_notes, processed_ids)
            if conversation_tree:
                # 将树结构转换为链式结构
                conversation_chain = flatten_conversation_tree(conversation_tree)
                conversations.append(conversation_chain)
    
    # 然后处理有replyto但还没被处理的notes（可能是回复到submission的评论链）
    remaining_notes = [note for note in starting_notes 
                      if note['id'] not in processed_ids and note.get('replyto')]
    
    for remaining_note in remaining_notes:
        if remaining_note['id'] not in processed_ids:
            # 构建以此note为起点的对话链
            conversation_tree = add_replies(remaining_note, forum_notes, processed_ids)
            if conversation_tree:
                # 将树结构转换为链式结构
                conversation_chain = flatten_conversation_tree(conversation_tree)
                conversations.append(conversation_chain)
    
    return conversations


def is_reviewer_followup(node: Dict[str, Any]) -> bool:
    """判断是否是评审员的后续回复（只有comment字段的评审员回复，且不是初始评审）"""
    signatures = node.get('signatures', [])
    if not signatures:
        return False
    
    # 检查是否是评审员
    signature = signatures[0] if isinstance(signatures, list) else signatures
    if not re.search(r'Reviewer_', signature):
        return False
    
    # 检查content是否只有comment字段
    content = node.get('content', {})
    content_keys = list(content.keys())
    
    # 必须只有comment字段
    if content_keys != ['comment']:
        return False
    
    # 检查invitations字段，排除初始评审
    invitations = node.get('invitations', [])
    if isinstance(invitations, list):
        # 如果包含Official_Review，说明是初始评审，不是后续回复
        for invitation in invitations:
            if 'Official_Review' in str(invitation):
                return False
    
    # 必须有replyto字段，说明是对某个内容的回复
    return node.get('replyto') is not None


def find_reply_chain_root(node_id: str, all_nodes: Dict[str, Dict[str, Any]], visited: set = None) -> str:
    """
    找到回复链的根节点ID
    处理 A -> B -> C 这样的回复链，找到最初的根节点
    
    Args:
        node_id: 当前节点ID
        all_nodes: 所有节点的映射 {id: node}
        visited: 已访问的节点集合，用于避免循环引用
    
    Returns:
        str: 根节点的ID
    """
    if visited is None:
        visited = set()
    
    if node_id in visited:
        return node_id  # 避免循环引用
    
    visited.add(node_id)
    
    if node_id not in all_nodes:
        return node_id
    
    node = all_nodes[node_id]
    replyto = node.get('replyto')
    
    if not replyto or replyto not in all_nodes:
        return node_id
    
    # 检查replyto的节点是否也是同类型的回复
    replyto_node = all_nodes[replyto]
    current_signatures = tuple(node.get('signatures', []))
    replyto_signatures = tuple(replyto_node.get('signatures', []))
    
    # 如果是同一作者的回复，继续向上查找
    if (is_author_response(node) and is_author_response(replyto_node) and 
        current_signatures == replyto_signatures):
        return find_reply_chain_root(replyto, all_nodes, visited)
    elif (is_reviewer_followup(node) and is_reviewer_followup(replyto_node) and 
          current_signatures == replyto_signatures):
        return find_reply_chain_root(replyto, all_nodes, visited)
    else:
        # 找到了不同类型的节点，当前replyto就是根
        return replyto


def flatten_conversation_tree(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将对话树结构扁平化为链式结构，并合并作者和评审员的连续回复"""
    chain = []
    
    def traverse(node):
        # 添加当前节点（不包含replies字段），但保留replyto信息用于合并判断
        node_copy = {k: v for k, v in node.items() if k != 'replies'}
        chain.append(node_copy)
        
        # 递归处理回复
        if 'replies' in node:
            for reply in node['replies']:
                traverse(reply)
    
    traverse(tree)
    
    # 创建节点映射，用于查找回复链根节点
    all_nodes_map = {node['id']: node for node in chain}
    
    # 改进的合并策略：使用回复链根节点作为分组键
    from collections import defaultdict
    
    # 分组收集需要合并的回复
    merge_groups = defaultdict(list)
    non_merge_nodes = []
    
    for node in chain:
        if is_author_response(node) or is_reviewer_followup(node):
            # 确定回复类型
            reply_type = 'author' if is_author_response(node) else 'reviewer_followup'
            
            # 找到回复链的根节点
            root_id = find_reply_chain_root(node['id'], all_nodes_map)
            
            # 创建分组键：(signatures, root_reply_id, type)
            group_key = (tuple(node['signatures']), root_id, reply_type)
            merge_groups[group_key].append(node)
        else:
            non_merge_nodes.append(node)
    
    # 合并每个分组中的回复
    merged_nodes = []
    for group_key, nodes in merge_groups.items():
        if len(nodes) > 1:
            # 按时间戳排序，确保合并顺序正确
            nodes.sort(key=lambda x: x.get('timestamp', 0))
            
            # 需要合并
            merged_node = nodes[0].copy()  # 使用第一个回复作为基础
            
            # 合并所有回复的comment内容
            comments = []
            for reply in nodes:
                if 'content' in reply and 'comment' in reply['content']:
                    comment_data = reply['content']['comment']
                    if isinstance(comment_data, dict) and 'value' in comment_data:
                        comments.append(comment_data['value'])
                    elif isinstance(comment_data, str):
                        comments.append(comment_data)
            
            # 用\n\n拼接所有comment
            if comments:
                merged_comment = '\n\n'.join(comments)
                if 'content' not in merged_node:
                    merged_node['content'] = {}
                merged_node['content']['comment'] = {'value': merged_comment}
            
            # 使用最后一个回复的时间戳（最新的时间）
            if nodes:
                merged_node['timestamp'] = nodes[-1]['timestamp']
            
            merged_nodes.append(merged_node)
        else:
            # 只有一个回复，直接添加
            merged_nodes.append(nodes[0])
    
    # 合并所有节点并按原始顺序排序
    all_nodes = merged_nodes + non_merge_nodes
    
    # 创建一个映射来保持原始顺序
    original_positions = {}
    for i, node in enumerate(chain):
        original_positions[node['id']] = i
    
    # 按原始位置排序
    all_nodes.sort(key=lambda x: original_positions.get(x['id'], float('inf')))
    
    return all_nodes


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='将 all_notes_readable.json 转换为 structured_review_conversations.json',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python convert_to_structured.py --dir output
  python convert_to_structured.py --dir /path/to/data
        """
    )
    
    parser.add_argument(
        '--dir', 
        type=str, 
        default='output',
        help='指定包含输入文件的目录路径 (默认: output)'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    print("开始转换 all_notes_readable.json 到 structured_review_conversations.json...")
    
    # 构建输入和输出文件路径
    input_file = os.path.join(args.dir, 'all_notes_readable.json')
    output_file = os.path.join(args.dir, 'structured_review_conversations.json')
    
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    
    # 检查输入目录是否存在
    if not os.path.exists(args.dir):
        print(f"错误: 目录 '{args.dir}' 不存在")
        return
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            all_notes = json.load(f)
        print(f"成功加载 {len(all_notes)} 条记录")
    except FileNotFoundError:
        print(f"错误: 找不到输入文件 {input_file}")
        return
    except json.JSONDecodeError as e:
        print(f"错误: JSON解析失败 - {e}")
        return
    
    # 按forum分组
    forums = defaultdict(list)
    for note in all_notes:
        forum_id = note.get('forum')
        if forum_id:
            forums[forum_id].append(note)
    
    print(f"发现 {len(forums)} 个论坛")
    
    # 构建结构化数据
    structured_data = {}
    total_conversations = 0
    
    for forum_id, forum_notes in forums.items():
        # 提取论文信息
        paper_info = extract_paper_info(forum_notes, forum_id)
        
        # 提取结果信息
        result_info = extract_result_info(forum_notes, forum_id)
        
        # 构建对话链
        conversations = build_conversation_chains(forum_notes)
        
        if conversations:  # 只保存有对话的forum
            structured_data[forum_id] = {
                'paper_info': paper_info,
                'result': result_info,
                'conversations': conversations
            }
            total_conversations += len(conversations)
    
    print(f"处理了 {len(structured_data)} 个论坛")
    print(f"生成了 {total_conversations} 个评审对话链")
    
    # 保存结果
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, indent=2, ensure_ascii=False)
        print(f"结果已保存到 {output_file}")
    except Exception as e:
        print(f"错误: 保存文件失败 - {e}")
        return
    
    print("\n转换完成！")


if __name__ == "__main__":
    main()