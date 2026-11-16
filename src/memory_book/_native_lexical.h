/* Complete small lexical loops.  Python still owns normalization order and
 * supplies the running interpreter's Unicode database; no Unicode tables or
 * tokenization rules are introduced by this implementation. */
#ifndef MEMORY_BOOK_NATIVE_LEXICAL_H
#define MEMORY_BOOK_NATIVE_LEXICAL_H

static PyObject *
native_strip_nonspacing_marks(PyObject *self, PyObject *args)
{
    PyObject *text, *category;
    PyObject *characters = NULL, *iterator = NULL, *removed = NULL, *mn = NULL;
    PyObject *character = NULL, *value = NULL, *ordinal = NULL, *result = NULL;
    Py_ssize_t processed = 0;
    int matches;

    (void)self;
    if (!PyArg_ParseTuple(args, "OO:strip_nonspacing_marks", &text, &category)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    if (!PyCallable_Check(category)) {
        PyErr_SetString(PyExc_TypeError, "category must be callable");
        return NULL;
    }
    /* Keep set(text)'s iteration and category-call order, including for a
     * direct call with a custom category function. */
    characters = PySet_New(text);
    if (characters == NULL) {
        goto done;
    }
    iterator = PyObject_GetIter(characters);
    removed = PyDict_New();
    mn = PyUnicode_FromString("Mn");
    if (iterator == NULL || removed == NULL || mn == NULL) {
        goto done;
    }
    while ((character = PyIter_Next(iterator)) != NULL) {
        value = PyObject_CallOneArg(category, character);
        if (value == NULL) {
            goto done;
        }
        matches = PyObject_RichCompareBool(value, mn, Py_EQ);
        Py_CLEAR(value);
        if (matches < 0) {
            goto done;
        }
        if (matches) {
            ordinal = PyLong_FromUnsignedLong(PyUnicode_READ_CHAR(character, 0));
            if (ordinal == NULL || PyDict_SetItem(removed, ordinal, Py_None) < 0) {
                goto done;
            }
            Py_CLEAR(ordinal);
        }
        Py_CLEAR(character);
        if ((processed++ & 4095) == 0 && PyErr_CheckSignals() < 0) {
            goto done;
        }
    }
    if (PyErr_Occurred()) {
        goto done;
    }
    result = PyDict_Size(removed) ? PyUnicode_Translate(text, removed, NULL) : Py_NewRef(text);

done:
    Py_XDECREF(characters);
    Py_XDECREF(iterator);
    Py_XDECREF(removed);
    Py_XDECREF(mn);
    Py_XDECREF(character);
    Py_XDECREF(value);
    Py_XDECREF(ordinal);
    return result;
}

static PyObject *
native_identifier_has_boundary(PyObject *self, PyObject *args)
{
    PyObject *text;
    Py_ssize_t index, length;
    Py_UCS4 previous = 0;
    int kind;
    void *data;

    (void)self;
    if (!PyArg_ParseTuple(args, "O:identifier_has_boundary", &text)) {
        return NULL;
    }
    if (require_exact_unicode(text) < 0) {
        return NULL;
    }
    kind = PyUnicode_KIND(text);
    data = PyUnicode_DATA(text);
    length = PyUnicode_GET_LENGTH(text);
    for (index = 0; index < length; index++) {
        Py_UCS4 current = PyUnicode_READ(kind, data, index);
        if ((index & 65535) == 0 && PyErr_CheckSignals() < 0) {
            return NULL;
        }
        if (current == '_') {
            Py_RETURN_TRUE;
        }
        if (current >= 'A' && current <= 'Z' && index) {
            if ((previous >= 'a' && previous <= 'z') || (previous >= '0' && previous <= '9')) {
                Py_RETURN_TRUE;
            }
            if (previous >= 'A' && previous <= 'Z' && index + 1 < length) {
                Py_UCS4 next = PyUnicode_READ(kind, data, index + 1);
                if (next >= 'a' && next <= 'z') {
                    Py_RETURN_TRUE;
                }
            }
        }
        previous = current;
    }
    Py_RETURN_FALSE;
}

#endif
