/* Optional native implementations of the existing lexical loops.
 *
 * These helpers do not own normalization rules or persistent caches.  Python
 * supplies the stop set and Unicode callables, and remains the reference path
 * for inputs outside the guarded signatures.  Unicode offsets are CPython
 * code-point offsets, including isolated surrogate code points; no UTF-8
 * conversion is performed.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

static int
require_exact_unicode(PyObject *value)
{
    if (!PyUnicode_CheckExact(value)) {
        PyErr_SetString(PyExc_TypeError, "text must be an exact str");
        return -1;
    }
#if PY_VERSION_HEX < 0x030C0000
    if (PyUnicode_READY(value) < 0) {
        return -1;
    }
#endif
    return 0;
}

static int
ascii_lower(unsigned char value)
{
    return value >= 'a' && value <= 'z';
}

static int
ascii_upper(unsigned char value)
{
    return value >= 'A' && value <= 'Z';
}

static int
ascii_digit(unsigned char value)
{
    return value >= '0' && value <= '9';
}

static int
append_ascii_token(PyObject *result, const unsigned char *data,
                   Py_ssize_t start, Py_ssize_t end, int fold_case,
                   int query, PyObject *stop)
{
    PyObject *token;
    unsigned char *destination;
    Py_ssize_t index;
    int contains, status;

    token = PyUnicode_New(end - start, 127);
    if (token == NULL) {
        return -1;
    }
    destination = PyUnicode_1BYTE_DATA(token);
    for (index = start; index < end; index++) {
        unsigned char character = data[index];
        destination[index - start] = (fold_case && ascii_upper(character))
            ? (unsigned char)(character + ('a' - 'A')) : character;
    }
    if (query) {
        contains = PySequence_Contains(stop, token);
        if (contains < 0) {
            Py_DECREF(token);
            return -1;
        }
        if (contains) {
            Py_DECREF(token);
            return 0;
        }
    }
    status = PyList_Append(result, token);
    Py_DECREF(token);
    return status;
}

static PyObject *
ascii_terms_impl(PyObject *args, int original_input)
{
    PyObject *text, *query, *stop, *result;
    const unsigned char *data;
    Py_ssize_t length, index, start = -1;
    int filter;

    if (!PyArg_ParseTuple(args, "OOO", &text, &query, &stop)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyUnicode_IS_ASCII(text)) {
        PyErr_SetString(PyExc_ValueError, "text must contain only ASCII code points");
        return NULL;
    }
    if (!PyBool_Check(query)) {
        PyErr_SetString(PyExc_TypeError, "query must be an exact bool");
        return NULL;
    }
    filter = query == Py_True;
    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }
    data = PyUnicode_1BYTE_DATA(text);
    length = PyUnicode_GET_LENGTH(text);
    for (index = 0; index < length; index++) {
        unsigned char character = data[index];
        int word = ascii_lower(character) || ascii_digit(character)
            || (original_input && ascii_upper(character));
        int boundary = original_input && index > 0 && ascii_lower(data[index - 1])
            && ascii_upper(character);
        if ((index & 65535) == 0 && PyErr_CheckSignals() < 0) {
            goto error;
        }
        if (start >= 0 && (!word || boundary)) {
            if (append_ascii_token(result, data, start, index, original_input,
                                   filter, stop) < 0) {
                goto error;
            }
            start = -1;
        }
        if (word && start < 0) {
            start = index;
        }
    }
    if (start >= 0 && append_ascii_token(result, data, start, length,
                                        original_input, filter, stop) < 0) {
        goto error;
    }
    return result;

error:
    Py_DECREF(result);
    return NULL;
}

static PyObject *
native_terms_ascii(PyObject *self, PyObject *args)
{
    (void)self;
    return ascii_terms_impl(args, 1);
}

static PyObject *
native_ascii_tokens(PyObject *self, PyObject *args)
{
    (void)self;
    return ascii_terms_impl(args, 0);
}

/* Keep the historical per-character NFKD -> casefold -> category-Mn removal
 * order.  In particular, this is not whole-string NFKD and is not a filter on
 * Unicode combining classes.  The cache exists only for this one invocation.
 */
static PyObject *
fold_character(PyObject *character, PyObject *normalize, PyObject *category,
               PyObject *nfkd, PyObject *mn)
{
    PyObject *normalized = NULL, *folded = NULL, *piece = NULL;
    PyObject *unit = NULL, *unit_category = NULL;
    Py_ssize_t length, index, written = 0;
    int kind, piece_kind, keep;
    void *data, *piece_data;

    normalized = PyObject_CallFunctionObjArgs(normalize, nfkd, character, NULL);
    if (normalized == NULL) {
        goto error;
    }
    folded = PyObject_CallMethod(normalized, "casefold", NULL);
    if (folded == NULL) {
        goto error;
    }
    if (require_exact_unicode(folded) < 0) {
        goto error;
    }
    length = PyUnicode_GET_LENGTH(folded);
    kind = PyUnicode_KIND(folded);
    data = PyUnicode_DATA(folded);
    piece = PyUnicode_New(length, PyUnicode_MAX_CHAR_VALUE(folded));
    if (piece == NULL) {
        goto error;
    }
    piece_kind = PyUnicode_KIND(piece);
    piece_data = PyUnicode_DATA(piece);
    for (index = 0; index < length; index++) {
        Py_UCS4 code_point = PyUnicode_READ(kind, data, index);
        unit = PyUnicode_FromOrdinal((int)code_point);
        if (unit == NULL) {
            goto error;
        }
        unit_category = PyObject_CallOneArg(category, unit);
        Py_CLEAR(unit);
        if (unit_category == NULL) {
            goto error;
        }
        keep = PyObject_RichCompareBool(unit_category, mn, Py_NE);
        Py_CLEAR(unit_category);
        if (keep < 0) {
            goto error;
        }
        if (keep) {
            PyUnicode_WRITE(piece_kind, piece_data, written, code_point);
            written++;
        }
    }
    /* Removing a mark can lower the largest remaining code point.  Rebuild
     * through the public constructor so the result uses CPython's canonical
     * Unicode kind (rather than retaining a wider temporary representation).
     */
    if (written != length) {
        PyObject *canonical = PyUnicode_FromKindAndData(piece_kind, piece_data, written);
        if (canonical == NULL) {
            goto error;
        }
        Py_SETREF(piece, canonical);
    }
    Py_DECREF(normalized);
    Py_DECREF(folded);
    return piece;

error:
    Py_XDECREF(normalized);
    Py_XDECREF(folded);
    Py_XDECREF(piece);
    Py_XDECREF(unit);
    Py_XDECREF(unit_category);
    return NULL;
}

static PyObject *
native_fold_excerpt_source(PyObject *self, PyObject *args)
{
    PyObject *text, *normalize, *category;
    PyObject *folds = NULL, *positions = NULL, *cache = NULL, *nfkd = NULL, *mn = NULL;
    PyObject *character = NULL, *piece = NULL, *position = NULL;
    PyObject *empty = NULL, *joined = NULL, *result = NULL;
    Py_ssize_t length, index, size, copy;
    int kind;
    void *data;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:fold_excerpt_source", &text, &normalize, &category)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyCallable_Check(normalize) || !PyCallable_Check(category)) {
        PyErr_SetString(PyExc_TypeError, "normalize and category must be callable");
        return NULL;
    }
    length = PyUnicode_GET_LENGTH(text);
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);
    folds = PyList_New(length);
    positions = PyList_New(0);
    cache = PyDict_New();
    nfkd = PyUnicode_FromString("NFKD");
    mn = PyUnicode_FromString("Mn");
    if (folds == NULL || positions == NULL || cache == NULL || nfkd == NULL || mn == NULL) {
        goto done;
    }
    for (index = 0; index < length; index++) {
        if ((index & 4095) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
        character = PyUnicode_FromOrdinal((int)PyUnicode_READ(kind, data, index));
        if (character == NULL) {
            goto done;
        }
        piece = PyDict_GetItemWithError(cache, character);
        if (piece == NULL) {
            if (PyErr_Occurred()) {
                goto done;
            }
            piece = fold_character(character, normalize, category, nfkd, mn);
            if (piece == NULL) {
                goto done;
            }
            if (PyDict_SetItem(cache, character, piece) < 0) {
                goto done;
            }
        }
        else {
            Py_INCREF(piece);
        }
        Py_CLEAR(character);
        size = PyUnicode_GET_LENGTH(piece);
        PyList_SET_ITEM(folds, index, piece);  /* steals the owned reference */
        piece = NULL;
        if (size) {
            position = PyLong_FromSsize_t(index);
            if (position == NULL) {
                goto done;
            }
            for (copy = 0; copy < size; copy++) {
                if (PyList_Append(positions, position) < 0) {
                    goto done;
                }
            }
            Py_CLEAR(position);
        }
    }
    empty = PyUnicode_New(0, 0);
    if (empty == NULL) {
        goto done;
    }
    joined = PyUnicode_Join(empty, folds);
    if (joined == NULL) {
        goto done;
    }
    result = PyTuple_Pack(2, joined, positions);

done:
    Py_XDECREF(folds);
    Py_XDECREF(positions);
    Py_XDECREF(cache);
    Py_XDECREF(nfkd);
    Py_XDECREF(mn);
    Py_XDECREF(character);
    Py_XDECREF(piece);
    Py_XDECREF(position);
    Py_XDECREF(empty);
    Py_XDECREF(joined);
    return result;
}

static int
append_span(PyObject *result, Py_ssize_t start, Py_ssize_t end)
{
    PyObject *span = Py_BuildValue("(nn)", start, end);
    int status;
    if (span == NULL) {
        return -1;
    }
    status = PyList_Append(result, span);
    Py_DECREF(span);
    return status;
}

static PyObject *
native_evidence_units(PyObject *self, PyObject *args)
{
    PyObject *text, *result;
    Py_ssize_t width, length, cursor = 0;
    int kind;
    void *data;

    (void)self;
    if (!PyArg_ParseTuple(args, "On:evidence_units", &text, &width)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    length = PyUnicode_GET_LENGTH(text);
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);
    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }
    while (cursor < length) {
        Py_ssize_t lo, hi, start, boundary;
        if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
            goto error;
        }
        if (PyUnicode_READ(kind, data, cursor) == '\n') {
            cursor++;
            continue;
        }
        lo = cursor;
        while (cursor < length && PyUnicode_READ(kind, data, cursor) != '\n') {
            cursor++;
            if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
                goto error;
            }
        }
        hi = cursor;
        if (hi - lo <= width) {
            if (append_span(result, lo, hi) < 0) {
                goto error;
            }
            continue;
        }
        start = lo;
        for (boundary = lo; boundary < hi; boundary++) {
            Py_UCS4 character = PyUnicode_READ(kind, data, boundary);
            int sentence_end = character == 0x3002 || character == 0xff01 || character == 0xff1f;
            if ((boundary & 65535) == 0 && PyErr_CheckSignals() < 0) {
                goto error;
            }
            if (!sentence_end && (character == '.' || character == '!' || character == '?')) {
                sentence_end = boundary + 1 == hi
                    || Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, boundary + 1));
            }
            if (!sentence_end) {
                continue;
            }
            if (boundary + 1 - start <= width && append_span(result, start, boundary + 1) < 0) {
                goto error;
            }
            start = boundary + 1;
            while (start < hi && Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, start))) {
                start++;
            }
        }
        if (start < hi && hi - start <= width && append_span(result, start, hi) < 0) {
            goto error;
        }
    }
    return result;

error:
    Py_DECREF(result);
    return NULL;
}

static PyMethodDef native_methods[] = {
    {"terms_ascii", native_terms_ascii, METH_VARARGS,
     "terms_ascii(text, query, stop) -> exact legacy ASCII terms."},
    {"ascii_tokens", native_ascii_tokens, METH_VARARGS,
     "ascii_tokens(text, query, stop) -> [a-z0-9]+ runs from normalized ASCII."},
    {"fold_excerpt_source", native_fold_excerpt_source, METH_VARARGS,
     "fold_excerpt_source(text, normalize, category) -> (folded text, code-point positions)."},
    {"evidence_units", native_evidence_units, METH_VARARGS,
     "evidence_units(text, width) -> unchanged source line/sentence spans."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_module = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "Optional, source-equivalent native lexical loops for AI-Memory-Book.",
    0,
    native_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__native(void)
{
    return PyModule_Create(&native_module);
}
