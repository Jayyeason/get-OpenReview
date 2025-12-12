import json
import argparse

def main():
    # 1. 定义命令行参数解析器
    parser = argparse.ArgumentParser(
        description="统计 JSON 文件最外层有多少个对象"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,              # 必须提供
        help="要读取的 JSON 文件路径"
    )

    args = parser.parse_args()

    filename = args.input  # 通过 --input/-i 传进来的文件名

    # 2. 读取 JSON 文件
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 3. 根据最外层结构统计数量
    if isinstance(data, dict):
        num_objects = len(data)
        print(f"最外层是一个对象(dict)，包含 {num_objects} 个子对象。")
    elif isinstance(data, list):
        num_objects = len(data)
        print(f"最外层是一个数组(list)，包含 {num_objects} 个元素。")
    else:
        print(f"最外层是类型：{type(data)}，无法直接统计 ‘多个对象’ 的数量。")

if __name__ == "__main__":
    main()