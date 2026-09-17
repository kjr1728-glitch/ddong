"""
다음에 만들 주제 하나를 골라서 출력한다 (cron 자동 실행용)

topics.txt에 적어둔 주제들을 위에서부터 순서대로 하나씩 꺼내 씁니다.
어디까지 썼는지는 output/.topic_state.json에 기록해두므로, 매일 실행하면
매번 다른 주제가 나오고 목록 끝에 닿으면 처음으로 돌아갑니다.

주제 이름만 표준출력으로 내보내므로 cron에서 그대로 쓸 수 있습니다:
    python main.py --keyword "$(python scripts/pick_topic.py)"

사용법:
    python scripts/pick_topic.py            # 다음 주제를 꺼내 쓰고 기록
    python scripts/pick_topic.py --peek     # 기록하지 않고 미리보기만
    python scripts/pick_topic.py --list     # 전체 목록과 현재 위치 보기
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TOPICS = os.path.join(PROJECT_ROOT, "topics.txt")
DEFAULT_STATE = os.path.join(PROJECT_ROOT, "output", ".topic_state.json")


def load_topics(path: str) -> list:
    if not os.path.exists(path):
        sys.exit(
            f"주제 목록 파일이 없습니다: {path}\n"
            "한 줄에 하나씩 주제를 적은 topics.txt를 만들어주세요.\n"
            "(# 으로 시작하는 줄은 메모로 보고 건너뜁니다)"
        )

    with open(path, "r", encoding="utf-8") as f:
        topics = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not topics:
        sys.exit(f"{path}에 사용할 수 있는 주제가 없습니다.")

    return topics


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"index": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # 사람이 파일을 잘못 고쳤거나 깨졌어도 자동화가 멈추지 않게 한다
        return {"index": int(state.get("index", 0))}
    except (ValueError, OSError):
        return {"index": 0}


def save_state(path: str, index: int, topic: str):
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"index": index, "last_topic": topic}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topics", default=DEFAULT_TOPICS)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--peek", action="store_true", help="기록하지 않고 다음 주제만 보기")
    parser.add_argument("--list", action="store_true", help="전체 목록과 현재 위치 보기")
    args = parser.parse_args()

    topics = load_topics(args.topics)
    index = load_state(args.state)["index"] % len(topics)
    topic = topics[index]

    if args.list:
        # 목록 보기는 사람이 읽는 용도이므로 stderr가 아니라 stdout으로 충분히 출력
        for i, t in enumerate(topics):
            marker = "→" if i == index else " "
            print(f"{marker} {i + 1:2d}. {t}")
        return

    if not args.peek:
        save_state(args.state, (index + 1) % len(topics), topic)

    # cron에서 $(...)로 받아쓰기 때문에, 주제 이름 외에는 stdout에 아무것도 쓰지 않는다
    print(topic)


if __name__ == "__main__":
    main()
