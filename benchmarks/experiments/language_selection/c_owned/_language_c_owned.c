/* Isolated C control for the complete Rust-owned ordinary-query window.
 * Same domain, candidates, native numeric state, summation and source offsets.
 * This includes the frozen released C translation unit only for its Unicode,
 * binary-search and rendering helpers; no product file is edited.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#pragma push_macro("PyMODINIT_FUNC")
#undef PyMODINIT_FUNC
#define PyMODINIT_FUNC static PyObject *
#include "_native.c"
#pragma pop_macro("PyMODINIT_FUNC")

typedef struct {
    memory_book_excerpt_unit *data;
    size_t count;
    size_t capacity;
} owned_units;

static int
owned_push_unit(owned_units *units, Py_ssize_t lo, Py_ssize_t hi)
{
    if (units->count == units->capacity) {
        size_t capacity = units->capacity ? units->capacity * 2 : 16;
        memory_book_excerpt_unit *data;
        if (capacity < units->capacity || capacity > SIZE_MAX / sizeof(*data)) {
            PyErr_NoMemory();
            return -1;
        }
        data = realloc(units->data, capacity * sizeof(*data));
        if (data == NULL) {
            PyErr_NoMemory();
            return -1;
        }
        units->data = data;
        units->capacity = capacity;
    }
    units->data[units->count].lo = lo;
    units->data[units->count].hi = hi;
    units->data[units->count].mask = 0;
    units->count++;
    return 0;
}

static int
owned_scan_units(PyObject *text, Py_ssize_t width, owned_units *units)
{
    Py_ssize_t cursor = 0, length = PyUnicode_GET_LENGTH(text);
    int kind = PyUnicode_KIND(text);
    void *data = PyUnicode_DATA(text);
    units->capacity = 16;
    units->data = malloc(units->capacity * sizeof(*units->data));
    if (units->data == NULL) {
        PyErr_NoMemory();
        return -1;
    }
    while (cursor < length) {
        Py_ssize_t lo, hi, start, boundary;
        if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
            return -1;
        }
        if (PyUnicode_READ(kind, data, cursor) == '\n') {
            cursor++;
            continue;
        }
        lo = cursor;
        while (cursor < length && PyUnicode_READ(kind, data, cursor) != '\n') {
            cursor++;
            if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
                return -1;
            }
        }
        hi = cursor;
        if (hi - lo <= width) {
            if (owned_push_unit(units, lo, hi) < 0) {
                return -1;
            }
            continue;
        }
        start = lo;
        for (boundary = lo; boundary < hi; boundary++) {
            Py_UCS4 ch = PyUnicode_READ(kind, data, boundary);
            int end = ch == 0x3002 || ch == 0xff01 || ch == 0xff1f;
            if ((boundary & 65535) == 0 && PyErr_CheckSignals() < 0) {
                return -1;
            }
            if (!end && (ch == '.' || ch == '!' || ch == '?')) {
                end = boundary + 1 == hi
                    || Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, boundary + 1));
            }
            if (!end) {
                continue;
            }
            if (boundary + 1 - start <= width
                    && owned_push_unit(units, start, boundary + 1) < 0) {
                return -1;
            }
            start = boundary + 1;
            while (start < hi && Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, start))) {
                start++;
            }
        }
        if (start < hi && hi - start <= width && owned_push_unit(units, start, hi) < 0) {
            return -1;
        }
    }
    return 0;
}

/* Error-free partial summation with the identical final half-even correction.
 * The actual window uses at most 64 finite log1p(integer in 1..40) values.
 * No fast-math, persistent frequency table or ordinary floating sum is used.
 */
static double
owned_positive_sum(const double *values, size_t length)
{
    double partials[64] = {0.0};
    size_t n = 0, index;
    double hi = 0.0, lo = 0.0;
    for (index = 0; index < length; index++) {
        double x = values[index];
        size_t i = 0, j;
        for (j = 0; j < n; j++) {
            double y = partials[j];
            if (fabs(x) < fabs(y)) {
                double swap = x;
                x = y;
                y = swap;
            }
            hi = x + y;
            lo = y - (hi - x);
            if (lo != 0.0) {
                partials[i++] = lo;
            }
            x = hi;
        }
        n = i;
        if (x != 0.0) {
            partials[n++] = x;
        }
    }
    hi = lo = 0.0;
    if (n) {
        hi = partials[--n];
    }
    while (n) {
        double x = hi, y = partials[--n];
        hi = x + y;
        lo = y - (hi - x);
        if (lo != 0.0) {
            break;
        }
    }
    if (n && ((lo < 0.0 && partials[n-1] < 0.0)
              || (lo > 0.0 && partials[n-1] > 0.0))) {
        double y = lo * 2.0, x = hi + y;
        if (x - hi == y) {
            hi = x;
        }
    }
    return hi;
}

static PyObject *
owned_excerpt_window(PyObject *self, PyObject *args)
{
    PyObject *text, *q, *positions, *width_object;
    PyObject *snapshot = NULL, *term_ids = NULL, *result = NULL;
    memory_book_excerpt_hit *hits = NULL;
    memory_book_excerpt_unit *matched = NULL;
    owned_units units = {NULL, 0, 0};
    Py_ssize_t *starts = NULL;
    Py_ssize_t length, width, last_start, q_count, hit_count, index;
    Py_ssize_t matched_count = 0, starts_count = 0, unique_count = 0;
    Py_ssize_t counts[64] = {0}, per_term[64] = {0};
    Py_ssize_t left = 0, right = 0, position_sum = 0, active = 0;
    Py_ssize_t best_start = 0, best_active = -1, best_complete = -1;
    double best_frequency = -1.0, best_negative_placement = -1.0;
    Py_ssize_t best_negative_start = -1;
    int next[64], previous[64], head = -1, tail = -1;
    int unsupported = 0;
    uint64_t safe_sum = UINT64_C(9007199254740991);
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOO:excerpt_window_owned", &text, &q,
                          &positions, &width_object)) {
        return NULL;
    }
    if (!PyUnicode_CheckExact(text) || !PyList_CheckExact(q)
            || !PyList_CheckExact(positions) || !PyLong_CheckExact(width_object)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    length = PyUnicode_GET_LENGTH(text);
    width = PyLong_AsSsize_t(width_object);
    if (width == -1 && PyErr_Occurred()) {
        PyErr_Clear();
        Py_RETURN_NOTIMPLEMENTED;
    }
    if ((uint64_t)PY_SSIZE_T_MAX < safe_sum) {
        safe_sum = (uint64_t)PY_SSIZE_T_MAX;
    }
    hit_count = PyList_GET_SIZE(positions);
    if (width <= 0 || width >= length || PyList_GET_SIZE(q) > 64 || hit_count > 2560
            || (uint64_t)length > safe_sum / (uint64_t)(hit_count ? hit_count : 1)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    snapshot = PyList_AsTuple(q);
    if (snapshot == NULL) {
        goto done;
    }
    q_count = PyTuple_GET_SIZE(snapshot);
    if (q_count > 64) {
        unsupported = 1;
        goto done;
    }
    term_ids = PyDict_New();
    if (term_ids == NULL) {
        goto done;
    }
    for (index = 0; index < q_count; index++) {
        PyObject *term = PyTuple_GET_ITEM(snapshot, index), *identifier;
        if (!PyUnicode_CheckExact(term)) {
            unsupported = 1;
            goto done;
        }
        identifier = PyDict_GetItemWithError(term_ids, term);
        if (identifier != NULL) {
            unsupported = 1;
            goto done;
        }
        if (PyErr_Occurred()) {
            goto done;
        }
        identifier = PyLong_FromSsize_t(index);
        if (identifier == NULL) {
            goto done;
        }
        if (PyDict_SetItem(term_ids, term, identifier) < 0) {
            Py_DECREF(identifier);
            goto done;
        }
        Py_DECREF(identifier);
    }
    hit_count = PyList_GET_SIZE(positions);
    if (hit_count > 2560
            || (uint64_t)length > safe_sum / (uint64_t)(hit_count ? hit_count : 1)) {
        unsupported = 1;
        goto done;
    }
    for (index = 0; index < hit_count; index++) {
        PyObject *pair = PyList_GET_ITEM(positions, index), *position, *term, *identifier;
        Py_ssize_t pos, term_id;
        if (!PyTuple_CheckExact(pair) || PyTuple_GET_SIZE(pair) != 2) {
            unsupported = 1;
            goto done;
        }
        position = PyTuple_GET_ITEM(pair, 0);
        term = PyTuple_GET_ITEM(pair, 1);
        if (!PyLong_CheckExact(position) || !PyUnicode_CheckExact(term)) {
            unsupported = 1;
            goto done;
        }
        pos = PyLong_AsSsize_t(position);
        if (pos == -1 && PyErr_Occurred()) {
            PyErr_Clear();
            unsupported = 1;
            goto done;
        }
        if (pos < 0 || pos > length) {
            unsupported = 1;
            goto done;
        }
        identifier = PyDict_GetItemWithError(term_ids, term);
        if (identifier == NULL) {
            if (!PyErr_Occurred()) {
                unsupported = 1;
            }
            goto done;
        }
        term_id = PyLong_AsSsize_t(identifier);
        if (++per_term[term_id] > 40) {
            unsupported = 1;
            goto done;
        }
    }
    /* All fallback checks precede the observable in-place sort. */
    if (PyList_Sort(positions) < 0) {
        goto done;
    }
    if (hit_count) {
        hits = malloc((size_t)hit_count * sizeof(*hits));
        if (hits == NULL) {
            PyErr_NoMemory();
            goto done;
        }
    }
    starts = malloc((size_t)(hit_count * 3 + 2) * sizeof(*starts));
    if (starts == NULL) {
        PyErr_NoMemory();
        goto done;
    }
    last_start = length - width;
    starts[starts_count++] = 0;
    starts[starts_count++] = last_start;
    for (index = 0; index < hit_count; index++) {
        PyObject *pair = PyList_GET_ITEM(positions, index);
        PyObject *identifier = PyDict_GetItemWithError(term_ids, PyTuple_GET_ITEM(pair, 1));
        Py_ssize_t start;
        if (identifier == NULL) {
            if (!PyErr_Occurred()) {
                PyErr_SetString(PyExc_RuntimeError, "excerpt positions changed during sorting");
            }
            goto done;
        }
        hits[index].position = PyLong_AsSsize_t(PyTuple_GET_ITEM(pair, 0));
        hits[index].term = (unsigned int)PyLong_AsSsize_t(identifier);
        start = hits[index].position - width / 3;
        starts[starts_count++] = start < 0 ? 0 : start > last_start ? last_start : start;
    }
    if (hit_count) {
        if (owned_scan_units(text, width, &units) < 0) {
            goto done;
        }
        matched = malloc((size_t)hit_count * sizeof(*matched));
        if (matched == NULL) {
            PyErr_NoMemory();
            goto done;
        }
        for (index = 0; index < hit_count; index++) {
            Py_ssize_t unit = excerpt_window_bisect_lo(units.data, (Py_ssize_t)units.count,
                                                      hits[index].position, 1) - 1;
            if (unit >= 0 && hits[index].position < units.data[unit].hi) {
                if (!matched_count || matched[matched_count - 1].lo != units.data[unit].lo) {
                    matched[matched_count++] = units.data[unit];
                }
                matched[matched_count - 1].mask |= (uint64_t)1 << hits[index].term;
            }
        }
        for (index = 0; index < matched_count; index++) {
            Py_ssize_t start = matched[index].lo < last_start ? matched[index].lo : last_start;
            starts[starts_count++] = start;
            start = matched[index].hi - width;
            starts[starts_count++] = start > 0 ? start : 0;
        }
    }
    qsort(starts, (size_t)starts_count, sizeof(*starts), excerpt_window_compare_start);
    for (index = 0; index < starts_count; index++) {
        if (!unique_count || starts[index] != starts[unique_count - 1]) {
            starts[unique_count++] = starts[index];
        }
    }
    for (index = 0; index < 64; index++) {
        next[index] = previous[index] = -1;
    }
    for (index = 0; index < unique_count; index++) {
        Py_ssize_t start = starts[index], end = start + width;
        Py_ssize_t first_unit, last_unit, unit, count, complete;
        uint64_t whole = 0;
        double logs[64] = {0.0}, frequency, negative_placement;
        Py_ssize_t negative_start = -start;
        size_t log_count = 0;
        int term, better;
        if (PyErr_CheckSignals() < 0) {
            goto done;
        }
        while (right < hit_count && hits[right].position < end) {
            term = (int)hits[right].term;
            if (!counts[term]) {
                previous[term] = tail;
                next[term] = -1;
                if (tail >= 0) {
                    next[tail] = term;
                }
                else {
                    head = term;
                }
                tail = term;
                active++;
            }
            counts[term]++;
            position_sum += hits[right++].position;
        }
        while (left < right && hits[left].position < start) {
            term = (int)hits[left].term;
            if (!--counts[term]) {
                if (previous[term] >= 0) {
                    next[previous[term]] = next[term];
                }
                else {
                    head = next[term];
                }
                if (next[term] >= 0) {
                    previous[next[term]] = previous[term];
                }
                else {
                    tail = previous[term];
                }
                next[term] = previous[term] = -1;
                active--;
            }
            position_sum -= hits[left++].position;
        }
        first_unit = excerpt_window_bisect_lo(matched, matched_count, start, 0);
        last_unit = excerpt_window_bisect_hi(matched, matched_count, end);
        for (unit = first_unit; unit < last_unit; unit++) {
            whole |= matched[unit].mask;
        }
        count = right - left;
        /* Guarded integer conversions are exact, preserving Python true
         * division's rounding. No fast-math transformations are permitted. */
        negative_placement = count
            ? -fabs(((double)position_sum / (double)count - (double)start)
                    / (double)width - 1.0 / 3.0) : -1.0;
        for (term = head; term >= 0; term = next[term]) {
            logs[log_count++] = log1p((double)counts[term]);
        }
        frequency = owned_positive_sum(logs, log_count);
        complete = (Py_ssize_t)__builtin_popcountll(whole);
        better = active > best_active
            || (active == best_active && (complete > best_complete
                || (complete == best_complete && (frequency > best_frequency
                    || (frequency == best_frequency && (negative_placement > best_negative_placement
                        || (negative_placement == best_negative_placement
                            && negative_start > best_negative_start)))))));
        if (better) {
            best_start = start;
            best_active = active;
            best_complete = complete;
            best_frequency = frequency;
            best_negative_placement = negative_placement;
            best_negative_start = negative_start;
        }
    }
    result = excerpt_window_render(text, best_start, best_start + width);
done:
    Py_XDECREF(snapshot);
    Py_XDECREF(term_ids);
    free(hits);
    free(starts);
    free(units.data);
    free(matched);
    return unsupported ? Py_NewRef(Py_NotImplemented) : result;
}

static PyObject *
owned_log1p_values(PyObject *self, PyObject *args)
{
    PyObject *values, *result;
    Py_ssize_t length, index;
    (void)self;
    if (!PyArg_ParseTuple(args, "O:log1p_values", &values)) {
        return NULL;
    }
    if (!PyList_CheckExact(values)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    length = PyList_GET_SIZE(values);
    result = PyList_New(length);
    if (result == NULL) {
        return NULL;
    }
    for (index = 0; index < length; index++) {
        double value = PyFloat_AsDouble(PyList_GET_ITEM(values, index));
        PyObject *logged;
        if (value == -1.0 && PyErr_Occurred()) {
            Py_DECREF(result);
            return NULL;
        }
        logged = PyFloat_FromDouble(log1p(value));
        if (logged == NULL) {
            Py_DECREF(result);
            return NULL;
        }
        PyList_SET_ITEM(result, index, logged);
    }
    return result;
}

static PyObject *
owned_positive_fsum(PyObject *self, PyObject *args)
{
    PyObject *values;
    Py_ssize_t length, index;
    double numbers[64] = {0.0};
    (void)self;
    if (!PyArg_ParseTuple(args, "O:positive_fsum", &values)) {
        return NULL;
    }
    if (!PyList_CheckExact(values)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    length = PyList_GET_SIZE(values);
    if (length > 64) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    for (index = 0; index < length; index++) {
        numbers[index] = PyFloat_AsDouble(PyList_GET_ITEM(values, index));
        if (numbers[index] == -1.0 && PyErr_Occurred()) {
            return NULL;
        }
        if (!isfinite(numbers[index]) || numbers[index] < 0.0) {
            Py_RETURN_NOTIMPLEMENTED;
        }
    }
    return PyFloat_FromDouble(owned_positive_sum(numbers, (size_t)length));
}

static PyMethodDef owned_methods[] = {
    {"excerpt_window_owned", owned_excerpt_window, METH_VARARGS, "Complete ordinary-query native C window."},
    {"log1p_values", owned_log1p_values, METH_VARARGS, "Frequency-domain floating-point diagnostic."},
    {"positive_fsum", owned_positive_fsum, METH_VARARGS, "Frequency-domain partial-summation diagnostic."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef owned_module = {
    PyModuleDef_HEAD_INIT,
    "_language_c_owned",
    "Isolated C control for the same complete owned-window boundary as Rust.",
    -1,
    owned_methods,
    NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC
PyInit__language_c_owned(void)
{
    return PyModule_Create(&owned_module);
}
