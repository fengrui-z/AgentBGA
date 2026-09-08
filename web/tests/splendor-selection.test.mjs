import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import test from "node:test";
import {canAddToken, counts, reservationChoices, resolveSelection, selectionCandidates, tokenTotal} from "../app/splendor-selection.ts";

// Exercise the picker against real engine action sets, including sparse banks
// and overflow, so presentation changes cannot silently alter agent actions.
const scenarios = JSON.parse(execFileSync("python3", ["-c", `
import json
from agentbga import splendor

def scenario(held, bank=None):
    state = splendor.new_game(2, 42)
    for color, amount in held.items():
        state['bank'][color] -= amount
        state['players'][0]['tokens'][color] += amount
    if bank is not None:
        for color, amount in bank.items():
            state['players'][1]['tokens'][color] += state['bank'][color] - amount
            state['bank'][color] = amount
    splendor.validate_state(state)
    return splendor.legal_actions(state, 0)

print(json.dumps({
    'initial': scenario({}),
    'overflow': scenario({'red': 3, 'blue': 3, 'green': 2, 'gold': 2}),
    'scarce': scenario({'red': 2}, {'red': 0, 'blue': 0, 'green': 0}),
    'oneColor': scenario({'red': 3, 'blue': 3}, {'red': 0, 'blue': 0, 'green': 0, 'white': 0}),
    'noGold': scenario({'gold': 5, 'red': 3, 'blue': 2}),
}))
`], {cwd: new URL("../../", import.meta.url), env: {...process.env, PYTHONPATH: "src"}, encoding: "utf8"}));

test("take selection enforces three colors or a legal same-color pair", () => {
  const actions = scenarios.initial.filter(item => item.action.type === "take_tokens");
  assert.equal(resolveSelection(selectionCandidates(actions, "take", {red: 1}), {}), null);
  assert.ok(canAddToken(actions, "take", {red: 1}, "red"));
  assert.ok(resolveSelection(selectionCandidates(actions, "take", {red: 2}), {}));
  assert.equal(canAddToken(actions, "take", {red: 2}, "blue"), false);
  assert.equal(canAddToken(actions, "take", {red: 1, blue: 1}, "red"), false);
  assert.ok(resolveSelection(selectionCandidates(actions, "take", {red: 1, blue: 1, green: 1}), {}));
  assert.equal(canAddToken(actions, "take", {red: 1, blue: 1, green: 1}, "white"), false);
  assert.equal(canAddToken(actions, "take", {}, "gold"), false);
});

test("low inventory supports all remaining colors and rejects unavailable pairs", () => {
  assert.ok(resolveSelection(selectionCandidates(scenarios.scarce, "take", {white: 1, black: 1}), {}));
  assert.ok(resolveSelection(selectionCandidates(scenarios.oneColor, "take", {black: 1}), {}));
  assert.equal(canAddToken(scenarios.scarce, "take", {}, "red"), false);
  assert.equal(canAddToken(scenarios.overflow, "take", {red: 1}, "red"), false);
});

test("overflow requires exact returns, including newly taken gems and gold", () => {
  const choices = selectionCandidates(scenarios.overflow, "take", {red: 1, blue: 1, white: 1});
  assert.equal(tokenTotal(counts(choices[0].action.return)), 3);
  assert.equal(resolveSelection(choices, {}), null);
  assert.equal(resolveSelection(choices, {gold: 1}), null);
  assert.ok(resolveSelection(choices, {gold: 2, white: 1}));
  assert.equal(resolveSelection(choices, {gold: 3}), null);
  assert.equal(resolveSelection(choices, {gold: 2, white: 2}), null);
  assert.equal(canAddToken(choices, "return", {gold: 2, white: 1}, "red"), false);
  // Undoing a selection leaves zero entries, which are equivalent to absence.
  assert.ok(resolveSelection(choices, {red: 3, blue: 0}));
});

test("reservations show one choice per card/deck and resolve the chosen return", () => {
  const actions = scenarios.overflow.filter(item => item.action.type.startsWith("reserve_"));
  const choices = reservationChoices(actions);
  assert.equal(choices.length, 15);
  assert.ok(actions.length > choices.length);
  for (const choice of choices) {
    const candidates = selectionCandidates(actions, choice, {});
    assert.equal(resolveSelection(candidates, {}), null);
    const resolved = resolveSelection(candidates, {gold: 1});
    assert.ok(resolved);
    assert.equal(resolved.action.card_id, choice.action.card_id);
    assert.equal(resolved.action.tier, choice.action.tier);
  }
  const noGold = scenarios.noGold.find(item => item.action.type === "reserve_deck");
  assert.ok(resolveSelection(selectionCandidates(scenarios.noGold, noGold, {}), {}));
});

test("every enumerated take/return and reservation remains reachable with its original ID", () => {
  for (const actions of Object.values(scenarios)) {
    const original = JSON.stringify(actions);
    for (const item of actions) {
      const kind = item.action.type;
      if (kind !== "take_tokens" && !kind.startsWith("reserve_")) continue;
      const take = counts(item.action.take);
      if (kind === "take_tokens") {
        const selected = {};
        for (const [color, amount] of Object.entries(take)) {
          for (let n = 0; n < amount; n++) {
            assert.ok(canAddToken(actions, "take", selected, color));
            selected[color] = (selected[color] ?? 0) + 1;
          }
        }
      }
      const candidates = selectionCandidates(actions, kind === "take_tokens" ? "take" : item, take);
      const returned = {};
      for (const [color, amount] of Object.entries(counts(item.action.return))) {
        for (let n = 0; n < amount; n++) {
          assert.ok(canAddToken(candidates, "return", returned, color));
          returned[color] = (returned[color] ?? 0) + 1;
        }
      }
      assert.equal(resolveSelection(candidates, returned)?.id, item.id);
    }
    assert.equal(JSON.stringify(actions), original);
  }
});
