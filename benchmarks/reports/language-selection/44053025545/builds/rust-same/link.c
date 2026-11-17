/* Generated experimental link unit; no product source edit. */
#define PyInit__native language_original_PyInit__native
#include "/home/runner/work/AI-Memory-Book/AI-Memory-Book/.artifacts/language-selection/run/current/src/memory_book/_native.c"
#undef PyInit__native
#include <stdint.h>
extern PyObject *rust_terms_ascii(PyObject *, PyObject *);
extern PyObject *rust_ascii_tokens(PyObject *, PyObject *);
extern PyObject *rust_unicode_tokens(PyObject *, PyObject *);
extern PyObject *rust_literal_positions(PyObject *, PyObject *);
extern PyObject *rust_fold_excerpt_source(PyObject *, PyObject *);
extern PyObject *rust_evidence_units(PyObject *, PyObject *);
static PyCFunction language_original_methods[] = {
    native_segmentation_ready,
    native_make_turns,
    native_page_cuts,
    native_build_pages,
    native_segment_turns,
    native_strip_nonspacing_marks,
    native_identifier_has_boundary,
    native_excerpt_window,
    native_rank_candidates,
    native_select_novelty,
    native_context_allocations,
    native_refs_from_parsed,
    native_source_units,
    native_projected_units,
    native_source_map_matches,
    native_terms_ascii,
    native_ascii_tokens,
    native_unicode_tokens,
    native_identifier_aliases,
    native_literal_positions,
    native_fold_excerpt_source,
    native_evidence_units
};
PyMODINIT_FUNC PyInit__native(void) {
    for (int i = 0; native_methods[i].ml_name; i++) {
    if (strcmp(native_methods[i].ml_name, "terms_ascii") == 0) native_methods[i].ml_meth = rust_terms_ascii;
    if (strcmp(native_methods[i].ml_name, "ascii_tokens") == 0) native_methods[i].ml_meth = rust_ascii_tokens;
    if (strcmp(native_methods[i].ml_name, "unicode_tokens") == 0) native_methods[i].ml_meth = rust_unicode_tokens;
    if (strcmp(native_methods[i].ml_name, "literal_positions") == 0) native_methods[i].ml_meth = rust_literal_positions;
    if (strcmp(native_methods[i].ml_name, "fold_excerpt_source") == 0) native_methods[i].ml_meth = rust_fold_excerpt_source;
    if (strcmp(native_methods[i].ml_name, "evidence_units") == 0) native_methods[i].ml_meth = rust_evidence_units;
    }
    return language_original_PyInit__native();
}
PyObject *language_rust_manifest(void) {
    PyObject *rows = PyList_New(0);
    if (!rows) return NULL;
    for (int i = 0; native_methods[i].ml_name; i++) {
        PyObject *row = Py_BuildValue("{s:s,s:K,s:K,s:i,s:i}",
            "name", native_methods[i].ml_name,
            "original_address", (unsigned long long)(uintptr_t)language_original_methods[i],
            "effective_address", (unsigned long long)(uintptr_t)native_methods[i].ml_meth,
            "flags", native_methods[i].ml_flags,
            "replaced", native_methods[i].ml_meth != language_original_methods[i]);
        if (!row || PyList_Append(rows, row) < 0) { Py_XDECREF(row); Py_DECREF(rows); return NULL; }
        Py_DECREF(row);
    }
    return rows;
}
