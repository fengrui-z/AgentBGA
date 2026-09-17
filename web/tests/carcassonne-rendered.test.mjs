import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const compiled = ts.transpileModule(readFileSync(new URL("../app/carcassonne-table.tsx", import.meta.url), "utf8"), {
  compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const output = {exports: {}};
vm.runInNewContext("(function(require, module, exports) {" + compiled + "\n})")(
  createRequire(import.meta.url), output, output.exports,
);
const {CarcassonneTable, CarcassonnePlayerPanel, CarcassonneTile} = output.exports;
// Obtain real current-engine projections instead of hand-maintaining a second schema.
const repo = fileURLToPath(new URL("../../", import.meta.url));
const fixtures = JSON.parse(execFileSync("python3", ["-c", `
import json, random
from agentbga import carcassonne as c
s = c.new_game(2, 42)
result = {"placement": {"view": c.observe(s, 0), "actions": c.legal_actions(s, 0)}}
a = c.legal_actions(s, 0)[0]["action"]
s, _ = c.apply_action(s, 0, a)
result["follower"] = {"view": c.observe(s, 0), "actions": c.legal_actions(s, 0)}
rng = random.Random(42)
while s["status"] == "active":
    s, _ = c.apply_action(s, s["active_seat"], rng.choice(c.legal_actions(s, s["active_seat"]))["action"])
result["finished"] = {"view": c.observe(s, 0), "actions": []}
result["tiles"] = [c._tile_view({"tile_id": code + "-1", "rotation": r}) for code in c.CATALOG for r in range(4)]
print(json.dumps(result))
`], {cwd: repo, env: {...process.env, PYTHONPATH: `${repo}/src`}, encoding: "utf8"}));
const identities = [{seat: 0, name: "Red"}, {seat: 1, name: "Blue"}];
const render = (fixture, extra = {}) => renderToStaticMarkup(React.createElement(CarcassonneTable, {
  ...fixture, lang: "zh", identities, onChoose() {}, ...extra,
}));

test("tile placement renders only legal spaces in the selected rotation", () => {
  const html = render(fixtures.placement);
  const rotation = fixtures.placement.actions[0].action.rotation;
  assert.match(html, /旋转地形，选择拼接位置/);
  assert.match(html, /可滚动地形棋盘/);
  assert.match(html, /aria-label="放大棋盘"/);
  assert.equal((html.match(/aria-label="放置地形/g) || []).length,
    fixtures.placement.actions.filter(a => a.action.rotation === rotation).length);
  assert.ok(fixtures.placement.actions.filter(a => a.action.rotation === rotation).length > 0);
  for (const a of fixtures.placement.actions.filter(a => a.action.rotation === rotation)) {
    assert.ok(html.includes(`aria-label="放置地形 (${a.action.x}, ${a.action.y}) · ${rotation * 90}°"`));
  }
  assert.doesNotMatch(html, /NaN|undefined/);
});

test("follower decision exposes accessible feature targets and skip", () => {
  const html = render(fixtures.follower);
  assert.match(html, /派遣一名随从，或跳过/);
  assert.match(html, /跳过随从 →/);
  assert.match(html, /role="button" tabindex="0"/);
  assert.equal((html.match(/role="button"/g) || []).length,
    fixtures.follower.actions.filter(a => a.action.type === "place_meeple").length);
  assert.doesNotMatch(html, /aria-label="放置地形/);
  const disabled = render(fixtures.follower, {disabled: true});
  assert.doesNotMatch(disabled, /role="button" tabindex="0"/);
  assert.match(disabled, /aria-disabled="true"/);
});

test("spectators can inspect tiles but cannot place tiles or followers", () => {
  for (const fixture of [fixtures.placement, fixtures.follower]) {
    const html = render(fixture, {actions: []});
    assert.match(html, /正在观看对局/);
    assert.match(html, /aria-label="查看地形/);
    assert.doesNotMatch(html, /aria-label="放置地形|派遣随从到|跳过随从 →/);
  }
});

test("finished matches and score panels render final scoring in both languages", () => {
  assert.match(render(fixtures.finished), /已完成终局计分/);
  assert.match(render(fixtures.finished, {lang: "en"}), /Game complete · final scoring included/);
  assert.doesNotMatch(render(fixtures.finished), /01 \/ LANDSCAPE|02 \/ FOLLOWER/);
  const html = renderToStaticMarkup(React.createElement(CarcassonnePlayerPanel, {
    player: fixtures.finished.view.players[0], identity: identities[0], lang: "en", active: false,
  }));
  assert.match(html, /Red/);
  assert.match(html, /Available followers/);
  assert.match(html, /Field/);
});

test("all 24 tiles in all four orientations render original geometry and follower targets", () => {
  assert.equal(fixtures.tiles.length, 96);
  for (const tile of fixtures.tiles) {
    const options = tile.features.map(f => ({id: f.id, action: {type: "place_meeple", feature: f.id}}));
    const html = renderToStaticMarkup(React.createElement(CarcassonneTile, {tile, lang: "en", options, onChoose() {}}));
    assert.doesNotMatch(html, /NaN|undefined/);
    assert.equal((html.match(/role="button"/g) || []).length, tile.features.length);
    assert.ok(html.includes(`rotate(${tile.rotation * 90} 50 50)`));
    assert.doesNotMatch(html, /<image|https?:/);
  }
});
