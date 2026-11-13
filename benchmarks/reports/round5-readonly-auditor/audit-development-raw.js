/**
 * Read-only independent arithmetic and identity audit.
 * Inputs are exact Git raw strings supplied by the caller; this module performs
 * no retrieval, benchmark, file/network access, source execution or mutation.
 * sha256 must hash UTF-8 strings. Numerical tolerance is 1e-10, relative or absolute.
 */
function auditDevelopmentRaw({oldRaw, summaryRaw, workerRaw, identity}, sha256) {
  const fail = (message) => { throw new Error(message); };
  const equal = (actual, expected, label) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) fail(label);
  };
  const near = (actual, expected, label) => {
    if (!Number.isFinite(actual) || !Number.isFinite(expected) ||
        Math.abs(actual - expected) > 1e-10 * Math.max(1, Math.abs(expected))) fail(label);
  };
  if (sha256(oldRaw) !== "02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5")
    fail("Original immutable schedule changed");
  const old = JSON.parse(oldRaw), summary = JSON.parse(summaryRaw);
  const cohorts = ["synthetic61", "public1015"];
  const configs = ["native-char4000", "native-token512", "native-token1024", "native-token2048"];
  const expectedOrder = cohorts.flatMap(c => [
    c + "-r0-baseline", c + "-r0-candidate", c + "-r1-candidate", c + "-r1-baseline"]);
  equal(summary.workers.map(w => w.id), expectedOrder, "Worker sequence changed");
  equal(Object.keys(workerRaw).sort(), expectedOrder.slice().sort(), "Raw worker inventory changed");
  if (summary.status !== "completed" || summary.attempt !== identity.attempt ||
      summary.calls !== 4096 || summary.complete_payload_pairs !== 2048 ||
      summary.formal_acceptance !== false || summary.fresh_rows_decoded !== 0 ||
      summary.audit_retrieval_calls !== 0 || summary.cells.length !== 8)
    fail("Summary boundary changed");
  equal(old.baseline.commit, identity.baseline_commit, "Baseline commit");
  equal(old.baseline.runtime_sha256, identity.baseline_runtime_sha256, "Baseline runtime");
  const parsed = {}, hashes = [];
  let observations = 0;
  for (let index = 0; index < expectedOrder.length; index++) {
    const id = expectedOrder[index], record = summary.workers[index], raw = workerRaw[id];
    const w = JSON.parse(raw), checksum = sha256(raw);
    const match = /^(synthetic61|public1015)-r([01])-(baseline|candidate)$/.exec(id);
    const cohort = match[1], round = Number(match[2]), label = match[3];
    if (record.sha256 !== checksum || record.calls !== 512 ||
        record.path !== "benchmarks/reports/" + identity.attempt + "/" + id + ".json")
      fail("Raw worker receipt: " + id);
    if (w.status !== "completed" || w.label !== label || w.cohort !== cohort || w.round !== round ||
        w.runtime_source_sha256 !== identity[label + "_runtime_sha256"] ||
        w.dataset_sha256 !== old.cohorts[cohort].dataset_sha256)
      fail("Raw source/data/worker identity: " + id);
    equal(w.cells.map(c => c.configuration), configs, "Configuration order: " + id);
    for (const cell of w.cells) {
      const ids = cell.rows.map(row => row.query_id);
      if (ids.length !== 128 || new Set(ids).size !== 128 ||
          ids.some(q => typeof q !== "string")) fail("Unique complete query IDs: " + id);
      equal(ids.slice().sort(), old.cohorts[cohort].paired_selected_query_ids.slice().sort(),
            "Frozen query selection: " + id);
      const order = old.cohorts[cohort].paired_orders.filter(
        v => v.round === round && v.configuration === cell.configuration);
      if (order.length !== 1 || sha256(JSON.stringify(ids)) !== order[0].query_ids_sha256)
        fail("Immutable premeasurement query order: " + id + "/" + cell.configuration);
      for (const row of cell.rows) {
        if (typeof row.wall_ms !== "number" || !Number.isFinite(row.wall_ms) || row.wall_ms < 0 ||
            typeof row.payload_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(row.payload_sha256))
          fail("Timing or full payload digest: " + id);
        observations++;
      }
    }
    parsed[id] = w;
    hashes.push({path: record.path, sha256: checksum});
  }
  function stats(values) {
    const sorted = values.slice().sort((a,b) => a-b);
    const quantile = p => {
      const at = (sorted.length - 1) * p, lo = Math.floor(at), hi = Math.ceil(at);
      return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo);
    };
    let sum = 0, correction = 0;
    for (const value of values) {
      const adjusted = value - correction, next = sum + adjusted;
      correction = (next - sum) - adjusted;
      sum = next;
    }
    return {samples: values.length, p50: quantile(.5), p95: quantile(.95), mean: sum / values.length};
  }
  function verifyStats(actual, expected, label) {
    if (actual.samples !== expected.samples) fail("Sample count: " + label);
    for (const key of ["p50", "p95", "mean"]) near(actual[key], expected[key], label + "/" + key);
  }
  const cells = [], mismatches = [];
  let pairs = 0;
  for (const cohort of cohorts) for (let ci = 0; ci < configs.length; ci++) {
    const configuration = configs[ci], pooled = {baseline: [], candidate: []}, rounds = [];
    const saved = summary.cells[cells.length];
    if (saved.cohort !== cohort || saved.configuration !== configuration || saved.rounds.length !== 2)
      fail("Summary cell order");
    for (let round = 0; round < 2; round++) {
      const a = parsed[cohort + "-r" + round + "-baseline"].cells[ci].rows;
      const b = parsed[cohort + "-r" + round + "-candidate"].cells[ci].rows;
      for (let i = 0; i < 128; i++) {
        equal(a[i].query_id, b[i].query_id, "Pair query");
        if (a[i].payload_sha256 !== b[i].payload_sha256)
          mismatches.push({cohort, round, configuration, query_id: a[i].query_id,
                          baseline: a[i].payload_sha256, candidate: b[i].payload_sha256});
        pairs++;
      }
      const data = {baseline: a.map(r => r.wall_ms), candidate: b.map(r => r.wall_ms)};
      const result = {round, baseline: stats(data.baseline), candidate: stats(data.candidate)};
      if (saved.rounds[round].round !== round) fail("Summary round order");
      for (const label of ["baseline", "candidate"]) {
        pooled[label].push(...data[label]);
        verifyStats(result[label], saved.rounds[round][label], cohort + "/" + configuration + "/" + round);
      }
      for (const metric of ["p50", "p95"]) {
        if (result.baseline[metric] <= 0) fail("Zero comparison denominator");
        result[metric + "_change_percent"] = (result.candidate[metric] / result.baseline[metric] - 1) * 100;
        near(result[metric + "_change_percent"], saved.rounds[round][metric + "_change_percent"], "Round change");
      }
      rounds.push(result);
    }
    const result = {cohort, configuration, baseline: stats(pooled.baseline),
                    candidate: stats(pooled.candidate), rounds};
    for (const label of ["baseline", "candidate"]) verifyStats(result[label], saved[label], "Pooled summary");
    for (const metric of ["p50", "p95"]) {
      if (result.baseline[metric] <= 0) fail("Zero pooled denominator");
      result[metric + "_change_percent"] = (result.candidate[metric] / result.baseline[metric] - 1) * 100;
      near(result[metric + "_change_percent"], saved[metric + "_change_percent"], "Pooled change");
    }
    cells.push(result);
  }
  const gm = (1 - Math.exp(cells.reduce((s,c) =>
    s + Math.log(c.candidate.p95 / c.baseline.p95), 0) / cells.length)) * 100;
  near(gm, summary.pooled_p95_geomean_improvement_percent, "P95 geometric mean");
  equal(mismatches, summary.mismatches, "Complete mismatches");
  if (summary.all_payloads_equal !== (mismatches.length === 0)) fail("Parity summary");
  const adverse = cells.filter(c => c.p50_change_percent > 5 || c.p95_change_percent > 5);
  equal(adverse.map(c => [c.cohort,c.configuration]),
        summary.adverse_cells_over_five_percent.map(c => [c.cohort,c.configuration]), "All adverse cells");
  for (let i = 0; i < adverse.length; i++) for (const metric of ["p50", "p95"])
    near(adverse[i][metric + "_change_percent"],
         summary.adverse_cells_over_five_percent[i][metric + "_change_percent"], "Adverse value");
  if (observations !== 4096 || pairs !== 2048) fail("Incomplete observation/pair totals");
  return {schema_version: 1, result_commit: identity.result_commit,
    source_commit: identity.candidate_commit, runtime_sha256: identity.candidate_runtime_sha256,
    worker_hashes: hashes, calls: observations, complete_payload_pairs: pairs,
    payload_mismatches: mismatches.length, mismatches, cells,
    pooled_p95_geomean_improvement_percent: gm,
    public_native_char4000_p95_improvement_percent:
      -cells.find(c => c.cohort === "public1015" && c.configuration === "native-char4000").p95_change_percent,
    all_summary_quantiles_reproduced: true, all_round_and_pooled_means_reproduced: true,
    immutable_premeasurement_order_hashes_verified: 32,
    numerical_relative_or_absolute_tolerance: 1e-10,
    adverse_cells_over_five_percent: adverse.length, retrieval_calls_executed_by_audit: 0,
    fresh_rows_decoded: 0, formal_acceptance: false};
}
