// A transport shim around the actual, pinned billion-context kernel.
import readline from "node:readline";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { performance } from "node:perf_hooks";

const kernel = await import(
  pathToFileURL(path.join(process.argv[2], "kernel/src/search.js")).href
);
let allDocs = [];
let byProject = new Map();
for await (const line of readline.createInterface({ input: process.stdin })) {
  try {
    const request = JSON.parse(line);
    if (request.op === "init") {
      allDocs = [];
      byProject = new Map();
      for (const input of request.documents) {
        // Uniform role avoids inserting a relevance hint into shared-page runs.
        const doc = {
          kind: "message",
          role: "assistant",
          ref: input.id,
          text: input.text,
          title: input.title,
        };
        allDocs.push(doc);
        if (!byProject.has(input.project)) byProject.set(input.project, []);
        byProject.get(input.project).push(doc);
      }
      process.stdout.write(JSON.stringify({
        ok: true, documents: allDocs.length,
        default_algorithm: kernel.DEFAULT_ALGORITHM,
        algorithms: kernel.listSearchAlgorithms().map(a => a.name),
        node: process.version,
      }) + "\n");
    } else if (request.op === "search") {
      const docs = request.project == null
        ? allDocs
        : byProject.get(request.project) ?? [];
      const start = performance.now();
      const results = kernel.searchBlocks(docs, request.query, {
        limit: request.limit,
        previewLength: request.preview_chars,
      });
      const search_ms = performance.now() - start;
      process.stdout.write(JSON.stringify({ results, search_ms }) + "\n");
    } else if (request.op === "clear_cache") {
      kernel.clearDocFeatures();
      process.stdout.write(JSON.stringify({ ok: true }) + "\n");
    } else if (request.op === "close") {
      break;
    } else {
      throw new Error("unknown operation");
    }
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: String(error?.stack ?? error) }) + "\n");
  }
}
