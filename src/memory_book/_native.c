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
ascii_terms_text(PyObject *text, int filter, PyObject *stop, int original_input)
{
    PyObject *result;
    const unsigned char *data;
    Py_ssize_t length, index, start = -1;

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
ascii_terms_impl(PyObject *args, int original_input)
{
    PyObject *text, *query, *stop;

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
    return ascii_terms_text(text, query == Py_True, stop, original_input);
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

static int
is_ascii_identifier(Py_UCS4 character)
{
    return character < 128 && (ascii_lower((unsigned char)character)
        || ascii_upper((unsigned char)character)
        || ascii_digit((unsigned char)character) || character == '_');
}

/* IDENTIFIER_WORD_BOUNDARY splits only ASCII runs.  Keep its acronym,
 * lowercase/digit-to-uppercase and underscore alternatives in their original
 * order; the returned parts are casefolded exactly once, after splitting.
 */
static PyObject *
identifier_parts(PyObject *value)
{
    PyObject *parts = PyList_New(0);
    const unsigned char *data = PyUnicode_1BYTE_DATA(value);
    Py_ssize_t length = PyUnicode_GET_LENGTH(value), index = 0, start = 0;

    if (parts == NULL) {
        return NULL;
    }
    while (index < length) {
        int boundary;
        if ((index & 65535) == 0 && PyErr_CheckSignals() < 0) {
            goto error;
        }
        if (data[index] == '_') {
            if (start < index
                    && append_ascii_token(parts, data, start, index, 1, 0, Py_None) < 0) {
                goto error;
            }
            do {
                index++;
                if ((index & 65535) == 0 && PyErr_CheckSignals() < 0) {
                    goto error;
                }
            } while (index < length && data[index] == '_');
            start = index;
            continue;
        }
        boundary = index > start && ascii_upper(data[index])
            && (ascii_lower(data[index - 1]) || ascii_digit(data[index - 1])
                || (ascii_upper(data[index - 1]) && index + 1 < length
                    && ascii_lower(data[index + 1])));
        if (boundary) {
            if (append_ascii_token(parts, data, start, index, 1, 0, Py_None) < 0) {
                goto error;
            }
            start = index;
        }
        index++;
    }
    if (start < length
            && append_ascii_token(parts, data, start, length, 1, 0, Py_None) < 0) {
        goto error;
    }
    return parts;

error:
    Py_DECREF(parts);
    return NULL;
}

/* The Python wrapper still performs whole-text normalization and terms().
 * This translates only its identifier callback/alias loops.  Index aliases
 * compare against the same legacy ASCII terms for each individual run; they
 * never deduplicate across runs or reorder the original page tokens.
 */
static PyObject *
native_identifier_aliases(PyObject *self, PyObject *args)
{
    PyObject *text, *query, *stop;
    PyObject *pieces = NULL, *aliases = NULL, *value = NULL, *parts = NULL;
    PyObject *joined = NULL, *legacy = NULL, *existing = NULL, *replacement = NULL;
    PyObject *piece = NULL, *rewritten = NULL, *empty = NULL, *space = NULL, *result = NULL;
    Py_ssize_t length, cursor = 0, last_end = 0;
    int kind, filter;
    void *data;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:identifier_aliases", &text, &query, &stop)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyBool_Check(query)) {
        PyErr_SetString(PyExc_TypeError, "query must be an exact bool");
        return NULL;
    }
    filter = query == Py_True;
    length = PyUnicode_GET_LENGTH(text);
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);
    aliases = PyList_New(0);
    empty = PyUnicode_New(0, 0);
    if (aliases == NULL || empty == NULL) {
        goto done;
    }
    if (filter) {
        pieces = PyList_New(0);
        space = PyUnicode_FromString(" ");
        if (pieces == NULL || space == NULL) {
            goto done;
        }
    }
    while (cursor < length) {
        Py_ssize_t start, count, index;
        int contains;
        if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
        if (!is_ascii_identifier(PyUnicode_READ(kind, data, cursor))) {
            cursor++;
            continue;
        }
        start = cursor;
        do {
            cursor++;
            if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
                goto done;
            }
        } while (cursor < length && is_ascii_identifier(PyUnicode_READ(kind, data, cursor)));
        value = PyUnicode_Substring(text, start, cursor);
        if (value == NULL) {
            goto done;
        }
        parts = identifier_parts(value);
        if (parts == NULL) {
            goto done;
        }
        count = PyList_GET_SIZE(parts);
        if (count >= 2) {
            joined = PyUnicode_Join(empty, parts);
            if (joined == NULL) {
                goto done;
            }
        }
        if (filter) {
            if (joined != NULL) {
                contains = PySequence_Contains(stop, joined);
                if (contains < 0 || (!contains && PyList_Append(aliases, joined) < 0)) {
                    goto done;
                }
                replacement = PyUnicode_Join(space, parts);
            }
            else {
                replacement = Py_NewRef(value);
            }
            if (replacement == NULL) {
                goto done;
            }
            if (last_end < start) {
                piece = PyUnicode_Substring(text, last_end, start);
                if (piece == NULL || PyList_Append(pieces, piece) < 0) {
                    goto done;
                }
                Py_CLEAR(piece);
            }
            if (PyList_Append(pieces, replacement) < 0) {
                goto done;
            }
            last_end = cursor;
            Py_CLEAR(replacement);
        }
        else if (joined != NULL) {
            legacy = ascii_terms_text(value, 0, Py_None, 1);
            if (legacy == NULL) {
                goto done;
            }
            existing = PySet_New(legacy);
            Py_CLEAR(legacy);
            if (existing == NULL) {
                goto done;
            }
            for (index = 0; index <= count; index++) {
                PyObject *alias = index == count ? joined : PyList_GET_ITEM(parts, index);
                contains = PySet_Contains(existing, alias);
                if (contains < 0) {
                    goto done;
                }
                if (!contains && (PyList_Append(aliases, alias) < 0
                                  || PySet_Add(existing, alias) < 0)) {
                    goto done;
                }
            }
            Py_CLEAR(existing);
        }
        Py_CLEAR(value);
        Py_CLEAR(parts);
        Py_CLEAR(joined);
    }
    if (filter) {
        if (last_end < length) {
            piece = PyUnicode_Substring(text, last_end, length);
            if (piece == NULL || PyList_Append(pieces, piece) < 0) {
                goto done;
            }
            Py_CLEAR(piece);
        }
        rewritten = PyUnicode_Join(empty, pieces);
    }
    else {
        rewritten = Py_NewRef(text);
    }
    if (rewritten != NULL) {
        result = PyTuple_Pack(2, rewritten, aliases);
    }

done:
    Py_XDECREF(pieces);
    Py_XDECREF(aliases);
    Py_XDECREF(value);
    Py_XDECREF(parts);
    Py_XDECREF(joined);
    Py_XDECREF(legacy);
    Py_XDECREF(existing);
    Py_XDECREF(replacement);
    Py_XDECREF(piece);
    Py_XDECREF(rewritten);
    Py_XDECREF(empty);
    Py_XDECREF(space);
    return result;
}

static int
is_legacy_cjk(Py_UCS4 character)
{
    return (character >= 0x3400 && character <= 0x4dbf)
        || (character >= 0x4e00 && character <= 0x9fff)
        || (character >= 0xf900 && character <= 0xfaff);
}

static int
append_unicode_token(PyObject *result, PyObject *text,
                     Py_ssize_t start, Py_ssize_t end,
                     int query, PyObject *stop)
{
    PyObject *token = PyUnicode_Substring(text, start, end);
    int contains, status;
    if (token == NULL) {
        return -1;
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
native_unicode_tokens(PyObject *self, PyObject *args)
{
    PyObject *text, *query, *stop, *zh_stop, *result;
    Py_ssize_t length, cursor = 0;
    int kind, filter;
    void *data;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOOO:unicode_tokens", &text, &query, &stop, &zh_stop)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyBool_Check(query)) {
        PyErr_SetString(PyExc_TypeError, "query must be an exact bool");
        return NULL;
    }
    filter = query == Py_True;
    length = PyUnicode_GET_LENGTH(text);
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);
    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }
    /* RUNS matches either a CJK run or Unicode alphanumeric runs connected by
     * one of _./:-.  IDENTIFIER_SEPARATOR then splits every such connector.
     * Consequently the exact emitted non-CJK pieces are contiguous Unicode
     * alphanumeric runs.  Py_UNICODE_ISALNUM is the same Unicode predicate
     * used by CPython re's \w (apart from underscore, already a separator).
     * Supplementary CJK characters outside the three historical ranges are
     * ordinary alphanumeric text; deliberately do not broaden these ranges.
     */
    while (cursor < length) {
        Py_ssize_t start = cursor;
        Py_UCS4 character = PyUnicode_READ(kind, data, cursor);
        if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
            goto error;
        }
        if (is_legacy_cjk(character)) {
            Py_ssize_t index;
            do {
                cursor++;
                if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
                    goto error;
                }
            } while (cursor < length && is_legacy_cjk(PyUnicode_READ(kind, data, cursor)));
            if (cursor - start == 1) {
                if (append_unicode_token(result, text, start, cursor, filter, zh_stop) < 0) {
                    goto error;
                }
            }
            else {
                for (index = start; index < cursor - 1; index++) {
                    if ((index & 65535) == 0 && PyErr_CheckSignals() < 0) {
                        goto error;
                    }
                    if (append_unicode_token(result, text, index, index + 2, filter, zh_stop) < 0) {
                        goto error;
                    }
                }
            }
        }
        else if (Py_UNICODE_ISALNUM(character)) {
            do {
                cursor++;
                if ((cursor & 65535) == 0 && PyErr_CheckSignals() < 0) {
                    goto error;
                }
                if (cursor == length) {
                    break;
                }
                character = PyUnicode_READ(kind, data, cursor);
            } while (Py_UNICODE_ISALNUM(character) && !is_legacy_cjk(character));
            if (append_unicode_token(result, text, start, cursor, filter, stop) < 0) {
                goto error;
            }
        }
        else {
            cursor++;
        }
    }
    return result;

error:
    Py_DECREF(result);
    return NULL;
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
    PyObject *ascii_folds[128] = {NULL};
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
        Py_UCS4 code_point = PyUnicode_READ(kind, data, index);
        if ((index & 4095) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
        /* This is the same invocation-local character cache as the Python
         * reference.  ASCII keys use an array instead of a hash lookup, but
         * every first occurrence still calls the supplied Unicode functions.
         */
        if (code_point < 128) {
            piece = ascii_folds[code_point];
        }
        else {
            character = PyUnicode_FromOrdinal((int)code_point);
            if (character == NULL) {
                goto done;
            }
            piece = PyDict_GetItemWithError(cache, character);
            if (piece == NULL && PyErr_Occurred()) {
                goto done;
            }
        }
        if (piece == NULL) {
            if (character == NULL) {
                character = PyUnicode_FromOrdinal((int)code_point);
                if (character == NULL) {
                    goto done;
                }
            }
            piece = fold_character(character, normalize, category, nfkd, mn);
            if (piece == NULL) {
                goto done;
            }
            if (code_point < 128) {
                ascii_folds[code_point] = Py_NewRef(piece);
            }
            else if (PyDict_SetItem(cache, character, piece) < 0) {
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
    for (index = 0; index < 128; index++) {
        Py_XDECREF(ascii_folds[index]);
    }
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

/* re.finditer(re.escape(term), lower) is a literal, non-overlapping search.
 * Keep the per-term forty-match cap and the caller's term order, including
 * duplicates and empty strings.  Sorting and all excerpt scoring stay in
 * Python.  PyUnicode_Find uses the same code-point coordinates as re; neither
 * surrogate code points nor non-BMP characters pass through a byte encoding.
 */
static PyObject *
native_literal_positions(PyObject *self, PyObject *args)
{
    PyObject *lower, *terms, *source_positions, *result = NULL;
    PyObject *term = NULL, *position = NULL, *entry = NULL;
    Py_ssize_t length, index;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:literal_positions", &lower, &terms, &source_positions)) {
        return NULL;
    }
    if (require_exact_unicode(lower) < 0) {
        return NULL;
    }
    if (!PyList_CheckExact(terms)) {
        PyErr_SetString(PyExc_TypeError, "terms must be an exact list");
        return NULL;
    }
    if (source_positions != Py_None && !PyList_CheckExact(source_positions)) {
        PyErr_SetString(PyExc_TypeError, "source_positions must be None or an exact list");
        return NULL;
    }
    length = PyUnicode_GET_LENGTH(lower);
    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }
    for (index = 0; index < PyList_GET_SIZE(terms); index++) {
        Py_ssize_t cursor = 0, term_length;
        int count;
        if (PyErr_CheckSignals() < 0) {
            goto error;
        }
        if (index >= PyList_GET_SIZE(terms)) {
            break;
        }
        /* A Python loop and its regex iterator retain the current term even
         * if a GC/signal callback mutates the supplied terms list while result
         * tuples are allocated.  Keep the same owned lifetime here.
         */
        term = Py_NewRef(PyList_GET_ITEM(terms, index));
        if (require_exact_unicode(term) < 0) {
            goto error;
        }
        term_length = PyUnicode_GET_LENGTH(term);
        for (count = 0; count < 40; count++) {
            Py_ssize_t found = PyUnicode_Find(lower, term, cursor, length, 1);
            if (found == -2) {
                goto error;
            }
            if (found < 0) {
                break;
            }
            position = source_positions == Py_None
                ? PyLong_FromSsize_t(found) : PySequence_GetItem(source_positions, found);
            if (position == NULL) {
                goto error;
            }
            entry = PyTuple_Pack(2, position, term);
            Py_CLEAR(position);
            if (entry == NULL || PyList_Append(result, entry) < 0) {
                goto error;
            }
            Py_CLEAR(entry);
            if (term_length == 0) {
                /* The empty regex also matches the end position.  Stop there
                 * before adding one, avoiding overflow at PY_SSIZE_T_MAX.
                 */
                if (found == length) {
                    break;
                }
                cursor = found + 1;
            }
            else {
                /* A successful find guarantees found + term_length <= length. */
                cursor = found + term_length;
            }
        }
        Py_CLEAR(term);
    }
    return result;

error:
    Py_XDECREF(term);
    Py_XDECREF(position);
    Py_XDECREF(entry);
    Py_DECREF(result);
    return NULL;
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

#include "_native_lexical.h"
#include "_native_excerpt.h"
#include "_native_rank.h"
#include "_native_source.h"

static PyMethodDef native_methods[] = {
    {"strip_nonspacing_marks", native_strip_nonspacing_marks, METH_VARARGS, "Equivalent whole-string mark filtering."},
    {"identifier_has_boundary", native_identifier_has_boundary, METH_VARARGS, "Equivalent fixed identifier boundary predicate."},
    {"excerpt_window", native_excerpt_window, METH_VARARGS, "Complete equivalent source-window selection."},
    {"rank_candidates", native_rank_candidates, METH_VARARGS, "Equivalent batch scoring and stable sorting."},
    {"select_novelty", native_select_novelty, METH_VARARGS, "Equivalent bounded novelty selection."},
    {"context_allocations", native_context_allocations, METH_VARARGS, "Equivalent cited character-budget allocation."},
    {"refs_from_parsed", native_refs_from_parsed, METH_VARARGS, "Equivalent source-reference clipping."},
    {"source_units", native_source_units, METH_VARARGS, "Equivalent original-turn source units."},
    {"projected_units", native_projected_units, METH_VARARGS, "Equivalent source-unit projection."},
    {"source_map_matches", native_source_map_matches, METH_VARARGS, "Equivalent source-map certificate."},
    {"terms_ascii", native_terms_ascii, METH_VARARGS,
     "terms_ascii(text, query, stop) -> exact legacy ASCII terms."},
    {"ascii_tokens", native_ascii_tokens, METH_VARARGS,
     "ascii_tokens(text, query, stop) -> [a-z0-9]+ runs from normalized ASCII."},
    {"unicode_tokens", native_unicode_tokens, METH_VARARGS,
     "unicode_tokens(text, query, stop, zh_stop) -> tokens from prepared Unicode text."},
    {"identifier_aliases", native_identifier_aliases, METH_VARARGS,
     "identifier_aliases(text, query, stop) -> (rewritten text, ordered identifier aliases)."},
    {"literal_positions", native_literal_positions, METH_VARARGS,
     "literal_positions(lower, terms, source_positions) -> literal match positions, capped per term."},
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
