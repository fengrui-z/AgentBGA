type Counts = Record<string, number>;
type Action = {id: string; action: Record<string, unknown>};

export function counts(value: unknown): Counts {
  return (value ?? {}) as Counts;
}

export function tokenTotal(tokens: Counts) {
  return Object.values(tokens).reduce((sum, amount) => sum + amount, 0);
}

export function containsTokens(pool: Counts, selected: Counts) {
  return Object.entries(selected).every(([color, amount]) => amount >= 0 && amount <= (pool[color] ?? 0));
}

export function sameTokens(a: Counts, b: Counts) {
  return containsTokens(a, b) && containsTokens(b, a);
}

function reservationKey(item: Action) {
  return JSON.stringify([item.action.type, item.action.tier, item.action.card_id]);
}

// Collapse only the human presentation. Keep every original action and ID for
// resolving the final selection against the engine's complete legal action set.
export function reservationChoices(actions: Action[]) {
  return [...new Map(actions.map(item => [reservationKey(item), item])).values()];
}

export function selectionCandidates(actions: Action[], selection: "take" | Action, take: Counts) {
  return actions.filter(item => selection === "take"
    ? item.action.type === "take_tokens" && sameTokens(counts(item.action.take), take)
    : reservationKey(item) === reservationKey(selection));
}

export function resolveSelection(candidates: Action[], returned: Counts) {
  return candidates.find(item => sameTokens(counts(item.action.return), returned)) ?? null;
}

export function canAddToken(actions: Action[], field: "take" | "return", selected: Counts, color: string) {
  const next = {...selected, [color]: (selected[color] ?? 0) + 1};
  return actions.some(item => containsTokens(counts(item.action[field]), next));
}
