#!/usr/bin/env node
/**
 * statusLine 用サンプルスクリプト（動作検証用、任意機能）。
 *
 * stdin に Claude Code の statusLine JSON を受け取り、stdout に表示文字列を出す。
 * 依存は Node 標準モジュールのみ。Windows/macOS で共通に動く。
 * スキーマ: https://code.claude.com/docs/en/statusline
 * 入力欠落・破損があっても例外で落ちず、出せる範囲で出して必ず exit 0 する。
 */

"use strict";

const { execFileSync } = require("child_process");
const path = require("path");

const GIT_TIMEOUT_MS = 500;

/** N トークンを "138k" や "1M" のような表記に変換する。 */
function formatTokens(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  if (n >= 1000000) return `${Math.floor(n / 1000000)}M`;
  return `${Math.floor(n / 1000)}k`;
}

/** model.display_name に effort.level を反映した表示名を作る。 */
function formatModelName(model, effort) {
  let name = (model && model.display_name) || "";
  const level = effort && effort.level;
  if (!level) return name;
  if (name.includes("1M context")) {
    return name.replace("1M context", `1M - ${level}`);
  }
  return name ? `${name} (${level})` : "";
}

/** 1 行目: model | dir | ctx% (used/window) · session tokens · edit (+a, -r) */
function buildLine1(data) {
  const model = formatModelName(data.model, data.effort);
  const dir = (data.workspace && data.workspace.current_dir) || data.cwd || "";
  const dirName = dir ? path.basename(dir) : "";

  const parts = [model, dirName].filter((s) => s);
  const head = parts.join(" | ");

  const ctx = data.context_window || {};
  const segments = [];

  if (typeof ctx.used_percentage === "number") {
    const pct = Math.round(ctx.used_percentage);
    const cur = ctx.current_usage || {};
    const used =
      (cur.input_tokens || 0) +
      (cur.cache_creation_input_tokens || 0) +
      (cur.cache_read_input_tokens || 0);
    const windowSize = ctx.context_window_size;
    const usedFmt = formatTokens(used);
    const windowFmt = formatTokens(windowSize);
    const tokensStr = usedFmt && windowFmt ? ` (${usedFmt}/${windowFmt})` : "";
    segments.push(`ctx ${pct}%${tokensStr}`);
  }

  if (typeof ctx.total_input_tokens === "number" && typeof ctx.total_output_tokens === "number") {
    const sessionTotal = formatTokens(ctx.total_input_tokens + ctx.total_output_tokens);
    if (sessionTotal) segments.push(`session ${sessionTotal}`);
  }

  const cost = data.cost || {};
  const added = cost.total_lines_added || 0;
  const removed = cost.total_lines_removed || 0;
  if (added > 0 || removed > 0) {
    segments.push(`edit (+${added}, -${removed})`);
  }

  const tail = segments.join(" · ");
  if (head && tail) return `${head} | ${tail}`;
  return head || tail;
}

/** dir が git 管理下なら { branch, worktree, changes } を返す。管理下でなければ null。 */
function readGitInfo(dir, worktree) {
  if (!dir) return null;
  const gitOpts = { cwd: dir, timeout: GIT_TIMEOUT_MS, stdio: ["ignore", "pipe", "ignore"] };
  let branch;
  try {
    execFileSync("git", ["rev-parse", "--git-dir"], gitOpts);
    branch = execFileSync("git", ["branch", "--show-current"], gitOpts).toString().trim();
    if (!branch) {
      branch = execFileSync("git", ["rev-parse", "--short", "HEAD"], gitOpts).toString().trim();
    }
  } catch {
    return null;
  }
  if (!branch) return null;

  let changes = "";
  try {
    const shortstat = execFileSync("git", ["diff", "--shortstat", "HEAD"], gitOpts).toString();
    const insertions = /(\d+) insertion/.exec(shortstat);
    const deletions = /(\d+) deletion/.exec(shortstat);
    const added = insertions ? Number(insertions[1]) : 0;
    const removed = deletions ? Number(deletions[1]) : 0;
    if (added > 0 || removed > 0) changes = `(+${added}, -${removed})`;
  } catch {
    // HEAD が無い（初回コミット前）等。差分なしとして扱う。
  }

  return { branch, worktree: worktree && worktree.name, changes };
}

/** 2 行目: branch [worktree] (+a, -r)。git 管理下でなければ null。 */
function buildLine2(data) {
  const dir = (data.workspace && data.workspace.current_dir) || data.cwd || "";
  const info = readGitInfo(dir, data.worktree);
  if (!info) return null;

  let line = info.branch;
  if (info.worktree) line += ` [${info.worktree}]`;
  if (info.changes) line += ` ${info.changes}`;
  return line;
}

function main(raw) {
  let data = {};
  try {
    data = JSON.parse(raw) || {};
  } catch {
    data = {};
  }
  if (typeof data !== "object" || data === null) data = {};

  const lines = [];
  try {
    lines.push(buildLine1(data));
  } catch {
    lines.push("");
  }
  try {
    const line2 = buildLine2(data);
    if (line2) lines.push(line2);
  } catch {
    // 2 行目は出せなければ省略する。
  }

  process.stdout.write(lines.join("\n") + "\n");
}

let input = "";
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  try {
    main(input);
  } catch {
    // どんな例外でも exit 0 で終える。
  }
  process.exit(0);
});
process.stdin.on("error", () => {
  process.exit(0);
});
