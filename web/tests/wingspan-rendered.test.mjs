import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import vm from "node:vm";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";
const compiled=ts.transpileModule(readFileSync(new URL("../app/wingspan-table.tsx",import.meta.url),"utf8"),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const output={exports:{}};
vm.runInNewContext("(function(require,module,exports){"+compiled+"\n})")(createRequire(import.meta.url),output,output.exports);
const {WingspanTable,WingspanPlayerPanel,WingspanBird}=output.exports;
const fixtures=JSON.parse(readFileSync(new URL("./fixtures/wingspan.json",import.meta.url),"utf8"));
const identities=[{seat:0,name:"Player A"},{seat:1,name:"Player B"}];
const render=(fixture,extra={})=>renderToStaticMarkup(React.createElement(WingspanTable,{...fixture,identities,lang:"zh",onChoose(){},...extra}));
test("setup lets a human select any subset including no birds",()=>{
 const html=render(fixtures.setup);
 assert.equal((html.match(/type="checkbox"/g)||[]).length,5);
 assert.match(html,/保留 0 张鸟牌，支付 0 个食物/);
 for(const c of fixtures.setup.view.players[fixtures.setup.view.viewer_seat].hand) assert.ok(html.includes(c.name.replaceAll("'","&#x27;")));
 assert.doesNotMatch(html,/NaN|undefined/);
});
test("pending egg decisions render playable bird targets and all three habitats",()=>{
 const html=render(fixtures.eggs);
 assert.match(html,/选择放置鸟蛋的鸟类/);
 assert.match(html,/放置鸟蛋/);
 for(const h of ['forest','grassland','wetland']) assert.ok(html.includes(`ws-habitat ws-${h}`));
 assert.match(html,/剩余|公开鸟牌/);
 assert.doesNotMatch(html,/NaN|undefined/);
});
test("spectator table omits action choices and player panel distinguishes hidden bonus score",()=>{
 const html=render(fixtures.eggs,{actions:[],lang:"en"});
 assert.doesNotMatch(html,/>Lay egg<|>Take action</);
 assert.match(html,/Shared birdfeeder/);
 const player=fixtures.eggs.view.players[1-fixtures.eggs.view.viewer_seat];
 const panel=renderToStaticMarkup(React.createElement(WingspanPlayerPanel,{player,identity:identities[player.seat],active:false,lang:"en"}));
 assert.match(panel,/Bonus points revealed at game end/);
});
test("all 170 base birds render mechanical values and no publisher images",()=>{
 const catalog=JSON.parse(readFileSync(new URL("../../src/agentbga/wingspan/birds.json",import.meta.url),"utf8"));
 assert.equal(catalog.length,170);
 for(const c of catalog){
  const html=renderToStaticMarkup(React.createElement(WingspanBird,{card:{...c,power_summary:"Mechanical power summary"},lang:"en"}));
  assert.match(html,/cm/);assert.doesNotMatch(html,/NaN|undefined|<img/);
 }
});
test("completed games expose a clear final result notice",()=>{
 const view={...fixtures.eggs.view,status:"finished"};
 assert.match(render({...fixtures.eggs,view},{actions:[]}),/对局结束 · 奖励卡与最终得分已公开/);
});
