/* Exact source-unit and source-map loops, included by _native.c.
 *
 * The Python wrapper certifies the fixed regexes and callable identities.
 * Coordinates remain CPython Unicode code points.  The projection helpers
 * return NotImplemented before mutating the cache for unsupported/custom
 * objects; their original Python bodies retain those objects' behavior.
 */

static Py_UCS4
source_character(PyObject *text, Py_ssize_t index)
{
    return PyUnicode_READ(PyUnicode_KIND(text), PyUnicode_DATA(text), index);
}

static int
source_horizontal(Py_UCS4 character)
{
    return character == ' ' || character == '\t';
}

static int
source_add_span(PyObject *spans, Py_ssize_t start, Py_ssize_t end)
{
    PyObject *span = Py_BuildValue("(nn)", start, end);
    int status;
    if (span == NULL) {
        return -1;
    }
    status = PySet_Add(spans, span);
    Py_DECREF(span);
    return status;
}

static int
source_add_primary(PyObject *primary, PyObject *spans,
                   Py_ssize_t start, Py_ssize_t end)
{
    PyObject *span = Py_BuildValue("(nn)", start, end);
    int status;
    if (span == NULL) {
        return -1;
    }
    status = PyList_Append(primary, span);
    if (status == 0) {
        status = PySet_Add(spans, span);
    }
    Py_DECREF(span);
    return status;
}

static PyObject *
source_sorted_spans(PyObject *spans)
{
    PyObject *result = PySequence_List(spans);
    if (result != NULL && PyList_Sort(result) < 0) {
        Py_CLEAR(result);
    }
    return result;
}

/* _ROLE is anchored, case-sensitive, and consumes ASCII space/tab only. */
static Py_ssize_t
source_after_role(PyObject *text, Py_ssize_t start, Py_ssize_t end)
{
    static const char *roles[] = {"USER:", "ASSISTANT:", "SYSTEM:",
                                  "DEVELOPER:", "TOOL:"};
    static const Py_ssize_t lengths[] = {5, 10, 7, 10, 5};
    Py_ssize_t role, index;
    for (role = 0; role < 5; role++) {
        if (end - start < lengths[role]) {
            continue;
        }
        for (index = 0; index < lengths[role]; index++) {
            if (source_character(text, start + index) != (unsigned char)roles[role][index]) {
                break;
            }
        }
        if (index == lengths[role]) {
            start += lengths[role];
            while (start < end && source_horizontal(source_character(text, start))) {
                start++;
            }
            return start;
        }
    }
    return start;
}

static PyObject *
source_units_text(PyObject *text)
{
    PyObject *lines = NULL, *primary = NULL, *spans = NULL, *result = NULL;
    Py_ssize_t line_number, offset = 0, fence_start = 0, fence_size = 0;
    Py_ssize_t length = PyUnicode_GET_LENGTH(text);
    Py_UCS4 fence_character = 0;

    /* splitlines(True), unlike a scan for LF, retains every Python Unicode
     * line-boundary rule, including CRLF, VT/FF, NEL and U+2028/U+2029. */
    lines = PyUnicode_Splitlines(text, 1);
    primary = PyList_New(0);
    spans = PySet_New(NULL);
    if (lines == NULL || primary == NULL || spans == NULL) {
        goto done;
    }
    for (line_number = 0; line_number < PyList_GET_SIZE(lines); line_number++) {
        PyObject *line = PyList_GET_ITEM(lines, line_number);
        Py_ssize_t lo = offset, hi, cursor, run_start, run_size, start, end;
        Py_UCS4 character;
        offset += PyUnicode_GET_LENGTH(line);
        hi = offset;
        /* The reference strips only CR/LF here, not other splitlines ends. */
        while (hi > lo && (source_character(text, hi - 1) == '\r'
                          || source_character(text, hi - 1) == '\n')) {
            hi--;
        }
        if ((line_number & 4095) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
        if (fence_character) {
            cursor = lo;
            while (cursor < hi && cursor - lo < 3
                    && source_horizontal(source_character(text, cursor))) {
                cursor++;
            }
            run_start = cursor;
            while (cursor < hi && source_character(text, cursor) == fence_character) {
                cursor++;
            }
            run_size = cursor - run_start;
            while (cursor < hi && source_horizontal(source_character(text, cursor))) {
                cursor++;
            }
            if (run_size >= fence_size && cursor == hi) {
                if (source_add_primary(primary, spans, fence_start, hi) < 0) {
                    goto done;
                }
                fence_character = 0;
            }
            continue;
        }
        start = source_after_role(text, lo, hi);
        cursor = start;
        while (cursor < hi && cursor - start < 3
                && source_horizontal(source_character(text, cursor))) {
            cursor++;
        }
        character = cursor < hi ? source_character(text, cursor) : 0;
        if (character == '`' || character == '~') {
            run_start = cursor;
            while (cursor < hi && source_character(text, cursor) == character) {
                cursor++;
            }
            run_size = cursor - run_start;
            if (run_size >= 3) {
                int valid = 1;
                if (character == '`') {
                    for (; cursor < hi; cursor++) {
                        if (source_character(text, cursor) == '`') {
                            valid = 0;
                            break;
                        }
                    }
                }
                if (valid) {
                    fence_character = character;
                    fence_size = run_size;
                    fence_start = lo;
                    continue;
                }
            }
        }
        start = lo;
        end = hi;
        while (start < end && Py_UNICODE_ISSPACE(source_character(text, start))) {
            start++;
        }
        if (start == end) {
            continue;
        }
        while (end > start && Py_UNICODE_ISSPACE(source_character(text, end - 1))) {
            end--;
        }
        if (source_add_primary(primary, spans, start, end) < 0) {
            goto done;
        }
        cursor = start;
        for (run_start = start; run_start < end; run_start++) {
            int boundary;
            character = source_character(text, run_start);
            boundary = character == 0x3002 || character == 0xff01 || character == 0xff1f;
            if (!boundary && (character == '.' || character == '!' || character == '?')) {
                boundary = run_start + 1 == end
                    || Py_UNICODE_ISSPACE(source_character(text, run_start + 1));
            }
            if ((run_start & 65535) == 0 && PyErr_CheckSignals() < 0) {
                goto done;
            }
            if (boundary) {
                Py_ssize_t stop = run_start + 1;
                if (cursor < stop && source_add_span(spans, cursor, stop) < 0) {
                    goto done;
                }
                cursor = stop;
                while (cursor < end && Py_UNICODE_ISSPACE(source_character(text, cursor))) {
                    cursor++;
                }
            }
        }
        if (cursor < end && source_add_span(spans, cursor, end) < 0) {
            goto done;
        }
    }
    for (line_number = 0; line_number < PyList_GET_SIZE(primary); line_number++) {
        PyObject *span = PyList_GET_ITEM(primary, line_number);
        Py_ssize_t next, start = PyLong_AsSsize_t(PyTuple_GET_ITEM(span, 0));
        for (next = line_number + 1;
                next < PyList_GET_SIZE(primary) && next - line_number < 3; next++) {
            PyObject *neighbor = PyList_GET_ITEM(primary, next);
            Py_ssize_t end = PyLong_AsSsize_t(PyTuple_GET_ITEM(neighbor, 1));
            if (source_add_span(spans, start, end) < 0) {
                goto done;
            }
        }
    }
    if (!fence_character && length && source_add_span(spans, 0, length) < 0) {
        goto done;
    }
    result = source_sorted_spans(spans);

done:
    Py_XDECREF(lines);
    Py_XDECREF(primary);
    Py_XDECREF(spans);
    return result;
}

static PyObject *
native_source_units(PyObject *self, PyObject *args)
{
    PyObject *text;
    (void)self;
    if (!PyArg_ParseTuple(args, "O:source_units", &text)
            || require_exact_unicode(text) < 0) {
        return NULL;
    }
    return source_units_text(text);
}

/* These certificates never invoke user-defined mapping/hash/index methods.
 * bool, subclasses and arbitrary-precision coordinates take the Python path.
 * The quarter-range bound leaves room for the exact a + b - c arithmetic. */
static int
source_small_integer(PyObject *value, Py_ssize_t *number)
{
    if (value == NULL || !PyLong_CheckExact(value)) {
        return 0;
    }
    *number = PyLong_AsSsize_t(value);
    if (*number == -1 && PyErr_Occurred()) {
        PyErr_Clear();  /* exact PyLong overflow is an unsupported fast input */
        return 0;
    }
    return *number >= -(PY_SSIZE_T_MAX / 4) && *number <= PY_SSIZE_T_MAX / 4;
}

static int
source_named_dict(PyObject *value)
{
    PyObject *key, *item;
    Py_ssize_t position = 0;
    if (!PyDict_CheckExact(value)) {
        return 0;
    }
    while (PyDict_Next(value, &position, &key, &item)) {
        if (!PyUnicode_CheckExact(key)) {
            return 0;
        }
    }
    return 1;
}

static int
source_keyed_dict(PyObject *value)
{
    PyObject *key, *item;
    Py_ssize_t position = 0, index;
    if (!PyDict_CheckExact(value)) {
        return 0;
    }
    while (PyDict_Next(value, &position, &key, &item)) {
        if (!PyTuple_CheckExact(key) || PyTuple_GET_SIZE(key) != 2
                || !PyUnicode_CheckExact(PyTuple_GET_ITEM(key, 0))
                || !source_small_integer(PyTuple_GET_ITEM(key, 1), &index)) {
            return 0;
        }
    }
    return 1;
}

static int
source_unit_pair(PyObject *value, Py_ssize_t *start, Py_ssize_t *end)
{
    return PyTuple_CheckExact(value) && PyTuple_GET_SIZE(value) == 2
        && source_small_integer(PyTuple_GET_ITEM(value, 0), start)
        && source_small_integer(PyTuple_GET_ITEM(value, 1), end);
}

/* bisect_left(units, (position,)): an equal first item sorts after the
 * singleton key, regardless of the unit's second value.  Inspect only the
 * tuple items that Python's bisection reads, retaining malformed-list fallbacks.
 */
static int
source_bisect(PyObject *units, Py_ssize_t position, Py_ssize_t *result)
{
    Py_ssize_t lo = 0, hi = PyList_GET_SIZE(units), value;
    while (lo < hi) {
        Py_ssize_t mid = lo + (hi - lo) / 2;
        PyObject *unit = PyList_GET_ITEM(units, mid);
        if (!PyTuple_CheckExact(unit) || PyTuple_GET_SIZE(unit) != 2
                || !source_small_integer(PyTuple_GET_ITEM(unit, 0), &value)) {
            return 0;
        }
        if (value < position) {
            lo = mid + 1;
        }
        else {
            hi = mid;
        }
    }
    *result = lo;
    return 1;
}

static int
source_candidate_bounds(PyObject *units, Py_ssize_t turn_start, Py_ssize_t turn_end,
                        Py_ssize_t *first, Py_ssize_t *stop)
{
    Py_ssize_t index, start, end;
    if (!PyList_CheckExact(units)
            || !source_bisect(units, turn_start, first)
            || !source_bisect(units, turn_end, stop)) {
        return 0;
    }
    for (index = *first; index < *stop; index++) {
        if (!source_unit_pair(PyList_GET_ITEM(units, index), &start, &end)) {
            return 0;
        }
    }
    return 1;
}

static int
source_projection_ready(PyObject *row, PyObject *turns, PyObject *cache, PyObject *refs)
{
    PyObject *content, *session, *ref, *ordinal, *key, *original, *units;
    Py_ssize_t index, turn, start, turn_start, turn_end, first, stop;
    if (!source_named_dict(row) || !source_keyed_dict(turns)
            || !source_keyed_dict(cache) || !PyList_CheckExact(refs)) {
        return 0;
    }
    content = PyDict_GetItemString(row, "content");
    session = PyDict_GetItemString(row, "session_pk");
    if (content == NULL || session == NULL || !PyUnicode_CheckExact(content)
            || !PyUnicode_CheckExact(session)) {
        return PyErr_Occurred() ? -1 : 0;
    }
    for (index = 0; index < PyList_GET_SIZE(refs); index++) {
        ref = PyList_GET_ITEM(refs, index);
        if (!source_named_dict(ref)) {
            return 0;
        }
        ordinal = PyDict_GetItemString(ref, "turn_index");
        if (!source_small_integer(ordinal, &turn)
                || !source_small_integer(PyDict_GetItemString(ref, "start"), &start)
                || !source_small_integer(PyDict_GetItemString(ref, "turn_start"), &turn_start)
                || !source_small_integer(PyDict_GetItemString(ref, "turn_end"), &turn_end)) {
            return PyErr_Occurred() ? -1 : 0;
        }
        key = PyTuple_Pack(2, session, ordinal);
        if (key == NULL) {
            return -1;
        }
        original = PyDict_GetItemWithError(turns, key);
        units = PyDict_GetItemWithError(cache, key);
        Py_DECREF(key);
        if (PyErr_Occurred()) {
            return -1;
        }
        if (original == NULL || !PyUnicode_CheckExact(original)) {
            return 0;
        }
        if (units != NULL && !source_candidate_bounds(units, turn_start, turn_end, &first, &stop)) {
            return 0;
        }
    }
    return 1;
}

/* PyUnicode_Substring itself rejects negative indexes; Python slices clamp
 * them relative to the string length.  Preserve that behavior for malformed
 * but ordinary integer maps which still enter the historical unit checks. */
static PyObject *
source_slice(PyObject *text, Py_ssize_t start, Py_ssize_t end)
{
    Py_ssize_t length = PyUnicode_GET_LENGTH(text);
    if (start < 0) {
        start += length;
    }
    if (end < 0) {
        end += length;
    }
    start = start < 0 ? 0 : (start > length ? length : start);
    end = end < 0 ? 0 : (end > length ? length : end);
    if (end < start) {
        end = start;
    }
    return PyUnicode_Substring(text, start, end);
}

static PyObject *
native_projected_units(PyObject *self, PyObject *args)
{
    PyObject *row, *turns, *cache, *refs, *content = NULL, *session = NULL;
    PyObject *spans = NULL, *key = NULL, *original = NULL, *units = NULL;
    PyObject *left = NULL, *right = NULL, *result = NULL;
    Py_ssize_t index, unit_index, start, end, turn_start, turn_end, origin, first, stop;
    int ready;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOO:projected_units", &row, &turns, &cache, &refs)) {
        return NULL;
    }
    ready = source_projection_ready(row, turns, cache, refs);
    if (ready < 0) {
        return NULL;
    }
    if (!ready) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    content = Py_NewRef(PyDict_GetItemString(row, "content"));
    session = Py_NewRef(PyDict_GetItemString(row, "session_pk"));
    spans = PySet_New(NULL);
    if (spans == NULL) {
        goto done;
    }
    for (index = 0; index < PyList_GET_SIZE(refs); index++) {
        PyObject *ref = PyList_GET_ITEM(refs, index);
        source_small_integer(PyDict_GetItemString(ref, "start"), &origin);
        source_small_integer(PyDict_GetItemString(ref, "turn_start"), &turn_start);
        source_small_integer(PyDict_GetItemString(ref, "turn_end"), &turn_end);
        key = PyTuple_Pack(2, session, PyDict_GetItemString(ref, "turn_index"));
        if (key == NULL) {
            goto done;
        }
        original = Py_NewRef(PyDict_GetItemWithError(turns, key));
        units = Py_XNewRef(PyDict_GetItemWithError(cache, key));
        if (units == NULL) {
            units = source_units_text(original);
            if (units == NULL || PyDict_SetItem(cache, key, units) < 0) {
                goto done;
            }
        }
        /* Preflight checked existing units; generated units are exact pairs. */
        source_bisect(units, turn_start, &first);
        source_bisect(units, turn_end, &stop);
        for (unit_index = first; unit_index < stop; unit_index++) {
            Py_ssize_t lo, hi;
            int equal;
            source_unit_pair(PyList_GET_ITEM(units, unit_index), &start, &end);
            if (!(turn_start <= start && start < end && end <= turn_end)) {
                continue;
            }
            lo = origin + start - turn_start;
            hi = origin + end - turn_start;
            left = source_slice(content, lo, hi);
            right = source_slice(original, start, end);
            if (left == NULL || right == NULL) {
                goto done;
            }
            equal = PyObject_RichCompareBool(left, right, Py_EQ);
            Py_CLEAR(left);
            Py_CLEAR(right);
            if (equal < 0) {
                goto done;
            }
            if (!equal) {
                PyErr_SetString(PyExc_ValueError, "Page source coordinates do not match the original turn");
                goto done;
            }
            if (source_add_span(spans, lo, hi) < 0) {
                goto done;
            }
        }
        Py_CLEAR(key);
        Py_CLEAR(original);
        Py_CLEAR(units);
    }
    result = source_sorted_spans(spans);

done:
    Py_XDECREF(content);
    Py_XDECREF(session);
    Py_XDECREF(spans);
    Py_XDECREF(key);
    Py_XDECREF(original);
    Py_XDECREF(units);
    Py_XDECREF(left);
    Py_XDECREF(right);
    return result;
}

static PyObject *
native_source_map_matches(PyObject *self, PyObject *args)
{
    PyObject *row, *turns, *refs, *content, *session;
    PyObject *key = NULL, *original = NULL, *left = NULL, *right = NULL;
    Py_ssize_t index, turn, start, end, turn_start, turn_end;
    int equal;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:source_map_matches", &row, &turns, &refs)) {
        return NULL;
    }
    if (!source_named_dict(row) || !source_keyed_dict(turns) || !PyList_CheckExact(refs)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    content = PyDict_GetItemString(row, "content");
    session = PyDict_GetItemString(row, "session_pk");
    if (content == NULL || session == NULL || !PyUnicode_CheckExact(content)
            || !PyUnicode_CheckExact(session)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    /* Validate shapes before returning False: an unsupported later ref must
     * not change the reference's earlier success/failure or exception order. */
    for (index = 0; index < PyList_GET_SIZE(refs); index++) {
        PyObject *ref = PyList_GET_ITEM(refs, index);
        if (!source_named_dict(ref)
                || !source_small_integer(PyDict_GetItemString(ref, "turn_index"), &turn)
                || !source_small_integer(PyDict_GetItemString(ref, "start"), &start)
                || !source_small_integer(PyDict_GetItemString(ref, "end"), &end)
                || !source_small_integer(PyDict_GetItemString(ref, "turn_start"), &turn_start)
                || !source_small_integer(PyDict_GetItemString(ref, "turn_end"), &turn_end)) {
            Py_RETURN_NOTIMPLEMENTED;
        }
    }
    for (index = 0; index < PyList_GET_SIZE(refs); index++) {
        PyObject *ref = PyList_GET_ITEM(refs, index);
        source_small_integer(PyDict_GetItemString(ref, "start"), &start);
        source_small_integer(PyDict_GetItemString(ref, "end"), &end);
        source_small_integer(PyDict_GetItemString(ref, "turn_start"), &turn_start);
        source_small_integer(PyDict_GetItemString(ref, "turn_end"), &turn_end);
        key = PyTuple_Pack(2, session, PyDict_GetItemString(ref, "turn_index"));
        if (key == NULL) {
            goto error;
        }
        original = Py_XNewRef(PyDict_GetItemWithError(turns, key));
        Py_CLEAR(key);
        if (original == NULL && PyErr_Occurred()) {
            goto error;
        }
        if (original == NULL || original == Py_None) {
            Py_XDECREF(original);
            Py_RETURN_FALSE;
        }
        if (!PyUnicode_CheckExact(original)) {
            Py_DECREF(original);
            Py_RETURN_NOTIMPLEMENTED;
        }
        if (!(0 <= start && start <= end && end <= PyUnicode_GET_LENGTH(content)
                && 0 <= turn_start && turn_start <= turn_end
                && turn_end <= PyUnicode_GET_LENGTH(original))
                || end - start != turn_end - turn_start) {
            Py_DECREF(original);
            Py_RETURN_FALSE;
        }
        left = PyUnicode_Substring(content, start, end);
        right = PyUnicode_Substring(original, turn_start, turn_end);
        if (left == NULL || right == NULL) {
            goto error;
        }
        equal = PyObject_RichCompareBool(left, right, Py_EQ);
        Py_CLEAR(left);
        Py_CLEAR(right);
        Py_CLEAR(original);
        if (equal < 0) {
            goto error;
        }
        if (!equal) {
            Py_RETURN_FALSE;
        }
    }
    Py_RETURN_TRUE;

error:
    Py_XDECREF(key);
    Py_XDECREF(original);
    Py_XDECREF(left);
    Py_XDECREF(right);
    return NULL;
}
