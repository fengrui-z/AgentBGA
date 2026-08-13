import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("static export contains the AgentBGA match setup", async () => {
  const html = await readFile(new URL("dist/client/index.html", root), "utf8");

  assert.match(html, /<html lang="zh-CN">/);
  assert.match(html, /<title>AgentBGA · Splendor Live Table<\/title>/);
  assert.match(html, /创建一桌璀璨宝石/);
  assert.match(html, /OpenAI 兼容/);
  assert.match(html, /Anthropic/);
  assert.match(html, /Gemini/);
  assert.match(html, /DeepSeek 官方/);
  assert.match(html, /阿里云百炼/);
  assert.match(html, /智谱开放平台/);
  assert.match(html, /MiniMax 官方/);
  assert.match(html, /Claude Code/);
  assert.match(html, />Pi</);
  assert.match(html, />Codex</);
  assert.match(html, />OpenCode</);
  assert.match(html, /value="deepseek-v4-flash"/);
  assert.match(html, /value="https:\/\/api\.deepseek\.com"/);
  assert.match(html, /固定使用最高思考强度/);
  assert.match(html, /人类 vs Agent/);
  assert.match(html, /添加人类/);
  assert.match(html, /type="password"/);
  const source = await readFile(new URL("app/page.tsx", root), "utf8");
  assert.match(source, /deepseekHarnessPlayer\(1, "opencode"\)/);
  assert.match(source, /deepseekHarnessPlayer\(2, "codex"\)/);
  assert.match(source, /MODEL STREAM|模型 Chat/);
  assert.match(source, /暂停|继续对局/);
  assert.match(source, /human_turn|submitHumanAction/);
  assert.match(source, /随机座次|movePlayer/);
  assert.doesNotMatch(html, /react-loading-skeleton|Your site is taking shape/);
});

test("static export has all assets needed by the Python server", async () => {
  const html = await readFile(new URL("dist/client/index.html", root), "utf8");
  const refs = [...html.matchAll(/(?:src|href)="(\/_next\/static\/[^"]+)"/g)]
    .map(([, path]) => new URL(`dist/client${path}`, root));

  assert.ok(refs.length >= 2);
  await Promise.all(refs.map(path => access(path)));
  await access(new URL("dist/client/index.rsc", root));
});
