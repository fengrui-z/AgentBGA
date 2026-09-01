/**
 * AgentBGA's cold-start, resumable replacement for dsh-headless.
 *
 * The stock headless runner intentionally creates a random session for every
 * invocation.  This plugin keeps the same one-turn lifecycle while binding the
 * persisted session to an AgentBGA-owned stable ID.  It deliberately imports
 * only Node built-ins so a `file://` Cordis entry can load it without installing
 * another package into each isolated DSH_HOME.
 */

import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export const name = "agentbga-resumable-headless-runner";
export const inject = [
  "agentDefaultModel",
  "agents",
  "headlessStartup",
  "sessions",
];

function installModelSelection(agentCtx, selection) {
  const disposeAssembly = agentCtx.on(
    "system-prompt/assemble",
    async (_assembly, _context, next) => {
      const selected = selection.current;
      const assembled = await next();
      selection.assembled = selected;
      if (selected === undefined) return assembled;
      return {
        ...assembled,
        variables: {
          ...assembled.variables,
          provider: selected.provider,
          model: selected.model,
        },
      };
    },
  );
  const disposeRequest = agentCtx.on("agent/request", async (_payload, next) => {
    const resolved = await next();
    const selected = selection.assembled;
    if (selected === undefined) return resolved;
    const { reasoningEffort: _inheritedEffort, ...withoutInheritedEffort } = resolved;
    return {
      ...withoutInheritedEffort,
      provider: selected.provider,
      model: selected.model,
      ...(selected.reasoningEffort === undefined
        ? {}
        : { reasoningEffort: selected.reasoningEffort }),
    };
  });
  return () => {
    disposeAssembly();
    disposeRequest();
  };
}

function userMessage(task) {
  return Object.freeze({
    id: randomUUID(),
    role: "user",
    content: Object.freeze([Object.freeze({ type: "text", text: task })]),
    source: Object.freeze({ kind: "user" }),
  });
}

function summarize(events, firstSeq) {
  let started = false;
  let text = "";
  let reason;
  for (const event of events) {
    if (event.seq < firstSeq) continue;
    if (event.type === "turn/start") {
      started = true;
      continue;
    }
    if (!started) continue;
    if (event.type === "assistant/message") {
      const joined = event.data.message.content
        .filter((block) => block.type === "text")
        .map((block) => block.text)
        .join("");
      if (joined !== "") text = joined;
    }
    if (event.type === "turn/end") reason = event.data.reason;
  }
  return { text, reason };
}

async function readState(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return undefined;
    throw new Error(`cannot read AgentBGA DSh session state: ${error}`);
  }
}

async function writeJsonAtomic(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(value), "utf8");
  await rename(temporary, path);
}

function validateConfig(config) {
  for (const key of ["task", "sessionId", "ownerKey", "statePath", "metadataPath"]) {
    if (typeof config?.[key] !== "string" || config[key].trim() === "") {
      throw new Error(`agentbga resumable runner requires non-empty ${key}`);
    }
  }
}

function validateState(state, config) {
  if (
    typeof state !== "object" ||
    state === null ||
    state.schemaVersion !== "agentbga.dsh-session.v1" ||
    state.sessionId !== config.sessionId ||
    state.ownerKey !== config.ownerKey ||
    !Number.isSafeInteger(state.resumeCount) ||
    state.resumeCount < 0
  ) {
    throw new Error(
      "AgentBGA DSh session state does not match this session key; " +
        "clear the isolated DSH_HOME or choose a new match/series ID",
    );
  }
}

function compactEvents(events, firstSeq = 0) {
  return events
    .filter((event) => event.seq >= firstSeq && event.type.startsWith("compaction/"))
    .map((event) => ({ seq: event.seq, type: event.type, data: event.data }));
}

function summarizeUsage(events, firstSeq) {
  const samples = new Map();
  for (const event of events) {
    if (event.seq < firstSeq) continue;
    let current;
    if (event.type === "assistant/chunk" && event.data?.chunk?.type === "usage") {
      current = event.data.chunk.usage;
    } else if (event.type === "assistant/message") {
      current = event.data?.usage;
    }
    if (current === undefined || current === null) continue;
    // Match DSh's token-meter projection: a final assistant/message replaces
    // an early usage chunk for the same turn/step instead of double-counting.
    samples.set(`${event.data?.turn}:${event.data?.step}`, current);
  }
  const usage = {
    inputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    outputTokens: 0,
    reasoningTokens: 0,
    modelResponses: 0,
  };
  for (const current of samples.values()) {
    usage.inputTokens += Number(current.inputTokens) || 0;
    usage.cacheReadTokens += Number(current.cacheReadTokens) || 0;
    usage.cacheWriteTokens += Number(current.cacheWriteTokens) || 0;
    usage.outputTokens += Number(current.outputTokens) || 0;
    usage.reasoningTokens += Number(current.reasoningTokens) || 0;
  }
  usage.modelResponses = samples.size;
  return usage;
}

export async function run(ctx, config, io) {
  validateConfig(config);
  await ctx.get("loader")?.await();
  const agents = ctx.get("agents");
  const defaultModel = ctx.get("agentDefaultModel");
  const sessions = ctx.get("sessions");
  if (agents === undefined || defaultModel === undefined || sessions === undefined) {
    throw new Error("required DSh services are unavailable");
  }

  const state = await readState(config.statePath);
  if (state !== undefined) validateState(state, config);
  const resumed = state !== undefined;
  const resumeCount = resumed ? state.resumeCount + 1 : 0;
  const selection = defaultModel.currentSelection();
  const setup = (agentCtx) => {
    // Match dsh-headless's setup contract: install scoped listeners but do not
    // return their disposer as an AgentSetupCommit.
    installModelSelection(agentCtx, { current: selection, assembled: undefined });
  };
  const agentOptions = { provider: selection.provider, model: selection.model };
  const handle = resumed
    ? await agents.resume({
        resumeSessionId: config.sessionId,
        agentOptions,
        setup,
      })
    : await agents.create({
        sessionId: config.sessionId,
        meta: { cwd: process.cwd() },
        agentOptions,
        setup,
      });
  const { agent } = handle;

  await agent.whenIdle();
  const firstSeq = agent.session.seq;
  agent.followup(userMessage(config.task));
  await agent.whenIdle();
  await sessions.flush(agent.session);

  const outcome = summarize(agent.session.events, firstSeq);
  const tokenUsage = summarizeUsage(agent.session.events, firstSeq);
  const turnCompactions = compactEvents(agent.session.events, firstSeq);
  const allCompactions = compactEvents(agent.session.events);
  const completedAt = new Date().toISOString();
  await writeJsonAtomic(config.statePath, {
    schemaVersion: "agentbga.dsh-session.v1",
    sessionId: config.sessionId,
    ownerKey: config.ownerKey,
    resumeCount,
    completedAt,
  });
  await writeJsonAtomic(config.metadataPath, {
    schemaVersion: "agentbga.dsh-turn.v1",
    sessionId: config.sessionId,
    ownerKey: config.ownerKey,
    resumed,
    resumeCount,
    firstSeq,
    lastSeq: agent.session.seq,
    compactionEvents: turnCompactions,
    compactionEventCountTotal: allCompactions.length,
    tokenUsage,
    outcome: outcome.reason,
    completedAt,
  });

  io.stdout.write(outcome.text + "\n");
  if (outcome.reason?.kind === "error") {
    io.stderr.write(
      `dsh: ${outcome.reason.error.code}: ${outcome.reason.error.message}\n`,
    );
  }
  io.exit(outcome.reason?.kind === "completed" ? 0 : 1);
}

async function writeFailureMetadata(config, error) {
  if (typeof config?.metadataPath !== "string" || config.metadataPath === "") return;
  await writeJsonAtomic(config.metadataPath, {
    schemaVersion: "agentbga.dsh-turn.v1",
    sessionId: config.sessionId,
    ownerKey: config.ownerKey,
    error: error instanceof Error ? error.message : String(error),
    completedAt: new Date().toISOString(),
  });
}

export function apply(ctx, config) {
  const exit = ctx.get("appExit");
  if (exit === undefined) {
    throw new Error("agentbga resumable runner requires the DSh appExit service");
  }
  const io = { stdout: process.stdout, stderr: process.stderr, exit };
  run(ctx, config, io).catch(async (error) => {
    try {
      await writeFailureMetadata(config, error);
    } catch {
      // Preserve the original runner failure.
    }
    io.stderr.write(`dsh: ${error instanceof Error ? error.message : String(error)}\n`);
    io.exit(1);
  });
}
