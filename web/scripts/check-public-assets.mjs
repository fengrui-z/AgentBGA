import { lstat } from "node:fs/promises";

// Vite copies public assets even when no page links to them.
try {
  await lstat(new URL("../public/results", import.meta.url));
} catch (error) {
  if (error.code === "ENOENT") process.exit(0);
  throw error;
}

throw new Error(
  "Benchmark results are withheld from this site. Move web/public/results " +
  "to a private location outside web/public before building.",
);
