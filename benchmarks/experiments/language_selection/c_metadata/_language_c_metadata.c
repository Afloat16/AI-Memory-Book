#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* Isolated complete-method control. SQL and Python continuations are supplied
 * by the same frozen adapter as the Rust candidate. No production file is
 * included, replaced on disk, or bypassed by a fabricated native identity. */
enum Key {
    K_STORE, K_READY, K_AFTER_LIGHT, K_AFTER_DIRS, K_BOOK, K_ROWS, K_SQLITE,
    K_CONNECTION, K_ROW, K_DB, K_ROW_FACTORY, K_TEXT_FACTORY, K_TOKENS,
    K_CACHE, K_WRAPPED, K_ORDINARY, K_METADATA, K_RID, K_VALUES, K_EXECUTE,
    K_FETCHALL, K_PROJECT_ID, K_CHAPTER_ID, K_CHAPTER_TITLE, K_SESSION_ID,
    K_SESSION_TITLE, K_CREATED_AT, K_COUNT
};
static const char *key_names[K_COUNT] = {
    "store", "ordinary_ready", "after_light", "after_directories", "MemoryBook",
    "_RecallCandidates", "sqlite3", "Connection", "Row", "db", "row_factory",
    "text_factory", "_directory_tokens", "_ordinary_directory_cache", "__wrapped__",
    "_ORDINARY_DIRECTORY_TOKENS", "metadata", "rid", "values", "execute", "fetchall",
    "project_id", "chapter_id", "chapter_title", "session_id", "session_title", "created_at"
};
typedef struct {
    PyObject *keys[K_COUNT];
    PyObject *cache_type;
} MetadataState;

static int exact_keys(PyObject *mapping) {
    Py_ssize_t pos = 0;
    PyObject *key, *value;
    while (PyDict_Next(mapping, &pos, &key, &value)) {
        if (!PyUnicode_CheckExact(key)) return 0;
    }
    return 1;
}

/* No user equality, iteration or numeric conversion is invoked by this check. */
static int ordinary_rows(PyObject *rows, PyObject *rid_key) {
    Py_ssize_t pos = 0;
    PyObject *key, *value;
    while (PyDict_Next(rows, &pos, &key, &value)) {
        if (!PyUnicode_CheckExact(key) || !PyDict_CheckExact(value) || !exact_keys(value)) return 0;
        PyObject *rid = PyDict_GetItemWithError(value, rid_key);
        if (!rid) return PyErr_Occurred() ? -1 : 0;
        if (!PyLong_CheckExact(rid)) return 0;
    }
    return 1;
}

static int carried_shape(PyObject *mapping) {
    Py_ssize_t pos = 0;
    PyObject *key, *row;
    while (PyDict_Next(mapping, &pos, &key, &row)) {
        if (!PyUnicode_CheckExact(key) || !PyTuple_CheckExact(row) || PyTuple_GET_SIZE(row) != 4) return 0;
        for (Py_ssize_t i = 0; i < 4; ++i) {
            if (!PyUnicode_CheckExact(PyTuple_GET_ITEM(row, i))) return 0;
        }
    }
    return 1;
}

static int ready(PyObject *function) {
    PyObject *value = PyObject_CallNoArgs(function);
    if (!value) return -1;
    int answer = PyObject_IsTrue(value);
    Py_DECREF(value);
    return answer;
}

static int descending(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return x < y ? 1 : x > y ? -1 : 0;
}

static PyObject *statement(const char *prefix, const char *placeholder,
                           const char *suffix, Py_ssize_t count) {
    size_t first = strlen(prefix), middle = strlen(placeholder), last = strlen(suffix);
    if (count < 0 || (size_t)count > ((size_t)PY_SSIZE_T_MAX - first - last) / (middle + 1)) {
        PyErr_NoMemory();
        return NULL;
    }
    size_t size = first + last + (size_t)count * middle + (count ? (size_t)count - 1 : 0);
    char *buffer = PyMem_Malloc(size + 1);
    if (!buffer) return PyErr_NoMemory();
    char *at = buffer;
    memcpy(at, prefix, first);
    at += first;
    for (Py_ssize_t i = 0; i < count; ++i) {
        if (i) *at++ = ',';
        memcpy(at, placeholder, middle);
        at += middle;
    }
    memcpy(at, suffix, last);
    at += last;
    *at = '\0';
    PyObject *result = PyUnicode_DecodeASCII(buffer, (Py_ssize_t)size, "strict");
    PyMem_Free(buffer);
    return result;
}

static PyObject *fetchall(MetadataState *state, PyObject *db, PyObject *sql, PyObject *parameters) {
    PyObject *cursor = PyObject_CallMethodObjArgs(db, state->keys[K_EXECUTE], sql, parameters, NULL);
    if (!cursor) return NULL;
    PyObject *result = PyObject_CallMethodObjArgs(cursor, state->keys[K_FETCHALL], NULL);
    Py_DECREF(cursor);
    return result;
}

/* 1: normal fixed-shape row; 0: custom sequence, use the exact continuation.
 * All fields are returned as owned references, including on partial failure. */
static int fields(PyObject *row, PyObject *row_type, Py_ssize_t count, PyObject **out) {
    if (PyTuple_CheckExact(row)) {
        if (PyTuple_GET_SIZE(row) != count) return 0;
        for (Py_ssize_t i = 0; i < count; ++i) out[i] = Py_NewRef(PyTuple_GET_ITEM(row, i));
        return 1;
    }
    if (PyList_CheckExact(row)) {
        if (PyList_GET_SIZE(row) != count) return 0;
        for (Py_ssize_t i = 0; i < count; ++i) out[i] = Py_NewRef(PyList_GET_ITEM(row, i));
        return 1;
    }
    if (Py_TYPE(row) != (PyTypeObject *)row_type) return 0;
    Py_ssize_t size = PySequence_Size(row);
    if (size < 0) return -1;
    if (size != count) return 0;
    for (Py_ssize_t i = 0; i < count; ++i) {
        out[i] = PySequence_GetItem(row, i);
        if (!out[i]) return -1;
    }
    return 1;
}

static void release_fields(PyObject **values, Py_ssize_t count) {
    for (Py_ssize_t i = 0; i < count; ++i) Py_CLEAR(values[i]);
}

/* Full original light validation, followed by stable pair construction.
 * Codes: 1 success, 0 original None, 2 continuation, -1 exception.
 * The original light object is retained for the later, SQL-after traversal. */
static int prepare_pairs(PyObject *rows, PyObject *light, PyObject *row_type, PyObject **pairs) {
    Py_ssize_t size = PyObject_Length(light);
    if (size < 0) return -1;
    if (size != PyDict_Size(rows)) return 0;
    PyObject *identities = PySet_New(NULL), *unique = PyDict_New(), *iterator = NULL;
    PyObject *row = NULL, *part[4] = {NULL, NULL, NULL, NULL};
    int result = -1;
    if (!identities || !unique) goto done;
    iterator = PyObject_GetIter(light);
    if (!iterator) goto done;
    while ((row = PyIter_Next(iterator))) {
        int shape = fields(row, row_type, 4, part);
        if (shape < 0) goto done;
        if (!shape) { result = 2; goto done; }
        /* Ordinary SQL rows contain only sqlite scalar types. Non-string IDs
         * with custom hash semantics are left to the continuation. */
        for (int i = 0; i < 4; ++i) {
            if (!PyUnicode_CheckExact(part[i])) { result = 2; goto done; }
        }
        if (PySet_Add(identities, part[0]) < 0) goto done;
        release_fields(part, 4);
        Py_CLEAR(row);
    }
    if (PyErr_Occurred()) goto done;
    Py_CLEAR(iterator);
    if (PySet_Size(identities) != PyDict_Size(rows)) { result = 0; goto done; }
    Py_ssize_t pos = 0;
    PyObject *key, *value;
    while (PyDict_Next(rows, &pos, &key, &value)) {
        int present = PySet_Contains(identities, key);
        if (present < 0) goto done;
        if (!present) { result = 0; goto done; }
    }
    iterator = PyObject_GetIter(light);
    if (!iterator) goto done;
    while ((row = PyIter_Next(iterator))) {
        int shape = fields(row, row_type, 4, part);
        if (shape != 1) { result = shape < 0 ? -1 : 2; goto done; }
        PyObject *pair = PyTuple_Pack(2, part[2], part[3]);
        if (!pair) goto done;
        int added = PyDict_SetItem(unique, pair, Py_None);
        Py_DECREF(pair);
        if (added < 0) goto done;
        release_fields(part, 4);
        Py_CLEAR(row);
    }
    if (PyErr_Occurred()) goto done;
    *pairs = PyDict_Keys(unique);
    result = *pairs ? 1 : -1;
done:
    release_fields(part, 4);
    Py_XDECREF(row);
    Py_XDECREF(iterator);
    Py_XDECREF(identities);
    Py_XDECREF(unique);
    return result;
}

static PyObject *bounded_metadata(PyObject *self, PyObject *arguments) {
    MetadataState *state = PyModule_GetState(self);
    PyObject *book, *rows, *relevance, *count_object, *env;
    if (!PyArg_UnpackTuple(arguments, "bounded_metadata", 5, 5,
                           &book, &rows, &relevance, &count_object, &env)) return NULL;
    if (!PyDict_CheckExact(env) || !PyDict_CheckExact(relevance) || !PyLong_CheckExact(count_object)) Py_RETURN_NOTIMPLEMENTED;
    PyObject *store = PyDict_GetItemWithError(env, state->keys[K_STORE]);
    PyObject *ready_function = PyDict_GetItemWithError(env, state->keys[K_READY]);
    PyObject *after_light = PyDict_GetItemWithError(env, state->keys[K_AFTER_LIGHT]);
    PyObject *after_dirs = PyDict_GetItemWithError(env, state->keys[K_AFTER_DIRS]);
    if (!store || !ready_function || !after_light || !after_dirs || !PyModule_CheckExact(store)
            || !PyCallable_Check(ready_function) || !PyCallable_Check(after_light) || !PyCallable_Check(after_dirs)) {
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NOTIMPLEMENTED;
    }
    Py_INCREF(store); Py_INCREF(ready_function); Py_INCREF(after_light); Py_INCREF(after_dirs);
    PyObject *book_type = NULL, *rows_type = NULL, *sqlite_module = NULL, *connection_type = NULL;
    PyObject *row_type = NULL, *db = NULL, *carried = NULL, *factory = NULL;
    PyObject *tokens = NULL, *cache = NULL, *wrapped = NULL, *ordinary = NULL;
    PyObject *retained = NULL, *light = NULL, *pairs = NULL, *directories = NULL;
    PyObject *ids = NULL, *sql = NULL, *parameters = NULL, *metadata = NULL, *result = NULL;
    PyObject *iterator = NULL, *row = NULL, *part[8] = {NULL};
    double *scores = NULL;
    int use_carried = 0;
#define ATTR(target, object, key) do { target = PyObject_GetAttr(object, state->keys[key]); if (!target) goto error; } while (0)
#define NONE_RESULT() do { result = Py_NewRef(Py_None); goto done; } while (0)
#define UNSUPPORTED() do { result = Py_NewRef(Py_NotImplemented); goto done; } while (0)
#define CONTINUE_LIGHT() do { result = PyObject_CallFunctionObjArgs(after_light, book, rows, retained, light, NULL); goto done; } while (0)
#define CONTINUE_DIRS() do { result = PyObject_CallFunctionObjArgs(after_dirs, rows, retained, light, pairs, directories, NULL); goto done; } while (0)

    Py_ssize_t count = PyLong_AsSsize_t(count_object);
    if (count == -1 && PyErr_Occurred()) { PyErr_Clear(); UNSUPPORTED(); }
    if (count <= 0) UNSUPPORTED();
    ATTR(book_type, store, K_BOOK);
    ATTR(rows_type, store, K_ROWS);
    if (!PyType_Check(book_type) || !PyType_Check(rows_type)
            || Py_TYPE(book) != (PyTypeObject *)book_type) UNSUPPORTED();
    use_carried = Py_TYPE(rows) == (PyTypeObject *)rows_type;
    if (!PyDict_CheckExact(rows) && !use_carried) UNSUPPORTED();
    if (!PyDict_Check(rows)) UNSUPPORTED();
    int row_shape = ordinary_rows(rows, state->keys[K_RID]);
    if (row_shape < 0) goto error;
    if (!row_shape) UNSUPPORTED();
    if (PyDict_Size(rows) != PyDict_Size(relevance) || !exact_keys(relevance)) UNSUPPORTED();
    Py_ssize_t pos = 0;
    PyObject *key, *value;
    while (PyDict_Next(relevance, &pos, &key, &value)) {
        if (!PyFloat_CheckExact(value)) UNSUPPORTED();
        int present = PyDict_Contains(rows, key);
        if (present < 0) goto error;
        if (!present) UNSUPPORTED();
    }
    ATTR(db, book, K_DB);
    ATTR(sqlite_module, store, K_SQLITE);
    ATTR(connection_type, sqlite_module, K_CONNECTION);
    ATTR(row_type, sqlite_module, K_ROW);
    if (!PyType_Check(connection_type) || !PyType_Check(row_type)
            || Py_TYPE(db) != (PyTypeObject *)connection_type) UNSUPPORTED();
    if (use_carried) {
        carried = PyObject_GetAttr(rows, state->keys[K_METADATA]);
        if (!carried) { PyErr_Clear(); UNSUPPORTED(); }
        if (!PyDict_CheckExact(carried) || !carried_shape(carried)) UNSUPPORTED();
    }
    Py_ssize_t length = PyDict_Size(rows);
    if (length <= count) NONE_RESULT();
    ATTR(factory, db, K_ROW_FACTORY);
    if (factory != row_type) NONE_RESULT();
    Py_CLEAR(factory);
    ATTR(factory, db, K_TEXT_FACTORY);
    if (factory != (PyObject *)&PyUnicode_Type) NONE_RESULT();
    Py_CLEAR(factory);
    ATTR(tokens, book, K_TOKENS);
    ATTR(cache, book, K_CACHE);
    if (tokens != cache) NONE_RESULT();
    if (Py_TYPE(tokens) != (PyTypeObject *)state->cache_type) UNSUPPORTED();
    wrapped = PyObject_GetAttr(tokens, state->keys[K_WRAPPED]);
    if (!wrapped) {
        if (PyErr_ExceptionMatches(PyExc_AttributeError)) { PyErr_Clear(); NONE_RESULT(); }
        goto error;
    }
    ATTR(ordinary, store, K_ORDINARY);
    if (wrapped != ordinary) NONE_RESULT();
    pos = 0;
    while (PyDict_Next(relevance, &pos, &key, &value)) {
        double score = PyFloat_AS_DOUBLE(value);
        if (!isfinite(score) || score < 0.0) NONE_RESULT();
    }
    if ((size_t)length > (size_t)PY_SSIZE_T_MAX / sizeof(double)) { PyErr_NoMemory(); goto error; }
    scores = PyMem_Malloc((size_t)length * sizeof(double));
    if (!scores) { PyErr_NoMemory(); goto error; }
    pos = 0;
    Py_ssize_t i = 0;
    while (PyDict_Next(relevance, &pos, &key, &value)) scores[i++] = PyFloat_AS_DOUBLE(value);
    qsort(scores, (size_t)length, sizeof(double), descending);
    double floor = scores[count - 1];
    PyMem_Free(scores); scores = NULL;
    retained = PySet_New(NULL);
    if (!retained) goto error;
    pos = 0;
    while (PyDict_Next(relevance, &pos, &key, &value)) {
        if (PyFloat_AS_DOUBLE(value) * 1.15 >= floor && PySet_Add(retained, key) < 0) goto error;
    }
    if (PySet_Size(retained) == length) NONE_RESULT();

    if (use_carried) {
        light = PyObject_CallMethodObjArgs(carried, state->keys[K_VALUES], NULL);
        if (!light) goto error;
    } else {
        ids = PyList_New(length);
        if (!ids) goto error;
        pos = 0; i = 0;
        while (PyDict_Next(rows, &pos, &key, &value)) {
            PyObject *rid = PyDict_GetItemWithError(value, state->keys[K_RID]);
            if (!rid) goto error;
            PyList_SET_ITEM(ids, i++, Py_NewRef(rid));
        }
        sql = statement("SELECT id,project_id,chapter_id,session_pk\n              FROM pages INDEXED BY pages_recall_metadata WHERE rid IN (", "?", ")", length);
        if (!sql) goto error;
        light = fetchall(state, db, sql, ids);
        if (!light) goto error;
        Py_CLEAR(sql);
        int eligible = ready(ready_function);
        if (eligible < 0) goto error;
        if (!eligible || !PyList_CheckExact(light)
                || (!PyDict_CheckExact(rows) && Py_TYPE(rows) != (PyTypeObject *)rows_type)) CONTINUE_LIGHT();
        int shape = ordinary_rows(rows, state->keys[K_RID]);
        if (shape < 0) goto error;
        if (!shape) CONTINUE_LIGHT();
    }
    int prepared = prepare_pairs(rows, light, row_type, &pairs);
    if (prepared < 0) goto error;
    if (!prepared) NONE_RESULT();
    if (prepared == 2) CONTINUE_LIGHT();
    Py_ssize_t pair_count = PyList_GET_SIZE(pairs);
    if (pair_count > PY_SSIZE_T_MAX / 2) { PyErr_NoMemory(); goto error; }
    parameters = PyList_New(pair_count * 2);
    if (!parameters) goto error;
    for (i = 0; i < pair_count; ++i) {
        PyObject *pair = PyList_GET_ITEM(pairs, i);
        PyList_SET_ITEM(parameters, 2*i, Py_NewRef(PyTuple_GET_ITEM(pair, 0)));
        PyList_SET_ITEM(parameters, 2*i+1, Py_NewRef(PyTuple_GET_ITEM(pair, 1)));
    }
    sql = statement("WITH requested(chapter_id,session_pk) AS (VALUES ", "(?,?)",
        ")\n          SELECT requested.chapter_id,requested.session_pk,c.id,s.id,\n            c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at\n          FROM requested LEFT JOIN chapters c ON c.id=requested.chapter_id\n          LEFT JOIN sessions s ON s.id=requested.session_pk", pair_count);
    if (!sql) goto error;
    /* A trace/authorizer callback may have changed book.db during the first
     * query. The original method resolves it again for its second execute. */
    Py_CLEAR(db);
    ATTR(db, book, K_DB);
    directories = fetchall(state, db, sql, parameters);
    if (!directories) goto error;
    int eligible = ready(ready_function);
    if (eligible < 0) goto error;
    if (!eligible || !PyList_CheckExact(directories)
            || (!PyDict_CheckExact(rows) && Py_TYPE(rows) != (PyTypeObject *)rows_type)) CONTINUE_DIRS();
    int shape = ordinary_rows(rows, state->keys[K_RID]);
    if (shape < 0) goto error;
    if (!shape) CONTINUE_DIRS();
    if (use_carried && (!PyDict_CheckExact(carried) || !carried_shape(carried))) CONTINUE_DIRS();

    if (PyList_GET_SIZE(directories) != pair_count) NONE_RESULT();
    metadata = PyDict_New();
    if (!metadata) goto error;
    for (i = 0; i < pair_count; ++i) {
        PyObject *directory = PyList_GET_ITEM(directories, i);
        int fetched = fields(directory, row_type, 8, part);
        if (fetched < 0) goto error;
        if (!fetched) CONTINUE_DIRS();
        for (int j = 0; j < 8; ++j) {
            if (!PyUnicode_CheckExact(part[j])) NONE_RESULT();
        }
        PyObject *pair = PyTuple_Pack(2, part[0], part[1]);
        if (!pair) goto error;
        int added = PyDict_SetItem(metadata, pair, directory);
        Py_DECREF(pair);
        if (added < 0) goto error;
        release_fields(part, 8);
    }
    if (PyDict_Size(metadata) != pair_count) NONE_RESULT();
    for (i = 0; i < pair_count; ++i) {
        int present = PyDict_Contains(metadata, PyList_GET_ITEM(pairs, i));
        if (present < 0) goto error;
        if (!present) NONE_RESULT();
    }
    /* Inspect the live view before the first mutation. If a SQL callback made
     * the tail non-ordinary, its exact continuation preserves any later error
     * and any partial update the original Python loop would perform. */
    iterator = PyObject_GetIter(light);
    if (!iterator) goto error;
    while ((row = PyIter_Next(iterator))) {
        int fetched = fields(row, row_type, 4, part);
        if (fetched < 0) goto error;
        if (!fetched) CONTINUE_DIRS();
        for (int j = 0; j < 4; ++j) {
            if (!PyUnicode_CheckExact(part[j])) CONTINUE_DIRS();
        }
        int wanted = PySet_Contains(retained, part[0]);
        if (wanted < 0) goto error;
        if (wanted) {
            PyObject *target = PyDict_GetItemWithError(rows, part[0]);
            if (!target || !PyDict_CheckExact(target)) {
                if (PyErr_Occurred()) goto error;
                CONTINUE_DIRS();
            }
            PyObject *pair = PyTuple_Pack(2, part[2], part[3]);
            if (!pair) goto error;
            int present = PyDict_Contains(metadata, pair);
            Py_DECREF(pair);
            if (present < 0) goto error;
            if (!present) CONTINUE_DIRS();
        }
        release_fields(part, 4);
        Py_CLEAR(row);
    }
    if (PyErr_Occurred()) goto error;
    Py_CLEAR(iterator);
    iterator = PyObject_GetIter(light);
    if (!iterator) goto error;
    while ((row = PyIter_Next(iterator))) {
        int fetched = fields(row, row_type, 4, part);
        if (fetched != 1) goto error;
        int wanted = PySet_Contains(retained, part[0]);
        if (wanted < 0) goto error;
        if (wanted) {
            PyObject *pair = PyTuple_Pack(2, part[2], part[3]);
            if (!pair) goto error;
            PyObject *directory = PyDict_GetItemWithError(metadata, pair);
            Py_DECREF(pair);
            if (!directory) goto error;
            PyObject *target = PyDict_GetItemWithError(rows, part[0]);
            if (!target) goto error;
            if (PyDict_SetItem(target, state->keys[K_PROJECT_ID], part[1]) < 0
                    || PyDict_SetItem(target, state->keys[K_CHAPTER_ID], part[2]) < 0) goto error;
            for (int j = 4; j < 8; ++j) {
                PyObject *field = PySequence_GetItem(directory, j);
                if (!field) goto error;
                int added = PyDict_SetItem(target, state->keys[K_CHAPTER_TITLE + j - 4], field);
                Py_DECREF(field);
                if (added < 0) goto error;
            }
        }
        release_fields(part, 4);
        Py_CLEAR(row);
    }
    if (PyErr_Occurred()) goto error;
    result = PyDict_New();
    if (!result) goto error;
    pos = 0;
    while (PyDict_Next(rows, &pos, &key, &value)) {
        int present = PySet_Contains(retained, key);
        if (present < 0 || (present && PyDict_SetItem(result, key, value) < 0)) goto error;
    }
    goto done;
error:
    Py_CLEAR(result);
done:
    PyMem_Free(scores);
    release_fields(part, 8);
    Py_XDECREF(row); Py_XDECREF(iterator);
    Py_XDECREF(book_type); Py_XDECREF(rows_type); Py_XDECREF(sqlite_module);
    Py_XDECREF(connection_type); Py_XDECREF(row_type); Py_XDECREF(db); Py_XDECREF(carried);
    Py_XDECREF(factory); Py_XDECREF(tokens); Py_XDECREF(cache); Py_XDECREF(wrapped); Py_XDECREF(ordinary);
    Py_XDECREF(retained); Py_XDECREF(light); Py_XDECREF(pairs); Py_XDECREF(directories);
    Py_XDECREF(ids); Py_XDECREF(sql); Py_XDECREF(parameters); Py_XDECREF(metadata);
    Py_DECREF(store); Py_DECREF(ready_function); Py_DECREF(after_light); Py_DECREF(after_dirs);
    return result;
#undef ATTR
#undef NONE_RESULT
#undef UNSUPPORTED
#undef CONTINUE_LIGHT
#undef CONTINUE_DIRS
}

static PyMethodDef methods[] = {
    {"bounded_metadata", bounded_metadata, METH_VARARGS, "Complete ordinary bounded metadata method."},
    {NULL, NULL, 0, NULL}
};
static int traverse(PyObject *module, visitproc visit, void *arg) {
    MetadataState *state = PyModule_GetState(module);
    for (int i = 0; i < K_COUNT; ++i) Py_VISIT(state->keys[i]);
    Py_VISIT(state->cache_type);
    return 0;
}
static int clear(PyObject *module) {
    MetadataState *state = PyModule_GetState(module);
    for (int i = 0; i < K_COUNT; ++i) Py_CLEAR(state->keys[i]);
    Py_CLEAR(state->cache_type);
    return 0;
}
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_language_c_metadata", "Isolated C metadata control.",
    sizeof(MetadataState), methods, NULL, traverse, clear, NULL
};
PyMODINIT_FUNC PyInit__language_c_metadata(void) {
    PyObject *result = PyModule_Create(&module);
    if (!result) return NULL;
    MetadataState *state = PyModule_GetState(result);
    for (int i = 0; i < K_COUNT; ++i) {
        state->keys[i] = PyUnicode_InternFromString(key_names[i]);
        if (!state->keys[i]) { Py_DECREF(result); return NULL; }
    }
    PyObject *functools = PyImport_ImportModule("functools");
    if (!functools) { Py_DECREF(result); return NULL; }
    state->cache_type = PyObject_GetAttrString(functools, "_lru_cache_wrapper");
    Py_DECREF(functools);
    if (!state->cache_type || !PyType_Check(state->cache_type)) {
        Py_DECREF(result);
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_TypeError, "Unexpected functools cache type");
        return NULL;
    }
    return result;
}
