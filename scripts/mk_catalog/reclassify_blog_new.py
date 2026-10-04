import json
from collections import Counter
from pathlib import Path

catalog = json.load(Path("data/mk_catalog/products_web.json").open(encoding="utf-8"))


def _classify_a(name, t):
    if "힘펠" in name or "환풍기" in t:
        return "환풍기"
    if any(
        k in t
        for k in ["감지기", "소화기", "유도등", "비디오폰", "도어폰", "타이머", "차단기", "노출BOX", "카메라 비막이"]
    ):
        return "안전·방재"
    if "리모콘" in name and "스위치" in name:
        return "안전·방재"
    if name.startswith("스피커"):
        return "안전·방재"
    return None


def _classify_b(name, t):
    if any(
        k in t
        for k in [
            "콘센트",
            "스위치",
            "모듈",
            "멀티탭",
            "멀티 콘센트",
            "멀티 하이탭",
            "플러그",
            "바나나잭",
            "스피커잭",
            "보조대",
            "CATV",
            "MATV",
            "조광기",
            "텀블러 스위치",
            "배선기구",
        ]
    ):
        return "배선기구"
    if any(k in t for k in ["CD 파이프", "로맥스", "HIV ", "전선"]):
        return "전선·자재"
    return None


def _classify_c(name, t):
    if any(
        k in name
        for k in [
            "이지라인",
            "SMPS",
            "네온플렉스",
            "레이지바",
            "마그네틱",
            "SMD칩",
            "COB칩",
            "실링팬",
            "안정기",
            "드라이버",
            "리모컨",
            "리모콘 스위치",
            "컨트롤러",
            "무선 스위치",
            "라인바",
            "라인 시스템",
            "실리콘 바",
            "LED 바",
            "T5",
            "T3 시리즈",
            "T-LINE",
        ]
    ):
        return "LED스트립·자재"
    if any(
        k in name
        for k in [
            "거실등",
            "거실6등",
            "거실5등",
            "거실4등",
            "거실3등",
            "거실2등",
            "거실1등",
            "방등",
            "주방등",
            "주방1등",
            "주방2등",
            "평판등",
            "면조명",
        ]
    ):
        return "거실·방등"
    if "레일" in t:
        return "레일조명"
    if "벽시계" in name:
        return "벽시계"
    return None


def _classify_d(name, t):
    if any(
        k in t
        for k in [
            "지중등",
            "잔디등",
            "문주등",
            "정원등",
            "외벽등",
            "외등",
            "수목",
            "투사등",
            "보안등",
            "방습등",
            "팩등",
        ]
    ):
        return "야외등"
    if "거울등" in t:
        return "거울등"
    if "다운라이트" in t or "매입" in name:
        return "다운라이트·매입등"
    if "B/R" in name or "B_R" in name or "벽등" in name:
        return "벽등(B/R)"
    if "S/T" in name:
        return "스탠드(S/T)"
    if "펜던트" in name or "P/D" in name:
        return "펜던트(P/D)"
    if "센서" in t:
        return "센서등"
    if "직부" in t:
        return "직부등"
    return None


def _classify_e(name, t):
    if any(
        k in name
        for k in [
            "에디슨",
            "스파이럴",
            "벌브",
            "인치구",
            "볼구",
            "촛대구",
            "콘벌브",
            "크립톤",
            "파20",
            "파30",
            "옥수수",
            "GX53",
            "MR",
            "GU10",
        ]
    ):
        return "램프·전구"
    if any(k in name for k in ["에지", "LED바", "라인시스템"]):
        return "LED스트립·자재"
    return None


def classify(name, features):
    t = (name or "") + " " + (features or "")
    return (
        _classify_a(name, t)
        or _classify_b(name, t)
        or _classify_c(name, t)
        or _classify_d(name, t)
        or _classify_e(name, t)
        or "기타"
    )


changed = 0
for c in catalog:
    if c["src"] == "blog-new":
        new_cat = classify(c["name"], c.get("features", ""))
        if new_cat != c["cat"]:
            changed += 1
        c["cat"] = new_cat

print("reclassified:", changed)


newitems = [c for c in catalog if c["src"] == "blog-new"]
print(Counter(c["cat"] for c in newitems).most_common())

json.dump(catalog, Path("data/mk_catalog/products_web.json").open("w", encoding="utf-8"), ensure_ascii=False)
