type VersionedMatch = {match_id: string; version: number; event_seq?: number};

/** HTTP replies and SSE events can arrive out of order for the same match. */
export function mergeMatchSnapshot<T extends VersionedMatch>(current: T | null, incoming: T): T | null {
  if (!current || current.match_id !== incoming.match_id || incoming.version < current.version) return current;
  if (incoming.version === current.version && incoming.event_seq !== undefined &&
      current.event_seq !== undefined && incoming.event_seq < current.event_seq) return current;
  return incoming;
}
