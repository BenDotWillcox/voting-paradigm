import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const isWindows = process.platform === "win32";
const webPort = port("PERSONAL_JOURNAL_WEB_PORT", 3035);
const apiPort = port("PERSONAL_JOURNAL_API_PORT", 8035);
if (apiPort === webPort) throw new Error("The journal web and API ports must differ.");

function port(name, fallback) {
  const raw = process.env[name] ?? String(fallback);
  const value = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error(`Invalid port in ${name}`);
  }
  return value;
}

const localPython = join(root, "venv", ...(isWindows ? ["Scripts", "python.exe"] : ["bin", "python"]));
const python = process.env.PERSONAL_JOURNAL_PYTHON ||
  (existsSync(localPython) ? localPython : isWindows ? "python" : "python3");
const env = {
  ...process.env,
  NODE_ENV: "development",
  PERSONAL_JOURNAL_LOCAL: "1",
  PERSONAL_JOURNAL_API_ORIGIN: `http://127.0.0.1:${apiPort}`,
  PERSONAL_JOURNAL_API_TOKEN: randomBytes(32).toString("hex"),
};

const children = [];
let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) {
    if (child.exitCode === null) child.kill();
  }
}
function start(command, args) {
  const child = spawn(command, args, { cwd: root, env, stdio: "inherit", windowsHide: true });
  children.push(child);
  child.on("error", error => {
    console.error(error.message);
    stop(1);
  });
  child.on("exit", (code, signal) => stop(code ?? (signal ? 1 : 0)));
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
console.log(`Personal ballot journal: http://127.0.0.1:${webPort}/preferences/journal`);
start(python, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(apiPort)]);
start(process.execPath, [join(root, "node_modules", "next", "dist", "bin", "next"), "dev",
  "--hostname", "127.0.0.1", "--port", String(webPort)]);
