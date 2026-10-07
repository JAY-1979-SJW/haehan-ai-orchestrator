// tests/test_electron_runtime_guards.py 가 `node electron_guard_harness.js <case> <userDataDir> <repoRoot>` 로 호출하는 시험 도우미.
// electron 모듈은 가짜(app.getPath → userData 임시 폴더)로 대체하고, 결과를 JSON 한 줄로 출력한다.
const Module = require("module");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

const [, , testCase, userData, repo] = process.argv;
const origLoad = Module._load;
Module._load = function (request, ...rest) {
  if (request === "electron") {
    return { app: { getPath: () => userData, setName() {}, isPackaged: false } };
  }
  return origLoad.call(this, request, ...rest);
};
const lib = (n) => require(path.join(repo, "admin-web", "electron", "lib", n));
const out = (o) => console.log(JSON.stringify(o));
const cfgFile = () => path.join(userData, "config.json");

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

async function main() {
  if (testCase === "config-missing") {
    const c = lib("config.js");
    const s1 = c.getOrCreateJwtSecret();
    const s2 = c.getOrCreateJwtSecret();
    out({ same: s1 === s2, len: s1.length, saved: JSON.parse(fs.readFileSync(cfgFile(), "utf-8")).jwt_secret === s1, tmp: fs.existsSync(cfgFile() + ".tmp") });
  } else if (testCase === "config-keeps-other-settings") {
    fs.writeFileSync(cfgFile(), JSON.stringify({ license_key: "LIC-1", owner_mode: true, enabled_sites: ["a"] }));
    const c = lib("config.js");
    const s = c.getOrCreateJwtSecret();
    const cfg = JSON.parse(fs.readFileSync(cfgFile(), "utf-8"));
    out({ jwt: cfg.jwt_secret === s, license: cfg.license_key, owner: cfg.owner_mode, sites: cfg.enabled_sites });
  } else if (testCase === "config-corrupt") {
    const secret = "ab".repeat(32);
    fs.writeFileSync(cfgFile(), `{"jwt_secret": "${secret}", "auth_token": "tok-1", "license_key": "LIC-9", "owner_mode": true, "broken": [1, 2,`);
    const c = lib("config.js");
    const got = c.getOrCreateJwtSecret();
    const after = JSON.parse(fs.readFileSync(cfgFile(), "utf-8"));
    const preserved = fs.readdirSync(userData).filter((f) => f.startsWith("config.json.corrupt-"));
    out({ keptSecret: got === secret, salvaged: [after.auth_token, after.license_key, after.owner_mode], preserved: preserved.length, preservedHasOriginal: preserved.length === 1 && fs.readFileSync(path.join(userData, preserved[0]), "utf-8").includes("broken"), warnings: c.consumeConfigWarnings().length });
  } else if (testCase === "config-corrupt-no-secret") {
    fs.writeFileSync(cfgFile(), "this is not json");
    const c = lib("config.js");
    const s = c.getOrCreateJwtSecret();
    out({ newSecret: s.length === 64, saved: JSON.parse(fs.readFileSync(cfgFile(), "utf-8")).jwt_secret === s, preserved: fs.readdirSync(userData).filter((f) => f.includes(".corrupt-")).length, warnings: c.consumeConfigWarnings().length });
  } else if (testCase === "config-unreadable") {
    const original = JSON.stringify({ license_key: "LIC-KEEP", jwt_secret: "cd".repeat(32) });
    fs.writeFileSync(cfgFile(), original);
    const realRead = fs.readFileSync;
    fs.readFileSync = function (p, ...a) {
      if (String(p) === cfgFile()) {
        const e = new Error("EBUSY: resource busy or locked");
        e.code = "EBUSY";
        throw e;
      }
      return realRead.call(this, p, ...a);
    };
    const c = lib("config.js");
    let threw = false;
    try {
      c.saveConfig({ x: 1 });
    } catch {
      threw = true;
    }
    let threwPatch = false;
    try {
      c.patchConfig({ y: 1 });
    } catch {
      threwPatch = true;
    }
    const secret = c.getOrCreateJwtSecret();
    const again = c.getOrCreateJwtSecret();
    fs.readFileSync = realRead;
    out({ threw, threwPatch, unchanged: realRead.call(fs, cfgFile(), "utf-8") === original, ephemeralStable: secret === again, ephemeralNotSaved: secret !== "cd".repeat(32), warnings: c.consumeConfigWarnings().length > 0 });
  } else if (testCase === "pid-kills-own-leftover") {
    const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { stdio: "ignore" });
    const g = lib("pid_guard.js");
    g.writePid("fastapi", child.pid, path.basename(process.execPath));
    const r = g.killPreviousFromPidFile("fastapi");
    sleep(300);
    let alive = true;
    try {
      process.kill(child.pid, 0);
    } catch {
      alive = false;
    }
    out({ killed: r.killed, alive, pidFileGone: !fs.existsSync(g.pidFilePath("fastapi")) });
    try { child.kill(); } catch {}
  } else if (testCase === "pid-image-mismatch-not-killed") {
    const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { stdio: "ignore" });
    const g = lib("pid_guard.js");
    g.writePid("fastapi", child.pid, "some-other-program.exe"); // 기록된 이름과 실제 프로세스 이름이 다름 = 남의 프로세스
    const r = g.killPreviousFromPidFile("fastapi");
    let alive = true;
    try {
      process.kill(child.pid, 0);
    } catch {
      alive = false;
    }
    out({ killed: r.killed, reason: r.reason, alive, pidFileGone: !fs.existsSync(g.pidFilePath("fastapi")) });
    try { child.kill(); } catch {}
  } else if (testCase === "pid-cmdline-mismatch-not-killed") {
    const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { stdio: "ignore" });
    const g = lib("pid_guard.js");
    g.writePid("nextjs", child.pid, path.basename(process.execPath), "C:\\nowhere\\nextjs\\wrapper.js"); // 같은 실행 파일이지만 다른 명령줄
    const r = g.killPreviousFromPidFile("nextjs");
    let alive = true;
    try {
      process.kill(child.pid, 0);
    } catch {
      alive = false;
    }
    out({ killed: r.killed, alive });
    try { child.kill(); } catch {}
  } else if (testCase === "pid-never-kills-self-or-dead") {
    const g = lib("pid_guard.js");
    g.writePid("fastapi", process.pid, path.basename(process.execPath));
    const self = g.killPreviousFromPidFile("fastapi");
    g.writePid("fastapi", 2147483, path.basename(process.execPath)); // 존재하지 않을 PID
    const dead = g.killPreviousFromPidFile("fastapi");
    const none = g.killPreviousFromPidFile("fastapi"); // PID 파일 없음
    out({ self: self.reason, dead: dead.reason, none: none.reason, stillRunning: true });
  } else if (testCase === "build-info") {
    const dir = path.join(userData, "res");
    fs.mkdirSync(dir, { recursive: true });
    process.resourcesPath = dir;
    const f = lib("fastapi_server.js");
    const none = f.readBuildInfo();
    fs.writeFileSync(path.join(dir, "build-info.json"), JSON.stringify({ git_sha: "a".repeat(40), build_time: "2026-10-07T12:34:56Z", version: "20261007-aaaaaaa" }));
    const ok = f.readBuildInfo();
    fs.writeFileSync(path.join(dir, "build-info.json"), JSON.stringify({ git_sha: "<script>", build_time: "x".repeat(41), version: 5 }));
    const bad = f.readBuildInfo();
    fs.writeFileSync(path.join(dir, "build-info.json"), "{not json");
    const broken = f.readBuildInfo();
    out({ none, ok, bad, broken });
  } else if (testCase.startsWith("desktop-session-")) {
    const http = require("http");
    const mode = testCase.slice("desktop-session-".length); // 200 | needs-setup | 404 | no-owner | down
    const c = lib("config.js");
    c.setAuthToken("OLD-TOKEN");
    const seen = {};
    const server = http.createServer((req, res) => {
      seen.method = req.method;
      seen.path = req.url;
      seen.header = req.headers["x-haehan-desktop"];
      const send = (code, obj) => {
        res.writeHead(code, { "Content-Type": "application/json" });
        res.end(JSON.stringify(obj));
      };
      if (mode === "200") send(200, { token: "NEW-TOKEN", user: { id: "u1" } });
      else if (mode === "needs-setup") send(409, { detail: "needs_setup" });
      else if (mode === "no-owner") send(409, { detail: "no_active_owner" });
      else send(404, { detail: "Not Found" });
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    let port = server.address().port;
    if (mode === "down") {
      await new Promise((r) => server.close(r));
    }
    const ds = lib("desktop_session.js");
    const result = await ds.refreshDesktopSession(port);
    if (mode !== "down") await new Promise((r) => server.close(r));
    out({ result, token: c.getAuthToken(), seen });
  } else {
    throw new Error("unknown case " + testCase);
  }
}

main().then(() => process.exit(0), (e) => {
  console.error(e);
  process.exit(1);
});
