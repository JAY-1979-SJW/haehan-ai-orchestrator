# shadowed_modules — 같은 이름의 패키지에 가려져 실행된 적이 없던 모듈 (2026-09-30 이동)

같은 부모 디렉터리에 `x.py` 와 `x/__init__.py` 가 함께 있으면 파이썬은 **패키지 `x/` 를 먼저** 가져온다. 아래 세 파일은 그렇게 가려져
한 번도 임포트되지 않았다. 삭제하지 않고(코드 보존 규칙) 이력을 보존해 여기로 옮겼다. **이 폴더의 파일은 임포트 대상이 아니다.**

| 옮긴 파일 | 원래 위치 | 성격 |
|---|---|---|
| `naver_cafe_legacy_module.py` | `scripts/naver/cafe.py` | 옛 `NaverCafe`(글쓰기 `send=False` 시그니처). 라우터가 이 시그니처로 호출하다 `TypeError` 가 났던 원인 (2026-09-30) |
| `naver_blog_seo_stub.py` | `scripts/naver/blog/seo.py` | `seo/` 패키지로 옮긴 뒤 남은 재수출 stub |
| `naver_smartstore_product_stub.py` | `scripts/naver/smartstore/product.py` | `product/` 패키지로 옮긴 뒤 남은 재수출 stub |

복원이 필요하면 `git log --follow` 로 이력을 확인한 뒤 **패키지 이름과 겹치지 않는 이름으로** 옮긴다.
