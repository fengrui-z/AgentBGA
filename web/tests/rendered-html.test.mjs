import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("static export contains the AgentBGA match setup", async () => {
  const html = await readFile(new URL("dist/client/index.html", root), "utf8");

  assert.match(html, /<html lang="zh-CN">/);
  assert.match(html, /<title>AgentBGA · Long-Horizon Game Arena<\/title>/);
  assert.match(html, /创建一桌.*璀璨宝石/);
  assert.match(html, /方舟动物园/);
  assert.match(html, /伯明翰/);
  assert.match(html, /香料之路/);
  assert.match(html, /CONTROLLED CORE/);
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
  assert.match(html, /Hermes Agent/);
  assert.match(html, /value="deepseek-v4-flash"/);
  assert.match(html, /value="https:\/\/api\.deepseek\.com"/);
  assert.match(html, /独立设置思考强度/);
  assert.match(html, /Reasoning Effort/);
  assert.match(html, /人类 vs Agent/);
  assert.match(html, /添加人类/);
  assert.match(html, /type="password"/);
  const source = await readFile(new URL("app/page.tsx", root), "utf8");
  assert.match(source, /deepseekHarnessPlayer\(1, "opencode"\)/);
  assert.match(source, /codexHarnessPlayer\(2\)/);
  assert.match(source, /MODEL STREAM|模型 Chat/);
  assert.match(source, /暂停|继续对局/);
  assert.match(source, /human_turn|submitHumanAction/);
  assert.match(source, /随机座次|movePlayer/);
  assert.match(source, /ArkNovaBoard/);
  assert.match(source, /BrassBoard/);
  assert.match(source, /CenturyBoard/);
  assert.match(source, /century_spice_road/);
  assert.match(source, /game_description\.runnable/);
  assert.match(source, /GEM_ORDER = \["red", "green", "white", "blue", "black", "gold"\]/);
  assert.match(source, /DevCard key=\{card\.id\} card=\{card\} reserved/);
  assert.match(source, /players\.find\(player => player\.backend === "human"\)/);
  assert.match(source, /function HumanActionChoice/);
  assert.match(source, /card-action-grid/);
  assert.match(source, /token-action-choice/);
  assert.match(source, /token-choice-gems/);
  assert.match(source, /Array\.isArray\(action\.card_ids\)/);
  assert.match(source, /kept_count \?\? 0/);
  assert.doesNotMatch(source, /\(action\.card_ids as string\[\]\)\.join/);
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

test("results arena and trusted ingest worker are included", async () => {
  const html = await readFile(new URL("dist/client/arena.html", root), "utf8");
  assert.match(html, /GLOBAL RATINGS/);
  assert.match(html, /综合排名/);
  assert.match(html, /提交 results JSON/);
  assert.match(html, /归一化多人 Elo/);

  const worker = await readFile(new URL("worker/results.ts", root), "utf8");
  assert.match(worker, /RESULT_SUBMISSION_TOKENS/);
  assert.match(worker, /delete stored\.submission/);
  assert.match(worker, /content digest does not match artifact/);
  assert.match(worker, /result_id collision with different content/);
  assert.match(worker, /K_FACTOR = 32/);
});
