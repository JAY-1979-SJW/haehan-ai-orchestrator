"""가비아 AI 채팅 엔드포인트 — GPT → 도구 호출 → SSE 스트리밍.

지원 도구:
  - get_status          : 가비아 업무 현황 조회
  - start_login_watch   : 로그인 감지 시작 (사용자 직접 로그인 유도)
  - get_dns_tasks       : DNS 업무 레지스트리 조회
  - get_nav_plan        : DNS 업무 브라우저 네비게이션 계획
  - prepare_dns_record  : DNS 레코드 입력 초안 생성 (실제 저장 안 함)
  - open_gabia_dns      : 가비아 DNS 관리 화면 CDP로 열기

금지: 비밀번호/OTP 자동 입력, 최종 저장 버튼 자동 클릭, 결제 자동화
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]

GPT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """당신은 가비아(Gabia) 도메인/DNS/호스팅 업무 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 호출하세요.

핵심 운영 원칙:
- 가비아 로그인은 OTP/2FA 필수이므로 사용자가 직접 수행합니다. AI는 로그인 감지만 합니다.
- DNS 레코드 최종 저장 버튼은 AI가 절대 자동 클릭하지 않습니다. 사용자 승인 필수.
- AI는 레코드 입력 준비, 화면 이동, 초안 생성까지만 자동 수행합니다.
- 결제/청구는 사용자가 직접 my.gabia.com에서 처리합니다.
- 비밀번호/OTP/세션/쿠키는 절대 다루지 않습니다.

업무 흐름:
1. 사용자가 원하는 작업 설명
2. AI가 작업 계획 안내
3. 필요 시 로그인 감지 시작 → 사용자가 브라우저에서 직접 로그인
4. AI가 DNS 관리 화면으로 이동 + 레코드 입력 초안 준비
5. 사용자가 확인 후 최종 저장

답변은 한국어로 간결하게 합니다."""


def _tool_defs() -> list:
    def _fn(name, desc, props, required=None):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": props, "required": required or []},
            },
        }

    return [
        _fn("get_status", "가비아 업무 현황 및 게이트 정책을 조회합니다.", {}),
        _fn(
            "start_login_watch",
            "가비아 로그인 감지를 시작합니다.",
            {
                "timeout": {"type": "integer", "description": "최대 대기 시간(초), 기본 300"},
            },
        ),
        _fn("get_dns_tasks", "가비아 DNS 업무 레지스트리 목록을 조회합니다.", {}),
        _fn("get_nav_plan", "가비아 DNS 업무 브라우저 네비게이션 단계별 계획을 조회합니다.", {}),
        _fn(
            "prepare_dns_record",
            "DNS 레코드 입력 초안을 준비합니다. 실제 저장하지 않습니다.",
            {
                "subdomain": {"type": "string", "description": "서브도메인 (예: autowork, app, api)"},
                "record_type": {"type": "string", "enum": ["A", "CNAME", "MX", "TXT"]},
                "value": {"type": "string", "description": "레코드 값 (IP 또는 도메인)"},
                "ttl": {"type": "integer", "description": "TTL (기본 3600)"},
            },
            ["subdomain", "record_type", "value"],
        ),
        _fn(
            "open_gabia_dns",
            "CDP 브라우저로 가비아 DNS 관리 화면을 엽니다.",
            {
                "domain": {"type": "string", "description": "도메인 (기본: haehan-ai.kr)"},
            },
        ),
    ]


def _run_tool(name: str, inputs: dict) -> str:
    if name == "get_status":
        ops = [
            {"name": "공개 페이지 조회", "gate": "READ_ONLY_ALLOWED", "user_required": False},
            {"name": "계정 정보 조회", "gate": "LOCAL_AGENT_REQUIRED", "user_required": True},
            {"name": "로그인/OTP", "gate": "USER_DIRECT_REQUIRED", "user_required": True},
            {"name": "DNS 레코드 변경", "gate": "APPROVAL_REQUIRED", "user_required": True},
            {"name": "DNS 레코드 삭제", "gate": "APPROVAL_REQUIRED", "user_required": True},
            {"name": "도메인 연장/이전", "gate": "APPROVAL_REQUIRED", "user_required": True},
            {"name": "결제/청구", "gate": "BLOCKED", "user_required": True},
        ]
        return json.dumps(
            {
                "provider": "gabia",
                "base_url": "https://www.gabia.com",
                "dns_mgmt_url": "https://my.gabia.com/service/domain/haehan-ai.kr/dns",
                "login_note": "OTP/2FA 필수 — 사용자가 브라우저에서 직접 로그인",
                "operations": ops,
            },
            ensure_ascii=False,
        )

    if name == "start_login_watch":
        script = ROOT / "scripts" / "gabia_login_watch.py"
        if not script.exists():
            return json.dumps({"ok": False, "message": "gabia_login_watch.py 없음"})
        timeout = inputs.get("timeout", 300)
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script), "--timeout", str(timeout)],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return json.dumps(
                {
                    "ok": True,
                    "pid": proc.pid,
                    "message": f"로그인 감지 시작 (최대 {timeout}초). 브라우저에서 가비아 로그인을 진행하세요.",
                }
            )
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)})

    if name == "get_dns_tasks":
        try:
            from ai_orchestrator.gabia.gabia_dns_work_registry import list_gabia_external_works

            works = list_gabia_external_works()
            return json.dumps(
                [
                    {
                        "id": w.external_work_id,
                        "action": w.action_type,
                        "category": w.category,
                        "risk": w.risk_level,
                        "approval_required": w.approval_required,
                        "desc": w.description,
                    }
                    for w in works
                ],
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    if name == "get_nav_plan":
        try:
            from ai_orchestrator.gabia.gabia_browser_task import GABIA_NAV_PLAN

            return json.dumps(
                [
                    {"step": s["step"], "actor": s["actor"], "action": s["action"], "safe_to_auto": s["safe_to_auto"]}
                    for s in GABIA_NAV_PLAN
                ],
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    if name == "prepare_dns_record":
        subdomain = inputs.get("subdomain", "")
        record_type = inputs.get("record_type", "A")
        value = inputs.get("value", "")
        ttl = inputs.get("ttl", 3600)
        fqdn = f"{subdomain}.haehan-ai.kr"
        draft = {
            "fqdn": fqdn,
            "record_type": record_type,
            "value": value,
            "ttl": ttl,
            "safe_to_prepare": True,
            "safe_to_click_final_button": False,
            "requires_final_approval": True,
            "note": f"{fqdn} {record_type} 레코드 초안 생성됨. 가비아 DNS 관리 화면에서 사용자가 직접 저장해야 합니다.",
            "dns_mgmt_url": "https://my.gabia.com/service/domain/haehan-ai.kr/dns",
        }
        return json.dumps(draft, ensure_ascii=False)

    if name == "open_gabia_dns":
        domain = inputs.get("domain", "haehan-ai.kr")
        url = f"https://my.gabia.com/service/domain/{domain}/dns"
        try:
            from scripts.web_connector import get_page

            page = get_page()
            page.goto(url, timeout=15000)
            return json.dumps({"ok": True, "url": url, "message": "DNS 관리 화면으로 이동했습니다."})
        except Exception as e:
            return json.dumps(
                {"ok": False, "url": url, "message": f"CDP 이동 실패: {e}. 브라우저에서 직접 접속하세요: {url}"}
            )

    return json.dumps({"error": f"unknown tool: {name}"})


class ChatRequest(BaseModel):
    messages: list[dict]
    confirmed: bool | None = False


@router.post("/chat")
async def gabia_chat(body: ChatRequest):
    import os

    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "OPENAI_API_KEY 미설정"}, status_code=503)

    client = OpenAI(api_key=api_key)

    async def stream():
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m["role"], "content": m["content"]} for m in body.messages
        ]
        tools = _tool_defs()
        step = 0

        while True:
            resp = client.chat.completions.create(
                model=GPT_MODEL,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto",
                messages=messages,
            )
            msg = resp.choices[0].message

            if msg.content:
                yield f"event: text\ndata: {json.dumps({'text': msg.content}, ensure_ascii=False)}\n\n"

            if not msg.tool_calls:
                yield f"event: done\ndata: {json.dumps({'steps': step})}\n\n"
                break

            # 도구 실행
            tool_results = []
            for tc in msg.tool_calls:
                step += 1
                tool_name = tc.function.name
                tool_inputs = json.loads(tc.function.arguments or "{}")

                yield f"event: step\ndata: {json.dumps({'step': step, 'tool': tool_name, 'status': 'running'}, ensure_ascii=False)}\n\n"

                result_str = _run_tool(tool_name, tool_inputs)

                yield f"event: step\ndata: {json.dumps({'step': step, 'tool': tool_name, 'status': 'ok', 'detail': result_str[:200]}, ensure_ascii=False)}\n\n"

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    }
                )

            # ChatCompletionMessage 객체를 dict로 변환해야 다음 API 호출에 전달 가능
            messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in (msg.tool_calls or [])
                    ],
                }
            )
            messages.extend(tool_results)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
