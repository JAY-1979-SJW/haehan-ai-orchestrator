import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.common.app_paths import onedrive_root, resolve_external  # noqa: E402
from scripts.youtube.uploader import APPROVAL_PHRASE, execute_upload_plan, prepare_upload_plan  # noqa: E402

video_path = str(
    resolve_external("HAEHAN_VIDEO_DIR", "전등 이미지", "video", base=onedrive_root()) / "kakao_skill_bot_ep01" / "final.mp4"
)
values = {
    "title": "퇴근 후 카톡 문의, AI로 24시간 자동상담 직접 만들었습니다 (추가 AI비용 0원)",
    "description": (
        "카카오톡 채널에 24시간 자동상담을 붙이는 과정을, 실제로 겪었던 함정까지 그대로 보여드립니다.\n"
        "저장과 배포는 다르다는 것, 봇 응답을 스킬데이터로 바꿔야 한다는 것, 서버 주소는 매번 재확인해야 한다는 것.\n"
        "카카오톡 채널 챗봇은 무료이고, 기존 서버를 활용해 추가 AI API 비용 없이 만들었습니다.\n"
        "직접 만들기 어렵고 구축이 필요하시면 채널 링크로 문의 주세요.\n"
        "다음 편에서는 우리 회사 정보로 답하는 진짜 AI 상담사로 업그레이드합니다."
    ),
    "privacy": "private",
    "tags": "AI자동화,카카오톡챗봇,오픈빌더,자동상담,해한AI",
    "token_file": "ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json",
}

plan, plan_path = prepare_upload_plan(video_path, values)
print("PLAN OK", plan_path)
# 승인 문구는 사용자가 --confirm= 으로 직접 입력해야 한다(코드에 고정해 자동 승인하지 않는다). 없으면 드라이런만 한다.
confirm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--confirm=")), "")
live = confirm == APPROVAL_PHRASE
if not live:
    print("[DRY-RUN] 실제 업로드하려면 --confirm=<승인 문구(직접 입력)> 가 필요합니다")
result, result_path = execute_upload_plan(plan_path, approved=live, confirm=confirm, dry_run=not live)
print(json.dumps(result, ensure_ascii=False, indent=2))
