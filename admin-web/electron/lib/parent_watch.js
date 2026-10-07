/**
 * lib/parent_watch.js — Next 자식 프로세스용 부모 감시 (fork 시 --require 로 선행 로드)
 *
 * Electron 본체가 강제 종료·크래시하면 자식 Next 서버가 고아로 남아 포트 3000 과 파일 핸들을 쥔다.
 * 부모 PID(HAEHAN_PARENT_PID)가 사라지면 스스로 종료한다. 실패해도 서버 시작을 막지 않는다.
 */
try {
  const ppid = Number(process.env.HAEHAN_PARENT_PID);
  if (Number.isInteger(ppid) && ppid > 0) {
    const t = setInterval(() => {
      try {
        process.kill(ppid, 0);
      } catch (e) {
        if (e && e.code === "ESRCH") process.exit(0);
      }
    }, 2000);
    t.unref();
  }
} catch {}
