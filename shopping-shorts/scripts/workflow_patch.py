"""
ComfyUI 워크플로우(API 포맷 JSON)에 값을 채워 넣는 도구

노드 번호가 아니라 class_type으로 노드를 찾기 때문에, ComfyUI에서
"Save (API Format)"으로 내보낸 어떤 Wan 워크플로우든 그대로 쓸 수 있습니다.

  LoadImage                         → 시작 프레임 파일명
  Wan22ImageToVideoLatent / WanImageToVideo → 가로/세로/프레임 수
  KSampler / KSamplerAdvanced       → 시드 (positive/negative 링크를 따라가 프롬프트도 찾음)
  CLIPTextEncode                    → 긍정/부정 프롬프트 텍스트
  SaveVideo / SaveAnimatedWEBP / VHS_VideoCombine → 결과 파일 이름 앞부분
"""
import copy
import json

LATENT_NODES = ("Wan22ImageToVideoLatent", "WanImageToVideo", "WanFirstLastFrameToVideo")
SAMPLER_NODES = ("KSampler", "KSamplerAdvanced")
SAVE_NODES = ("SaveVideo", "SaveAnimatedWEBP", "VHS_VideoCombine", "SaveWEBM")
TEXT_NODES = ("CLIPTextEncode",)
LOADER_NODES = {
    "UNETLoader": "unet_name",
    "CLIPLoader": "clip_name",
    "VAELoader": "vae_name",
    "LoraLoaderModelOnly": "lora_name",
    "UnetLoaderGGUF": "unet_name",
    "CheckpointLoaderSimple": "ckpt_name",
}


def load_workflow(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        wf = json.load(f)
    if "nodes" in wf and "links" in wf:
        raise SystemExit(
            f"{path} 는 UI 포맷 워크플로우입니다. ComfyUI에서 설정(톱니바퀴) → "
            "'Dev mode' 를 켜고 'Save (API Format)'으로 다시 내보내 주세요."
        )
    return wf


def nodes_of(wf: dict, class_types) -> list:
    if isinstance(class_types, str):
        class_types = (class_types,)
    return [nid for nid, node in wf.items() if node.get("class_type") in class_types]


def _follow_to_text_node(wf: dict, link, role: str, depth: int = 0):
    """[node_id, output_index] 링크를 따라가 CLIPTextEncode 노드 id를 찾는다.
    role은 "positive" 또는 "negative". WanImageToVideo처럼 두 조건을 모두 받아
    통과시키는 노드를 만나면 같은 역할의 입력만 따라간다."""
    if depth > 6 or not isinstance(link, list) or not link:
        return None
    nid = str(link[0])
    node = wf.get(nid)
    if node is None:
        return None
    if node.get("class_type") in TEXT_NODES:
        return nid
    inputs = node.get("inputs", {})
    for key in (role, "conditioning"):
        if key in inputs:
            found = _follow_to_text_node(wf, inputs[key], role, depth + 1)
            if found:
                return found
    return None


def find_prompt_nodes(wf: dict):
    """(positive 노드 id 집합, negative 노드 id 집합)"""
    pos, neg = set(), set()
    for sid in nodes_of(wf, SAMPLER_NODES):
        inputs = wf[sid].get("inputs", {})
        p = _follow_to_text_node(wf, inputs.get("positive"), "positive")
        n = _follow_to_text_node(wf, inputs.get("negative"), "negative")
        if p:
            pos.add(p)
        if n:
            neg.add(n)
    return pos, neg


def patch_workflow(
    wf: dict,
    *,
    image_name: str = None,
    positive: str = None,
    negative: str = None,
    width: int = None,
    height: int = None,
    length: int = None,
    seed: int = None,
    steps: int = None,
    filename_prefix: str = None,
) -> dict:
    wf = copy.deepcopy(wf)

    if image_name is not None:
        for nid in nodes_of(wf, "LoadImage"):
            wf[nid]["inputs"]["image"] = image_name

    pos_nodes, neg_nodes = find_prompt_nodes(wf)
    if positive is not None:
        for nid in pos_nodes:
            wf[nid]["inputs"]["text"] = positive
    if negative is not None:
        for nid in neg_nodes:
            wf[nid]["inputs"]["text"] = negative

    for nid in nodes_of(wf, LATENT_NODES):
        inputs = wf[nid]["inputs"]
        if width is not None and "width" in inputs:
            inputs["width"] = width
        if height is not None and "height" in inputs:
            inputs["height"] = height
        if length is not None and "length" in inputs:
            inputs["length"] = length

    for nid in nodes_of(wf, SAMPLER_NODES):
        inputs = wf[nid]["inputs"]
        if seed is not None:
            for key in ("seed", "noise_seed"):
                if key in inputs:
                    inputs[key] = seed
        # KSamplerAdvanced 두 개로 나눠 도는 14B 워크플로우는 start/end step이 steps와
        # 묶여 있어서 steps만 바꾸면 깨집니다. 단일 KSampler일 때만 바꿉니다.
        if steps is not None and wf[nid]["class_type"] == "KSampler":
            inputs["steps"] = steps

    if filename_prefix is not None:
        for nid in nodes_of(wf, SAVE_NODES):
            wf[nid]["inputs"]["filename_prefix"] = filename_prefix

    return wf


def describe(wf: dict) -> dict:
    """워크플로우가 어떤 노드/모델을 쓰는지 요약 (--check 용)"""
    pos, neg = find_prompt_nodes(wf)
    models = []
    for nid, node in wf.items():
        ct = node.get("class_type")
        if ct in LOADER_NODES:
            models.append((ct, node["inputs"].get(LOADER_NODES[ct])))
    latent = nodes_of(wf, LATENT_NODES)
    size = None
    if latent:
        i = wf[latent[0]]["inputs"]
        size = (i.get("width"), i.get("height"), i.get("length"))
    return {
        "class_types": sorted({n.get("class_type") for n in wf.values()}),
        "models": models,
        "positive_nodes": sorted(pos),
        "negative_nodes": sorted(neg),
        "load_image_nodes": nodes_of(wf, "LoadImage"),
        "save_nodes": nodes_of(wf, SAVE_NODES),
        "size": size,
    }


def check_against_server(wf: dict, client) -> list:
    """설치 안 된 노드, 없는 모델 파일을 찾아 문제 목록을 돌려준다"""
    problems = []
    info = client.object_info()
    for nid, node in wf.items():
        ct = node.get("class_type")
        if ct not in info:
            problems.append(f"노드 '{ct}' 가 ComfyUI에 없습니다 (ComfyUI 업데이트 또는 커스텀 노드 설치 필요)")
            continue
        if ct in LOADER_NODES:
            key = LOADER_NODES[ct]
            wanted = node["inputs"].get(key)
            options = info[ct].get("input", {}).get("required", {}).get(key, [[]])[0]
            if isinstance(options, list) and wanted not in options:
                problems.append(
                    f"모델 파일 '{wanted}' 이(가) 없습니다 ({ct}). "
                    f"현재 있는 파일: {options[:5] or '없음'}"
                )
    return problems
