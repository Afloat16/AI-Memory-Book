/* The complete existing excerpt-window loop, with bounded native storage.
 *
 * This keeps the same candidates, tuple ordering, Counter insertion order and
 * math functions.  Only ordinary, validated state enters this path.  Returning
 * NotImplemented happens before sorting or calling a supplied dependency so
 * that the Python reference can handle unusual inputs without replaying work.
 */
#ifndef MEMORY_BOOK_NATIVE_EXCERPT_H
#define MEMORY_BOOK_NATIVE_EXCERPT_H

#include <stdint.h>
#include <stdlib.h>

typedef struct {
    Py_ssize_t position;
    unsigned int term;
} memory_book_excerpt_hit;

typedef struct {
    Py_ssize_t lo;
    Py_ssize_t hi;
    uint64_t mask;
} memory_book_excerpt_unit;

static int
excerpt_window_compare_start(const void *left, const void *right)
{
    Py_ssize_t a = *(const Py_ssize_t *)left;
    Py_ssize_t b = *(const Py_ssize_t *)right;
    return (a > b) - (a < b);
}

static Py_ssize_t
excerpt_window_bisect_lo(memory_book_excerpt_unit *units, Py_ssize_t count,
                         Py_ssize_t value, int right)
{
    Py_ssize_t lo = 0, hi = count;
    while (lo < hi) {
        Py_ssize_t mid = lo + (hi - lo) / 2;
        if (units[mid].lo < value || (right && units[mid].lo == value)) {
            lo = mid + 1;
        }
        else {
            hi = mid;
        }
    }
    return lo;
}

static Py_ssize_t
excerpt_window_bisect_hi(memory_book_excerpt_unit *units, Py_ssize_t count,
                         Py_ssize_t value)
{
    Py_ssize_t lo = 0, hi = count;
    while (lo < hi) {
        Py_ssize_t mid = lo + (hi - lo) / 2;
        if (units[mid].hi <= value) {
            lo = mid + 1;
        }
        else {
            hi = mid;
        }
    }
    return lo;
}

static unsigned int
excerpt_window_bit_count(uint64_t value)
{
    unsigned int count = 0;
    while (value) {
        value &= value - 1;
        count++;
    }
    return count;
}

static PyObject *
excerpt_window_placement(Py_ssize_t position_sum, Py_ssize_t count,
                          PyObject *start, PyObject *width, PyObject *one_third)
{
    PyObject *numerator = NULL, *denominator = NULL;
    PyObject *mean = NULL, *shifted = NULL, *scaled = NULL, *delta = NULL;
    PyObject *result = NULL;

    if (!count) {
        return PyFloat_FromDouble(1.0);
    }
    /* Integer true division must precede conversion to floating point.  A
     * double cast of the sum can round twice when it exceeds 2**53. */
    numerator = PyLong_FromSsize_t(position_sum);
    denominator = PyLong_FromSsize_t(count);
    if (numerator == NULL || denominator == NULL) {
        goto done;
    }
    mean = PyNumber_TrueDivide(numerator, denominator);
    if (mean == NULL) {
        goto done;
    }
    shifted = PyNumber_Subtract(mean, start);
    if (shifted == NULL) {
        goto done;
    }
    scaled = PyNumber_TrueDivide(shifted, width);
    if (scaled == NULL) {
        goto done;
    }
    delta = PyNumber_Subtract(scaled, one_third);
    if (delta != NULL) {
        result = PyNumber_Absolute(delta);
    }

done:
    Py_XDECREF(numerator);
    Py_XDECREF(denominator);
    Py_XDECREF(mean);
    Py_XDECREF(shifted);
    Py_XDECREF(scaled);
    Py_XDECREF(delta);
    return result;
}

static PyObject *
excerpt_window_render(PyObject *text, Py_ssize_t start, Py_ssize_t end)
{
    PyObject *slice = NULL, *ellipsis = NULL, *rendered = NULL, *temporary = NULL;
    PyObject *span = NULL, *spans = NULL, *result = NULL;

    slice = PyUnicode_Substring(text, start, end);
    ellipsis = PyUnicode_FromOrdinal(0x2026);
    if (slice == NULL || ellipsis == NULL) {
        goto done;
    }
    rendered = start ? PyUnicode_Concat(ellipsis, slice) : Py_NewRef(slice);
    if (rendered == NULL) {
        goto done;
    }
    if (end < PyUnicode_GET_LENGTH(text)) {
        temporary = PyUnicode_Concat(rendered, ellipsis);
        if (temporary == NULL) {
            goto done;
        }
        Py_SETREF(rendered, temporary);
        temporary = NULL;
    }
    span = Py_BuildValue("(nn)", start, end);
    spans = PyList_New(1);
    if (span == NULL || spans == NULL) {
        goto done;
    }
    PyList_SET_ITEM(spans, 0, span);
    span = NULL;
    result = PyTuple_Pack(2, rendered, spans);

done:
    Py_XDECREF(slice);
    Py_XDECREF(ellipsis);
    Py_XDECREF(rendered);
    Py_XDECREF(temporary);
    Py_XDECREF(span);
    Py_XDECREF(spans);
    return result;
}

static PyObject *
native_excerpt_window(PyObject *self, PyObject *args)
{
    PyObject *text, *q, *positions, *width_object, *evidence_units, *log1p, *fsum;
    PyObject *q_snapshot = NULL, *term_ids = NULL, *units = NULL, *one_third = NULL;
    PyObject *best_score = NULL, *score = NULL, *start_object = NULL;
    PyObject *placement = NULL, *log_values = NULL, *frequency = NULL;
    PyObject *negative_placement = NULL, *negative_start = NULL;
    PyObject *coverage = NULL, *completeness = NULL, *result = NULL;
    memory_book_excerpt_hit *hits = NULL;
    memory_book_excerpt_unit *all_units = NULL, *matched = NULL;
    Py_ssize_t *starts = NULL;
    Py_ssize_t counts[64] = {0};
    int next[64], previous[64], head = -1, tail = -1;
    Py_ssize_t length, width, last_start, q_count, hit_count, term_count = 0;
    Py_ssize_t unit_count = 0, matched_count = 0, starts_count = 0;
    Py_ssize_t index, left = 0, right = 0, position_sum = 0, active = 0;
    Py_ssize_t best_start = 0, previous_start = -1;
    int unsupported = 0;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOOOO:excerpt_window", &text, &q, &positions,
                          &width_object, &evidence_units, &log1p, &fsum)) {
        return NULL;
    }
    if (!PyUnicode_CheckExact(text) || !PyList_CheckExact(q)
            || !PyList_CheckExact(positions) || !PyLong_CheckExact(width_object)
            || !PyCallable_Check(evidence_units) || !PyCallable_Check(log1p)
            || !PyCallable_Check(fsum)) {
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
    q_count = PyList_GET_SIZE(q);
    hit_count = PyList_GET_SIZE(positions);
    /* The public query path supplies at most 64 terms, 40 hits per term.
     * Wider prepared queries retain Python's unlimited integer masks. */
    if (width <= 0 || width >= length || q_count > 64 || hit_count > 2560
            || (hit_count && length > PY_SSIZE_T_MAX / hit_count)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    last_start = length - width;
    /* Allocations can trigger GC callbacks.  Hold query strings independently
     * of the caller's mutable list, and inspect positions after allocations. */
    q_snapshot = PyList_AsTuple(q);
    if (q_snapshot == NULL) {
        goto done;
    }
    q_count = PyTuple_GET_SIZE(q_snapshot);
    if (q_count > 64) {
        unsupported = 1;
        goto done;
    }
    for (index = 0; index < q_count; index++) {
        if (!PyUnicode_CheckExact(PyTuple_GET_ITEM(q_snapshot, index))) {
            unsupported = 1;
            goto done;
        }
    }
    term_ids = PyDict_New();
    if (term_ids == NULL) {
        goto done;
    }
    for (index = 0; index < q_count; index++) {
        PyObject *term = PyTuple_GET_ITEM(q_snapshot, index);
        PyObject *identifier = PyDict_GetItemWithError(term_ids, term);
        if (identifier == NULL) {
            if (PyErr_Occurred()) {
                goto done;
            }
            identifier = PyLong_FromSsize_t(term_count++);
            if (identifier == NULL) {
                goto done;
            }
            if (PyDict_SetItem(term_ids, term, identifier) < 0) {
                Py_DECREF(identifier);
                goto done;
            }
            Py_DECREF(identifier);
        }
    }
    hit_count = PyList_GET_SIZE(positions);
    if (hit_count > 2560 || (hit_count && length > PY_SSIZE_T_MAX / hit_count)) {
        unsupported = 1;
        goto done;
    }
    for (index = 0; index < hit_count; index++) {
        PyObject *hit = PyList_GET_ITEM(positions, index), *identifier;
        Py_ssize_t position;
        if (!PyTuple_CheckExact(hit) || PyTuple_GET_SIZE(hit) != 2
                || !PyLong_CheckExact(PyTuple_GET_ITEM(hit, 0))
                || !PyUnicode_CheckExact(PyTuple_GET_ITEM(hit, 1))) {
            unsupported = 1;
            goto done;
        }
        position = PyLong_AsSsize_t(PyTuple_GET_ITEM(hit, 0));
        if (position == -1 && PyErr_Occurred()) {
            PyErr_Clear();
            unsupported = 1;
            goto done;
        }
        if (position < 0 || position > length) {
            unsupported = 1;
            goto done;
        }
        identifier = PyDict_GetItemWithError(term_ids, PyTuple_GET_ITEM(hit, 1));
        if (identifier == NULL) {
            if (!PyErr_Occurred()) {
                unsupported = 1;
            }
            goto done;
        }
    }
    /* No fallback is permitted beyond this point: sorting and callbacks have
     * the same observable order as the retained Python implementation. */
    if (PyList_Sort(positions) < 0) {
        goto done;
    }
    hits = PyMem_Calloc((size_t)(hit_count ? hit_count : 1), sizeof(*hits));
    starts = PyMem_Malloc((size_t)(hit_count * 3 + 2) * sizeof(*starts));
    if (hits == NULL || starts == NULL) {
        PyErr_NoMemory();
        goto done;
    }
    starts[starts_count++] = 0;
    starts[starts_count++] = last_start;
    for (index = 0; index < hit_count; index++) {
        PyObject *hit = PyList_GET_ITEM(positions, index);
        PyObject *identifier = PyDict_GetItemWithError(term_ids, PyTuple_GET_ITEM(hit, 1));
        Py_ssize_t start;
        if (identifier == NULL) {
            if (!PyErr_Occurred()) {
                PyErr_SetString(PyExc_RuntimeError, "excerpt positions changed during sorting");
            }
            goto done;
        }
        hits[index].position = PyLong_AsSsize_t(PyTuple_GET_ITEM(hit, 0));
        hits[index].term = (unsigned int)PyLong_AsLong(identifier);
        start = hits[index].position - width / 3;
        if (start < 0) {
            start = 0;
        }
        else if (start > last_start) {
            start = last_start;
        }
        starts[starts_count++] = start;
    }
    if (hit_count) {
        units = PyObject_CallFunctionObjArgs(evidence_units, text, width_object, NULL);
        if (units == NULL) {
            goto done;
        }
        if (!PyList_CheckExact(units)) {
            PyErr_SetString(PyExc_TypeError, "evidence units must be an exact list");
            goto done;
        }
        unit_count = PyList_GET_SIZE(units);
        if ((size_t)unit_count > (size_t)PY_SSIZE_T_MAX / sizeof(*all_units)) {
            PyErr_NoMemory();
            goto done;
        }
        all_units = PyMem_Calloc((size_t)(unit_count ? unit_count : 1), sizeof(*all_units));
        matched = PyMem_Calloc((size_t)(hit_count ? hit_count : 1), sizeof(*matched));
        if (all_units == NULL || matched == NULL) {
            PyErr_NoMemory();
            goto done;
        }
        for (index = 0; index < unit_count; index++) {
            PyObject *unit = PyList_GET_ITEM(units, index);
            Py_ssize_t lo, hi;
            if (!PyTuple_CheckExact(unit) || PyTuple_GET_SIZE(unit) != 2
                    || !PyLong_CheckExact(PyTuple_GET_ITEM(unit, 0))
                    || !PyLong_CheckExact(PyTuple_GET_ITEM(unit, 1))) {
                PyErr_SetString(PyExc_TypeError, "evidence units must contain exact integer pairs");
                goto done;
            }
            lo = PyLong_AsSsize_t(PyTuple_GET_ITEM(unit, 0));
            if (lo == -1 && PyErr_Occurred()) {
                goto done;
            }
            hi = PyLong_AsSsize_t(PyTuple_GET_ITEM(unit, 1));
            if (hi == -1 && PyErr_Occurred()) {
                goto done;
            }
            if (lo < 0 || lo >= hi || hi > length
                    || (index && all_units[index - 1].hi > lo)) {
                PyErr_SetString(PyExc_ValueError, "evidence units must be ordered nonoverlapping source spans");
                goto done;
            }
            all_units[index].lo = lo;
            all_units[index].hi = hi;
        }
        for (index = 0; index < hit_count; index++) {
            Py_ssize_t unit = excerpt_window_bisect_lo(all_units, unit_count, hits[index].position, 1) - 1;
            if (unit >= 0 && hits[index].position < all_units[unit].hi) {
                /* Sorted occurrences encounter unit indices monotonically.
                 * This is the original masks dict in sorted-key order. */
                if (!matched_count || matched[matched_count - 1].lo != all_units[unit].lo) {
                    matched[matched_count++] = all_units[unit];
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
    one_third = PyFloat_FromDouble(1.0 / 3.0);
    best_score = Py_BuildValue("(iiddi)", -1, -1, -1.0, -1.0, -1);
    if (one_third == NULL || best_score == NULL) {
        goto done;
    }
    for (index = 0; index < 64; index++) {
        next[index] = previous[index] = -1;
    }
    for (index = 0; index < starts_count; index++) {
        Py_ssize_t start = starts[index], end = start + width;
        Py_ssize_t first_unit, last_unit, unit, count, log_index = 0;
        uint64_t whole_terms = 0;
        int term, better;
        if (start == previous_start) {
            continue;
        }
        previous_start = start;
        if (PyErr_CheckSignals() < 0) {
            goto done;
        }
        while (right < hit_count && hits[right].position < end) {
            term = (int)hits[right].term;
            if (!counts[term]++) {
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
            whole_terms |= matched[unit].mask;
        }
        count = right - left;
        start_object = PyLong_FromSsize_t(start);
        if (start_object == NULL) {
            goto done;
        }
        placement = excerpt_window_placement(position_sum, count, start_object, width_object, one_third);
        if (placement == NULL) {
            goto done;
        }
        log_values = PyList_New(active);
        if (log_values == NULL) {
            goto done;
        }
        /* The linked order models dict deletion and reinsertion, not term-id
         * order.  Invoke the original math functions on the same integer
         * frequencies; do not use libm log1p or an ordinary C floating sum. */
        for (term = head; term >= 0; term = next[term]) {
            PyObject *number = PyLong_FromSsize_t(counts[term]);
            PyObject *logged;
            if (number == NULL) {
                goto done;
            }
            logged = PyObject_CallOneArg(log1p, number);
            Py_DECREF(number);
            if (logged == NULL) {
                goto done;
            }
            PyList_SET_ITEM(log_values, log_index++, logged);
        }
        frequency = PyObject_CallOneArg(fsum, log_values);
        if (frequency == NULL) {
            goto done;
        }
        coverage = PyLong_FromSsize_t(active);
        completeness = PyLong_FromUnsignedLong(excerpt_window_bit_count(whole_terms));
        negative_placement = PyNumber_Negative(placement);
        negative_start = PyNumber_Negative(start_object);
        if (coverage == NULL || completeness == NULL || negative_placement == NULL || negative_start == NULL) {
            goto done;
        }
        score = PyTuple_Pack(5, coverage, completeness, frequency, negative_placement, negative_start);
        if (score == NULL) {
            goto done;
        }
        better = PyObject_RichCompareBool(score, best_score, Py_GT);
        if (better < 0) {
            goto done;
        }
        if (better) {
            best_start = start;
            Py_SETREF(best_score, score);
            score = NULL;
        }
        Py_CLEAR(score);
        Py_CLEAR(start_object);
        Py_CLEAR(placement);
        Py_CLEAR(log_values);
        Py_CLEAR(frequency);
        Py_CLEAR(coverage);
        Py_CLEAR(completeness);
        Py_CLEAR(negative_placement);
        Py_CLEAR(negative_start);
    }
    result = excerpt_window_render(text, best_start, best_start + width);

done:
    Py_XDECREF(q_snapshot);
    Py_XDECREF(term_ids);
    Py_XDECREF(units);
    Py_XDECREF(one_third);
    Py_XDECREF(best_score);
    Py_XDECREF(score);
    Py_XDECREF(start_object);
    Py_XDECREF(placement);
    Py_XDECREF(log_values);
    Py_XDECREF(frequency);
    Py_XDECREF(coverage);
    Py_XDECREF(completeness);
    Py_XDECREF(negative_placement);
    Py_XDECREF(negative_start);
    PyMem_Free(hits);
    PyMem_Free(starts);
    PyMem_Free(all_units);
    PyMem_Free(matched);
    return unsupported ? Py_NewRef(Py_NotImplemented) : result;
}

#endif
