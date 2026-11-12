/** Transport and supplied-page adaptation only; all search executes upstream. */
import { Database } from "bun:sqlite";
import { createInterface } from "node:readline";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { readFileSync, statSync } from "node:fs";

const [sourceRoot, databasePath] = process.argv.slice(2);
if (!sourceRoot || !databasePath) throw new Error("source root and DB path required");
const { SessionStore } = await import(pathToFileURL(join(sourceRoot, "src/services/sqlite/SessionStore.ts")).href);
const { SessionSearch } = await import(pathToFileURL(join(sourceRoot, "src/services/sqlite/SessionSearch.ts")).href);
let db: Database | undefined;
let store: any;
let search: any;
const pageIds = new Map<number, string>();

function fileBytes(path: string): number {
  try { return statSync(path).size; } catch (error: any) {
    if (error.code === "ENOENT") return 0;
    throw error;
  }
}
function resources() {
  let highWaterRss: number | null = null;
  try {
    const m = readFileSync("/proc/self/status", "utf8").match(/^VmHWM:\s+(\d+)\s+kB$/m);
    if (m) highWaterRss = Number(m[1]) * 1024;
  } catch { /* Linux-only measurement; absent means unknown. */ }
  return { rss_bytes: process.memoryUsage().rss, linux_high_water_rss_bytes: highWaterRss };
}
function storage() {
  const pages = db!.query("PRAGMA page_count").get() as {page_count:number};
  const size = db!.query("PRAGMA page_size").get() as {page_size:number};
  return {
    logical_database_bytes: pages.page_count * size.page_size,
    database_file_bytes: fileBytes(databasePath),
    wal_file_bytes: fileBytes(databasePath + "-wal"),
    shm_file_bytes: fileBytes(databasePath + "-shm")
  };
}
function initialize(documents: any[]) {
  if (db) throw new Error("already initialized");
  const begin = performance.now();
  db = new Database(databasePath);
  store = new SessionStore(db, {syncOpsEnabled: false});
  search = new SessionSearch(db);
  const schemaMs = performance.now() - begin;
  const fts = db.query("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('observations_fts','session_summaries_fts')").all();
  if (fts.length !== 2) throw new Error("native FTS tables not available");
  const started = performance.now();
  const session = db.prepare("INSERT INTO sdk_sessions (content_session_id,memory_session_id,project,user_prompt,started_at,started_at_epoch,status) VALUES (?,?,?,?,?,?,'completed')");
  const observation = db.prepare("INSERT INTO observations (memory_session_id,project,type,title,text,subtitle,narrative,facts,concepts,files_read,files_modified,created_at,created_at_epoch,discovery_tokens) VALUES (?,?,'discovery',?,?,NULL,NULL,'[]','[]','[]','[]',?,?,0)");
  db.transaction(() => {
    for (const doc of documents) {
      const epoch = Date.parse(doc.created_at);
      if (!Number.isFinite(epoch)) throw new Error("invalid source timestamp");
      const memoryId = "supplied-page:" + doc.id;
      session.run(memoryId, memoryId, doc.project, "", doc.created_at, epoch);
      const inserted = observation.run(memoryId, doc.project, doc.title, doc.text, doc.created_at, epoch);
      pageIds.set(Number(inserted.lastInsertRowid), doc.id);
    }
  })();
  const loadMs = performance.now() - started;
  const count = db.query("SELECT COUNT(*) AS n FROM observations").get() as {n:number};
  if (count.n !== documents.length || pageIds.size !== documents.length) throw new Error("page count mismatch");
  db.run("INSERT INTO observations_fts(observations_fts,rank) VALUES('integrity-check',1)");
  return {
    schema_initialization_ms: schemaMs, supplied_page_load_with_fts_ms: loadMs,
    supplied_pages: count.n, fts_integrity_check: true,
    sqlite_version: (db.query("SELECT sqlite_version() AS version").get() as any).version,
    ...storage(), ...resources()
  };
}

const input = createInterface({input: process.stdin, crlfDelay: Infinity});
for await (const line of input) {
  let request: any;
  try {
    request = JSON.parse(line);
    let result: any;
    if (request.op === "ping") {
      result = {bun_version: Bun.version, ...resources()};
    } else if (request.op === "init") {
      result = initialize(request.documents);
    } else if (request.op === "search") {
      if (!search) throw new Error("not initialized");
      const options: any = {limit: request.limit, orderBy: "relevance"};
      if (request.project !== null) options.project = request.project;
      const cpu = process.cpuUsage();
      const start = performance.now();
      const rows = search.searchObservations(request.query, options);
      const nativeMs = performance.now() - start;
      const used = process.cpuUsage(cpu);
      const ids = rows.map((row: any) => {
        const id = pageIds.get(row.id);
        if (!id) throw new Error("unmapped native observation");
        return id;
      });
      result = {hit_ids: ids, native_payload: rows, search_ms: nativeMs,
        native_cpu_user_us: used.user, native_cpu_system_us: used.system};
    } else if (request.op === "close") {
      if (db) {
        const before = storage();
        const started = performance.now();
        db.run("PRAGMA wal_checkpoint(TRUNCATE)");
        result = {before_checkpoint: before, checkpoint_ms: performance.now() - started,
          after_checkpoint: storage(), ...resources()};
        db.close();
        db = undefined;
      } else result = resources();
    } else throw new Error("unknown operation");
    process.stdout.write(JSON.stringify({id: request.id, result}) + "\n");
    if (request.op === "close") break;
  } catch (error: any) {
    process.stdout.write(JSON.stringify({id: request?.id, error: String(error?.stack ?? error)}) + "\n");
  }
}
if (db) db.close();
