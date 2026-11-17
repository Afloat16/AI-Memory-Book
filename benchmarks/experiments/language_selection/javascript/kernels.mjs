/** Isolated JavaScript candidates. No production module imports this file.
 *
 * Strings arriving as {$codepoints: [...]} contain literal Python surrogate
 * code points and must never be collapsed into JavaScript surrogate pairs.
 */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const properties = JSON.parse(readFileSync(new URL('./unicode-properties.json', import.meta.url), 'utf8'));
const alnum = new Uint8Array(0x110000);
for (const [lo, hi] of properties.ranges) alnum.fill(1, lo, hi);
const foldBytes = readFileSync(new URL('../rust/data/unicode_fold.bin', import.meta.url));
const foldMetadata = JSON.parse(readFileSync(new URL('../rust/data/unicode_fold.meta.json', import.meta.url), 'utf8'));
if (foldBytes.subarray(0, 8).toString('ascii') !== 'MBFOLD01') throw new Error('Unexpected fold table magic');
if (createHash('sha256').update(foldBytes).digest('hex') !== foldMetadata.sha256) throw new Error('Fold table hash differs');
const foldView = new DataView(foldBytes.buffer, foldBytes.byteOffset, foldBytes.byteLength);
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const tagged = value => value !== null && typeof value === 'object' && own(value, '$codepoints');
const points = value => tagged(value) ? value.$codepoints : Array.from(value, c => c.codePointAt(0));
function cpLength(value) {
  if (tagged(value)) return value.$codepoints.length;
  let size = value.length;
  for (let i = 0; i < value.length; i++) {
    const c = value.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < value.length) {
      const next = value.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) { size--; i++; }
    }
  }
  return size;
}
const isLower = c => c >= 97 && c <= 122;
const isUpper = c => c >= 65 && c <= 90;
const isDigit = c => c >= 48 && c <= 57;

function packPoints(cps) {
  if (cps.some(c => c >= 0xd800 && c <= 0xdfff)) return {$codepoints: cps};
  // Keep arguments bounded for long input strings.
  let value = '';
  for (let i = 0; i < cps.length; i += 8192) value += String.fromCodePoint(...cps.slice(i, i + 8192));
  return value;
}

function concat(...values) {
  return values.some(tagged) ? packPoints(values.flatMap(points)) : values.join('');
}

function ascii(text, query, stopValues, original) {
  if (typeof text !== 'string' || /[^\x00-\x7f]/.test(text)) throw new TypeError('ASCII string required');
  const stop = query ? new Set(stopValues) : null;
  const result = [];
  let start = -1;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    const word = isLower(c) || isDigit(c) || (original && isUpper(c));
    const boundary = original && i > 0 && isLower(text.charCodeAt(i - 1)) && isUpper(c);
    if (start >= 0 && (!word || boundary)) {
      let token = text.slice(start, i);
      if (original) token = token.toLowerCase();
      if (!query || !stop.has(token)) result.push(token);
      start = -1;
    }
    if (word && start < 0) start = i;
  }
  if (start >= 0) {
    let token = text.slice(start);
    if (original) token = token.toLowerCase();
    if (!query || !stop.has(token)) result.push(token);
  }
  return result;
}

export const terms_ascii = (text, query, stop) => ascii(text, query, stop, true);
export const ascii_tokens = (text, query, stop) => ascii(text, query, stop, false);

const cjk = c => (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x4e00 && c <= 0x9fff) || (c >= 0xf900 && c <= 0xfaff);
export function unicode_tokens(text, query, stopValues, zhStopValues) {
  const source = points(text), result = [];
  const stop = query ? new Set(stopValues) : null;
  const zhStop = query ? new Set(zhStopValues) : null;
  function append(lo, hi, stops) {
    const token = packPoints(source.slice(lo, hi));
    if (!query || !stops.has(token)) result.push(token);
  }
  let cursor = 0;
  while (cursor < source.length) {
    const start = cursor, cp = source[cursor];
    if (cjk(cp)) {
      while (++cursor < source.length && cjk(source[cursor])) {}
      if (cursor - start === 1) append(start, cursor, zhStop);
      else for (let i = start; i < cursor - 1; i++) append(i, i + 2, zhStop);
    } else if (alnum[cp]) {
      while (++cursor < source.length && alnum[source[cursor]] && !cjk(source[cursor])) {}
      append(start, cursor, stop);
    } else cursor++;
  }
  return result;
}

function foldEntry(cp) {
  const page = foldView.getUint16(64 + (cp >>> 8) * 2, true);
  return page === 0xffff ? 0xffffffff : foldView.getUint32(foldMetadata.entries_offset +
    (page * 256 + (cp & 255)) * 4, true);
}

/** Same immutable Unicode table and two-pass output allocation as C/Rust.
 * This is the separately labeled larger-boundary candidate, not a direct
 * translation of the current per-character Python callback implementation.
 */
export function fold_table(text) {
  const source = points(text);
  let size = 0;
  for (const cp of source) {
    const entry = foldEntry(cp);
    size += entry === 0xffffffff ? 1 : entry >>> 24;
  }
  const output = new Array(size), positions = new Array(size);
  let written = 0;
  for (let index = 0; index < source.length; index++) {
    const cp = source[index], entry = foldEntry(cp);
    if (entry === 0xffffffff) {
      output[written] = cp;
      positions[written++] = index;
    } else {
      const count = entry >>> 24, offset = entry & 0xffffff;
      for (let unit = 0; unit < count; unit++) {
        output[written] = foldView.getUint32(foldMetadata.values_offset + (offset + unit) * 4, true);
        positions[written++] = index;
      }
    }
  }
  return [packPoints(output), positions];
}

export function unicode_identity() {
  return {properties_unicode_version: properties.unicode_version, fold_unicode_version: foldMetadata.unicode_version,
    fold_sha256: foldMetadata.sha256};
}

function findPoints(haystack, needle, start) {
  if (!needle.length) return start <= haystack.length ? start : -1;
  outer: for (let i = start; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) if (haystack[i + j] !== needle[j]) continue outer;
    return i;
  }
  return -1;
}

/** Return term indexes, not copies of terms, to retain Python object identity.
 * Mapping application stays in the Python adapter so arbitrary Python mapping
 * values (including huge integers and object instances) are never serialized.
 */
export function literal_positions(lower, terms) {
  const result = [];
  if (tagged(lower) || terms.some(tagged)) {
    const source = points(lower);
    for (let termId = 0; termId < terms.length; termId++) {
      const needle = points(terms[termId]);
      let cursor = 0;
      for (let count = 0; count < 40; count++) {
        const found = findPoints(source, needle, cursor);
        if (found < 0) break;
        result.push([found, termId]);
        if (!needle.length && found === source.length) break;
        cursor = found + Math.max(1, needle.length);
      }
    }
    return result;
  }
  // Native substring search, with an explicit code-unit to code-point map.
  // Normal scalar strings cannot contain a match beginning inside a surrogate
  // pair unless the needle itself contains a surrogate, handled above.
  const sourceOffsets = new Int32Array(lower.length + 1);
  let codePoint = 0;
  for (let i = 0; i < lower.length;) {
    sourceOffsets[i] = codePoint++;
    i += lower.codePointAt(i) > 0xffff ? 2 : 1;
  }
  sourceOffsets[lower.length] = codePoint;
  for (let termId = 0; termId < terms.length; termId++) {
    const needle = terms[termId];
    let cursor = 0;
    for (let count = 0; count < 40; count++) {
      const found = lower.indexOf(needle, cursor);
      if (found < 0) break;
      result.push([sourceOffsets[found], termId]);
      if (!needle.length) {
        if (found === lower.length) break;
        cursor = found + (lower.codePointAt(found) > 0xffff ? 2 : 1);
      } else cursor = found + needle.length;
    }
  }
  return result;
}

// CPython str.isspace(), Unicode 15.0.0 (Python 3.12 in the frozen run).
// Explicit values also preserve Python's C0 separators missing from JS /\s/.
const whitespace = new Set([9,10,11,12,13,28,29,30,31,32,133,160,5760,
  8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288]);

function evidenceUnitsPoints(source, width) {
  const units = [];
  let lo = 0;
  while (lo < source.length) {
    if (source[lo] === 10) { lo++; continue; }
    let hi = lo;
    while (hi < source.length && source[hi] !== 10) hi++;
    if (hi - lo <= width) units.push([lo, hi]);
    else {
      let start = lo;
      for (let i = lo; i < hi; i++) {
        const c = source[i];
        const boundary = c === 0x3002 || c === 0xff01 || c === 0xff1f ||
          ((c === 46 || c === 33 || c === 63) && (i + 1 === hi || whitespace.has(source[i + 1])));
        if (!boundary) continue;
        const end = i + 1;
        if (end - start <= width) units.push([start, end]);
        start = end;
        while (start < hi && whitespace.has(source[start])) start++;
      }
      if (start < hi && hi - start <= width) units.push([start, hi]);
    }
    lo = hi + 1;
  }
  return units;
}

export function evidence_units(text, width) {
  return evidenceUnitsPoints(points(text), width);
}

function codePointCompare(left, right) {
  const a = points(left), b = points(right);
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

function bisect(values, needle, field, right) {
  let lo = 0, hi = values.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    const value = values[mid][field];
    if (value < needle || (right && value === needle)) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function popcount(value) {
  value -= (value >>> 1) & 0x55555555;
  value = (value & 0x33333333) + ((value >>> 2) & 0x33333333);
  return (((value + (value >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

/** Error-free partial summation, with CPython's final half-even correction.
 * This candidate only accepts finite positive log1p frequency values.
 */
export function positive_fsum(values) {
  const partials = [];
  for (let x of values) {
    let i = 0;
    for (let j = 0; j < partials.length; j++) {
      let y = partials[j];
      if (Math.abs(x) < Math.abs(y)) [x, y] = [y, x];
      const hi = x + y;
      const lo = y - (hi - x);
      if (lo !== 0) partials[i++] = lo;
      x = hi;
    }
    partials.length = i;
    if (x !== 0) partials.push(x);
  }
  let hi = 0, lo = 0;
  if (partials.length) hi = partials.pop();
  while (partials.length) {
    const x = hi, y = partials.pop();
    hi = x + y;
    lo = y - (hi - x);
    if (lo !== 0) break;
  }
  if (partials.length && ((lo < 0 && partials[partials.length - 1] < 0) ||
      (lo > 0 && partials[partials.length - 1] > 0))) {
    const y = lo * 2, x = hi + y;
    if (x - hi === y) hi = x;
  }
  return hi;
}

function greater(left, right) {
  for (let i = 0; i < left.length; i++) {
    if (left[i] > right[i]) return true;
    if (left[i] < right[i]) return false;
  }
  return false;
}

/** Complete source-window selection on an ordinary query (unique <=64 terms,
 * <=40 hits per term). Hits are [source_codepoint_offset, query_term_index].
 * A deployment would first verify Math.log1p(1..40) against the reference libm.
 */
export function excerpt_window(text, q, positions, width) {
  const source = points(text), length = source.length;
  if (new Set(q.map(value => points(value).join(','))).size !== q.length)
    throw new RangeError('excerpt_window requires unique query terms');
  if (!Number.isSafeInteger(width) || width <= 0 || width >= length || q.length > 64 ||
      positions.length > 2560 || length * positions.length > Number.MAX_SAFE_INTEGER)
    throw new RangeError('excerpt_window outside verified ordinary-query domain');
  const countsPerTerm = new Array(q.length).fill(0);
  for (const [position, term] of positions) {
    if (!Number.isSafeInteger(position) || position < 0 || position > length ||
        !Number.isSafeInteger(term) || term < 0 || term >= q.length || ++countsPerTerm[term] > 40)
      throw new RangeError('excerpt hits outside verified ordinary-query domain');
  }
  const lastStart = length - width;
  const hits = positions.slice().sort((a, b) => a[0] - b[0] || codePointCompare(q[a[1]], q[b[1]]));
  const starts = new Set([0, lastStart]);
  for (const [position] of hits) starts.add(Math.max(0, Math.min(lastStart, position - Math.floor(width / 3))));
  const units = hits.length ? evidenceUnitsPoints(source, width) : [];
  const masks = new Map();
  for (const [position, term] of hits) {
    const index = bisect(units, position, 0, true) - 1;
    if (index >= 0 && position < units[index][1]) {
      const mask = masks.get(index) ?? [0, 0];
      if (term < 32) mask[0] |= 1 << term;
      else mask[1] |= 1 << (term - 32);
      masks.set(index, mask);
    }
  }
  const matched = [...masks.entries()].sort((a,b) => a[0] - b[0])
    .map(([index, mask]) => [units[index][0], units[index][1], mask[0], mask[1]]);
  for (const [lo, hi] of matched) {
    starts.add(Math.min(lo, lastStart));
    starts.add(Math.max(0, hi - width));
  }
  let bestStart = 0, bestScore = [-1, -1, -1, -1, -1];
  let left = 0, right = 0, positionSum = 0;
  const inside = new Map();
  for (const start of [...starts].sort((a,b) => a - b)) {
    while (right < hits.length && hits[right][0] < start + width) {
      const [position, term] = hits[right++];
      inside.set(term, (inside.get(term) ?? 0) + 1);
      positionSum += position;
    }
    while (left < right && hits[left][0] < start) {
      const [position, term] = hits[left++];
      const remaining = inside.get(term) - 1;
      if (remaining === 0) inside.delete(term);
      else inside.set(term, remaining);
      positionSum -= position;
    }
    let wholeLow = 0, wholeHigh = 0;
    const firstUnit = bisect(matched, start, 0, false);
    const lastUnit = bisect(matched, start + width, 1, true);
    for (let i = firstUnit; i < lastUnit; i++) {
      wholeLow |= matched[i][2];
      wholeHigh |= matched[i][3];
    }
    const count = right - left;
    const placement = count ? Math.abs((positionSum / count - start) / width - 1 / 3) : 1;
    const frequency = positive_fsum([...inside.values()].map(n => Math.log1p(n)));
    const score = [inside.size, popcount(wholeLow) + popcount(wholeHigh), frequency, -placement, -start];
    if (greater(score, bestScore)) { bestStart = start; bestScore = score; }
  }
  const end = Math.min(length, bestStart + width);
  const content = packPoints(source.slice(bestStart, end));
  return [concat(bestStart ? '…' : '', content, end < length ? '…' : ''), [[bestStart, end]]];
}

/** Coarser boundary: literal positions + evidence/window selection/rendering.
 * Normalization and query preparation stay identical and are outside this stage.
 */
export function excerpt_selection(text, lower, q, sourcePositions, width) {
  const hits = literal_positions(lower, q);
  if (sourcePositions !== null) {
    for (const hit of hits) {
      if (hit[0] >= sourcePositions.length) throw new RangeError('source map index');
      hit[0] = sourcePositions[hit[0]];
    }
  }
  return excerpt_window(text, q, hits, width);
}

/** Entire existing character-budget allocation stage, including headers.
 * Result indexes let Python retain the original page dictionaries.
 */
export function context_allocations(pages, budget) {
  if (!Number.isSafeInteger(budget) || budget < 0) throw new RangeError('budget outside safe integer range');
  let minimum = 0, overhead = 0;
  const selected = [];
  for (let index = 0; index < pages.length; index++) {
    const row = pages[index];
    const header = concat('[', row.id, '] ', row.project_id, ' / ', row.session_id, ' | ', row.created_at, '\n');
    const citation = cpLength(header) + (selected.length ? 2 : 0);
    const length = cpLength(row.content);
    const reserve = Math.min(length, 120);
    const fits = citation <= budget - minimum && reserve <= budget - minimum - citation;
    if (fits || (!selected.length && budget > citation + 8)) {
      selected.push({index, header, length});
      overhead += citation;
      if (fits) minimum += citation + reserve;
    }
    if (!fits) break;
  }
  const order = selected.map((row, index) => ({index, length: row.length}));
  order.sort((a, b) => a.length - b.length || a.index - b.index);
  const allowances = new Array(selected.length);
  let remaining = budget - overhead;
  for (let i = 0; i < order.length; i++) {
    const allowance = Math.min(order[i].length, Math.floor(remaining / (order.length - i)));
    allowances[order[i].index] = allowance;
    remaining -= allowance;
  }
  return selected.map((row, i) => [row.index, row.header, allowances[i]]);
}

export const log1p_values = values => values.map(value => Math.log1p(value));
export const FUNCTIONS = {terms_ascii, ascii_tokens, unicode_tokens, literal_positions, evidence_units,
  context_allocations, positive_fsum, log1p_values, excerpt_window, excerpt_selection, fold_table, unicode_identity};
