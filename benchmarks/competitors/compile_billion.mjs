// Syntax-only TypeScript erasure. The upstream ranking source is never patched.
import { stripTypeScriptTypes } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const [sourceRoot, outputRoot, lockPath] = process.argv.slice(2);
if (!sourceRoot || !outputRoot || !lockPath) {
  throw new Error("usage: compile_billion.mjs SOURCE OUTPUT LOCK");
}
const lock = JSON.parse(await readFile(lockPath, "utf8"));
await mkdir(outputRoot, { recursive: true });
await writeFile(path.join(outputRoot, "package.json"), '{"type":"module"}\n');
for (const file of lock.files) {
  if (!file.path.endsWith(".ts")) continue;
  const source = await readFile(path.join(sourceRoot, file.path), "utf8");
  const output = stripTypeScriptTypes(source, {
    mode: "strip",
    sourceUrl: file.path,
  });
  const target = path.join(outputRoot, file.path.replace(/\.ts$/, ".js"));
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, output, "utf8");
}
