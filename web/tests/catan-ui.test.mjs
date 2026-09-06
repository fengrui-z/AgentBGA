import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

// Exercise the production components without adding a separate frontend test runner.
const source = await readFile(new URL("../app/catan.tsx", import.meta.url), "utf8");
const {outputText} = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022}});
const exports = {};
new Function("exports", "require", outputText)(exports, createRequire(import.meta.url));
const {CatanBoard, CatanPlayerPanel, CatanActionPicker, catanActionText} = exports;
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const identity = {seat: 0, name: "Alice", backend: "human"};
const player = {
  seat: 0, resource_count: 8, development_count: 1, played_knights: 2, longest_road_length: 4,
  public_score: 3, score: 4, roads_remaining: 11, settlements_remaining: 2, cities_remaining: 4,
  resources: {brick: 1, lumber: 2, wool: 3, grain: 1, ore: 1},
  development_cards: [{id: "dev-7", type: "victory_point", bought_turn: 3}],
};
const vertices = Array.from({length: 6}, (_, id) => ({
  id, x: Math.cos(id * Math.PI / 3), y: Math.sin(id * Math.PI / 3), hexes: [0], edges: [id, (id + 5) % 6],
  building: id === 0 ? {seat: 0, type: "settlement"} : id === 3 ? {seat: 1, type: "city"} : null, port: null,
}));
const view = {
  game: "catan", status: "active", phase: "main", active_seat: 0, turn_seat: 0, turn_count: 4, decision_count: 19,
  robber_hex: 0, last_roll: [3, 5], bank: {brick: 18, lumber: 17, wool: 16, grain: 18, ore: 18},
  players: [player], development_deck_count: 24, longest_road_seat: 0, largest_army_seat: null,
  discard_remaining: {}, free_roads_remaining: 0, trade: null,
  board: {
    hexes: [{id: 0, q: 0, r: 0, x: 0, y: 0, terrain: "brick", number: 8, vertices: [0, 1, 2, 3, 4, 5], edges: [0, 1, 2, 3, 4, 5]}],
    vertices, edges: vertices.map(({id}) => ({id, vertices: [id, (id + 1) % 6], owner: id === 0 ? 0 : null})),
    ports: [{id: 0, vertices: [1, 2], resource: "any"}],
  },
};

test("Catan action labels preserve each target and trade amount", () => {
  const cases = [
    [{type: "place_settlement", vertex: 0}, /Starting settlement.*vertex 0/],
    [{type: "place_road", edge: 2}, /Starting road.*edge 2/],
    [{type: "build_road", edge: 6}, /Build road.*edge 6/],
    [{type: "build_settlement", vertex: 5}, /Build settlement.*vertex 5/],
    [{type: "build_city", vertex: 3}, /Upgrade to city.*vertex 3/],
    [{type: "move_robber", hex: 12}, /Move robber.*hex 12/],
    [{type: "steal", victim: 1}, /seat 2/],
    [{type: "maritime_trade", give: "lumber", receive: "ore", ratio: 2}, /Trade 2 Lumber for 1 Ore/],
    [{type: "play_monopoly", resource: "wool"}, /Play monopoly.*Wool/],
    [{type: "discard", resource: "brick"}, /Discard resource.*Brick × 1/],
    [{type: "take_resource", resource: "grain"}, /Choose resource.*Grain × 1/],
    [{type: "free_road", edge: 9}, /Free road.*edge 9/],
    [{type: "propose_trade", partner: 2}, /seat 3/],
    [{type: "trade_amount", resource: "ore", amount: 4}, /Ore × 4/],
    [{type: "respond_trade", accept: true}, /^Accept trade$/],
    [{type: "respond_trade", accept: false}, /^Decline trade$/],
  ];
  for (const [action, label] of cases) {
    assert.match(catanActionText(action, "en"), label);
    assert.doesNotMatch(catanActionText(action, "zh"), /undefined|null|NaN/);
  }
  for (const type of ["roll_dice", "buy_development_card", "play_knight", "play_road_building", "play_year_of_plenty", "end_turn", "finish_road_building", "cancel_trade"]) {
    assert.ok(catanActionText({type}, "en"));
    assert.notEqual(catanActionText({type}, "en"), type);
  }
  assert.equal(catanActionText({type: "take_resource", resource: "coal", source: "market"}, "en"), null, "Brass resource actions retain their existing formatter");
  assert.equal(catanActionText({type: "buy_visible", card_id: "c1"}, "en"), null);
});

test("Catan board renders real geometry, ownership, ports, dice and selectable targets", () => {
  const selected = {id: "build-2", action: {type: "build_settlement", vertex: 2}};
  const html = render(CatanBoard, {view, players: [identity, {seat: 1, name: "Bob"}], lang: "en", humanActions: [selected], selectedActionId: selected.id, onChoose() {}});
  assert.match(html, /Catan hexes, settlements, cities and roads/);
  assert.match(html, /<polygon points=/);
  assert.match(html, /terrain-brick/);
  assert.match(html, /catan-road owned/);
  assert.match(html, /catan-vertex built settlement/);
  assert.match(html, /catan-vertex built city/);
  assert.match(html, /class="catan-vertex {2}actionable selected"[^>]*role="button"[^>]*tabindex="0"[^>]*aria-label="Build settlement · vertex 2"/);
  assert.match(html, /3 \+ 5 = 8/);
  assert.match(html, /Generic harbor 3:1/);
  assert.match(html, /Robber/);
  assert.match(html, /Longest road · 2 VP/);
  assert.doesNotMatch(html, /NaN|undefined/);
});

test("Catan opponents show counts and public score while own cards remain visible", () => {
  const own = render(CatanPlayerPanel, {player, identity, active: true, lang: "en"});
  assert.match(own, /<strong>4<\/strong><span>VP/);
  assert.match(own, /Victory point/);
  assert.match(own, /class="catan-resources"/);
  const opponent = render(CatanPlayerPanel, {player: {...player, score: null, resources: null, development_cards: null}, identity, active: false, lang: "en"});
  assert.match(opponent, /<strong>3<\/strong><span>VP/);
  assert.match(opponent, /Resource cards<\/span><b>8/);
  assert.match(opponent, /Resource types are private/);
  assert.match(opponent, /Card faces are private/);
  assert.doesNotMatch(opponent, /Victory point|class="catan-resources"/);
});

test("Catan action picker exposes precise choices and selected state", () => {
  const actions = [{id: "trade-yes", action: {type: "respond_trade", accept: true}}, {id: "trade-no", action: {type: "respond_trade", accept: false}}];
  const html = render(CatanActionPicker, {actions, lang: "en", disabled: false, selectedId: "trade-yes", onChoose() {}});
  assert.match(html, /aria-pressed="true">Accept trade/);
  assert.match(html, /aria-pressed="false">Decline trade/);
});
