import { RESULTS_SCHEMA_STATEMENTS } from "../db/schema";

export interface ResultsEnv {
  DB: D1Database;
  RESULT_SUBMISSION_TOKENS?: string;
}

type JsonRecord = Record<string, unknown>;

type RankingRow = {
  result_id: string;
  game: string;
  mode: string;
  received_at: string;
  participant_id: string;
  display_name: string;
  backend: string;
  model: string | null;
  seat: number;
  rank: number;
};

type Rating = {
  participant_id: string;
  display_name: string;
  backend: string;
  model: string | null;
  rating: number;
  games: number;
  wins: number;
};

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const MAX_MATCHES_PER_ARTIFACT = 500;
const INITIAL_RATING = 1500;
const K_FACTOR = 32;

let schemaReady: Promise<void> | undefined;

function json(data: unknown, status = 200): Response {
  return Response.json(data, {
    status,
    headers: {
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function ensureSchema(db: D1Database): Promise<void> {
  schemaReady ??= (async () => {
    for (const statement of RESULTS_SCHEMA_STATEMENTS) await db.prepare(statement).run();
  })().catch(error => {
    schemaReady = undefined;
    throw error;
  });
  return schemaReady;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

async function constantTimeEqual(left: string, right: string): Promise<boolean> {
  const [leftHash, rightHash] = await Promise.all([sha256(left), sha256(right)]);
  let difference = leftHash.length ^ rightHash.length;
  for (let index = 0; index < Math.max(leftHash.length, rightHash.length); index++) {
    difference |= (leftHash.charCodeAt(index) || 0) ^ (rightHash.charCodeAt(index) || 0);
  }
  return difference === 0;
}

function configuredTokens(raw: string | undefined): Record<string, string> {
  if (!raw) return {};
  const parsed: unknown = JSON.parse(raw);
  if (!isRecord(parsed)) throw new Error("RESULT_SUBMISSION_TOKENS must be a JSON object");
  const entries = Object.entries(parsed);
  if (!entries.length || entries.some(([, token]) => typeof token !== "string" || !token)) {
    throw new Error("RESULT_SUBMISSION_TOKENS must map submitter ids to non-empty tokens");
  }
  return Object.fromEntries(entries) as Record<string, string>;
}

async function authenticate(request: Request, artifact: JsonRecord, env: ResultsEnv): Promise<string | null> {
  const authorization = request.headers.get("authorization");
  const bodyToken = isRecord(artifact.submission) && typeof artifact.submission.token === "string"
    ? artifact.submission.token : "";
  const supplied = authorization?.startsWith("Bearer ") ? authorization.slice(7).trim() : bodyToken;
  if (!supplied) return null;
  for (const [submitter, token] of Object.entries(configuredTokens(env.RESULT_SUBMISSION_TOKENS))) {
    if (await constantTimeEqual(supplied, token)) return submitter;
  }
  return null;
}

function validateArtifact(value: unknown): asserts value is JsonRecord & {matches: JsonRecord[]} {
  if (!isRecord(value) || value.schema_version !== "agentbga.results.v1") {
    throw new Error("expected an agentbga.results.v1 document");
  }
  for (const field of ["experiment_id", "run_id", "mode", "generated_at"]) {
    if (typeof value[field] !== "string" || !value[field]) throw new Error(`missing ${field}`);
  }
  if (!["duel", "tournament", "series"].includes(String(value.mode))) throw new Error("invalid mode");
  const allowedRoot = new Set(["schema_version", "experiment_id", "run_id", "mode", "generated_at",
    "complete", "summary", "matches", "submission", "integrity"]);
  const unknownRoot = Object.keys(value).filter(key => !allowedRoot.has(key));
  if (unknownRoot.length) throw new Error(`unknown root fields: ${unknownRoot.join(", ")}`);
  if (value.submission !== undefined && (!isRecord(value.submission) ||
      typeof value.submission.token !== "string" ||
      Object.keys(value.submission).some(key => key !== "token"))) {
    throw new Error("submission must contain only a token string");
  }
  if (!Array.isArray(value.matches) || value.matches.length > MAX_MATCHES_PER_ARTIFACT) {
    throw new Error(`matches must be an array with at most ${MAX_MATCHES_PER_ARTIFACT} entries`);
  }
  if (!isRecord(value.integrity) || value.integrity.algorithm !== "sha256" ||
      typeof value.integrity.content_digest !== "string" ||
      !/^[a-f0-9]{64}$/.test(value.integrity.content_digest)) {
    throw new Error("invalid integrity block");
  }
  const resultIds = new Set<string>();
  for (const [index, match] of value.matches.entries()) {
    if (!isRecord(match)) throw new Error(`match ${index + 1} must be an object`);
    if (typeof match.result_id !== "string" || !/^[a-f0-9]{64}$/.test(match.result_id)) {
      throw new Error(`match ${index + 1} has an invalid result_id`);
    }
    if (resultIds.has(match.result_id)) throw new Error(`match ${index + 1} repeats result_id`);
    resultIds.add(match.result_id);
    if (!Number.isInteger(match.ordinal) || !Number.isInteger(match.seed) ||
        !Number.isInteger(match.player_count) || Number(match.player_count) < 2 || Number(match.player_count) > 4) {
      throw new Error(`match ${index + 1} has invalid schedule fields`);
    }
    if (typeof match.game !== "string" || !match.game || !["ok", "error"].includes(String(match.status))) {
      throw new Error(`match ${index + 1} has invalid game or status`);
    }
    if (!Array.isArray(match.participants) || match.participants.length !== match.player_count) {
      throw new Error(`match ${index + 1} participants do not match player_count`);
    }
    const participants = match.participants as unknown[];
    const ids = new Set<string>();
    const seats = new Set<number>();
    for (const participant of participants) {
      if (!isRecord(participant) || typeof participant.participant_id !== "string" || !participant.participant_id ||
          !Number.isInteger(participant.seat) || Number(participant.seat) < 0 || Number(participant.seat) >= Number(match.player_count) ||
          !isRecord(participant.player)) {
        throw new Error(`match ${index + 1} has an invalid participant`);
      }
      if (["api_key", "apiKey", "token", "password", "secret"].some(field =>
        Object.hasOwn(participant.player, field))) {
        throw new Error(`match ${index + 1} participant contains a secret field`);
      }
      ids.add(participant.participant_id);
      seats.add(Number(participant.seat));
    }
    if (ids.size !== participants.length || seats.size !== participants.length) {
      throw new Error(`match ${index + 1} repeats a participant or seat`);
    }
    if (match.status === "ok") {
      if (!isRecord(match.result) || !Array.isArray(match.result.rankings) ||
          match.result.rankings.length !== match.player_count) {
        throw new Error(`match ${index + 1} has invalid rankings`);
      }
      const rankedSeats = new Set<number>();
      for (const ranking of match.result.rankings) {
        if (!isRecord(ranking) || !Number.isInteger(ranking.seat) || !Number.isInteger(ranking.rank) ||
            Number(ranking.rank) < 1 || Number(ranking.rank) > Number(match.player_count) ||
            !seats.has(Number(ranking.seat))) {
          throw new Error(`match ${index + 1} has an invalid ranking row`);
        }
        rankedSeats.add(Number(ranking.seat));
      }
      if (rankedSeats.size !== participants.length) throw new Error(`match ${index + 1} repeats a ranked seat`);
    }
  }
}

async function verifyIntegrity(artifact: JsonRecord): Promise<string> {
  const content = Object.fromEntries(
    Object.entries(artifact).filter(([key]) => key !== "integrity" && key !== "submission"),
  );
  const calculated = await sha256(canonical(content));
  const expected = (artifact.integrity as JsonRecord).content_digest as string;
  if (!(await constantTimeEqual(calculated, expected))) throw new Error("content digest does not match artifact");
  return calculated;
}

function participantForSeat(match: JsonRecord, seat: number): JsonRecord {
  return (match.participants as JsonRecord[]).find(participant => participant.seat === seat)!;
}

async function submitResults(request: Request, env: ResultsEnv): Promise<Response> {
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_UPLOAD_BYTES) return json({error: "result file exceeds 5 MiB"}, 413);
  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_UPLOAD_BYTES) {
    return json({error: "result file exceeds 5 MiB"}, 413);
  }
  let artifact: unknown;
  try { artifact = JSON.parse(raw); } catch { return json({error: "result file is not valid JSON"}, 400); }
  try { validateArtifact(artifact); } catch (error) {
    return json({error: error instanceof Error ? error.message : String(error)}, 422);
  }
  let submitter: string | null;
  try { submitter = await authenticate(request, artifact, env); } catch (error) {
    return json({error: error instanceof Error ? error.message : String(error)}, 503);
  }
  if (!submitter) return json({error: "invalid or missing submission token"}, 401);

  let digest: string;
  try { digest = await verifyIntegrity(artifact); } catch (error) {
    return json({error: error instanceof Error ? error.message : String(error)}, 422);
  }
  await ensureSchema(env.DB);
  const prior = await env.DB.prepare(
    "SELECT submission_id, accepted_matches FROM result_submissions WHERE content_digest = ?",
  ).bind(digest).first<{submission_id: string; accepted_matches: number}>();
  if (prior) return json({ok: true, idempotent: true, submission_id: prior.submission_id,
    accepted_matches: prior.accepted_matches, duplicate_matches: artifact.matches.length});

  const submissionId = crypto.randomUUID();
  const receivedAt = new Date().toISOString();
  let accepted = 0;
  let duplicates = 0;
  const freshMatches: {match: JsonRecord; matchDigest: string}[] = [];
  for (const match of artifact.matches) {
    const matchDigest = await sha256(canonical(match));
    const exists = await env.DB.prepare("SELECT match_digest FROM benchmark_matches WHERE result_id = ?")
      .bind(match.result_id).first<{match_digest: string}>();
    if (exists) {
      if (exists.match_digest !== matchDigest) {
        return json({error: `result_id collision with different content: ${match.result_id}`}, 409);
      }
      duplicates += 1;
      continue;
    }
    freshMatches.push({match, matchDigest});
  }
  for (const {match, matchDigest} of freshMatches) {
    await env.DB.prepare(`INSERT INTO benchmark_matches
      (result_id, submission_id, experiment_id, run_id, mode, ordinal, game, seed,
       player_count, status, match_digest, series_id, series_game_index, received_at, result_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(match.result_id, submissionId, artifact.experiment_id, artifact.run_id, artifact.mode,
        match.ordinal, match.game, match.seed, match.player_count, match.status, matchDigest,
        match.series_id ?? null, match.series_game_index ?? null, receivedAt,
        JSON.stringify(match.result ?? {error: match.error ?? "unknown"})).run();
    if (match.status === "ok") {
      for (const ranking of (match.result as JsonRecord).rankings as JsonRecord[]) {
        const participant = participantForSeat(match, Number(ranking.seat));
        const player = participant.player as JsonRecord;
        await env.DB.prepare(`INSERT INTO match_rankings
          (result_id, participant_id, display_name, backend, model, seat, rank, ranking_json)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
          .bind(match.result_id, participant.participant_id, String(player.name ?? participant.participant_id),
            String(player.backend ?? "unknown"), player.model ? String(player.model) : null,
            ranking.seat, ranking.rank, JSON.stringify(ranking)).run();
      }
    }
    accepted += 1;
  }
  const stored = structuredClone(artifact) as JsonRecord;
  delete stored.submission;
  await env.DB.prepare(`INSERT INTO result_submissions
    (submission_id, experiment_id, run_id, submitter_id, content_digest, received_at,
     reported_matches, accepted_matches, artifact_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(submissionId, artifact.experiment_id, artifact.run_id, submitter, digest, receivedAt,
      artifact.matches.length, accepted, JSON.stringify(stored)).run();
  return json({ok: true, idempotent: false, submission_id: submissionId,
    accepted_matches: accepted, duplicate_matches: duplicates});
}

function getRating(map: Map<string, Rating>, row: RankingRow): Rating {
  let rating = map.get(row.participant_id);
  if (!rating) {
    rating = {participant_id: row.participant_id, display_name: row.display_name,
      backend: row.backend, model: row.model, rating: INITIAL_RATING, games: 0, wins: 0};
    map.set(row.participant_id, rating);
  }
  rating.display_name = row.display_name;
  rating.backend = row.backend;
  rating.model = row.model;
  return rating;
}

function updateRatings(map: Map<string, Rating>, rows: RankingRow[]): void {
  const before = new Map(rows.map(row => [row.participant_id, getRating(map, row).rating]));
  for (const row of rows) {
    const own = before.get(row.participant_id)!;
    let expected = 0;
    let actual = 0;
    for (const opponent of rows) {
      if (opponent.participant_id === row.participant_id) continue;
      expected += 1 / (1 + 10 ** ((before.get(opponent.participant_id)! - own) / 400));
      actual += row.rank < opponent.rank ? 1 : row.rank === opponent.rank ? 0.5 : 0;
    }
    const comparisons = rows.length - 1;
    const rating = getRating(map, row);
    rating.rating += K_FACTOR * (actual / comparisons - expected / comparisons);
    rating.games += 1;
    if (row.rank === 1) rating.wins += 1;
  }
}

async function leaderboard(env: ResultsEnv): Promise<Response> {
  await ensureSchema(env.DB);
  const query = await env.DB.prepare(`SELECT m.result_id, m.game, m.mode, m.received_at,
    r.participant_id, r.display_name, r.backend, r.model, r.seat, r.rank
    FROM benchmark_matches m JOIN match_rankings r ON r.result_id = m.result_id
    WHERE m.status = 'ok' ORDER BY m.received_at, m.run_id, m.ordinal, m.result_id, r.seat`).all<RankingRow>();
  const overall = new Map<string, Rating>();
  const byGame = new Map<string, Map<string, Rating>>();
  let currentId = "";
  let current: RankingRow[] = [];
  const flush = () => {
    if (!current.length) return;
    updateRatings(overall, current);
    const gameRatings = byGame.get(current[0].game) ?? new Map<string, Rating>();
    updateRatings(gameRatings, current);
    byGame.set(current[0].game, gameRatings);
  };
  for (const row of query.results) {
    if (currentId && row.result_id !== currentId) { flush(); current = []; }
    currentId = row.result_id;
    current.push(row);
  }
  flush();

  const stats = await env.DB.prepare(`SELECT
    (SELECT COUNT(*) FROM result_submissions) AS submissions,
    (SELECT COUNT(*) FROM benchmark_matches) AS matches,
    (SELECT COUNT(*) FROM benchmark_matches WHERE status = 'ok') AS rated_matches`)
    .first<{submissions: number; matches: number; rated_matches: number}>();
  const recent = await env.DB.prepare(`SELECT submission_id, experiment_id, run_id,
    submitter_id, received_at, reported_matches, accepted_matches
    FROM result_submissions ORDER BY received_at DESC LIMIT 8`).all();
  const entries = [...overall.values()].sort((a, b) => b.rating - a.rating).map((entry, index) => ({
    position: index + 1,
    ...entry,
    rating: Math.round(entry.rating * 10) / 10,
    win_rate: entry.games ? Math.round(entry.wins / entry.games * 1000) / 10 : 0,
    games_by_title: Object.fromEntries([...byGame.entries()].flatMap(([game, ratings]) => {
      const value = ratings.get(entry.participant_id);
      return value ? [[game, {rating: Math.round(value.rating * 10) / 10,
        games: value.games, wins: value.wins}]] : [];
    })),
  }));
  return json({
    generated_at: new Date().toISOString(),
    methodology: {name: "normalized multiplayer Elo", initial_rating: INITIAL_RATING,
      k_factor: K_FACTOR, note: "Each 2–4 player result is decomposed into normalized pairwise outcomes."},
    summary: stats ?? {submissions: 0, matches: 0, rated_matches: 0},
    entries,
    recent_submissions: recent.results,
  });
}

export async function handleResultsApi(request: Request, env: ResultsEnv): Promise<Response | null> {
  const {pathname} = new URL(request.url);
  if (pathname === "/api/results/leaderboard" && request.method === "GET") return leaderboard(env);
  if (pathname === "/api/results/submissions" && request.method === "POST") return submitResults(request, env);
  if (pathname.startsWith("/api/results/")) return json({error: "not found"}, 404);
  return null;
}
