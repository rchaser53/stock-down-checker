import json
import sys


def filter_stocks(input_path, output_path):
    # JSONファイル読み込み
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # JSON構造に応じて配列を取得
    if isinstance(data, dict):
        if "stocks" in data:
            items = data["stocks"]
        else:
            items = next(
                (v for v in data.values() if isinstance(v, list)),
                []
            )
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("JSONの形式が想定外です")

    # 条件で絞り込み
    result = [
        {
            "code": item["code"],
            "name": item["name"],
            "diff_percent_from_highest": item["diff_percent_from_highest"]
        }
        for item in items
        if isinstance(item, dict)
        and item.get("diff_percent_from_highest", 9999) <= -40
    ]

    # diff_percent_from_highest の小さい順にソート
    result.sort(key=lambda x: x["diff_percent_from_highest"])

    # 出力
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"{len(result)}件を出力しました: {output_path}")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output.json"

    filter_stocks(input_file, output_file)