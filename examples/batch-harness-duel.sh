#!/usr/bin/env bash
# Run N harness-vs-harness matches with different seeds and collect results.
# Usage: ./batch-harness-duel.sh <players-config.json> <N> [extra run args...]
set -uo pipefail

CONFIG="${1:?players-config json required}"
N="${2:?number of matches required}"
shift 2 || true
EXTRA_ARGS=("$@")

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/.agentbga/duels/$(basename "$CONFIG" .json)"
mkdir -p "$OUT_DIR"

# Read DEEPSEEK_API_KEY from dsh credentials if not already exported
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  CRED="$HOME/.dsh/.credentials.yaml"
  if [ -f "$CRED" ]; then
    export DEEPSEEK_API_KEY="$(awk -F': *' '/^DEEPSEEK_API_KEY:/{print $2; exit}' "$CRED")"
  fi
fi
[ -z "${DEEPSEEK_API_KEY:-}" ] && { echo "DEEPSEEK_API_KEY not set" >&2; exit 1; }

echo "seed,seat0_backend,seat1_backend,winner,scores,duration_s,db,status" > "$OUT_DIR/results.csv"

for seed in $(seq 1 "$N"); do
  DB="$OUT_DIR/seed-${seed}.sqlite3"
  rm -f "$DB"
  LOG="$OUT_DIR/seed-${seed}.log"
  START=$(date +%s)

  echo "[seed $seed/$N] running..."
  cd "$ROOT"
  PYTHONPATH=src DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" python3 -m agentbga run \
    --players-config "$CONFIG" \
    --seed "$seed" \
    --max-turns 250 \
    --fallback fail \
    --db "$DB" \
    --jsonl > "$LOG" 2>&1
  CODE=$?
  DURATION=$(( $(date +%s) - START ))

  if [ $CODE -ne 0 ]; then
    echo "[seed $seed] FAILED (exit $CODE), tail log:"
    tail -3 "$LOG" >&2
    echo "$seed,?,?,?,fail,,$DURATION,$DB,error" >> "$OUT_DIR/results.csv"
    continue
  fi

  # Parse final result from the last JSONL line that has rankings
  RESULT=$(grep '"type":"rankings"' "$LOG" | tail -1)
  if [ -z "$RESULT" ]; then
    RESULT=$(tail -1 "$LOG")
  fi
  WINNER=$(echo "$RESULT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); r=d.get('data',{}).get('rankings',[]); print(r[0]['player'] if r else '?')" 2>/dev/null || echo "?")
  SCORES=$(echo "$RESULT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); r=d.get('data',{}).get('rankings',[]); print('|'.join(f\"{x['player']}:{x.get('score','?')}\" for x in r))" 2>/dev/null || echo "?")

  echo "[seed $seed] winner=$WINNER scores=$SCORES duration=${DURATION}s"
  echo "$seed,?,?,\"$WINNER\",\"$SCORES\",$DURATION,$DB,ok" >> "$OUT_DIR/results.csv"
done

echo ""
echo "=== Results CSV: $OUT_DIR/results.csv ==="
cat "$OUT_DIR/results.csv"
