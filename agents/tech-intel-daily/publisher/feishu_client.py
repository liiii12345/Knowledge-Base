#!/usr/bin/env python3
"""飞书开放平台客户端：token 获取、block 写入、批量删除、权限设置。

踩过的坑（都在真实运行中遇到过）：
1. tenant_access_token 不能用 resp.json()，本地环境会出编码问题 → 用 json.loads(resp.text)
2. 文档标题写入后**不可更新**，标题写坏只能新建文档
3. batch_delete 用的是 start_index/end_index，不是按 block_id 删除
4. 写入 children 每批最多 50 个 block，过多会超时
5. 文档权限需要单独调用接口设置，新建后必须调用
"""
import json
import sys
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "https://open.feishu.cn/open-apis"
BATCH_SIZE = 50


class FeishuError(Exception):
    pass


def _request(method: str, path: str, token: str = "", payload: dict = None, timeout: int = 30):
    url = BASE + path
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    # 用 json.loads(resp.text) 而不是 resp.json()：后者在本地化环境里偶发编码异常
    body = json.loads(raw)
    if body.get("code") not in (0, None):
        raise FeishuError(f"{path} -> code={body.get('code')} msg={body.get('msg')}")
    return body.get("data", {})


def get_tenant_token(app_id: str, app_secret: str) -> str:
    data = _request("POST", "/auth/v3/tenant_access_token/internal",
                    payload={"app_id": app_id, "app_secret": app_secret})
    return data.get("tenant_access_token", "")


def clear_body(token: str, doc_id: str, keep_first: int = 1):
    """清空正文但保留标题 block（标题不可更新，删了就找不回来）。"""
    children = _request("GET", f"/docx/v1/documents/{doc_id}/blocks"
                               f"?page_size=500&document_revision_id=-1", token)
    items = children.get("items", [])
    if len(items) <= keep_first:
        return 0
    _request("DELETE", f"/docx/v1/documents/{doc_id}/blocks/{items[0]['block_id']}/children/batch_delete",
             token, {"start_index": keep_first, "end_index": len(items) - 1})
    return max(0, len(items) - keep_first)


def append_blocks(token: str, doc_id: str, blocks: list, parent_id: str = None) -> int:
    """分批写入，每批 50 个。返回写入总数。"""
    written = 0
    parent = parent_id or doc_id
    for i in range(0, len(blocks), BATCH_SIZE):
        chunk = blocks[i:i + BATCH_SIZE]
        _request("POST", f"/docx/v1/documents/{doc_id}/blocks/{parent}/children",
                 token, {"children": chunk, "index": -1})
        written += len(chunk)
    return written


def set_public(token: str, doc_id: str, chat_id: str = ""):
    """设置文档为组织内可读。新建文档后必须调用，否则订阅者打不开。"""
    payload = {"external_access": False, "security_entity": "anyone_can_view",
               "comment_entity": "anyone_can_view", "share_entity": "anyone",
               "link_share_entity": "tenant_readable"}
    try:
        _request("PUT", f"/drive/v2/permissions/{doc_id}/public?type=docx", token, payload)
        return True
    except FeishuError as exc:
        print(f"[warn] 权限设置失败：{exc}", file=sys.stderr)
        return False


def send_group_message(token: str, chat_id: str, text: str):
    _request("POST", "/im/v1/messages?receive_id_type=chat_id", token,
             {"receive_id": chat_id, "msg_type": "text",
              "content": json.dumps({"text": text}, ensure_ascii=False)})
