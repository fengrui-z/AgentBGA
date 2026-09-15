import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

// Render the real component, using the installed TypeScript compiler. No test
// copy of the renderer and no additional build/test dependencies are needed.
const source = readFileSync(new URL("../app/harmonies-table.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}}).outputText;
const output = {exports: {}};
vm.runInNewContext("(function(require, module, exports) {" + compiled + "\n})")(
  createRequire(import.meta.url), output, output.exports,
);
const {HarmoniesTable, HarmoniesPlayerPanel, Habitat} = output.exports;
const fixture = JSON.parse(readFileSync(new URL("./fixtures/harmonies.json", import.meta.url), "utf8"));
const identities = [{seat:0, name:"Human"}];
const render = (extra = {}) => renderToStaticMarkup(React.createElement(HarmoniesTable, {
  view:fixture.view, actions:fixture.actions, lang:"zh", identities, onChoose() {}, ...extra,
}));

test("Harmonies renders a real pending decision with 23 keyboard-accessible hexes", () => {
  const html = render();
  assert.equal((html.match(/role="button"/g) || []).length, 23);
  assert.match(html, /选择地形，点击高亮格放置/);
  assert.match(html, /aria-label="选择 山地"/);
  assert.match(html, /tabindex="0"/);
  assert.match(html, /动物牌市场/);
  assert.match(html, /栖息地；方块标记安置位置/);
  assert.doesNotMatch(html, />结束回合 →</);
});

test("spectators receive readable boards without action controls", () => {
  const html = render({actions:[]});
  assert.doesNotMatch(html, /role="button"/);
  assert.doesNotMatch(html, />拿取动物牌</);
  assert.doesNotMatch(html, />结束回合 →</);
  assert.match(html, /六角地形棋盘/);
  const panel = renderToStaticMarkup(React.createElement(HarmoniesPlayerPanel, {
    player:fixture.view.players[0], identity:identities[0], active:true, lang:"en",
  }));
  assert.match(panel, /Mountains/);
  assert.match(panel, /Human/);
});

test("completed solo games show the sun rating and both language variants render", () => {
  const view = {...fixture.view, status:"finished", final_round:8, solo_suns:7};
  assert.match(render({view, actions:[]}), /7.*枚太阳 · 单人成绩/);
  assert.match(render({view, actions:[], lang:"en"}), /suns · solo achievement/);
});

test("all 42 habitat cards render stack requirements and the marked animal target", () => {
  const catalog = JSON.parse(readFileSync(new URL("../../src/agentbga/data/harmonies-cards.json", import.meta.url), "utf8"));
  for (const card of catalog) {
    const html = renderToStaticMarkup(React.createElement(Habitat, {card, lang:"en"}));
    assert.match(html, /<svg/);
    assert.match(html, /settle here/);
    assert.match(html, /<rect/);
    assert.doesNotMatch(html, /NaN|undefined/);
  }
});
