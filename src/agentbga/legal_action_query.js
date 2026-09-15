// Pi's native tool uses the same seat-local metadata and query contract as Python.
function filteredLegal(value, args) {
  const metadata = value.legal_action_query, actions = value.legal_actions || [];
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  if (!object(args)) throw new Error("legal_actions arguments must be an object");
  const fields = metadata.fields, filters = args.filters ?? {};
  if (args.filters === null || !object(filters)) throw new Error("filters must be an object");
  const schema = __LEGAL_QUERY_SCHEMA__;
  for (const key of Object.keys(args)) {
    if (!(key in schema.properties)) throw new Error(`unknown legal_actions argument: ${key}`);
  }
  function validate(key, v, spec) {
    if (spec.type === "integer") {
      if (!Number.isInteger(v) || v < (spec.minimum ?? 0) || v > (spec.maximum ?? v))
        throw new Error(`${key} must be an integer in range`);
    } else if (typeof v !== "string" || !v) throw new Error(`${key} must be a non-empty string`);
    if (spec.enum && !spec.enum.includes(v)) throw new Error(`invalid ${key}`);
  }
  for (const [key, v] of Object.entries(filters)) {
    if (!(key in fields)) throw new Error(`unsupported filter: ${key}`);
    validate(key, v, fields[key]);
  }
  for (const key of ["group", "cursor", "limit"]) {
    if (key in args) validate(key, args[key], schema.properties[key]);
  }
  const group = args.group, counts = {};
  for (const item of actions) counts[item.type] = (counts[item.type] || 0) + 1;
  if (group !== undefined && !(group in counts)) throw new Error("unknown group");
  if (group !== undefined && "type" in filters && filters.type !== group)
    throw new Error("group and filters.type must match");
  // Match Python's inner json.dumps spacing before measuring the complete MCP envelope.
  function textJson(x) {
    if (Array.isArray(x)) return "[" + x.map(textJson).join(", ") + "]";
    if (object(x)) return "{" + Object.entries(x).map(([k,v]) => JSON.stringify(k) + ": " + textJson(v)).join(", ") + "}";
    return JSON.stringify(x);
  }
  function bytes(x) {
    return Buffer.byteLength(JSON.stringify({content: [{type: "text", text: textJson(x)}],
      structuredContent: {data: x}, isError: false}), "utf8");
  }
  if (!Object.keys(args).length) {
    if (bytes(actions) <= 16000) return actions;
    return {state_version: value.version, mode: "groups", total: actions.length,
      groups: Object.keys(counts).sort().map(group => ({group, count: counts[group]})),
      available_filters: Object.keys(fields),
      instruction: "Call legal_actions with group or filters; follow next_cursor with the same query."};
  }
  const selected = actions.filter(item => {
    if (group !== undefined && item.type !== group) return false;
    const values = metadata.values[item.id];
    return Object.entries(filters).every(([key, v]) => key in values &&
      (key.startsWith("max_") ? values[key] <= v : values[key] === v));
  });
  const cursor = args.cursor ?? 0, limit = args.limit ?? 50;
  if (cursor > selected.length) throw new Error("cursor exceeds the filtered action count");
  const page = selected.slice(cursor, cursor + limit);
  const result = {state_version: value.version, mode: "actions", group: group ?? null,
    filters, total: selected.length, cursor, next_cursor: null, actions: page};
  while (true) {
    const next = cursor + page.length;
    result.next_cursor = next < selected.length ? next : null;
    if (bytes(result) <= 16000) return result;
    if (page.length <= 1) throw new Error("a single legal action exceeds the response byte budget");
    page.pop();
  }
}
