import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { run } from "../src/agentbga/dsh_resumable_runner.mjs";

function fakeWorld() {
  const histories = new Map();
  const calls = { create: [], resume: [], flush: [] };
  let emitCompaction = true;

  function scopedContext() {
    return { on: () => () => {} };
  }

  function agentFor(sessionId, events) {
    const session = {
      events,
      get seq() {
        return this.events.length;
      },
    };
    return {
      session,
      async whenIdle() {},
      followup(message) {
        const append = (type, data) =>
          events.push({ seq: events.length, type, data });
        append("turn/start", { turn: `turn-${events.length}` });
        if (emitCompaction) {
          append("compaction/start", { reason: "token-threshold" });
          append("compaction/end", { replaced: 12 });
          emitCompaction = false;
        }
        append("user/message", { message });
        append("assistant/chunk", {
          turn: 1,
          step: 0,
          chunk: {
            type: "usage",
            usage: {
              inputTokens: 100,
              cacheReadTokens: 70,
              cacheWriteTokens: 5,
              outputTokens: 20,
              reasoningTokens: 12,
            },
          },
        });
        append("assistant/message", {
          turn: 1,
          step: 0,
          message: { content: [{ type: "text", text: "submitted" }] },
          usage: {
            inputTokens: 120,
            cacheReadTokens: 80,
            cacheWriteTokens: 5,
            outputTokens: 24,
            reasoningTokens: 16,
          },
        });
        append("turn/end", { reason: { kind: "completed" } });
      },
    };
  }

  const agents = {
    async create(options) {
      calls.create.push(options.sessionId);
      assert.equal(options.meta.cwd, process.cwd());
      assert.equal(options.setup(scopedContext()), undefined);
      const events = [];
      histories.set(options.sessionId, events);
      return { agent: agentFor(options.sessionId, events) };
    },
    async resume(options) {
      calls.resume.push(options.resumeSessionId);
      assert.equal(options.setup(scopedContext()), undefined);
      const events = histories.get(options.resumeSessionId);
      assert.ok(events, "resume must target a persisted fake session");
      return { agent: agentFor(options.resumeSessionId, events) };
    },
  };
  const services = {
    agents,
    agentDefaultModel: {
      currentSelection: () => ({ provider: "deepseek-official", model: "test" }),
    },
    sessions: {
      async flush(session) {
        calls.flush.push(session.events.length);
      },
    },
  };
  return {
    calls,
    ctx: { get: (name) => services[name] },
  };
}

function outputCapture() {
  return {
    stdout: { write() {} },
    stderr: { write() {} },
    exitCode: undefined,
    exit(code) {
      this.exitCode = code;
    },
  };
}

test("cold starts once, resumes continuously, and resumes after compaction", async () => {
  const directory = await mkdtemp(join(tmpdir(), "agentbga-dsh-runner-"));
  try {
    const world = fakeWorld();
    const statePath = join(directory, "seat-0", "state.json");
    const ownerKey = JSON.stringify({ scope: "series", id: "s20", seat: 0 });
    const base = {
      task: "choose one action",
      sessionId: "session-agentbga-series-test-seat-0",
      ownerKey,
      statePath,
    };

    const firstMetadata = join(directory, "turn-1.json");
    const firstIo = outputCapture();
    await run(world.ctx, { ...base, metadataPath: firstMetadata }, firstIo);
    assert.equal(firstIo.exitCode, 0);
    assert.deepEqual(world.calls.create, [base.sessionId]);
    assert.deepEqual(world.calls.resume, []);
    const first = JSON.parse(await readFile(firstMetadata, "utf8"));
    assert.equal(first.resumed, false);
    assert.equal(first.resumeCount, 0);
    assert.deepEqual(
      first.compactionEvents.map((event) => event.type),
      ["compaction/start", "compaction/end"],
    );
    assert.deepEqual(first.tokenUsage, {
      inputTokens: 120,
      cacheReadTokens: 80,
      cacheWriteTokens: 5,
      outputTokens: 24,
      reasoningTokens: 16,
      modelResponses: 1,
    });

    const secondMetadata = join(directory, "turn-2.json");
    const secondIo = outputCapture();
    await run(world.ctx, { ...base, task: "choose again", metadataPath: secondMetadata }, secondIo);
    assert.equal(secondIo.exitCode, 0);
    assert.deepEqual(world.calls.create, [base.sessionId]);
    assert.deepEqual(world.calls.resume, [base.sessionId]);
    const second = JSON.parse(await readFile(secondMetadata, "utf8"));
    assert.equal(second.resumed, true);
    assert.equal(second.resumeCount, 1);
    assert.deepEqual(second.compactionEvents, []);
    assert.equal(second.compactionEventCountTotal, 2);
    assert.equal(second.tokenUsage.inputTokens, 120);
    assert.equal(second.tokenUsage.modelResponses, 1);
    assert.equal(world.calls.flush.length, 2);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("state ownership mismatch fails instead of leaking another seat", async () => {
  const directory = await mkdtemp(join(tmpdir(), "agentbga-dsh-owner-"));
  try {
    const world = fakeWorld();
    const statePath = join(directory, "state.json");
    const first = {
      task: "seat zero",
      sessionId: "session-seat-0",
      ownerKey: JSON.stringify({ scope: "match", id: "m1", seat: 0 }),
      statePath,
      metadataPath: join(directory, "first.json"),
    };
    await run(world.ctx, first, outputCapture());
    await assert.rejects(
      run(
        world.ctx,
        {
          ...first,
          task: "seat one",
          ownerKey: JSON.stringify({ scope: "match", id: "m1", seat: 1 }),
          metadataPath: join(directory, "second.json"),
        },
        outputCapture(),
      ),
      /does not match this session key/,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
