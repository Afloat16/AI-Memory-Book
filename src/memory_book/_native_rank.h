/* Batch counterparts of store.py's unchanged ranking and source loops.
 * Unsupported signatures return NotImplemented before callbacks or writes.
 * All offsets remain Python integers and Unicode code-point counts.
 */
#include <math.h>
#include <stdlib.h>

static int
rank_string_keys(PyObject *mapping)
{
    PyObject *key, *value;
    Py_ssize_t position = 0;
    if (!PyDict_CheckExact(mapping)) return 0;
    while (PyDict_Next(mapping, &position, &key, &value)) {
        if (!PyUnicode_CheckExact(key)) return 0;
    }
    return 1;
}

static int
rank_finite_float(PyObject *value)
{
    return value != NULL && PyFloat_CheckExact(value)
        && isfinite(PyFloat_AS_DOUBLE(value));
}

static int
rank_string_set(PyObject *value)
{
    PyObject *iterator, *item;
    int valid = 1;
    if (!PySet_CheckExact(value)) return 0;
    iterator = PyObject_GetIter(value);
    if (iterator == NULL) return -1;
    while ((item = PyIter_Next(iterator)) != NULL) {
        valid = PyUnicode_CheckExact(item);
        Py_DECREF(item);
        if (!valid) break;
    }
    Py_DECREF(iterator);
    return PyErr_Occurred() ? -1 : valid;
}

static int
rank_number_map(PyObject *mapping, int integers)
{
    PyObject *key, *value;
    Py_ssize_t position = 0;
    if (!rank_string_keys(mapping)) return 0;
    while (PyDict_Next(mapping, &position, &key, &value)) {
        if (integers ? !PyLong_CheckExact(value) : !rank_finite_float(value)) return 0;
    }
    return 1;
}

static int
rank_ssize(PyObject *value, Py_ssize_t *result)
{
    if (!PyLong_CheckExact(value)) return 0;
    *result = PyLong_AsSsize_t(value);
    if (*result == -1 && PyErr_Occurred()) {
        if (!PyErr_ExceptionMatches(PyExc_OverflowError)) return -1;
        PyErr_Clear();
        return 0;
    }
    return 1;
}

static PyObject *
rank_required(PyObject *mapping, const char *key)
{
    PyObject *value = PyDict_GetItemString(mapping, key);
    if (value == NULL && !PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, key);
    return value;
}


static PyObject *
rank_owned_required(PyObject *mapping, const char *key)
{
    PyObject *value = rank_required(mapping, key);
    Py_XINCREF(value);
    return value;
}

static PyObject *
rank_get_default(PyObject *mapping, PyObject *identity, PyObject *fallback)
{
    PyObject *value = PyDict_GetItemWithError(mapping, identity);
    if (value == NULL) {
        if (PyErr_Occurred()) return NULL;
        value = fallback;
    }
    Py_INCREF(value);
    return value;
}

/* Re-read each operand at the same point as the Python expression. A directory
 * callback may replace numbers with objects whose arithmetic has observable
 * methods or errors. Exact floats keep the C path; other values retain Python
 * numeric dispatch without replaying the callback or earlier arithmetic. */
static PyObject *
rank_score_relevance(PyObject *row, PyObject *base, PyObject *fusion)
{
    PyObject *identity = NULL, *value = NULL, *product = NULL;
    PyObject *exact_part = NULL, *stem_part = NULL, *zero = NULL, *two = NULL;
    PyObject *result = NULL;
    if (base != Py_None) {
        identity = rank_owned_required(row, "id");
        if (identity == NULL) goto done;
        result = PyObject_GetItem(base, identity);
        goto done;
    }
    if (fusion == Py_None) {
        value = rank_owned_required(row, "rank");
        if (value != NULL) result = PyNumber_Negative(value);
        goto done;
    }
    zero = PyFloat_FromDouble(0.0);
    two = PyLong_FromLong(2);
    if (zero == NULL || two == NULL) goto done;
    identity = rank_owned_required(row, "id");
    if (identity == NULL) goto done;
    value = rank_get_default(PyTuple_GET_ITEM(fusion, 0), identity, zero);
    Py_CLEAR(identity);
    if (value == NULL) goto done;
    if (PyFloat_CheckExact(value)) {
        volatile double multiplied = 2.0 * PyFloat_AS_DOUBLE(value);
        volatile double divided = multiplied / PyFloat_AS_DOUBLE(PyTuple_GET_ITEM(fusion, 1));
        exact_part = PyFloat_FromDouble(divided);
        Py_CLEAR(value);
    } else {
        product = PyNumber_Multiply(two, value);
        Py_CLEAR(value);
        if (product == NULL) goto done;
        exact_part = PyNumber_TrueDivide(product, PyTuple_GET_ITEM(fusion, 1));
        Py_CLEAR(product);
    }
    if (exact_part == NULL) goto done;
    identity = rank_owned_required(row, "id");
    if (identity == NULL) goto done;
    value = rank_get_default(PyTuple_GET_ITEM(fusion, 2), identity, zero);
    Py_CLEAR(identity);
    if (value == NULL) goto done;
    if (PyFloat_CheckExact(value)) {
        volatile double divided = PyFloat_AS_DOUBLE(value) / PyFloat_AS_DOUBLE(PyTuple_GET_ITEM(fusion, 3));
        stem_part = PyFloat_FromDouble(divided);
    } else {
        stem_part = PyNumber_TrueDivide(value, PyTuple_GET_ITEM(fusion, 3));
    }
    Py_CLEAR(value);
    if (stem_part == NULL) goto done;
    if (PyFloat_CheckExact(exact_part) && PyFloat_CheckExact(stem_part)) {
        result = PyFloat_FromDouble(PyFloat_AS_DOUBLE(exact_part) + PyFloat_AS_DOUBLE(stem_part));
    } else {
        result = PyNumber_Add(exact_part, stem_part);
    }
done:
    Py_XDECREF(identity); Py_XDECREF(value); Py_XDECREF(product);
    Py_XDECREF(exact_part); Py_XDECREF(stem_part); Py_XDECREF(zero); Py_XDECREF(two);
    return result;
}

static PyObject *
rank_sort_key(PyObject *row, Py_ssize_t index, PyObject *fusion, PyObject *missing)
{
    PyObject *score = NULL, *negative = NULL, *identity = NULL;
    PyObject *a = NULL, *b = NULL, *ordinal = NULL, *result = NULL;
    score = rank_owned_required(row, "score");
    if (score == NULL) goto done;
    negative = PyNumber_Negative(score);
    Py_CLEAR(score);
    if (negative == NULL) goto done;
    if (fusion != Py_None) {
        identity = rank_owned_required(row, "id");
        if (identity == NULL) goto done;
        a = rank_get_default(PyTuple_GET_ITEM(fusion, 4), identity, missing);
        Py_CLEAR(identity);
        if (a == NULL) goto done;
        identity = rank_owned_required(row, "id");
        if (identity == NULL) goto done;
        b = rank_get_default(PyTuple_GET_ITEM(fusion, 5), identity, missing);
        Py_CLEAR(identity);
        if (b == NULL) goto done;
    }
    identity = rank_owned_required(row, "id");
    if (identity == NULL) goto done;
    ordinal = PyLong_FromSsize_t(index);
    if (ordinal == NULL) goto done;
    result = fusion != Py_None
        ? PyTuple_Pack(6, negative, a, b, identity, ordinal, row)
        : PyTuple_Pack(4, negative, identity, ordinal, row);
done:
    Py_XDECREF(score); Py_XDECREF(negative); Py_XDECREF(identity);
    Py_XDECREF(a); Py_XDECREF(b); Py_XDECREF(ordinal);
    return result;
}

static PyObject *
native_rank_candidates(PyObject *self, PyObject *args)
{
    PyObject *items, *query, *directory_tokens, *book, *base, *fusion;
    PyObject *exact = NULL, *stem = NULL, *exact_ranks = NULL, *stem_ranks = NULL;
    PyObject *work = NULL, *overlaps = NULL, *result = NULL, *keys = NULL;
    PyObject *row, *identity, *value, *directory = NULL, *space = NULL;
    PyObject *tokens = NULL, *intersection = NULL, *overlap_value = NULL;
    PyObject *score_value = NULL, *key = NULL, *missing_rank = NULL;
    PyObject *temporary = NULL, *chapter = NULL, *session = NULL;
    PyObject *relevance_object = NULL, *factor_object = NULL;
    Py_ssize_t i, count;
    double exact_scale = 1.0, stem_scale = 1.0;
    int fused, is_book, valid;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOOO:rank_candidates", &items, &query,
                          &directory_tokens, &book, &base, &fusion)) return NULL;
    if (!PyList_CheckExact(items) || !PyBool_Check(book)) Py_RETURN_NOTIMPLEMENTED;
    valid = rank_string_set(query);
    if (valid < 0) return NULL;
    if (!valid || PySet_GET_SIZE(query) == 0) Py_RETURN_NOTIMPLEMENTED;
    is_book = book == Py_True;
    if (is_book && !PyCallable_Check(directory_tokens)) Py_RETURN_NOTIMPLEMENTED;
    if (base != Py_None && !rank_number_map(base, 0)) Py_RETURN_NOTIMPLEMENTED;
    fused = fusion != Py_None;
    if (fused) {
        if (!PyTuple_CheckExact(fusion) || PyTuple_GET_SIZE(fusion) != 6) Py_RETURN_NOTIMPLEMENTED;
        exact = PyTuple_GET_ITEM(fusion, 0);
        stem = PyTuple_GET_ITEM(fusion, 2);
        exact_ranks = PyTuple_GET_ITEM(fusion, 4);
        stem_ranks = PyTuple_GET_ITEM(fusion, 5);
        if (!rank_number_map(exact, 0) || !rank_number_map(stem, 0)
                || !rank_number_map(exact_ranks, 1) || !rank_number_map(stem_ranks, 1)
                || !rank_finite_float(PyTuple_GET_ITEM(fusion, 1))
                || !rank_finite_float(PyTuple_GET_ITEM(fusion, 3))) Py_RETURN_NOTIMPLEMENTED;
        exact_scale = PyFloat_AS_DOUBLE(PyTuple_GET_ITEM(fusion, 1));
        stem_scale = PyFloat_AS_DOUBLE(PyTuple_GET_ITEM(fusion, 3));
        if (exact_scale <= 0.0 || stem_scale <= 0.0) Py_RETURN_NOTIMPLEMENTED;
    }
    count = PyList_GET_SIZE(items);
    for (i = 0; i < count; i++) {
        row = PyList_GET_ITEM(items, i);
        if (!rank_string_keys(row)) Py_RETURN_NOTIMPLEMENTED;
        identity = PyDict_GetItemString(row, "id");
        if (identity == NULL || !PyUnicode_CheckExact(identity)) Py_RETURN_NOTIMPLEMENTED;
        if (is_book) {
            value = PyDict_GetItemString(row, "chapter_title");
            if (value == NULL || !PyUnicode_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
            value = PyDict_GetItemString(row, "session_title");
            if (value == NULL || !PyUnicode_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
        }
        if (base != Py_None) {
            if (!rank_finite_float(PyDict_GetItemWithError(base, identity))) Py_RETURN_NOTIMPLEMENTED;
        } else if (!fused && !rank_finite_float(PyDict_GetItemString(row, "rank"))) {
            Py_RETURN_NOTIMPLEMENTED;
        }
    }
    /* Hold a private sequence across callbacks, including exceptional ones. */
    work = PyList_GetSlice(items, 0, count);
    overlaps = PyDict_New();
    keys = PyList_New(0);
    space = PyUnicode_FromString(" ");
    missing_rank = PyLong_FromLong(97);
    if (work == NULL || overlaps == NULL || keys == NULL || space == NULL || missing_rank == NULL) goto error;
    for (i = 0; i < count; i++) {
        double title_overlap = 0.0, score;
        volatile double bonus, factor;
        row = PyList_GET_ITEM(work, i);
        if (is_book) {
            chapter = rank_owned_required(row, "chapter_title");
            if (chapter == NULL) goto error;
            temporary = PyUnicode_CheckExact(chapter)
                ? PyUnicode_Concat(chapter, space) : PyNumber_Add(chapter, space);
            Py_CLEAR(chapter);
            if (temporary == NULL) goto error;
            session = rank_owned_required(row, "session_title");
            if (session == NULL) goto error;
            directory = PyUnicode_CheckExact(temporary) && PyUnicode_CheckExact(session)
                ? PyUnicode_Concat(temporary, session) : PyNumber_Add(temporary, session);
            Py_CLEAR(temporary); Py_CLEAR(session);
            if (directory == NULL) goto error;
            overlap_value = PyDict_GetItemWithError(overlaps, directory);
            Py_XINCREF(overlap_value);
            if (overlap_value == NULL) {
                Py_ssize_t numerator, denominator;
                if (PyErr_Occurred()) goto error;
                tokens = PyObject_CallFunctionObjArgs(directory_tokens, directory, NULL);
                if (tokens == NULL) goto error;
                intersection = PyNumber_And(query, tokens);
                Py_CLEAR(tokens);
                if (intersection == NULL) goto error;
                numerator = PyObject_Length(intersection);
                Py_CLEAR(intersection);
                if (numerator < 0) goto error;
                denominator = PySet_GET_SIZE(query);
                if (denominator == 0) {
                    PyErr_SetString(PyExc_ZeroDivisionError, "division by zero");
                    goto error;
                }
                title_overlap = (double)numerator / (double)denominator;
                overlap_value = PyFloat_FromDouble(title_overlap);
                if (overlap_value == NULL || PyDict_SetItem(overlaps, directory, overlap_value) < 0) goto error;
            } else {
                title_overlap = PyFloat_AS_DOUBLE(overlap_value);
            }
            Py_CLEAR(overlap_value);
            Py_CLEAR(directory);
        }
        relevance_object = rank_score_relevance(row, base, fusion);
        if (relevance_object == NULL) goto error;
        bonus = 0.15 * title_overlap;
        factor = is_book ? 1.0 + bonus : 1.0;
        if (PyFloat_CheckExact(relevance_object)) {
            score = PyFloat_AS_DOUBLE(relevance_object) * factor;
            score_value = PyFloat_FromDouble(score);
        } else {
            factor_object = is_book ? PyFloat_FromDouble(factor) : PyLong_FromLong(1);
            if (factor_object == NULL) goto error;
            score_value = PyNumber_Multiply(relevance_object, factor_object);
            Py_CLEAR(factor_object);
        }
        Py_CLEAR(relevance_object);
        if (score_value == NULL || PyDict_SetItemString(row, "score", score_value) < 0) goto error;
        Py_CLEAR(score_value);
    }
    /* Build keys after every callback, just as list.sort(key=...) does. */
    for (i = 0; i < count; i++) {
        row = PyList_GET_ITEM(work, i);
        key = rank_sort_key(row, i, fusion, missing_rank);
        if (key == NULL || PyList_Append(keys, key) < 0) goto error;
        Py_CLEAR(key);
    }
    if (PyList_Sort(keys) < 0) goto error;
    result = PyList_New(count);
    if (result == NULL) goto error;
    for (i = 0; i < count; i++) {
        key = PyList_GET_ITEM(keys, i);
        row = PyTuple_GET_ITEM(key, PyTuple_GET_SIZE(key) - 1);
        Py_INCREF(row);
        PyList_SET_ITEM(result, i, row);
    }
    key = NULL;
    goto done;
error:
    Py_CLEAR(result);
done:
    Py_XDECREF(work); Py_XDECREF(overlaps); Py_XDECREF(keys);
    Py_XDECREF(space); Py_XDECREF(missing_rank); Py_XDECREF(directory);
    Py_XDECREF(tokens); Py_XDECREF(intersection); Py_XDECREF(overlap_value);
    Py_XDECREF(score_value); Py_XDECREF(temporary); Py_XDECREF(key);
    Py_XDECREF(chapter); Py_XDECREF(session);
    Py_XDECREF(relevance_object); Py_XDECREF(factor_object);
    return result;
}

static int
rank_novelty_rows(PyObject *rows, PyObject *matched)
{
    Py_ssize_t i;
    for (i = 0; i < PyList_GET_SIZE(rows); i++) {
        PyObject *row = PyList_GET_ITEM(rows, i), *rid, *terms;
        int valid;
        if (!rank_string_keys(row)) return 0;
        rid = PyDict_GetItemString(row, "rid");
        if (rid == NULL || !PyLong_CheckExact(rid)
                || !rank_finite_float(PyDict_GetItemString(row, "score"))) return 0;
        terms = PyDict_GetItemWithError(matched, rid);
        if (terms == NULL) return PyErr_Occurred() ? -1 : 0;
        valid = rank_string_set(terms);
        if (valid != 1) return valid;
    }
    return 1;
}

static PyObject *
native_select_novelty(PyObject *self, PyObject *args)
{
    PyObject *pool, *deferred_input, *matched, *query_value, *limit_value;
    PyObject *chosen = NULL, *pending = NULL, *deferred = NULL, *covered = NULL;
    PyObject *difference = NULL, *result = NULL, *item, *rid, *terms, *joined;
    PyObject *map_key, *map_value;
    Py_ssize_t query_count, limit, i, position = 0;
    int valid;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOO:select_novelty", &pool, &deferred_input,
                          &matched, &query_value, &limit_value)) return NULL;
    if (!PyList_CheckExact(pool) || !PyList_CheckExact(deferred_input)
            || !PyDict_CheckExact(matched) || PyList_GET_SIZE(pool) == 0) Py_RETURN_NOTIMPLEMENTED;
    valid = rank_ssize(query_value, &query_count);
    if (valid < 0) return NULL;
    if (!valid || query_count <= 0 || query_count > 9007199254740992LL) Py_RETURN_NOTIMPLEMENTED;
    valid = rank_ssize(limit_value, &limit);
    if (valid < 0) return NULL;
    if (!valid) Py_RETURN_NOTIMPLEMENTED;
    while (PyDict_Next(matched, &position, &map_key, &map_value)) {
        if (!PyLong_CheckExact(map_key)) Py_RETURN_NOTIMPLEMENTED;
    }
    valid = rank_novelty_rows(pool, matched);
    if (valid < 0) return NULL;
    if (!valid) Py_RETURN_NOTIMPLEMENTED;
    valid = rank_novelty_rows(deferred_input, matched);
    if (valid < 0) return NULL;
    if (!valid) Py_RETURN_NOTIMPLEMENTED;
    chosen = PyList_GetSlice(pool, 0, 1);
    pending = PyList_GetSlice(pool, 1, PyList_GET_SIZE(pool));
    deferred = deferred_input;
    Py_INCREF(deferred);
    item = PyList_GET_ITEM(pool, 0);
    rid = PyDict_GetItemString(item, "rid");
    covered = PySet_New(PyDict_GetItemWithError(matched, rid));
    if (chosen == NULL || pending == NULL || covered == NULL) goto error;
    while ((PyList_GET_SIZE(pending) || PyList_GET_SIZE(deferred)) && PyList_GET_SIZE(chosen) < limit) {
        Py_ssize_t best = 0;
        double best_score = 0.0;
        if (PyList_GET_SIZE(pending) == 0) {
            Py_DECREF(pending);
            pending = deferred;
            deferred = PyList_New(0);
            if (deferred == NULL) goto error;
        }
        for (i = 0; i < PyList_GET_SIZE(pending); i++) {
            double score;
            volatile double ratio, factor;
            item = PyList_GET_ITEM(pending, i);
            rid = PyDict_GetItemString(item, "rid");
            terms = PyDict_GetItemWithError(matched, rid);
            difference = PyNumber_Subtract(terms, covered);
            if (difference == NULL) goto error;
            ratio = (double)PySet_GET_SIZE(difference) / (double)query_count;
            Py_CLEAR(difference);
            factor = 1.0 + ratio;
            score = PyFloat_AS_DOUBLE(PyDict_GetItemString(item, "score")) * factor;
            if (i == 0 || score > best_score) { best = i; best_score = score; }
        }
        item = PyList_GET_ITEM(pending, best);
        Py_INCREF(item);
        if (PySequence_DelItem(pending, best) < 0 || PyList_Append(chosen, item) < 0) {
            Py_DECREF(item);
            goto error;
        }
        rid = PyDict_GetItemString(item, "rid");
        terms = PyDict_GetItemWithError(matched, rid);
        joined = PyNumber_InPlaceOr(covered, terms);
        Py_DECREF(item);
        if (joined == NULL) goto error;
        Py_SETREF(covered, joined);
    }
    result = PySequence_Concat(chosen, pending);
    if (result == NULL) goto error;
    joined = PySequence_Concat(result, deferred);
    Py_SETREF(result, joined);
    goto done;
error:
    Py_CLEAR(result);
done:
    Py_XDECREF(chosen); Py_XDECREF(pending); Py_XDECREF(deferred);
    Py_XDECREF(covered); Py_XDECREF(difference);
    return result;
}

typedef struct {
    Py_ssize_t index;
    Py_ssize_t length;
    Py_ssize_t allowance;
} RankAllocation;

static int
rank_allocation_compare(const void *left, const void *right)
{
    const RankAllocation *a = (const RankAllocation *)left;
    const RankAllocation *b = (const RankAllocation *)right;
    if (a->length != b->length) return a->length < b->length ? -1 : 1;
    return a->index < b->index ? -1 : a->index != b->index;
}

static PyObject *
native_context_allocations(PyObject *self, PyObject *args)
{
    static const char *fields[] = {"id", "project_id", "session_id", "created_at", "content"};
    PyObject *pages, *budget_value, *selected = NULL, *result = NULL;
    PyObject *row, *header = NULL, *entry = NULL, *allowance_value = NULL;
    Py_ssize_t budget, minimum = 0, overhead = 0, count, i, selected_count, remaining;
    RankAllocation *order = NULL;
    Py_ssize_t *allowances = NULL;
    int j, valid;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO:context_allocations", &pages, &budget_value)) return NULL;
    if (!PyList_CheckExact(pages)) Py_RETURN_NOTIMPLEMENTED;
    valid = rank_ssize(budget_value, &budget);
    if (valid < 0) return NULL;
    if (!valid || budget < 0) Py_RETURN_NOTIMPLEMENTED;
    count = PyList_GET_SIZE(pages);
    for (i = 0; i < count; i++) {
        row = PyList_GET_ITEM(pages, i);
        if (!rank_string_keys(row)) Py_RETURN_NOTIMPLEMENTED;
        for (j = 0; j < 5; j++) {
            PyObject *value = PyDict_GetItemString(row, fields[j]);
            if (value == NULL || !PyUnicode_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
        }
    }
    selected = PyList_New(0);
    if (selected == NULL) goto error;
    for (i = 0; i < count; i++) {
        Py_ssize_t citation, length, reserve;
        int fits, keep;
        row = PyList_GET_ITEM(pages, i);
        header = PyUnicode_FromFormat("[%U] %U / %U | %U\n",
            PyDict_GetItemString(row, "id"), PyDict_GetItemString(row, "project_id"),
            PyDict_GetItemString(row, "session_id"), PyDict_GetItemString(row, "created_at"));
        if (header == NULL) goto error;
        citation = PyUnicode_GET_LENGTH(header);
        if (citation > PY_SSIZE_T_MAX - 2) { PyErr_SetString(PyExc_OverflowError, "citation is too long"); goto error; }
        citation += PyList_GET_SIZE(selected) ? 2 : 0;
        length = PyUnicode_GET_LENGTH(PyDict_GetItemString(row, "content"));
        reserve = length < 120 ? length : 120;
        fits = citation <= budget - minimum && reserve <= budget - minimum - citation;
        keep = fits || (PyList_GET_SIZE(selected) == 0 && budget > citation && budget - citation > 8);
        if (keep) {
            entry = PyTuple_Pack(2, row, header);
            if (entry == NULL || PyList_Append(selected, entry) < 0) goto error;
            Py_CLEAR(entry);
            overhead += citation;
            if (fits) minimum += citation + reserve;
        }
        Py_CLEAR(header);
        if (!fits) break;
    }
    selected_count = PyList_GET_SIZE(selected);
    if (selected_count > 0) {
        if ((size_t)selected_count > ((size_t)-1) / sizeof(RankAllocation)
                || (size_t)selected_count > ((size_t)-1) / sizeof(Py_ssize_t)) {
            PyErr_NoMemory(); goto error;
        }
        order = PyMem_Malloc((size_t)selected_count * sizeof(RankAllocation));
        allowances = PyMem_Malloc((size_t)selected_count * sizeof(Py_ssize_t));
        if (order == NULL || allowances == NULL) { PyErr_NoMemory(); goto error; }
    }
    for (i = 0; i < selected_count; i++) {
        row = PyTuple_GET_ITEM(PyList_GET_ITEM(selected, i), 0);
        order[i].index = i;
        order[i].length = PyUnicode_GET_LENGTH(PyDict_GetItemString(row, "content"));
    }
    if (selected_count > 1) qsort(order, (size_t)selected_count, sizeof(RankAllocation), rank_allocation_compare);
    remaining = budget - overhead;
    for (i = 0; i < selected_count; i++) {
        Py_ssize_t allowance = remaining / (selected_count - i);
        if (order[i].length < allowance) allowance = order[i].length;
        allowances[order[i].index] = allowance;
        remaining -= allowance;
    }
    result = PyList_New(selected_count);
    if (result == NULL) goto error;
    for (i = 0; i < selected_count; i++) {
        PyObject *pair = PyList_GET_ITEM(selected, i);
        allowance_value = PyLong_FromSsize_t(allowances[i]);
        if (allowance_value == NULL) goto error;
        entry = PyTuple_Pack(3, PyTuple_GET_ITEM(pair, 0), PyTuple_GET_ITEM(pair, 1), allowance_value);
        Py_CLEAR(allowance_value);
        if (entry == NULL) goto error;
        PyList_SET_ITEM(result, i, entry);
        entry = NULL;
    }
    goto done;
error:
    Py_CLEAR(result);
done:
    Py_XDECREF(selected); Py_XDECREF(header); Py_XDECREF(entry); Py_XDECREF(allowance_value);
    PyMem_Free(order); PyMem_Free(allowances);
    return result;
}

static PyObject *
rank_sequence_item(PyObject *sequence, Py_ssize_t index)
{
    return PyTuple_CheckExact(sequence) ? PyTuple_GET_ITEM(sequence, index) : PyList_GET_ITEM(sequence, index);
}

static PyObject *
native_refs_from_parsed(PyObject *self, PyObject *args)
{
    PyObject *refs, *spans, *result = NULL, *copy = NULL;
    PyObject *sum = NULL, *turn_start = NULL, *turn_end = NULL;
    Py_ssize_t i, j, count;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO:refs_from_parsed", &refs, &spans)) return NULL;
    if (!PyList_CheckExact(refs) || !(PyList_CheckExact(spans) || PyTuple_CheckExact(spans))) Py_RETURN_NOTIMPLEMENTED;
    count = PySequence_Size(spans);
    for (i = 0; i < count; i++) {
        PyObject *span = rank_sequence_item(spans, i);
        if (!(PyTuple_CheckExact(span) || PyList_CheckExact(span)) || PySequence_Size(span) != 2
                || !PyLong_CheckExact(rank_sequence_item(span, 0))
                || !PyLong_CheckExact(rank_sequence_item(span, 1))) Py_RETURN_NOTIMPLEMENTED;
    }
    for (i = 0; i < PyList_GET_SIZE(refs); i++) {
        PyObject *ref = PyList_GET_ITEM(refs, i), *value;
        if (!rank_string_keys(ref)) Py_RETURN_NOTIMPLEMENTED;
        value = PyDict_GetItemString(ref, "start");
        if (value == NULL || !PyLong_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
        value = PyDict_GetItemString(ref, "end");
        if (value == NULL || !PyLong_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
        value = PyDict_GetItemString(ref, "turn_start");
        if (value == NULL || !PyLong_CheckExact(value)) Py_RETURN_NOTIMPLEMENTED;
    }
    result = PyList_New(0);
    if (result == NULL) goto error;
    for (i = 0; i < count; i++) {
        PyObject *span = rank_sequence_item(spans, i);
        PyObject *lo = rank_sequence_item(span, 0), *hi = rank_sequence_item(span, 1);
        for (j = 0; j < PyList_GET_SIZE(refs); j++) {
            PyObject *ref = PyList_GET_ITEM(refs, j);
            PyObject *original_start = PyDict_GetItemString(ref, "start");
            PyObject *original_end = PyDict_GetItemString(ref, "end");
            PyObject *original_turn = PyDict_GetItemString(ref, "turn_start");
            PyObject *start, *end;
            int comparison = PyObject_RichCompareBool(original_start, lo, Py_GT);
            if (comparison < 0) goto error;
            start = comparison ? original_start : lo;
            comparison = PyObject_RichCompareBool(original_end, hi, Py_LT);
            if (comparison < 0) goto error;
            end = comparison ? original_end : hi;
            comparison = PyObject_RichCompareBool(start, end, Py_LT);
            if (comparison < 0) goto error;
            if (!comparison) continue;
            sum = PyNumber_Add(original_turn, start);
            if (sum == NULL) goto error;
            turn_start = PyNumber_Subtract(sum, original_start);
            Py_CLEAR(sum);
            if (turn_start == NULL) goto error;
            sum = PyNumber_Add(original_turn, end);
            if (sum == NULL) goto error;
            turn_end = PyNumber_Subtract(sum, original_start);
            Py_CLEAR(sum);
            if (turn_end == NULL) goto error;
            copy = PyDict_Copy(ref);
            if (copy == NULL || PyDict_SetItemString(copy, "start", start) < 0
                    || PyDict_SetItemString(copy, "end", end) < 0
                    || PyDict_SetItemString(copy, "turn_start", turn_start) < 0
                    || PyDict_SetItemString(copy, "turn_end", turn_end) < 0
                    || PyList_Append(result, copy) < 0) goto error;
            Py_CLEAR(copy); Py_CLEAR(turn_start); Py_CLEAR(turn_end);
        }
    }
    goto done;
error:
    Py_CLEAR(result);
done:
    Py_XDECREF(copy); Py_XDECREF(sum); Py_XDECREF(turn_start); Py_XDECREF(turn_end);
    return result;
}
