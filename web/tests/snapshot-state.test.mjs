import assert from "node:assert/strict";
import test from "node:test";
import {mergeMatchSnapshot} from "../app/snapshot-state.ts";

test("a late action reply cannot remove the next human turn delivered by SSE", () => {
  let snapshot = {match_id: "table", version: 10, human_turn: {seat: 0, version: 10}};
  const actionReply = {...snapshot, human_turn: null};
  const nextHumanTurn = {...snapshot, version: 12, human_turn: {seat: 0, version: 12}};
  snapshot = mergeMatchSnapshot(snapshot, nextHumanTurn);
  snapshot = mergeMatchSnapshot(snapshot, actionReply);
  assert.equal(snapshot.version, 12);
  assert.deepEqual(snapshot.human_turn, {seat: 0, version: 12});
});

test("same-version pause and human-wait updates still arrive", () => {
  const snapshot = {match_id: "table", version: 10, paused: false, human_turn: null};
  const paused = mergeMatchSnapshot(snapshot, {...snapshot, paused: true});
  assert.equal(paused.paused, true);
  const waiting = mergeMatchSnapshot(paused, {...paused, human_turn: {seat: 0, version: 10}});
  assert.equal(waiting.human_turn.version, 10);
});

test("responses from a table that was left cannot replace the current table", () => {
  const oldReply = {match_id: "old", version: 99};
  const current = {match_id: "new", version: 0};
  assert.equal(mergeMatchSnapshot(current, oldReply), current);
  assert.equal(mergeMatchSnapshot(null, oldReply), null);
});

test("a late reply cannot undo a newer pause or simultaneous-seat update at the same version", () => {
  const before = {match_id: "table", version: 10, event_seq: 3, paused: false, human_turn: null};
  const waiting = {...before, event_seq: 4, human_turn: {seat: 1, version: 10}};
  const paused = {...waiting, event_seq: 5, paused: true};
  let snapshot = mergeMatchSnapshot(before, waiting);
  snapshot = mergeMatchSnapshot(snapshot, paused);
  snapshot = mergeMatchSnapshot(snapshot, before);
  snapshot = mergeMatchSnapshot(snapshot, waiting);
  assert.deepEqual(snapshot, paused);
});
