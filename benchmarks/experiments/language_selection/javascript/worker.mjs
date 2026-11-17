import {createInterface} from 'node:readline';
import {FUNCTIONS} from './kernels.mjs';

function invoke(name, args) {
  if (!Object.hasOwn(FUNCTIONS, name)) throw new TypeError(`Unknown kernel ${name}`);
  return FUNCTIONS[name](...args);
}

function execute(request) {
  if (request.op === 'identity') return {node: process.version, versions: process.versions, pid: process.pid};
  if (request.op === 'invoke') return invoke(request.name, request.args);
  if (request.op === 'batch') return request.cases.map(({name, args}) => invoke(name, args));
  if (request.op === 'bench') {
    const {name, args, iterations = 1000, samples = 9, warmup = 1000} = request;
    if (![iterations, samples, warmup].every(n => Number.isSafeInteger(n) && n >= 0) || iterations < 1 || samples < 1)
      throw new RangeError('Invalid benchmark loop counts');
    let last, sink = 0;
    for (let i = 0; i < warmup; i++) last = invoke(name, args);
    const timings_ns = [];
    for (let sample = 0; sample < samples; sample++) {
      const before = process.hrtime.bigint();
      for (let i = 0; i < iterations; i++) {
        last = invoke(name, args);
        sink += last.length;
      }
      timings_ns.push(Number(process.hrtime.bigint() - before));
    }
    return {timings_ns, iterations, samples, warmup, sink, last, memory: process.memoryUsage()};
  }
  throw new TypeError(`Unknown operation ${request.op}`);
}

for await (const line of createInterface({input: process.stdin, crlfDelay: Infinity})) {
  try { process.stdout.write(JSON.stringify({ok: true, result: execute(JSON.parse(line))}) + '\n'); }
  catch (error) { process.stdout.write(JSON.stringify({ok: false, error: {name: error.name, message: error.message}}) + '\n'); }
}
