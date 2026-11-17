# C control for the complete bounded metadata method

This isolated candidate translates `MemoryBook._bounded_candidate_metadata`
from the frozen product source into C. It is the same-interface control for
the `rust_metadata` candidate. It does not change a production source file,
SQL statement, retained-candidate rule, ranking rule, or database layout.

| Boundary | Contract |
| --- | --- |
| Native entry | `bounded_metadata(book, rows, relevance, count, env)` |
| Ordinary result | The original result dictionary or `None` |
| Unsupported input | `NotImplemented`, only before SQL or candidate mutation |
| Installation | The shared `rust_metadata/adapter.py` installs one process-local method |
| Source authentication | The adapter binds the original `store.py` bytes and method code |
| SQL | Original statement bytes and parameter order; existing Python sqlite connection |
| Source of light metadata | The original live `dict_values` view, or the original SQL query |
| Candidate updates | Original dictionaries are mutated; returned values retain object identity |
| SQL callback changes | Resume the shared exact Python continuation after the query already executed |

The complete ordinary method runs in native code: finite-score validation,
the original descending-score threshold and `1.15` bound, light-row validation,
stable chapter/session pair construction, SQL statement and parameter assembly,
directory validation, metadata updates, and the ordered retained dictionary.
SQLite remains the existing engine. Calling its Python connection API is
part of the measured method, including connection callbacks and errors.

The ordinary domain uses exact built-in containers, string identities, float
relevance values, integer row IDs and a positive machine-sized integer count.
The shared adapter authenticates the class methods, attribute access, built-ins,
directory cache and math dependency before dispatch. Unsupported custom inputs
continue through the original method. After either SQL query, a changed
dependency or container resumes the corresponding original Python suffix;
the implementation does not rerun SQL. In particular, the second query reads
`book.db` again, and the final update loop sees the current contents of the
original light metadata view.

## Build and verify

```bash
python benchmarks/experiments/language_selection/c_metadata/build.py \
  --python-source /absolute/path/to/frozen/src \
  --output /absolute/path/to/new/c-metadata-build

python benchmarks/experiments/language_selection/rust_metadata/check.py \
  --python-source /absolute/path/to/frozen/src \
  --module _language_c_metadata \
  --binary /absolute/path/to/new/c-metadata-build/_language_c_metadata.cpython-312-x86_64-linux-gnu.so \
  --output /absolute/path/to/new/c-metadata-correctness.json
```

The builder refuses to overwrite an existing output directory and records the
compiler command, source/reference hashes and compiled binary hash. It uses
the same common C flags as the other experiment controls, without fast-math.

Correctness checks and native dispatch probes must pass on the exact frozen
binary before interpreting measurements. No performance result is claimed by
this directory. This is one complete retrieval stage; its results cannot by
themselves rank all possible complete-application language implementations.
