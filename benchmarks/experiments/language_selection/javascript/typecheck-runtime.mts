/**
 * Type-erasure/runtime identity diagnostic, not a performance benchmark.
 *
 * Node strips the annotations in this .mts file. The explicitly stripped facade
 * below uses types only and re-exports the existing JavaScript functions without
 * wrappers. A static TypeScript type checker is deliberately not claimed here.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
import {stripTypeScriptTypes} from 'node:module';
import {fileURLToPath} from 'node:url';
import * as kernels from './kernels.mjs';

type Probe = {name: keyof typeof kernels.FUNCTIONS; args: unknown[]};
const kernelUrl: string = new URL('./kernels.mjs', import.meta.url).href;
const typedSource: string = [
  'import * as kernels from ' + JSON.stringify(kernelUrl) + ';',
  'type FunctionName = keyof typeof kernels.FUNCTIONS;',
  'interface TypeOnlyMarker { readonly purpose: "compile-time-only"; }',
  'type KernelFacade = { readonly [Name in FunctionName]: (typeof kernels.FUNCTIONS)[Name] };',
  'export const typedKernels: KernelFacade = kernels.FUNCTIONS;',
].join('\n') + '\n';
const stripped: string = stripTypeScriptTypes(typedSource, {
  mode: 'strip', sourceUrl: 'language-selection-type-facade.mts',
});
assert.ok(!stripped.includes('interface TypeOnlyMarker'));
assert.ok(!stripped.includes('type KernelFacade'));
assert.ok(!stripped.includes(': KernelFacade'));

const loaded = await import('data:text/javascript;base64,' + Buffer.from(stripped).toString('base64'));
assert.deepEqual(Object.keys(loaded), ['typedKernels']);
assert.strictEqual(loaded.typedKernels, kernels.FUNCTIONS);
const names: string[] = Object.keys(kernels.FUNCTIONS).sort();
for (const name of names) {
  assert.strictEqual(loaded.typedKernels[name], kernels.FUNCTIONS[name]);
}

const text: string = 'A cache sentence.\nA second cache sentence.\n';
const terms: string[] = ['cache'];
const hits = kernels.literal_positions(text, terms);
const probes: Probe[] = [
  {name: 'terms_ascii', args: ['HTTPParser retryCount_17 of', true, ['of']]},
  {name: 'ascii_tokens', args: ['cache_17 values', false, []]},
  {name: 'unicode_tokens', args: ['Café 中文🙂 cache', true, [], []]},
  {name: 'literal_positions', args: ['A中🙂B中🙂', ['中🙂', '🙂']]},
  {name: 'evidence_units', args: [text, 24]},
  {name: 'context_allocations', args: [[{
    id: 'page🙂', project_id: 'project', session_id: 'session',
    created_at: '2026-11-17T00:00:00Z', content: text,
  }], 2400]},
  {name: 'positive_fsum', args: [[1e-16, 1.0, 1e-16]]},
  {name: 'log1p_values', args: [[1, 2, 5, 40]]},
  {name: 'excerpt_window', args: [text, terms, hits, 24]},
  {name: 'excerpt_selection', args: [text, text, terms, null, 24]},
  {name: 'fold_table', args: ['Straße cafe\u0301 中文🙂']},
  {name: 'fold_table', args: [{$codepoints: [65, 0xd800, 0xdc00, 0x1f642]}]},
  {name: 'unicode_identity', args: []},
];
const results = [];
for (const {name, args} of probes) {
  const direct = kernels.FUNCTIONS[name](...structuredClone(args));
  const typed = loaded.typedKernels[name](...structuredClone(args));
  assert.deepEqual(typed, direct);
  results.push({name, equal: true});
}
const sha = (value: string | Uint8Array): string => createHash('sha256').update(value).digest('hex');
const report = {
  status: 'passed',
  kind: 'typescript-type-erasure-runtime-identity-not-performance',
  node: process.version,
  source_sha256: sha(readFileSync(fileURLToPath(import.meta.url))),
  kernel_sha256: sha(readFileSync(new URL('./kernels.mjs', import.meta.url))),
  typed_facade_sha256: sha(typedSource),
  stripped_javascript_sha256: sha(stripped),
  function_identities_equal: names,
  namespace_identity_equal: true,
  type_only_declarations_absent_after_erasure: true,
  input_probes: results,
  static_type_check_performed: false,
  timings_collected: false,
  scope: 'This types-only facade executes the same 12 JavaScript function objects. '
    + 'It does not establish equal performance for arbitrary TypeScript and JavaScript programs, '
    + 'nor measure a complete Node application.',
};
const outputIndex: number = process.argv.indexOf('--output');
if (outputIndex >= 0) {
  const destination: string | undefined = process.argv[outputIndex + 1];
  assert.ok(destination, '--output requires a file');
  mkdirSync(dirname(destination), {recursive: true});
  writeFileSync(destination, JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify(report));
