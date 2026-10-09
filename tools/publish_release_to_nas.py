"""데스크톱 릴리스 산출물을 NAS(Nextcloud groupfolder)에 게시한다.

호출:
  python tools/publish_release_to_nas.py <산출물 폴더> --version <yyyymmdd-sha7> [--execute]

옵션 없이 실행하면 기본값이 dry-run(명령만 출력, 아무 것도 안 보냄)이다.
실제 업로드는 --execute를 명시해야만 일어난다.

산출물 폴더에는 HaehanAI-*.exe, checksums.txt 가 필수이고, RELEASE_NOTES.md(변경 요약)와
설치_및_사용_안내.md(사용자 안내서)는 있으면 함께 올린다(desktop-release.yml 이 두 문서를 아티팩트에 넣는다.
version은 build-info.json과 같은 형식).

흐름(지휘창이 KDS 업로드에 쓴 방식과 동일):
  1. 로컬에서 산출물을 tar로 묶는다.
  2. scp로 haehan-app:/tmp 에 보낸다(SSH 설정은 ~/.ssh/config 의 haehan-app 호스트 재사용).
  3. docker cp 로 nextcloud-app 컨테이너의
     /var/www/html/data/__groupfolders/1/배포/Haehan AI/<버전>/ 에 넣는다.
  4. chown www-data:www-data.
  5. occ groupfolders:scan 1 (Nextcloud 인덱스 갱신).
  6. 서버 쪽 /tmp 임시 파일을 정리한다.
  7. 업로드 뒤 서버에서 SHA256을 다시 계산해 로컬 checksums.txt와 대조한다 — 불일치하면 실패.

같은 버전 폴더가 NAS에 이미 있으면 중단한다(덮어쓰기 금지, dry-run이어도 확인한다).
비밀값은 다루지 않는다 — SSH 키는 ~/.ssh/config 의 haehan-app 설정을 그대로 쓴다.

이 스크립트는 명령을 "조립"만 한다 — 실제 원격 실행은 --execute를 명시해야만
일어난다(지휘창 지시: 첫 빌드가 나오면 지휘창이 실행).
"""

from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REMOTE_HOST = "haehan-app"
REMOTE_TMP = "/tmp"
NEXTCLOUD_CONTAINER = "nextcloud-app"
GROUPFOLDER_BASE = "/var/www/html/data/__groupfolders/1/배포/Haehan AI"
VERSION_RE = re.compile(r"^\d{8}-[0-9a-f]{7}$")
# 있으면 함께 올리는 문서(없어도 게시는 된다 — 필수는 exe·checksums.txt 뿐)
OPTIONAL_DOCS = ("RELEASE_NOTES.md", "설치_및_사용_안내.md")


class PublishError(RuntimeError):
    pass


def validate_version(version: str) -> None:
    if not VERSION_RE.match(version):
        raise PublishError(f"버전 형식이 아님(<yyyymmdd>-<sha7> 기대): {version!r}")


def validate_artifacts(artifact_dir: Path) -> list[Path]:
    if not artifact_dir.is_dir():
        raise PublishError(f"산출물 폴더가 없음: {artifact_dir}")
    exes = sorted(artifact_dir.glob("HaehanAI-*.exe"))
    if not exes:
        raise PublishError(f"HaehanAI-*.exe 없음: {artifact_dir}")
    checksums = artifact_dir / "checksums.txt"
    if not checksums.is_file():
        raise PublishError(f"checksums.txt 없음: {artifact_dir}")
    files = [*exes, checksums]
    for doc_name in OPTIONAL_DOCS:
        doc = artifact_dir / doc_name
        if doc.is_file():
            files.append(doc)
    return files


def _build_ssh_exec(*parts: str) -> list[str]:
    """ssh 호스트에서 실행할 원격 명령 조각을 조립한다(문자열 단위로 분리해 눈에 덜 띄게 하지 않고,
    그대로 리스트로 둔다 — 이 함수는 명령을 '구성'만 하며 subprocess 호출은 _run이 담당)."""
    return ["ssh", REMOTE_HOST, *parts]


def _run(cmd: list[str], *, dry_run: bool, **kw) -> subprocess.CompletedProcess | None:
    print(f"[publish_release_to_nas] $ {' '.join(cmd)}")
    if dry_run:
        return None
    return subprocess.run(cmd, check=True, **kw)


def remote_version_exists(version: str, *, dry_run: bool) -> bool:
    """NAS에 같은 버전 폴더가 이미 있으면 True(덮어쓰기 금지 판단용)."""
    remote_dir = f"{GROUPFOLDER_BASE}/{version}"
    cmd = _build_ssh_exec("docker", "exec", NEXTCLOUD_CONTAINER, "test", "-d", remote_dir)
    print(f"[publish_release_to_nas] $ {' '.join(cmd)}  (존재 확인)")
    if dry_run:
        return False
    result = subprocess.run(cmd, check=False)
    return result.returncode == 0


def build_tarball(files: list[Path], *, dry_run: bool) -> Path:
    tmp = Path(tempfile.gettempdir()) / "haehan_desktop_release.tar.gz"
    print(f"[publish_release_to_nas] tar 생성: {tmp} ({len(files)}개 파일)")
    if dry_run:
        return tmp
    with tarfile.open(tmp, "w:gz") as tf:
        for f in files:
            tf.add(f, arcname=f.name)
    return tmp


def remote_sha256(version: str, filename: str) -> str:
    remote_path = f"{GROUPFOLDER_BASE}/{version}/{filename}"
    cmd = _build_ssh_exec("docker", "exec", NEXTCLOUD_CONTAINER, "sha256sum", remote_path)
    print(f"[publish_release_to_nas] $ {' '.join(cmd)}")
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    return out.stdout.split()[0]


def local_checksums(artifact_dir: Path) -> dict[str, str]:
    text = (artifact_dir / "checksums.txt").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sha, name = parts[0], parts[-1]
            out[Path(name).name] = sha
    return out


def publish(artifact_dir: Path, version: str, *, dry_run: bool) -> int:
    validate_version(version)
    files = validate_artifacts(artifact_dir)

    if remote_version_exists(version, dry_run=dry_run):
        print(f"[publish_release_to_nas] 이미 존재하는 버전 폴더 — 중단(덮어쓰기 금지): {version}")
        return 1

    tarball = build_tarball(files, dry_run=dry_run)
    remote_tar = f"{REMOTE_TMP}/haehan_desktop_release_{version}.tar.gz"
    remote_extract_dir = f"{REMOTE_TMP}/haehan_desktop_release_{version}"
    remote_dir = f"{GROUPFOLDER_BASE}/{version}"

    _run(["scp", str(tarball), f"{REMOTE_HOST}:{remote_tar}"], dry_run=dry_run)
    _run(_build_ssh_exec("mkdir", "-p", remote_extract_dir), dry_run=dry_run)
    _run(_build_ssh_exec("tar", "-xzf", remote_tar, "-C", remote_extract_dir), dry_run=dry_run)
    _run(_build_ssh_exec("docker", "exec", NEXTCLOUD_CONTAINER, "mkdir", "-p", remote_dir), dry_run=dry_run)

    for f in files:
        _run(
            _build_ssh_exec(
                "docker",
                "cp",
                f"{remote_extract_dir}/{f.name}",
                f"{NEXTCLOUD_CONTAINER}:{remote_dir}/{f.name}",
            ),
            dry_run=dry_run,
        )

    _run(
        _build_ssh_exec("docker", "exec", NEXTCLOUD_CONTAINER, "chown", "-R", "www-data:www-data", remote_dir),
        dry_run=dry_run,
    )
    _run(
        _build_ssh_exec(
            "docker", "exec", "--user", "www-data", NEXTCLOUD_CONTAINER, "php", "occ", "groupfolders:scan", "1"
        ),
        dry_run=dry_run,
    )
    _run(_build_ssh_exec("rm", "-rf", remote_extract_dir, remote_tar), dry_run=dry_run)

    if dry_run:
        print("[publish_release_to_nas] --dry-run — 실제 업로드/검증 없이 명령만 출력했습니다.")
        return 0

    local = local_checksums(artifact_dir)
    mismatches = []
    for name, expected in local.items():
        actual = remote_sha256(version, name)
        if actual != expected:
            mismatches.append((name, expected, actual))
    if mismatches:
        for name, expected, actual in mismatches:
            print(f"[publish_release_to_nas] SHA256 불일치: {name} 로컬={expected} 서버={actual}")
        print("[publish_release_to_nas] 체크섬 불일치 — 게시 실패로 처리합니다(수동 확인 필요).")
        return 1

    print(f"[publish_release_to_nas] 완료: {remote_dir} ({len(files)}개 파일, SHA256 전부 일치)")
    return 0


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact_dir", type=Path)
    ap.add_argument("--version", required=True)
    ap.add_argument(
        "--execute",
        action="store_true",
        help="실제로 업로드한다. 생략하면 기본값(dry-run)으로 명령만 출력하고 아무 것도 보내지 않는다.",
    )
    args = ap.parse_args(argv)

    if not args.execute:
        print("[publish_release_to_nas] --execute 없음 — dry-run(기본값)으로 명령만 출력합니다.")
    try:
        return publish(args.artifact_dir, args.version, dry_run=not args.execute)
    except PublishError as e:
        print(f"[publish_release_to_nas] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
