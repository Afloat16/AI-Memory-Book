"""Copied independent saved-observation verifier; no runtime imports or calls."""
MEMO_LIMITS = {"entry_limit": 2048, "text_byte_limit": 2097152}
MEMO_COUNTERS = ("hits", "misses", "evictions", "invalidations", "oversized_bypasses", "uncertified_bypasses")
MEMO_DYNAMIC = ("allocated", "entries", "text_bytes", *MEMO_COUNTERS)
MEMO_BASELINE = {"available": False, "reason": "published-v0.3.2-has-no-derived-token-count-memo"}
MEMO_BOUNDARY = ("Read-only native snapshots outside timing. Same book retains exact token counts "
    "across native configurations; actual MCP uses fresh server processes and measured RSS without private memo counters.")
CONFIGS = tuple({"id": name, "surface": "native"} for name in
    ("native-char4000", "native-token512", "native-token1024", "native-token2048"))
def require(condition, message):
    if not condition:
        raise ValueError(message)

def audit_native_memo(worker):
    """Check saved native observations; never call or import a runtime counter."""
    observation = worker["native_token_count_memo"]
    require(set(observation) == {*MEMO_LIMITS, "boundary", "configurations"}
            and all(type(observation[name]) is int and observation[name] == value
                    for name, value in MEMO_LIMITS.items())
            and observation["boundary"] == MEMO_BOUNDARY,
            "Native memo policy or measurement boundary differs: " + worker["key"])
    expected_ids = [config["id"] for config in CONFIGS if config["surface"] == "native"]
    observed = observation["configurations"]
    native = [config for config in worker["configurations"] if config["surface"] == "native"]
    require([config["id"] for config in native] == expected_ids
            and [record["id"] for record in observed] == expected_ids,
            "Missing, extra or reordered native memo observations: " + worker["key"])
    previous = None
    records = []
    for position, (config, record) in enumerate(zip(native, observed, strict=True)):
        path = worker["key"] + ":" + record["id"]
        require(set(record) == {"id", "first_query_id", "before", "after_first_call", "after"}
                and record["first_query_id"] == config["rows"][0]["query_id"],
                "Native memo first-call observation is not the retained first row: " + path)
        snapshots = [record[name] for name in ("before", "after_first_call", "after")]
        for snapshot in snapshots:
            if worker["label"] == "baseline":
                require(snapshot == MEMO_BASELINE, "Baseline memo availability is misrepresented: " + path)
                continue
            require(worker["label"] == "candidate" and snapshot.get("available") is True
                    and set(snapshot) == {"available", *MEMO_LIMITS, *MEMO_DYNAMIC},
                    "Candidate native memo fields differ: " + path)
            require(all(type(snapshot[name]) is int and snapshot[name] >= 0
                        for name in (*MEMO_LIMITS, *MEMO_DYNAMIC))
                    and all(snapshot[name] == value for name, value in MEMO_LIMITS.items())
                    and snapshot["allocated"] in (0, 1)
                    and snapshot["entries"] <= MEMO_LIMITS["entry_limit"]
                    and snapshot["text_bytes"] <= MEMO_LIMITS["text_byte_limit"],
                    "Native memo exceeds its registered bounds or has invalid counters: " + path)
            require(snapshot["allocated"] == 1 or not any(snapshot[name] for name in MEMO_DYNAMIC),
                    "Unallocated native memo is not empty: " + path)
        require(previous is None or previous == snapshots[0],
                "Native memo state changed between configurations: " + path)
        if worker["label"] == "candidate":
            if position == 0:
                require(not any(snapshots[0][name] for name in MEMO_DYNAMIC),
                        "Fresh MemoryBook did not begin with an empty unallocated memo: " + path)
            if record["id"] == "native-char4000":
                require(snapshots[0] == snapshots[1] == snapshots[2],
                        "Character recalls allocated or warmed the token memo: " + path)
            for earlier, later in zip(snapshots, snapshots[1:]):
                require(later["allocated"] >= earlier["allocated"]
                        and all(later[name] >= earlier[name] for name in MEMO_COUNTERS),
                        "Native memo cumulative counters decreased: " + path)
            records.append({"id": record["id"], "first_query_id": record["first_query_id"],
                "before": snapshots[0], "after_first_call": snapshots[1], "after": snapshots[2],
                "retained_entries_at_start": snapshots[0]["entries"],
                "later_native_configuration": position > 1,
                "first_call_counter_delta": {name: snapshots[1][name] - snapshots[0][name]
                                             for name in MEMO_COUNTERS},
                "configuration_counter_delta": {name: snapshots[2][name] - snapshots[0][name]
                                                for name in MEMO_COUNTERS}})
        previous = snapshots[-1]
    return {"worker": worker["key"], "label": worker["label"],
        "available": worker["label"] == "candidate", "limits": MEMO_LIMITS,
        "empty_connection_start_verified": worker["label"] == "candidate",
        "native_configurations": records,
        "boundary": MEMO_BOUNDARY,
        "memory_boundary": "The 2 MiB cap counts retained str object sizes after encoding; key/container/encoder overhead and other process allocations are outside this cap and remain subject to the original RSS review."}
