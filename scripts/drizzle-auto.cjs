// Spawns drizzle-kit generate, answering all interactive prompts by
// pressing Enter (which selects the default option — for us that's
// "create" rather than "rename" for every enum/table.) Used because
// drizzle-kit's TUI doesn't respect piped stdin.
const { spawn } = require("child_process");

const proc = spawn(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["drizzle-kit", "generate"],
  { stdio: ["pipe", "inherit", "inherit"], shell: true }
);

// Drizzle uses inquirer-style TUI; sending \r every 200ms accepts the
// highlighted default for each prompt.
const tick = setInterval(() => {
  try {
    proc.stdin.write("\r");
  } catch {
    clearInterval(tick);
  }
}, 200);

proc.on("exit", (code) => {
  clearInterval(tick);
  process.exit(code ?? 0);
});
