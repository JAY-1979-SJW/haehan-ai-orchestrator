/**
 * lib/instance_guard.js — 자기 서버만 재사용하고, 앱이 끝나면 자식 서버가 반드시 같이 끝나게 하는 순수 도우미
 *
 * 왜: 포트(8401·3000)에 이미 떠 있는 서버를 "건강하면 재사용"하면 다른 userData(다른 실행·다른 프로필)가
 * 남긴 서버의 DB·환경을 그대로 쓰게 된다(첫 실행인데 /setup 이 안 뜨는 증상, E2E 실측). 그래서 실행마다 무작위
 * 인스턴스 ID 를 만들어 백엔드에 환경변수(HAEHAN_INSTANCE_ID)로 넘기고, /api/v1/health 가 그 값을 돌려주는 서버만
 * "내 서버"로 인정한다. ID 는 비밀이 아니다(포트 소유 확인용 표지).
 * 업무 로직·electron 의존 없음 — node --test 로 단독 검증한다.
 */
const crypto = require("crypto");

function newInstanceId() {
  return crypto.randomBytes(16).toString("hex");
}

/**
 * 헬스 응답을 분류한다.
 * @returns {"own"|"foreign"|"down"} down=응답 없음/비정상, own=내 인스턴스 ID 와 일치, foreign=건강하지만 내 서버가 아님
 */
function classifyHealth(result, expectedId) {
  if (!result || !result.ok) return "down";
  let body = null;
  try {
    body = JSON.parse(result.body || "");
  } catch {
    return "foreign";
  }
  if (body && typeof body.instance_id === "string" && expectedId && body.instance_id === expectedId) return "own";
  return "foreign";
}

module.exports = { newInstanceId, classifyHealth };
