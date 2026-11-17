/* Isolated experimental control: same immutable Unicode table as Rust.
 * No product source is edited.  Compile against the frozen _native.c to keep
 * its exact callable/error fallback for nonstandard Unicode dependencies.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* The reference translation unit is included for its private fold helper.
 * Its module initializer is made private and dead-code eliminated; the only
 * public module built here is _language_c_table below.
 */
#pragma push_macro("PyMODINIT_FUNC")
#undef PyMODINIT_FUNC
#define PyMODINIT_FUNC static PyObject *
#include "_native.c"
#pragma pop_macro("PyMODINIT_FUNC")

#include "fold_table.h"

#ifdef LANGUAGE_USE_RUST_TABLE
extern PyObject *rust_fold_table(PyObject *text);
#define TABLE_CANDIDATE_NAME "rust-table-fold"
#else
#define TABLE_CANDIDATE_NAME "c-table-fold"
#endif

typedef struct {
    PyObject *normalize;
    PyObject *category;
    PyObject *runtime_ucd;
    int enabled;
} TableState;

#ifndef LANGUAGE_USE_RUST_TABLE
static uint16_t
table_u16(size_t offset)
{
    return (uint16_t)FOLD_TABLE[offset]
        | (uint16_t)((uint16_t)FOLD_TABLE[offset + 1] << 8);
}

static uint32_t
table_u32(size_t offset)
{
    return (uint32_t)FOLD_TABLE[offset]
        | ((uint32_t)FOLD_TABLE[offset + 1] << 8)
        | ((uint32_t)FOLD_TABLE[offset + 2] << 16)
        | ((uint32_t)FOLD_TABLE[offset + 3] << 24);
}

/* UINT32_MAX denotes an identity character.  Every other entry has an
 * eight-bit expansion length and a 24-bit index into the shared value array.
 */
static uint32_t
table_entry(Py_UCS4 code_point)
{
    uint16_t page = table_u16(64 + (size_t)(code_point >> 8) * 2);
    if (page == UINT16_MAX) {
        return UINT32_MAX;
    }
    return table_u32(FOLD_ENTRIES_OFFSET
        + ((size_t)page * 256 + (code_point & 255)) * 4);
}

static Py_UCS4
table_value(uint32_t entry, unsigned int index)
{
    return (Py_UCS4)table_u32(FOLD_VALUES_OFFSET
        + ((size_t)(entry & 0xffffffu) + index) * 4);
}
#endif

static PyObject *
table_fold_excerpt_source(PyObject *module, PyObject *args)
{
    TableState *state = (TableState *)PyModule_GetState(module);
    PyObject *text, *normalize, *category;
#ifndef LANGUAGE_USE_RUST_TABLE
    PyObject *folded = NULL, *positions = NULL, *result = NULL;
    Py_ssize_t length, index, output_length = 0, written = 0;
    Py_UCS4 max_character = 0;
    int kind, output_kind;
    void *data, *output_data;
#endif

    if (!PyArg_ParseTuple(args, "OOO:fold_excerpt_source", &text,
                          &normalize, &category)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyCallable_Check(normalize) || !PyCallable_Check(category)) {
        PyErr_SetString(PyExc_TypeError, "normalize and category must be callable");
        return NULL;
    }
    if (!state->enabled || normalize != state->normalize || category != state->category) {
        return native_fold_excerpt_source(module, args);
    }
#ifdef LANGUAGE_USE_RUST_TABLE
    return rust_fold_table(text);
#else
    length = PyUnicode_GET_LENGTH(text);
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);

    /* Pass one determines exact sizes and canonical CPython Unicode width. */
    for (index = 0; index < length; index++) {
        Py_UCS4 code_point = PyUnicode_READ(kind, data, index);
        uint32_t entry;
        unsigned int count, unit;
        if ((index & 4095) == 0 && PyErr_CheckSignals() < 0) {
            return NULL;
        }
        entry = table_entry(code_point);
        count = entry == UINT32_MAX ? 1 : entry >> 24;
        if ((Py_ssize_t)count > PY_SSIZE_T_MAX - output_length) {
            PyErr_NoMemory();
            return NULL;
        }
        output_length += (Py_ssize_t)count;
        if (entry == UINT32_MAX) {
            if (code_point > max_character) {
                max_character = code_point;
            }
        }
        else {
            for (unit = 0; unit < count; unit++) {
                Py_UCS4 value = table_value(entry, unit);
                if (value > max_character) {
                    max_character = value;
                }
            }
        }
    }
    folded = PyUnicode_New(output_length, max_character);
    positions = PyList_New(output_length);
    if (folded == NULL || positions == NULL) {
        goto done;
    }
    output_kind = PyUnicode_KIND(folded);
    output_data = PyUnicode_DATA(folded);

    /* Pass two writes the result with one Python index object per source
     * character. Expansion entries share the index just as the reference does.
     */
    for (index = 0; index < length; index++) {
        Py_UCS4 code_point = PyUnicode_READ(kind, data, index);
        uint32_t entry;
        unsigned int count, unit;
        PyObject *position;
        if ((index & 4095) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
        entry = table_entry(code_point);
        count = entry == UINT32_MAX ? 1 : entry >> 24;
        if (!count) {
            continue;
        }
        position = PyLong_FromSsize_t(index);
        if (position == NULL) {
            goto done;
        }
        for (unit = 0; unit < count; unit++) {
            Py_UCS4 value = entry == UINT32_MAX ? code_point : table_value(entry, unit);
            PyUnicode_WRITE(output_kind, output_data, written, value);
            PyList_SET_ITEM(positions, written, Py_NewRef(position));
            written++;
        }
        Py_DECREF(position);
    }
    result = PyTuple_Pack(2, folded, positions);
done:
    Py_XDECREF(folded);
    Py_XDECREF(positions);
    return result;
#endif
}

static int
ordinary_unicode_callable(PyObject *value, PyObject *unicode_module, const char *name)
{
    PyObject *actual_name;
    int matches;
    if (!PyCFunction_Check(value) || PyCFunction_GetSelf(value) != unicode_module) {
        return 0;
    }
    actual_name = PyObject_GetAttrString(value, "__name__");
    if (actual_name == NULL) {
        return -1;
    }
    matches = PyUnicode_CheckExact(actual_name)
        && PyUnicode_CompareWithASCIIString(actual_name, name) == 0;
    Py_DECREF(actual_name);
    return matches;
}

static PyObject *
table_describe(PyObject *module, PyObject *unused)
{
    TableState *state = (TableState *)PyModule_GetState(module);
    (void)unused;
    return Py_BuildValue("{s:s,s:s,s:O,s:O,s:s,s:n,s:s}",
        "candidate", TABLE_CANDIDATE_NAME,
        "table_sha256", FOLD_TABLE_SHA256,
        "runtime_ucd_version", state->runtime_ucd,
        "table_enabled", state->enabled ? Py_True : Py_False,
        "table_ucd_version", FOLD_UCD_VERSION,
        "table_bytes", (Py_ssize_t)sizeof(FOLD_TABLE),
        "boundary", "fold_excerpt_source only; same-table two-pass kernel and shared C guard; custom callables retain original C fallback");
}

static PyObject *
table_install_into(PyObject *module, PyObject *target)
{
    PyObject *original, *replacement;
    if (!PyModule_Check(target)) {
        PyErr_SetString(PyExc_TypeError, "target must be the experimental native module");
        return NULL;
    }
    original = PyObject_GetAttrString(target, "fold_excerpt_source");
    if (original == NULL) {
        return NULL;
    }
    replacement = PyObject_GetAttrString(module, "fold_excerpt_source");
    if (replacement == NULL || PyObject_SetAttrString(target, "fold_excerpt_source", replacement) < 0) {
        Py_DECREF(original);
        Py_XDECREF(replacement);
        return NULL;
    }
    Py_DECREF(replacement);
    return original;
}

static int
table_exec(PyObject *module)
{
    TableState *state = (TableState *)PyModule_GetState(module);
    PyObject *unicode_module = PyImport_ImportModule("unicodedata");
    int normalizer_ok, category_ok;
    if (unicode_module == NULL) {
        return -1;
    }
    state->normalize = PyObject_GetAttrString(unicode_module, "normalize");
    state->category = PyObject_GetAttrString(unicode_module, "category");
    state->runtime_ucd = PyObject_GetAttrString(unicode_module, "unidata_version");
    if (state->normalize == NULL || state->category == NULL || state->runtime_ucd == NULL) {
        Py_DECREF(unicode_module);
        return -1;
    }
    normalizer_ok = ordinary_unicode_callable(state->normalize, unicode_module, "normalize");
    category_ok = ordinary_unicode_callable(state->category, unicode_module, "category");
    Py_DECREF(unicode_module);
    if (normalizer_ok < 0 || category_ok < 0) {
        return -1;
    }
    state->enabled = normalizer_ok && category_ok
        && PyUnicode_CheckExact(state->runtime_ucd)
        && PyUnicode_CompareWithASCIIString(state->runtime_ucd, FOLD_UCD_VERSION) == 0;
    return 0;
}

static int
table_traverse(PyObject *module, visitproc visit, void *arg)
{
    TableState *state = (TableState *)PyModule_GetState(module);
    Py_VISIT(state->normalize);
    Py_VISIT(state->category);
    Py_VISIT(state->runtime_ucd);
    return 0;
}

static int
table_clear(PyObject *module)
{
    TableState *state = (TableState *)PyModule_GetState(module);
    Py_CLEAR(state->normalize);
    Py_CLEAR(state->category);
    Py_CLEAR(state->runtime_ucd);
    state->enabled = 0;
    return 0;
}

static void
table_free(void *module)
{
    table_clear((PyObject *)module);
}

static PyMethodDef table_methods[] = {
    {"fold_excerpt_source", table_fold_excerpt_source, METH_VARARGS, "Same-table native fold control."},
    {"install_into", table_install_into, METH_O, "Install the isolated fold control before public modules import."},
    {"describe", table_describe, METH_NOARGS, "Return source-table and runtime eligibility metadata."},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef_Slot table_slots[] = {
    {Py_mod_exec, table_exec},
    {0, NULL}
};
static struct PyModuleDef table_module = {
    PyModuleDef_HEAD_INIT,
    "_language_c_table",
    "Isolated C control for the identical Rust Unicode fold table.",
    sizeof(TableState),
    table_methods,
    table_slots,
    table_traverse,
    table_clear,
    table_free
};

PyMODINIT_FUNC
PyInit__language_c_table(void)
{
    return PyModuleDef_Init(&table_module);
}
