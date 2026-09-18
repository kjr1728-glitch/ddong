"""
ComfyUI HTTP API 클라이언트 (외부 패키지 없이 requests만 사용)

ComfyUI는 --listen 옵션으로 띄우면 http://호스트:8188 에서 REST API를 제공합니다.
이 모듈은 그중 네 가지만 씁니다.
  POST /upload/image   시작 프레임 업로드
  POST /prompt         워크플로우(API 포맷 JSON) 실행 요청
  GET  /history/<id>   완료 여부 확인 + 결과 파일 목록
  GET  /view           결과 파일 내려받기

로컬 GPU든 Kaggle 터널이든 URL만 다르고 동작은 같습니다.
"""
import json
import os
import time
import uuid

import requests


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    # ------------------------------------------------------------------ 기본
    def _get(self, path: str, **kwargs):
        r = requests.get(self.base_url + path, timeout=self.timeout, **kwargs)
        r.raise_for_status()
        return r

    def _post(self, path: str, **kwargs):
        r = requests.post(self.base_url + path, timeout=self.timeout, **kwargs)
        if r.status_code >= 400:
            # ComfyUI는 잘못된 워크플로우를 400과 함께 어느 노드가 문제인지 알려줍니다.
            try:
                detail = json.dumps(r.json(), ensure_ascii=False, indent=2)
            except ValueError:
                detail = r.text
            raise ComfyError(f"ComfyUI 요청 실패 ({r.status_code}) {path}\n{detail}")
        return r

    def ping(self) -> dict:
        """서버가 살아 있는지 확인하고 GPU 정보를 돌려준다"""
        return self._get("/system_stats").json()

    def object_info(self, class_type: str = None) -> dict:
        """설치된 노드 정보. class_type을 주면 그 노드만 (없으면 빈 dict)"""
        path = "/object_info" + (f"/{class_type}" if class_type else "")
        try:
            return self._get(path).json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return {}
            raise

    # ------------------------------------------------------------------ 입력
    def upload_image(self, path: str, subfolder: str = "shopping_shorts") -> str:
        """이미지를 ComfyUI input 폴더에 올리고 LoadImage 노드에 넣을 이름을 돌려준다"""
        with open(path, "rb") as f:
            r = self._post(
                "/upload/image",
                files={"image": (os.path.basename(path), f)},
                data={"overwrite": "true", "subfolder": subfolder},
            )
        info = r.json()
        name = info["name"]
        sub = info.get("subfolder") or ""
        return f"{sub}/{name}" if sub else name

    # ------------------------------------------------------------------ 실행
    def queue(self, workflow: dict) -> str:
        r = self._post(
            "/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
        )
        data = r.json()
        if "prompt_id" not in data:
            raise ComfyError(f"prompt_id를 받지 못했습니다: {data}")
        return data["prompt_id"]

    def queue_position(self, prompt_id: str):
        """대기열에서 몇 번째인지 (실행 중이면 0, 없으면 None)"""
        try:
            q = self._get("/queue").json()
        except requests.RequestException:
            return None
        for item in q.get("queue_running", []):
            if len(item) > 1 and item[1] == prompt_id:
                return 0
        for i, item in enumerate(q.get("queue_pending", []), start=1):
            if len(item) > 1 and item[1] == prompt_id:
                return i
        return None

    def wait(self, prompt_id: str, timeout: int = 3600, poll: float = 3.0, log=print) -> dict:
        """완료될 때까지 기다렸다가 history 항목을 돌려준다. 실패하면 ComfyError."""
        started = time.time()
        last_report = 0.0
        while True:
            hist = self._get(f"/history/{prompt_id}").json()
            entry = hist.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(
                        "ComfyUI 실행 오류:\n" + _format_status_messages(status)
                    )
                if status.get("completed", True) or entry.get("outputs"):
                    return entry

            elapsed = time.time() - started
            if elapsed > timeout:
                raise ComfyError(f"{timeout}초 안에 끝나지 않았습니다 (prompt_id={prompt_id})")
            if log and elapsed - last_report >= 30:
                pos = self.queue_position(prompt_id)
                where = "실행 중" if pos == 0 else (f"대기 {pos}번째" if pos else "확인 중")
                log(f"    ... {int(elapsed)}초 경과 ({where})")
                last_report = elapsed
            time.sleep(poll)

    # ------------------------------------------------------------------ 출력
    @staticmethod
    def output_files(entry: dict) -> list:
        """history 항목에서 결과 파일 목록을 뽑는다 (영상 먼저, 이미지 나중)"""
        videos, images = [], []
        for node_out in entry.get("outputs", {}).values():
            for key, items in node_out.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict) or "filename" not in item:
                        continue
                    if key in ("videos", "gifs") or item["filename"].lower().endswith(
                        (".mp4", ".webm", ".mov", ".webp", ".gif")
                    ):
                        videos.append(item)
                    elif key == "images":
                        images.append(item)
        return videos + images

    def download(self, file_info: dict, dest_path: str):
        params = {
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder", ""),
            "type": file_info.get("type", "output"),
        }
        r = requests.get(self.base_url + "/view", params=params, stream=True, timeout=self.timeout)
        r.raise_for_status()
        tmp = dest_path + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        os.replace(tmp, dest_path)
        return dest_path


def _format_status_messages(status: dict) -> str:
    lines = []
    for msg in status.get("messages", []):
        if not isinstance(msg, (list, tuple)) or len(msg) < 2:
            continue
        kind, data = msg[0], msg[1]
        if kind == "execution_error" and isinstance(data, dict):
            lines.append(f"  노드 {data.get('node_id')} ({data.get('node_type')}): "
                         f"{data.get('exception_message')}")
    return "\n".join(lines) or json.dumps(status, ensure_ascii=False)
