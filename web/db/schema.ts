export const RESULTS_SCHEMA_STATEMENTS = [
`CREATE TABLE IF NOT EXISTS result_submissions (
  submission_id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  submitter_id TEXT NOT NULL,
  content_digest TEXT NOT NULL UNIQUE,
  received_at TEXT NOT NULL,
  reported_matches INTEGER NOT NULL,
  accepted_matches INTEGER NOT NULL,
  artifact_json TEXT NOT NULL
)`,
`CREATE TABLE IF NOT EXISTS benchmark_matches (
  result_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  experiment_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  game TEXT NOT NULL,
  seed INTEGER NOT NULL,
  player_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  match_digest TEXT NOT NULL,
  series_id TEXT,
  series_game_index INTEGER,
  received_at TEXT NOT NULL,
  result_json TEXT NOT NULL
)`,
`CREATE TABLE IF NOT EXISTS match_rankings (
  result_id TEXT NOT NULL,
  participant_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  backend TEXT NOT NULL,
  model TEXT,
  seat INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  ranking_json TEXT NOT NULL,
  PRIMARY KEY (result_id, participant_id),
  FOREIGN KEY (result_id) REFERENCES benchmark_matches(result_id) ON DELETE CASCADE
)`,
`CREATE INDEX IF NOT EXISTS idx_benchmark_matches_order
  ON benchmark_matches(received_at, result_id)`,
`CREATE INDEX IF NOT EXISTS idx_benchmark_matches_game
  ON benchmark_matches(game, received_at)`,
`CREATE INDEX IF NOT EXISTS idx_match_rankings_participant
  ON match_rankings(participant_id, result_id)`,
] as const;
