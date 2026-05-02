# 파일 지도 민감정보 표시 정책

**버전**: 1.0  
**작성일**: 2026-05-02  
**상태**: 활성화

---

## 목표

파일 지도(Local File Map) 리포트의 민감한 파일명을 기본적으로 마스킹하면서,
사용자가 본인 인증을 완료한 경우 원본 파일명을 볼 수 있는 정책을 수립합니다.

---

## 핵심 정책

### 1. 기본 마스킹 (Default)

모든 리포트와 외부 공유에서는 민감 파일명을 기본적으로 마스킹합니다.

**마스킹 대상 패턴**:
- 신분증류: 신분증, 주민등록증, 운전면허, 여권
- 금융정보: 통장사본, 계좌, 급여, 노임
- 법률문서: 형사사건, 고소, 변호인의견서, 소송
- 기타민감: 개인정보, 증거, 기밀, 계약서

**마스킹 예시**:
```
곽영규_신분증.jpg          → ****_[신분증].jpg
권명수_통장사본.pdf        → ****_[통장사본].pdf
01. 한컴오피스 2018.zip    → 01. 한**** 2018.zip
공갈죄_변호인의견서.docx   → ****_[법률문서].docx
```

### 2. 본인 인증 후 원본 표시 (Conditional)

사용자가 다음 조건을 모두 만족하면 원본 파일명을 볼 수 있습니다:

```
reveal_sensitive_names = True  AND  auth_verified = True
```

**조건 해석**:
- `reveal_sensitive_names=False` 또는 `auth_verified=False` → **마스킹 유지**
- `reveal_sensitive_names=True` AND `auth_verified=True` → **원본 표시**

**예시**:
| reveal_sensitive_names | auth_verified | 결과 |
|------------------------|---------------|------|
| False | False | 마스킹 ✓ (기본) |
| True | False | 마스킹 ✓ (부분 활성화) |
| False | True | 마스킹 ✓ (미인증) |
| True | True | 원본 표시 ✓ (완전 활성화) |

---

## 표시 범위

### 기본 마스킹 리포트 (공개용)
- 공유 링크
- 기본 markdown 리포트
- 외부 AI 분석용 데이터
- 서버 전송 데이터

### 원본 표시 가능 (인증 후)
- 로컬 UI
- 로컬 리포트 (사용자 기기에만 저장)
- 개인용 대시보드

### 절대 금지
- 비밀번호/PIN 값을 평문으로 저장
- 비밀번호/PIN 값을 로그에 기록
- 민감 파일명을 서버 로그에 저장
- 원본 파일명을 공개 문서에 저장

---

## 구현 상세

### 1. 렌더링 함수 (privacy.py)

```python
def render_filename(
    filename: str,
    reveal_sensitive_names: bool = False,
    auth_verified: bool = False
) -> str:
    """
    파일명을 표시 정책에 따라 렌더링

    Args:
        filename: 원본 파일명
        reveal_sensitive_names: 민감정보 표시 활성화 (기본값: False)
        auth_verified: 본인 인증 완료 여부 (기본값: False)

    Returns:
        렌더링된 파일명

    정책:
        - reveal_sensitive_names=False OR auth_verified=False → 마스킹
        - reveal_sensitive_names=True AND auth_verified=True → 원본
    """
    if reveal_sensitive_names and auth_verified:
        return filename  # 원본 표시
    return mask_filename(filename)  # 마스킹
```

### 2. 마크다운 렌더러 (markdown_renderer.py)

```python
class MarkdownRenderer:
    def __init__(
        self,
        reveal_sensitive_names: bool = False,
        auth_verified: bool = False
    ):
        self.reveal_sensitive_names = reveal_sensitive_names
        self.auth_verified = auth_verified
        # ... 내용 ...

    def render(self, report):
        # 모든 파일명 렌더링 시 정책 적용
        filename = self.masker.render_filename(
            file_info.get("name"),
            self.reveal_sensitive_names,
            self.auth_verified
        )
```

### 3. 기본값

- `reveal_sensitive_names`: **False** (기본 마스킹)
- `auth_verified`: **False** (미인증)

```python
# 기본 리포트 (공개용)
renderer = MarkdownRenderer()  # 모두 False → 마스킹

# 인증 후 로컬 UI
renderer = MarkdownRenderer(
    reveal_sensitive_names=True,
    auth_verified=True
)  # 원본 표시
```

---

## 감사 및 로깅

### 기록하는 항목
- ✓ 원본보기 시도 시각 및 사용자 ID
- ✓ 인증 성공/실패 여부
- ✓ 세션 ID

### 기록하지 않는 항목
- ✗ 원본 파일명
- ✗ 비밀번호/PIN
- ✗ 개인식별정보

**로그 예시**:
```
[2026-05-02 10:15:23] user=skyjwshin@gmail.com auth=success reveal_attempt=true
[2026-05-02 10:15:24] event=sensitive_reveal session=abc123 status=granted
```

---

## 향후 단계

### Phase 2: UI 구현
- 로컬 UI에 "원본보기" 버튼 추가
- 본인 인증 다이얼로그 구현 (비밀번호/생체인증)
- 일시적 원본보기 세션 (15분 제한)
- 자동 재마스킹

### Phase 3: 고급 정책
- 원본보기 감사 리포트
- 기간별 자동 마스킹 재적용
- 다중 기기 인증 토큰
- 관리자 감시 로그

---

## 보안 고려사항

### 1. 비밀번호/PIN 보호
```python
# ✗ 절대 금지
password = "mypassword123"
if password == user_input:
    auth_verified = True

# ✓ 올바른 방식 (해싱/소금)
import hashlib
hashed = hashlib.pbkdf2_hmac('sha256', user_input.encode(), salt, 100000)
if hashed == stored_hash:
    auth_verified = True
```

### 2. 세션 관리
- 원본보기 세션은 시간 제한 설정
- 브라우저 종료 시 자동 만료
- IP/기기 변경 시 재인증

### 3. 외부 전송 기본값
```python
# 서버/AI 전송용 (항상 마스킹)
response_data = {
    "files": files,
    "reveal_sensitive_names": False,  # 강제
    "auth_verified": False            # 강제
}
```

---

## 테스트 항목

- [ ] reveal_sensitive_names=False → 마스킹
- [ ] auth_verified=False → 마스킹
- [ ] 둘 다 False → 마스킹
- [ ] reveal_sensitive_names=True & auth_verified=False → 마스킹
- [ ] reveal_sensitive_names=False & auth_verified=True → 마스킹
- [ ] 둘 다 True → 원본 표시
- [ ] 코드에 비밀번호/PIN 평문 저장 없음
- [ ] 로그에 민감정보 기록 없음

---

## 참고 자료

- 파일 마스킹: `agent/local_inventory/file_map/privacy.py`
- 렌더링: `agent/local_inventory/file_map/markdown_renderer.py`
- 테스트: `agent/tests/test_local_file_map_report_privacy.py`

---

**정책 담당자**: AI Orchestrator Team  
**최종 수정**: 2026-05-02
