/* Source-preserving segmentation.  The wrappers retain the Python reference
 * and certify classes/helpers before entry.  Each loop owns its current item;
 * callbacks are looked up and called at the same point as in the reference. */
#ifndef MEMORY_BOOK_NATIVE_SEGMENTATION_H
#define MEMORY_BOOK_NATIVE_SEGMENTATION_H

static PyObject *
segmentation_global(PyObject *globals, const char *name)
{
    PyObject *value = PyDict_GetItemString(globals, name);
    if (value == NULL) {
        if (!PyErr_Occurred()) {
            PyErr_Format(PyExc_NameError, "name '%s' is not defined", name);
        }
        return NULL;
    }
    return Py_NewRef(value);
}

static PyObject *
segmentation_item(PyObject *mapping, const char *name)
{
    PyObject *key = PyUnicode_FromString(name), *value;
    if (key == NULL) {
        return NULL;
    }
    value = PyObject_GetItem(mapping, key);
    Py_DECREF(key);
    return value;
}

static int
segmentation_named_dict(PyObject *value)
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
segmentation_plain_messages(PyObject *messages)
{
    PyObject *snapshot;
    Py_ssize_t index;
    int ready = 1;
    if (!PyList_CheckExact(messages)) {
        return 0;
    }
    snapshot = PyList_AsTuple(messages);
    if (snapshot == NULL) {
        return -1;
    }
    for (index = 0; index < PyTuple_GET_SIZE(snapshot); index++) {
        PyObject *message = PyTuple_GET_ITEM(snapshot, index), *role, *content;
        if (!segmentation_named_dict(message)) {
            ready = 0;
            break;
        }
        role = PyDict_GetItemString(message, "role");
        content = PyDict_GetItemString(message, "content");
        if (role == NULL || content == NULL
                || !PyUnicode_CheckExact(role) || !PyUnicode_CheckExact(content)) {
            ready = PyErr_Occurred() ? -1 : 0;
            break;
        }
    }
    Py_DECREF(snapshot);
    return ready;
}

static int
segmentation_plain_turns(PyObject *turns, PyObject *globals)
{
    PyObject *snapshot, *turn_class;
    Py_ssize_t index;
    int ready = 1;
    if (!PyList_CheckExact(turns) || !PyDict_CheckExact(globals)) {
        return 0;
    }
    turn_class = PyDict_GetItemString(globals, "Turn");
    if (turn_class == NULL || !PyType_Check(turn_class)) {
        return PyErr_Occurred() ? -1 : 0;
    }
    Py_INCREF(turn_class);
    snapshot = PyList_AsTuple(turns);
    if (snapshot == NULL) {
        Py_DECREF(turn_class);
        return -1;
    }
    for (index = 0; index < PyTuple_GET_SIZE(snapshot); index++) {
        PyObject *turn = PyTuple_GET_ITEM(snapshot, index), *dictionary;
        PyObject *ordinal, *question, *content, *indices;
        Py_ssize_t message;
        if (Py_TYPE(turn) != (PyTypeObject *)turn_class) {
            ready = 0;
            break;
        }
        dictionary = PyObject_GenericGetDict(turn, NULL);
        if (dictionary == NULL) {
            if (PyErr_ExceptionMatches(PyExc_AttributeError)) {
                PyErr_Clear();
                ready = 0;
            }
            else {
                ready = -1;
            }
            break;
        }
        /* An ordinary instance can still have a non-string key manually
         * inserted into __dict__.  Refuse it before named lookups: a colliding
         * key's equality callback could mutate the dict and invalidate earlier
         * borrowed field values during this preflight. */
        if (!segmentation_named_dict(dictionary)) {
            Py_DECREF(dictionary);
            ready = 0;
            break;
        }
        ordinal = PyDict_GetItemString(dictionary, "index");
        question = PyDict_GetItemString(dictionary, "question");
        content = PyDict_GetItemString(dictionary, "content");
        indices = PyDict_GetItemString(dictionary, "message_indices");
        if (ordinal == NULL || question == NULL || content == NULL || indices == NULL
                || !PyLong_CheckExact(ordinal) || !PyUnicode_CheckExact(question)
                || !PyUnicode_CheckExact(content) || !PyTuple_CheckExact(indices)) {
            ready = PyErr_Occurred() ? -1 : 0;
        }
        else {
            for (message = 0; message < PyTuple_GET_SIZE(indices); message++) {
                if (!PyLong_CheckExact(PyTuple_GET_ITEM(indices, message))) {
                    ready = 0;
                    break;
                }
            }
        }
        Py_DECREF(dictionary);
        if (ready != 1) {
            break;
        }
    }
    Py_DECREF(snapshot);
    Py_DECREF(turn_class);
    return ready;
}

static int
segmentation_cap(PyObject *cap, Py_ssize_t *number)
{
    if (!PyLong_CheckExact(cap)) {
        return 0;
    }
    *number = PyLong_AsSsize_t(cap);
    if (*number == -1 && PyErr_Occurred()) {
        PyErr_Clear();
        return 0;
    }
    return *number > 0;
}

static PyObject *
segmentation_headline(PyObject *globals, PyObject *turn, int limit)
{
    PyObject *function = segmentation_global(globals, "headline");
    PyObject *question = NULL, *bound = NULL, *result = NULL;
    if (function == NULL) {
        return NULL;
    }
    question = PyObject_GetAttrString(turn, "question");
    if (question == NULL) {
        goto done;
    }
    if (limit < 0) {
        result = PyObject_CallOneArg(function, question);
    }
    else {
        bound = PyLong_FromLong(limit);
        if (bound != NULL) {
            result = PyObject_CallFunctionObjArgs(function, question, bound, NULL);
        }
    }
done:
    Py_DECREF(function);
    Py_XDECREF(question);
    Py_XDECREF(bound);
    return result;
}

static int
segmentation_attr_length(PyObject *turn, const char *name, Py_ssize_t *length)
{
    PyObject *value = PyObject_GetAttrString(turn, name);
    if (value == NULL) {
        return -1;
    }
    *length = PyObject_Length(value);
    Py_DECREF(value);
    return *length < 0 ? -1 : 0;
}

static PyObject *
segmentation_slice(PyObject *value, PyObject *start, PyObject *end)
{
    PyObject *slice = PySlice_New(start, end, Py_None), *result;
    if (slice == NULL) {
        return NULL;
    }
    result = PyObject_GetItem(value, slice);
    Py_DECREF(slice);
    return result;
}

static int
segmentation_unpack_pair(PyObject *value, PyObject **first, PyObject **second)
{
    PyObject *sequence = PySequence_Fast(value, "expected an iterable pair");
    if (sequence == NULL) {
        return -1;
    }
    if (PySequence_Fast_GET_SIZE(sequence) != 2) {
        PyErr_SetString(PyExc_ValueError, "expected exactly two values");
        Py_DECREF(sequence);
        return -1;
    }
    *first = Py_NewRef(PySequence_Fast_GET_ITEM(sequence, 0));
    *second = Py_NewRef(PySequence_Fast_GET_ITEM(sequence, 1));
    Py_DECREF(sequence);
    return 0;
}

static PyObject *
native_make_turns(PyObject *self, PyObject *args)
{
    PyObject *messages, *globals;
    PyObject *groups = NULL, *pending = NULL, *turns = NULL, *iterator = NULL;
    PyObject *message = NULL, *role = NULL, *pair = NULL, *user = NULL, *allowed = NULL;
    PyObject *group = NULL, *question = NULL, *parts = NULL, *body = NULL;
    PyObject *indices = NULL, *constructor = NULL, *ordinal = NULL, *created = NULL;
    PyObject *separator = NULL, *note = NULL, *result = NULL;
    Py_ssize_t number = 0, group_index;
    int ready, yes;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO:make_turns", &messages, &globals)) {
        return NULL;
    }
    ready = segmentation_plain_messages(messages);
    if (ready < 0) {
        return NULL;
    }
    if (!ready || !PyDict_CheckExact(globals)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    groups = PyList_New(0);
    pending = PyList_New(0);
    turns = PyList_New(0);
    user = PyUnicode_FromString("user");
    separator = PyUnicode_FromString("\n\n");
    note = PyUnicode_FromString("Conversation note");
    pair = Py_BuildValue("(sss)", "user", "assistant", "tool");
    if (pair != NULL) {
        allowed = PyFrozenSet_New(pair);
        Py_CLEAR(pair);
    }
    iterator = PyObject_GetIter(messages);
    if (groups == NULL || pending == NULL || turns == NULL || user == NULL
            || separator == NULL || note == NULL || allowed == NULL || iterator == NULL) {
        goto done;
    }
    while ((message = PyIter_Next(iterator)) != NULL) {
        if ((number & 4095) == 0 && PyErr_CheckSignals() < 0) goto done;
        role = segmentation_item(message, "role");
        if (role == NULL) {
            goto done;
        }
        yes = PyObject_RichCompareBool(role, user, Py_EQ);
        Py_CLEAR(role);
        if (yes < 0) {
            goto done;
        }
        if (yes) {
            int conversational = 0;
            Py_ssize_t index;
            for (index = 0; index < PyList_GET_SIZE(pending); index++) {
                PyObject *old = Py_NewRef(PyList_GET_ITEM(pending, index));
                PyObject *old_message = Py_NewRef(PyTuple_GET_ITEM(old, 1));
                role = segmentation_item(old_message, "role");
                Py_DECREF(old_message);
                Py_DECREF(old);
                if (role == NULL) {
                    goto done;
                }
                conversational = PySet_Contains(allowed, role);
                Py_CLEAR(role);
                if (conversational < 0) {
                    goto done;
                }
                if (conversational) {
                    break;
                }
            }
            if (PyList_GET_SIZE(pending) && conversational && PyList_Append(groups, pending) < 0) {
                goto done;
            }
            Py_CLEAR(pending);
            pending = PyList_New(0);
            if (pending == NULL) {
                goto done;
            }
            pair = Py_BuildValue("(nO)", number, message);
            if (pair == NULL || PyList_Append(pending, pair) < 0) {
                goto done;
            }
            Py_CLEAR(pair);
        }
        else {
            int keep = PyList_GET_SIZE(pending) != 0;
            if (!keep) {
                PyObject *assistant = NULL, *tool = NULL;
                role = segmentation_item(message, "role");
                assistant = PyUnicode_FromString("assistant");
                tool = PyUnicode_FromString("tool");
                if (role == NULL || assistant == NULL || tool == NULL) {
                    Py_XDECREF(assistant);
                    Py_XDECREF(tool);
                    goto done;
                }
                /* Exact roles were certified.  Use set membership for the
                 * reference's hash/equality behavior if a callback changed one. */
                pair = PyTuple_Pack(2, assistant, tool);
                Py_DECREF(assistant);
                Py_DECREF(tool);
                if (pair != NULL) {
                    PyObject *roles = PyFrozenSet_New(pair);
                    Py_CLEAR(pair);
                    if (roles != NULL) {
                        keep = PySet_Contains(roles, role);
                        Py_DECREF(roles);
                    }
                    else {
                        keep = -1;
                    }
                }
                else {
                    keep = -1;
                }
                Py_CLEAR(role);
                if (keep < 0) {
                    goto done;
                }
            }
            if (keep) {
                pair = Py_BuildValue("(nO)", number, message);
                if (pair == NULL || PyList_Append(pending, pair) < 0) {
                    goto done;
                }
                Py_CLEAR(pair);
            }
        }
        Py_CLEAR(message);
        number++;
    }
    if (PyErr_Occurred() || (PyList_GET_SIZE(pending) && PyList_Append(groups, pending) < 0)) {
        goto done;
    }
    Py_CLEAR(iterator);
    for (group_index = 0; group_index < PyList_GET_SIZE(groups); group_index++) {
        Py_ssize_t index;
        group = Py_NewRef(PyList_GET_ITEM(groups, group_index));
        question = Py_NewRef(note);
        for (index = 0; index < PyList_GET_SIZE(group); index++) {
            pair = Py_NewRef(PyList_GET_ITEM(group, index));
            message = Py_NewRef(PyTuple_GET_ITEM(pair, 1));
            role = segmentation_item(message, "role");
            if (role == NULL) {
                goto done;
            }
            yes = PyObject_RichCompareBool(role, user, Py_EQ);
            Py_CLEAR(role);
            if (yes < 0) {
                goto done;
            }
            if (yes) {
                PyObject *value = segmentation_item(message, "content");
                if (value == NULL) {
                    goto done;
                }
                Py_SETREF(question, value);
            }
            Py_CLEAR(message);
            Py_CLEAR(pair);
            if (yes) {
                break;
            }
        }
        parts = PyList_New(0);
        if (parts == NULL) {
            goto done;
        }
        for (index = 0; index < PyList_GET_SIZE(group); index++) {
            PyObject *upper = NULL, *role_text = NULL, *content = NULL, *content_text = NULL;
            PyObject *colon = NULL, *prefix = NULL, *line = NULL;
            pair = Py_NewRef(PyList_GET_ITEM(group, index));
            message = Py_NewRef(PyTuple_GET_ITEM(pair, 1));
            role = segmentation_item(message, "role");
            if (role != NULL) {
                upper = PyObject_CallMethod(role, "upper", NULL);
            }
            if (upper != NULL) {
                role_text = PyObject_Format(upper, NULL);
            }
            if (role_text != NULL) {
                content = segmentation_item(message, "content");
            }
            if (content != NULL) {
                content_text = PyObject_Format(content, NULL);
            }
            if (content_text != NULL) {
                colon = PyUnicode_FromString(": ");
            }
            if (colon != NULL) {
                prefix = PyUnicode_Concat(role_text, colon);
            }
            if (prefix != NULL) {
                line = PyUnicode_Concat(prefix, content_text);
            }
            yes = line == NULL ? -1 : PyList_Append(parts, line);
            Py_XDECREF(upper);
            Py_XDECREF(role_text);
            Py_XDECREF(content);
            Py_XDECREF(content_text);
            Py_XDECREF(colon);
            Py_XDECREF(prefix);
            Py_XDECREF(line);
            Py_CLEAR(role);
            Py_CLEAR(message);
            Py_CLEAR(pair);
            if (yes < 0) {
                goto done;
            }
        }
        body = PyUnicode_Join(separator, parts);
        if (body == NULL) goto done;
        constructor = segmentation_global(globals, "Turn");
        if (constructor == NULL) goto done;
        ordinal = PyLong_FromSsize_t(PyList_GET_SIZE(turns));
        indices = PyTuple_New(PyList_GET_SIZE(group));
        if (body == NULL || constructor == NULL || ordinal == NULL || indices == NULL) {
            goto done;
        }
        for (index = 0; index < PyList_GET_SIZE(group); index++) {
            PyObject *entry = PyList_GET_ITEM(group, index);
            PyTuple_SET_ITEM(indices, index, Py_NewRef(PyTuple_GET_ITEM(entry, 0)));
        }
        created = PyObject_CallFunctionObjArgs(constructor, ordinal, question, body, indices, NULL);
        if (created == NULL || PyList_Append(turns, created) < 0) {
            goto done;
        }
        Py_CLEAR(group);
        Py_CLEAR(question);
        Py_CLEAR(parts);
        Py_CLEAR(body);
        Py_CLEAR(constructor);
        Py_CLEAR(ordinal);
        Py_CLEAR(indices);
        Py_CLEAR(created);
    }
    result = Py_NewRef(turns);
done:
    Py_XDECREF(groups); Py_XDECREF(pending); Py_XDECREF(turns); Py_XDECREF(iterator);
    Py_XDECREF(message); Py_XDECREF(role); Py_XDECREF(pair); Py_XDECREF(user); Py_XDECREF(allowed);
    Py_XDECREF(group); Py_XDECREF(question); Py_XDECREF(parts); Py_XDECREF(body);
    Py_XDECREF(indices); Py_XDECREF(constructor); Py_XDECREF(ordinal); Py_XDECREF(created);
    Py_XDECREF(separator); Py_XDECREF(note);
    return result;
}

static PyObject *
native_joined_turns(PyObject *self, PyObject *args)
{
    PyObject *turns, *globals, *iterator = NULL, *turn = NULL;
    PyObject *parts = NULL, *refs = NULL, *position = NULL, *two = NULL, *zero = NULL;
    PyObject *content = NULL, *ordinal = NULL, *end = NULL, *length_object = NULL;
    PyObject *indices = NULL, *indices_list = NULL, *ref = NULL, *joined = NULL, *separator = NULL;
    PyObject *temporary = NULL, *result = NULL;
    Py_ssize_t length;
    int ready;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO:joined_turns", &turns, &globals)) {
        return NULL;
    }
    ready = segmentation_plain_turns(turns, globals);
    if (ready < 0) return NULL;
    if (!ready) Py_RETURN_NOTIMPLEMENTED;
    parts = PyList_New(0); refs = PyList_New(0);
    position = PyLong_FromLong(0); two = PyLong_FromLong(2); zero = PyLong_FromLong(0);
    iterator = PyObject_GetIter(turns);
    if (parts == NULL || refs == NULL || position == NULL || two == NULL || zero == NULL || iterator == NULL) goto done;
    while ((turn = PyIter_Next(iterator)) != NULL) {
        if (PyList_GET_SIZE(parts)) {
            temporary = PyNumber_Add(position, two);
            if (temporary == NULL) goto done;
            Py_SETREF(position, temporary); temporary = NULL;
        }
        content = PyObject_GetAttrString(turn, "content");
        if (content == NULL || PyList_Append(parts, content) < 0) goto done;
        Py_CLEAR(content);
        ordinal = PyObject_GetAttrString(turn, "index");
        if (ordinal == NULL || segmentation_attr_length(turn, "content", &length) < 0) goto done;
        length_object = PyLong_FromSsize_t(length);
        if (length_object == NULL) goto done;
        end = PyNumber_Add(position, length_object);
        Py_CLEAR(length_object);
        if (end == NULL || segmentation_attr_length(turn, "content", &length) < 0) goto done;
        length_object = PyLong_FromSsize_t(length);
        indices = PyObject_GetAttrString(turn, "message_indices");
        if (length_object == NULL || indices == NULL) goto done;
        indices_list = PySequence_List(indices);
        if (indices_list == NULL) goto done;
        ref = Py_BuildValue("{s:O,s:O,s:O,s:O,s:O,s:O}", "turn_index", ordinal, "start", position,
                           "end", end, "turn_start", zero, "turn_end", length_object,
                           "message_indices", indices_list);
        if (ref == NULL || PyList_Append(refs, ref) < 0) goto done;
        Py_CLEAR(length_object);
        if (segmentation_attr_length(turn, "content", &length) < 0) goto done;
        length_object = PyLong_FromSsize_t(length);
        if (length_object == NULL) goto done;
        temporary = PyNumber_Add(position, length_object);
        if (temporary == NULL) goto done;
        Py_SETREF(position, temporary); temporary = NULL;
        Py_CLEAR(turn); Py_CLEAR(ordinal); Py_CLEAR(end); Py_CLEAR(length_object);
        Py_CLEAR(indices); Py_CLEAR(indices_list); Py_CLEAR(ref);
    }
    if (PyErr_Occurred()) goto done;
    separator = PyUnicode_FromString("\n\n");
    if (separator == NULL) goto done;
    joined = PyUnicode_Join(separator, parts);
    if (joined != NULL) result = PyTuple_Pack(2, joined, refs);
done:
    Py_XDECREF(iterator); Py_XDECREF(turn); Py_XDECREF(parts); Py_XDECREF(refs);
    Py_XDECREF(position); Py_XDECREF(two); Py_XDECREF(zero); Py_XDECREF(content);
    Py_XDECREF(ordinal); Py_XDECREF(end); Py_XDECREF(length_object); Py_XDECREF(indices);
    Py_XDECREF(indices_list); Py_XDECREF(ref); Py_XDECREF(joined); Py_XDECREF(separator);
    Py_XDECREF(temporary);
    return result;
}

static PyObject *
native_page_cuts(PyObject *self, PyObject *args)
{
    PyObject *text, *cap_object, *cuts = NULL, *double_newline = NULL, *newline = NULL;
    Py_ssize_t cap, length, start = 0;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO:page_cuts", &text, &cap_object)) return NULL;
    if (!PyUnicode_CheckExact(text) || !segmentation_cap(cap_object, &cap)) Py_RETURN_NOTIMPLEMENTED;
    if (require_exact_unicode(text) < 0) return NULL;
    length = PyUnicode_GET_LENGTH(text);
    cuts = PyList_New(0);
    double_newline = PyUnicode_FromString("\n\n");
    newline = PyUnicode_FromString("\n");
    if (cuts == NULL || double_newline == NULL || newline == NULL) goto error;
    while (start < length) {
        Py_ssize_t end = cap >= length - start ? length : start + cap;
        if (PyErr_CheckSignals() < 0) goto error;
        if (end < length) {
            Py_ssize_t floor = start + cap / 2;
            Py_ssize_t boundary = PyUnicode_Find(text, double_newline, floor, end, -1);
            if (boundary == -2) goto error;
            if (boundary < 0) {
                boundary = PyUnicode_Find(text, newline, floor, end, -1);
                if (boundary == -2) goto error;
            }
            if (boundary >= floor) {
                end = boundary + ((boundary + 1 < length && PyUnicode_READ_CHAR(text, boundary + 1) == '\n') ? 2 : 1);
            }
        }
        if (append_span(cuts, start, end) < 0) goto error;
        start = end;
    }
    Py_DECREF(double_newline); Py_DECREF(newline);
    return cuts;
error:
    Py_XDECREF(cuts); Py_XDECREF(double_newline); Py_XDECREF(newline);
    return NULL;
}

static PyObject *
native_build_pages(PyObject *self, PyObject *args)
{
    PyObject *group, *cap, *globals, *function = NULL, *joined = NULL, *text = NULL, *refs = NULL;
    PyObject *spans = NULL, *hints = NULL, *first_title = NULL, *pages = NULL;
    PyObject *iterator = NULL, *turn = NULL, *key = NULL, *hint = NULL, *first = NULL;
    PyObject *span_iterator = NULL, *span = NULL, *start = NULL, *end = NULL;
    PyObject *local_refs = NULL, *ref_iterator = NULL, *ref = NULL, *lo = NULL, *hi = NULL;
    PyObject *ref_start = NULL, *ref_end = NULL, *copy = NULL, *value = NULL, *temporary = NULL;
    PyObject *suffix = NULL, *local_turns = NULL, *question_parts = NULL, *question = NULL;
    PyObject *separator = NULL, *title = NULL, *content = NULL, *ref_tuple = NULL, *page = NULL;
    PyObject *result = NULL;
    Py_ssize_t cap_number, number = 0, span_count;
    int ready, comparison;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:build_pages", &group, &cap, &globals)) return NULL;
    ready = segmentation_plain_turns(group, globals);
    if (ready < 0) return NULL;
    if (!ready || (cap != Py_None && !segmentation_cap(cap, &cap_number))) Py_RETURN_NOTIMPLEMENTED;
    function = segmentation_global(globals, "_joined");
    if (function == NULL) goto done;
    joined = PyObject_CallOneArg(function, group);
    Py_CLEAR(function);
    if (joined == NULL || segmentation_unpack_pair(joined, &text, &refs) < 0) goto done;
    Py_CLEAR(joined);
    if (cap == Py_None) {
        Py_ssize_t length = PyObject_Length(text);
        if (length < 0) goto done;
        span = Py_BuildValue("(nn)", (Py_ssize_t)0, length);
        spans = PyList_New(0);
        if (span == NULL || spans == NULL || PyList_Append(spans, span) < 0) goto done;
        Py_CLEAR(span);
    }
    else {
        function = segmentation_global(globals, "_cuts");
        if (function == NULL) goto done;
        spans = PyObject_CallFunctionObjArgs(function, text, cap, NULL);
        Py_CLEAR(function);
        if (spans == NULL) goto done;
    }
    hints = PyDict_New();
    iterator = PyObject_GetIter(group);
    if (hints == NULL || iterator == NULL) goto done;
    while ((turn = PyIter_Next(iterator)) != NULL) {
        /* A comprehension evaluates its key before the headline callback. */
        key = PyObject_GetAttrString(turn, "index");
        if (key == NULL) goto done;
        hint = segmentation_headline(globals, turn, 240);
        if (hint == NULL || PyDict_SetItem(hints, key, hint) < 0) goto done;
        Py_CLEAR(key); Py_CLEAR(hint); Py_CLEAR(turn);
    }
    if (PyErr_Occurred()) goto done;
    Py_CLEAR(iterator);
    first = PySequence_GetItem(group, 0);
    if (first == NULL) goto done;
    first_title = segmentation_headline(globals, first, 76);
    Py_CLEAR(first);
    pages = PyList_New(0);
    span_iterator = PyObject_GetIter(spans);
    if (first_title == NULL || pages == NULL || span_iterator == NULL) goto done;
    while ((span = PyIter_Next(span_iterator)) != NULL) {
        if (segmentation_unpack_pair(span, &start, &end) < 0) goto done;
        local_refs = PyList_New(0);
        ref_iterator = PyObject_GetIter(refs);
        if (local_refs == NULL || ref_iterator == NULL) goto done;
        while ((ref = PyIter_Next(ref_iterator)) != NULL) {
            ref_start = segmentation_item(ref, "start");
            if (ref_start == NULL) goto done;
            comparison = PyObject_RichCompareBool(ref_start, start, Py_GT);
            if (comparison < 0) goto done;
            lo = Py_NewRef(comparison ? ref_start : start);
            ref_end = segmentation_item(ref, "end");
            if (ref_end == NULL) goto done;
            comparison = PyObject_RichCompareBool(ref_end, end, Py_LT);
            if (comparison < 0) goto done;
            hi = Py_NewRef(comparison ? ref_end : end);
            comparison = PyObject_RichCompareBool(lo, hi, Py_LT);
            if (comparison < 0) goto done;
            if (comparison) {
                copy = PyDict_New();
                if (copy == NULL || PyDict_Update(copy, ref) < 0) goto done;
                value = PyNumber_Subtract(lo, start);
                if (value == NULL || PyDict_SetItemString(copy, "start", value) < 0) goto done;
                Py_CLEAR(value);
                value = PyNumber_Subtract(hi, start);
                if (value == NULL || PyDict_SetItemString(copy, "end", value) < 0) goto done;
                Py_CLEAR(value); Py_CLEAR(ref_start);
                ref_start = segmentation_item(ref, "start");
                if (ref_start == NULL) goto done;
                value = PyNumber_Subtract(lo, ref_start);
                if (value == NULL || PyDict_SetItemString(copy, "turn_start", value) < 0) goto done;
                Py_CLEAR(value); Py_CLEAR(ref_start);
                ref_start = segmentation_item(ref, "start");
                if (ref_start == NULL) goto done;
                value = PyNumber_Subtract(hi, ref_start);
                if (value == NULL || PyDict_SetItemString(copy, "turn_end", value) < 0) goto done;
                Py_CLEAR(value);
                if (PyList_Append(local_refs, copy) < 0) goto done;
                Py_CLEAR(copy);
            }
            Py_CLEAR(ref); Py_CLEAR(ref_start); Py_CLEAR(ref_end); Py_CLEAR(lo); Py_CLEAR(hi);
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(ref_iterator);
        span_count = PyObject_Length(spans);
        if (span_count < 0) goto done;
        suffix = span_count > 1 ? PyUnicode_FromFormat(" %c %zd/%zd", 0x00b7, number + 1, span_count)
                               : PyUnicode_New(0, 0);
        local_turns = PySet_New(NULL);
        ref_iterator = PyObject_GetIter(local_refs);
        if (suffix == NULL || local_turns == NULL || ref_iterator == NULL) goto done;
        while ((ref = PyIter_Next(ref_iterator)) != NULL) {
            key = segmentation_item(ref, "turn_index");
            if (key == NULL || PySet_Add(local_turns, key) < 0) goto done;
            Py_CLEAR(key); Py_CLEAR(ref);
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(ref_iterator);
        question_parts = PyList_New(0);
        iterator = PyObject_GetIter(group);
        if (question_parts == NULL || iterator == NULL) goto done;
        while ((turn = PyIter_Next(iterator)) != NULL) {
            key = PyObject_GetAttrString(turn, "index");
            if (key == NULL) goto done;
            comparison = PySet_Contains(local_turns, key);
            Py_CLEAR(key);
            if (comparison < 0) goto done;
            if (comparison) {
                key = PyObject_GetAttrString(turn, "index");
                if (key == NULL) goto done;
                hint = PyObject_GetItem(hints, key);
                if (hint == NULL || PyList_Append(question_parts, hint) < 0) goto done;
                Py_CLEAR(key); Py_CLEAR(hint);
            }
            Py_CLEAR(turn);
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(iterator);
        separator = PyUnicode_FromString(" | ");
        if (separator == NULL) goto done;
        temporary = PyUnicode_Join(separator, question_parts);
        if (temporary == NULL) goto done;
        question = PyUnicode_Substring(temporary, 0, 1200);
        Py_CLEAR(temporary); Py_CLEAR(separator);
        if (question == NULL) goto done;
        function = segmentation_global(globals, "Page");
        if (function == NULL) goto done;
        title = PyNumber_Add(first_title, suffix);
        if (title == NULL) goto done;
        content = segmentation_slice(text, start, end);
        if (content == NULL) goto done;
        ref_tuple = PySequence_Tuple(local_refs);
        if (ref_tuple == NULL) goto done;
        page = PyObject_CallFunctionObjArgs(function, title, question, content, ref_tuple, NULL);
        if (page == NULL || PyList_Append(pages, page) < 0) goto done;
        Py_CLEAR(function); Py_CLEAR(title); Py_CLEAR(content); Py_CLEAR(ref_tuple); Py_CLEAR(page);
        Py_CLEAR(span); Py_CLEAR(start); Py_CLEAR(end); Py_CLEAR(local_refs);
        Py_CLEAR(suffix); Py_CLEAR(local_turns); Py_CLEAR(question_parts); Py_CLEAR(question);
        number++;
    }
    if (!PyErr_Occurred()) result = PySequence_Tuple(pages);
done:
    Py_XDECREF(function); Py_XDECREF(joined); Py_XDECREF(text); Py_XDECREF(refs); Py_XDECREF(spans);
    Py_XDECREF(hints); Py_XDECREF(first_title); Py_XDECREF(pages); Py_XDECREF(iterator);
    Py_XDECREF(turn); Py_XDECREF(key); Py_XDECREF(hint); Py_XDECREF(first); Py_XDECREF(span_iterator);
    Py_XDECREF(span); Py_XDECREF(start); Py_XDECREF(end); Py_XDECREF(local_refs); Py_XDECREF(ref_iterator);
    Py_XDECREF(ref); Py_XDECREF(lo); Py_XDECREF(hi); Py_XDECREF(ref_start); Py_XDECREF(ref_end);
    Py_XDECREF(copy); Py_XDECREF(value); Py_XDECREF(temporary); Py_XDECREF(suffix); Py_XDECREF(local_turns);
    Py_XDECREF(question_parts); Py_XDECREF(question); Py_XDECREF(separator); Py_XDECREF(title);
    Py_XDECREF(content); Py_XDECREF(ref_tuple); Py_XDECREF(page);
    return result;
}

static PyObject *
native_segment_turns(PyObject *self, PyObject *args)
{
    PyObject *turns, *mode, *maximum, *minimum, *threshold, *globals;
    PyObject *groups = NULL, *current = NULL, *size = NULL, *two = NULL, *iterator = NULL;
    PyObject *turn = NULL, *function = NULL, *last = NULL, *left = NULL, *right = NULL;
    PyObject *value = NULL, *related = NULL, *length_object = NULL, *candidate = NULL, *temporary = NULL;
    PyObject *group = NULL, *sections = NULL, *constructor = NULL, *title = NULL, *summary = NULL;
    PyObject *summary_parts = NULL, *group_iterator = NULL, *separator = NULL, *pages = NULL, *section = NULL;
    PyObject *result = NULL;
    Py_ssize_t maximum_number, length, group_index;
    int ready, adaptive, session, related_true, can_fit, split;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOOO:segment_turns", &turns, &mode, &maximum,
                          &minimum, &threshold, &globals)) return NULL;
    ready = segmentation_plain_turns(turns, globals);
    if (ready < 0) return NULL;
    if (!ready || !PyUnicode_CheckExact(mode) || !PyList_GET_SIZE(turns)
            || !segmentation_cap(maximum, &maximum_number) || !PyLong_CheckExact(minimum)
            || !(PyFloat_CheckExact(threshold) || PyLong_CheckExact(threshold))) Py_RETURN_NOTIMPLEMENTED;
    adaptive = PyUnicode_CompareWithASCIIString(mode, "adaptive") == 0;
    session = PyUnicode_CompareWithASCIIString(mode, "session") == 0;
    if (!adaptive && !session && PyUnicode_CompareWithASCIIString(mode, "turn") != 0) Py_RETURN_NOTIMPLEMENTED;
    groups = PyList_New(0);
    two = PyLong_FromLong(2);
    if (groups == NULL || two == NULL) goto done;
    if (session) {
        if (PyList_Append(groups, turns) < 0) goto done;
    }
    else if (!adaptive) {
        iterator = PyObject_GetIter(turns);
        if (iterator == NULL) goto done;
        while ((turn = PyIter_Next(iterator)) != NULL) {
            current = PyList_New(0);
            if (current == NULL || PyList_Append(current, turn) < 0 || PyList_Append(groups, current) < 0) goto done;
            Py_CLEAR(current); Py_CLEAR(turn);
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(iterator);
    }
    else {
        current = PyList_New(0);
        size = PyLong_FromLong(0);
        iterator = PyObject_GetIter(turns);
        if (current == NULL || size == NULL || iterator == NULL) goto done;
        while ((turn = PyIter_Next(iterator)) != NULL) {
            related = Py_NewRef(Py_True);
            if (PyList_GET_SIZE(current)) {
                function = segmentation_global(globals, "similarity");
                last = PySequence_GetItem(current, -1);
                if (function == NULL || last == NULL) goto done;
                left = PyObject_GetAttrString(last, "question");
                right = PyObject_GetAttrString(turn, "question");
                if (left == NULL || right == NULL) goto done;
                value = PyObject_CallFunctionObjArgs(function, left, right, NULL);
                Py_CLEAR(function); Py_CLEAR(last); Py_CLEAR(left); Py_CLEAR(right);
                if (value == NULL) goto done;
                temporary = PyObject_RichCompare(value, threshold, Py_GE);
                Py_CLEAR(value);
                if (temporary == NULL) goto done;
                Py_SETREF(related, temporary); temporary = NULL;
                related_true = PyObject_IsTrue(related);
                if (related_true < 0) goto done;
                if (!related_true) {
                    function = segmentation_global(globals, "is_followup");
                    if (function == NULL) goto done;
                    right = PyObject_GetAttrString(turn, "question");
                    if (right == NULL) goto done;
                    temporary = PyObject_CallOneArg(function, right);
                    Py_CLEAR(function); Py_CLEAR(right);
                    if (temporary == NULL) goto done;
                    Py_SETREF(related, temporary); temporary = NULL;
                }
            }
            if (segmentation_attr_length(turn, "content", &length) < 0) goto done;
            length_object = PyLong_FromSsize_t(length);
            if (length_object == NULL) goto done;
            candidate = PyNumber_Add(size, length_object);
            Py_CLEAR(length_object);
            if (candidate == NULL) goto done;
            temporary = PyNumber_Add(candidate, two);
            Py_CLEAR(candidate);
            if (temporary == NULL) goto done;
            can_fit = PyObject_RichCompareBool(temporary, maximum, Py_LE);
            Py_CLEAR(temporary);
            if (can_fit < 0) goto done;
            split = 0;
            if (PyList_GET_SIZE(current)) {
                split = !can_fit;
                if (!split) {
                    related_true = PyObject_IsTrue(related);
                    if (related_true < 0) goto done;
                    if (!related_true) {
                        split = PyObject_RichCompareBool(size, minimum, Py_GE);
                        if (split < 0) goto done;
                    }
                    if (!split) split = PyList_GET_SIZE(current) >= 4;
                }
            }
            if (split) {
                if (PyList_Append(groups, current) < 0) goto done;
                Py_CLEAR(current); Py_CLEAR(size);
                current = PyList_New(0); size = PyLong_FromLong(0);
                if (current == NULL || size == NULL) goto done;
            }
            if (PyList_Append(current, turn) < 0 || segmentation_attr_length(turn, "content", &length) < 0) goto done;
            length_object = PyLong_FromSsize_t(length);
            if (length_object == NULL) goto done;
            candidate = PyNumber_Add(length_object, two);
            Py_CLEAR(length_object);
            if (candidate == NULL) goto done;
            temporary = PyNumber_Add(size, candidate);
            Py_CLEAR(candidate);
            if (temporary == NULL) goto done;
            Py_SETREF(size, temporary); temporary = NULL;
            Py_CLEAR(related); Py_CLEAR(turn);
        }
        if (PyErr_Occurred() || (PyList_GET_SIZE(current) && PyList_Append(groups, current) < 0)) goto done;
        Py_CLEAR(iterator);
    }
    sections = PyList_New(0);
    separator = PyUnicode_FromString(" \xc2\xb7 ");
    if (sections == NULL || separator == NULL) goto done;
    for (group_index = 0; group_index < PyList_GET_SIZE(groups); group_index++) {
        group = Py_NewRef(PyList_GET_ITEM(groups, group_index));
        constructor = segmentation_global(globals, "Section");
        if (constructor == NULL) goto done;
        last = PySequence_GetItem(group, 0);
        if (last == NULL) goto done;
        title = segmentation_headline(globals, last, -1);
        Py_CLEAR(last);
        if (title == NULL) goto done;
        summary_parts = PyList_New(0);
        group_iterator = PyObject_GetIter(group);
        if (summary_parts == NULL || group_iterator == NULL) goto done;
        while ((turn = PyIter_Next(group_iterator)) != NULL) {
            value = segmentation_headline(globals, turn, 96);
            if (value == NULL || PyList_Append(summary_parts, value) < 0) goto done;
            Py_CLEAR(value); Py_CLEAR(turn);
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(group_iterator);
        temporary = PyUnicode_Join(separator, summary_parts);
        if (temporary == NULL) goto done;
        summary = PyUnicode_Substring(temporary, 0, 360);
        Py_CLEAR(temporary);
        if (summary == NULL) goto done;
        function = segmentation_global(globals, "_pages");
        if (function == NULL) goto done;
        pages = PyObject_CallFunctionObjArgs(function, group, adaptive ? maximum : Py_None, NULL);
        Py_CLEAR(function);
        if (pages == NULL) goto done;
        section = PyObject_CallFunctionObjArgs(constructor, title, summary, pages, NULL);
        if (section == NULL || PyList_Append(sections, section) < 0) goto done;
        Py_CLEAR(group); Py_CLEAR(constructor); Py_CLEAR(title); Py_CLEAR(summary);
        Py_CLEAR(summary_parts); Py_CLEAR(pages); Py_CLEAR(section);
    }
    result = Py_NewRef(sections);
done:
    Py_XDECREF(groups); Py_XDECREF(current); Py_XDECREF(size); Py_XDECREF(two); Py_XDECREF(iterator);
    Py_XDECREF(turn); Py_XDECREF(function); Py_XDECREF(last); Py_XDECREF(left); Py_XDECREF(right);
    Py_XDECREF(value); Py_XDECREF(related); Py_XDECREF(length_object); Py_XDECREF(candidate);
    Py_XDECREF(temporary); Py_XDECREF(group); Py_XDECREF(sections); Py_XDECREF(constructor);
    Py_XDECREF(title); Py_XDECREF(summary); Py_XDECREF(summary_parts); Py_XDECREF(group_iterator);
    Py_XDECREF(separator); Py_XDECREF(pages); Py_XDECREF(section);
    return result;
}

/* Repeat the Python readiness checks in C; no result, class state or helper is
 * cached.  The public wrapper retains its reference body for non-dict guard
 * metadata and unusual names, before this routine has called user code. */
static PyObject *
segmentation_guard_get(PyObject *dictionary, PyObject *key)
{
    PyObject *value = PyDict_GetItemWithError(dictionary, key);
    if (value == NULL) {
        if (PyErr_Occurred()) return NULL;
        value = Py_None;
    }
    return Py_NewRef(value);
}

/* UNPACK_SEQUENCE consumes at most count + 1 items from a custom iterator.
 * PySequence_Fast would consume an entire generator and change its effects. */
static int
segmentation_guard_unpack(PyObject *value, PyObject **items, Py_ssize_t count)
{
    PyObject *iterator = NULL, *extra = NULL;
    Py_ssize_t index, length;
    if (PyTuple_CheckExact(value) || PyList_CheckExact(value)) {
        length = PyTuple_CheckExact(value) ? PyTuple_GET_SIZE(value) : PyList_GET_SIZE(value);
        if (length < count) {
            PyErr_Format(PyExc_ValueError, "not enough values to unpack (expected %zd, got %zd)",
                         count, length);
            return -1;
        }
        if (length > count) {
            PyErr_Format(PyExc_ValueError, "too many values to unpack (expected %zd)", count);
            return -1;
        }
        for (index = 0; index < count; index++) {
            items[index] = Py_NewRef(PyTuple_CheckExact(value)
                                    ? PyTuple_GET_ITEM(value, index) : PyList_GET_ITEM(value, index));
        }
        return 0;
    }
    iterator = PyObject_GetIter(value);
    if (iterator == NULL) {
        if (PyErr_ExceptionMatches(PyExc_TypeError)
                && Py_TYPE(value)->tp_iter == NULL && !PySequence_Check(value)) {
            PyErr_Clear();
            PyErr_Format(PyExc_TypeError, "cannot unpack non-iterable %.200s object",
                         Py_TYPE(value)->tp_name);
        }
        return -1;
    }
    for (index = 0; index < count; index++) {
        items[index] = PyIter_Next(iterator);
        if (items[index] == NULL) {
            if (!PyErr_Occurred()) {
                PyErr_Format(PyExc_ValueError,
                             "not enough values to unpack (expected %zd, got %zd)", count, index);
            }
            goto failed;
        }
    }
    extra = PyIter_Next(iterator);
    if (extra != NULL) {
        Py_DECREF(extra);
        PyErr_Format(PyExc_ValueError, "too many values to unpack (expected %zd)", count);
        goto failed;
    }
    if (PyErr_Occurred()) goto failed;
    Py_DECREF(iterator);
    return 0;
failed:
    Py_DECREF(iterator);
    for (index = 0; index < count; index++) Py_CLEAR(items[index]);
    return -1;
}

static PyObject *
native_segmentation_ready(PyObject *self, PyObject *args)
{
    PyObject *name, *globals, *defaults, *states, *dependencies;
    PyObject *dependency = NULL, *classes = NULL, *functions = NULL, *iterator = NULL;
    PyObject *item = NULL, *current = NULL, *expected = NULL, *state = NULL;
    PyObject *cls = NULL, *new_method = NULL, *init = NULL, *getattribute = NULL, *fields = NULL;
    PyObject *field_iterator = NULL, *pair = NULL, *field = NULL, *value = NULL, *dictionary = NULL;
    PyObject *unpacked[5] = {NULL, NULL, NULL, NULL, NULL}, *result = NULL;
    const char *method_names[3] = {"__new__", "__init__", "__getattribute__"};
    Py_ssize_t index;
    int different;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOO:segmentation_ready",
                          &name, &globals, &defaults, &states, &dependencies)) return NULL;
    if (!PyUnicode_CheckExact(name) || !PyDict_CheckExact(globals)
            || !PyDict_CheckExact(defaults) || !PyDict_CheckExact(states)
            || !PyDict_CheckExact(dependencies)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    dependency = PyObject_GetItem(dependencies, name);
    if (dependency == NULL || segmentation_guard_unpack(dependency, unpacked, 2) < 0) goto done;
    classes = unpacked[0]; unpacked[0] = NULL;
    functions = unpacked[1]; unpacked[1] = NULL;
    Py_CLEAR(dependency);
    iterator = PyObject_GetIter(functions);
    if (iterator == NULL) goto done;
    while ((item = PyIter_Next(iterator)) != NULL) {
        current = segmentation_guard_get(globals, item);
        if (current == NULL) goto done;
        expected = PyObject_GetItem(defaults, item);
        if (expected == NULL) goto done;
        different = current != expected;
        Py_CLEAR(current); Py_CLEAR(expected); Py_CLEAR(item);
        if (different) { result = Py_NewRef(Py_False); goto done; }
    }
    if (PyErr_Occurred()) goto done;
    Py_CLEAR(iterator);
    iterator = PyObject_GetIter(classes);
    if (iterator == NULL) goto done;
    while ((item = PyIter_Next(iterator)) != NULL) {
        state = PyObject_GetItem(states, item);
        if (state == NULL || segmentation_guard_unpack(state, unpacked, 5) < 0) goto done;
        cls = unpacked[0]; unpacked[0] = NULL;
        new_method = unpacked[1]; unpacked[1] = NULL;
        init = unpacked[2]; unpacked[2] = NULL;
        getattribute = unpacked[3]; unpacked[3] = NULL;
        fields = unpacked[4]; unpacked[4] = NULL;
        Py_CLEAR(state);
        current = segmentation_guard_get(globals, item);
        if (current == NULL) goto done;
        different = current != cls;
        Py_CLEAR(current);
        if (different) { result = Py_NewRef(Py_False); goto done; }
        for (index = 0; index < 3; index++) {
            PyObject *method = index == 0 ? new_method : index == 1 ? init : getattribute;
            current = PyObject_GetAttrString(cls, method_names[index]);
            if (current == NULL) goto done;
            different = current != method;
            Py_CLEAR(current);
            if (different) { result = Py_NewRef(Py_False); goto done; }
        }
        field_iterator = PyObject_GetIter(fields);
        if (field_iterator == NULL) goto done;
        while ((pair = PyIter_Next(field_iterator)) != NULL) {
            if (segmentation_guard_unpack(pair, unpacked, 2) < 0) goto done;
            field = unpacked[0]; unpacked[0] = NULL;
            value = unpacked[1]; unpacked[1] = NULL;
            Py_CLEAR(pair);
            /* With the exact builtin metaclass, cls.__dict__.get is precisely
             * this dictionary lookup.  It avoids a mappingproxy allocation per
             * field while retaining descriptors as values, without invoking
             * them.  Custom metaclasses follow the original attribute/call. */
            if (Py_TYPE(cls) == &PyType_Type && ((PyTypeObject *)cls)->tp_dict != NULL
                    && PyDict_CheckExact(((PyTypeObject *)cls)->tp_dict)) {
                current = segmentation_guard_get(((PyTypeObject *)cls)->tp_dict, field);
            }
            else {
                dictionary = PyObject_GetAttrString(cls, "__dict__");
                if (dictionary == NULL) goto done;
                current = PyObject_CallMethod(dictionary, "get", "(O)", field);
                Py_CLEAR(dictionary);
            }
            if (current == NULL) goto done;
            different = current != value;
            Py_CLEAR(current); Py_CLEAR(field); Py_CLEAR(value);
            if (different) { result = Py_NewRef(Py_False); goto done; }
        }
        if (PyErr_Occurred()) goto done;
        Py_CLEAR(field_iterator);
        Py_CLEAR(cls); Py_CLEAR(new_method); Py_CLEAR(init); Py_CLEAR(getattribute); Py_CLEAR(fields);
        Py_CLEAR(item);
    }
    if (PyErr_Occurred()) goto done;
    result = Py_NewRef(Py_True);
done:
    Py_XDECREF(dependency); Py_XDECREF(classes); Py_XDECREF(functions); Py_XDECREF(iterator);
    Py_XDECREF(item); Py_XDECREF(current); Py_XDECREF(expected); Py_XDECREF(state);
    Py_XDECREF(cls); Py_XDECREF(new_method); Py_XDECREF(init); Py_XDECREF(getattribute); Py_XDECREF(fields);
    Py_XDECREF(field_iterator); Py_XDECREF(pair); Py_XDECREF(field); Py_XDECREF(value); Py_XDECREF(dictionary);
    for (index = 0; index < 5; index++) Py_XDECREF(unpacked[index]);
    return result;
}

#endif
