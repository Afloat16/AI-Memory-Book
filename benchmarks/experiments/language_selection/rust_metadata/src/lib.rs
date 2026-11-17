//! Complete ordinary bounded candidate metadata method, isolated from product.
//! All SQL and Python-object mutation remain at their original semantic points.
//! The shared adapter owns exact continuations for SQL callback customization.
#![allow(non_snake_case)]

use pyo3_ffi as py;
use std::ffi::{c_int, c_void};
use std::ptr::null_mut;

type Obj = *mut py::PyObject;
type R<T> = Result<T, ()>;

struct Owned(Obj);
impl Owned {
    unsafe fn new(value: Obj) -> R<Self> {
        if value.is_null() { Err(()) } else { Ok(Self(value)) }
    }
    unsafe fn borrowed(value: Obj) -> Self { py::Py_INCREF(value); Self(value) }
    fn take(self) -> Obj { let value = self.0; std::mem::forget(self); value }
}
impl Drop for Owned {
    fn drop(&mut self) { unsafe { py::Py_DECREF(self.0) } }
}
fn output(value: R<Owned>) -> Obj {
    match value { Ok(value) => value.take(), Err(()) => null_mut() }
}
unsafe fn status(value: c_int) -> R<()> { if value < 0 { Err(()) } else { Ok(()) } }
unsafe fn none() -> Owned { Owned::borrowed(py::Py_None()) }
unsafe fn unsupported() -> Owned { Owned::borrowed(py::Py_NotImplemented()) }

#[repr(usize)]
#[derive(Clone, Copy)]
enum Key {
    Store, Ready, AfterLight, AfterDirs, Book, Rows, Sqlite, Connection, Row,
    Db, RowFactory, TextFactory, Tokens, Cache, Wrapped, Ordinary, Metadata,
    Rid, Values, Execute, Fetchall, ProjectId, ChapterId, ChapterTitle,
    SessionId, SessionTitle, CreatedAt, Id, Rank,
}
const NKEYS: usize = 29;
const NAMES: [&std::ffi::CStr; NKEYS] = [
    c"store", c"ordinary_ready", c"after_light", c"after_directories", c"MemoryBook",
    c"_RecallCandidates", c"sqlite3", c"Connection", c"Row", c"db", c"row_factory",
    c"text_factory", c"_directory_tokens", c"_ordinary_directory_cache", c"__wrapped__",
    c"_ORDINARY_DIRECTORY_TOKENS", c"metadata", c"rid", c"values", c"execute",
    c"fetchall", c"project_id", c"chapter_id", c"chapter_title", c"session_id",
    c"session_title", c"created_at", c"id", c"rank",
];
#[repr(C)]
struct State { keys: [Obj; NKEYS], cache_type: Obj }
impl State {
    fn key(&self, key: Key) -> Obj { self.keys[key as usize] }
    unsafe fn attr(&self, value: Obj, key: Key) -> R<Owned> {
        Owned::new(py::PyObject_GetAttr(value, self.key(key)))
    }
    unsafe fn entry(&self, value: Obj, key: Key) -> R<Option<Owned>> {
        let item = py::PyDict_GetItemWithError(value, self.key(key));
        if item.is_null() {
            if py::PyErr_Occurred().is_null() { Ok(None) } else { Err(()) }
        } else { Ok(Some(Owned::borrowed(item))) }
    }
}

unsafe fn exact_keys(mapping: Obj) -> bool {
    let (mut offset, mut key, mut value) = (0, null_mut(), null_mut());
    while py::PyDict_Next(mapping, &mut offset, &mut key, &mut value) != 0 {
        if py::PyUnicode_CheckExact(key) == 0 { return false; }
    }
    true
}
unsafe fn ordinary_rows(rows: Obj, state: &State) -> R<bool> {
    let (mut offset, mut key, mut value) = (0, null_mut(), null_mut());
    while py::PyDict_Next(rows, &mut offset, &mut key, &mut value) != 0 {
        if py::PyUnicode_CheckExact(key) == 0 || py::PyDict_CheckExact(value) == 0 || !exact_keys(value)
                || py::PyDict_Size(value) != 3 {
            return Ok(false);
        }
        for required in [Key::Id, Key::Rank] {
            match py::PyDict_Contains(value, state.key(required)) { -1 => return Err(()), 0 => return Ok(false), _ => (), }
        }
        let rid = py::PyDict_GetItemWithError(value, state.key(Key::Rid));
        if rid.is_null() {
            return if py::PyErr_Occurred().is_null() { Ok(false) } else { Err(()) };
        }
        if py::PyLong_CheckExact(rid) == 0 { return Ok(false); }
    }
    Ok(true)
}
unsafe fn carried_shape(mapping: Obj) -> bool {
    let (mut offset, mut key, mut row) = (0, null_mut(), null_mut());
    while py::PyDict_Next(mapping, &mut offset, &mut key, &mut row) != 0 {
        if py::PyUnicode_CheckExact(key) == 0 || py::PyTuple_CheckExact(row) == 0 || py::PyTuple_GET_SIZE(row) != 4 {
            return false;
        }
        for i in 0..4 {
            if py::PyUnicode_CheckExact(py::PyTuple_GET_ITEM(row, i)) == 0 { return false; }
        }
    }
    true
}
unsafe fn ready(function: Obj) -> R<bool> {
    let value = Owned::new(py::PyObject_CallNoArgs(function))?;
    let result = py::PyObject_IsTrue(value.0);
    if result < 0 { Err(()) } else { Ok(result != 0) }
}
unsafe fn call(function: Obj, arguments: &[Obj]) -> R<Owned> {
    let tuple = Owned::new(py::PyTuple_New(arguments.len() as isize))?;
    for (index, value) in arguments.iter().enumerate() {
        py::PyTuple_SET_ITEM(tuple.0, index as isize, Owned::borrowed(*value).take());
    }
    Owned::new(py::PyObject_CallObject(function, tuple.0))
}
unsafe fn iter(value: Obj) -> R<Owned> { Owned::new(py::PyObject_GetIter(value)) }
unsafe fn next(iterator: Obj) -> R<Option<Owned>> {
    let item = py::PyIter_Next(iterator);
    if item.is_null() {
        if py::PyErr_Occurred().is_null() { Ok(None) } else { Err(()) }
    } else { Ok(Some(Owned(item))) }
}

/// Stack-owned fixed-size field references, mirroring the C control's array.
struct Fields { values: [Obj; 8] }
impl Drop for Fields {
    fn drop(&mut self) { unsafe { for value in self.values { py::Py_XDECREF(value); } } }
}
unsafe fn fields(row: Obj, row_type: Obj, count: isize) -> R<Option<Fields>> {
    let mut result = Fields { values: [null_mut(); 8] };
    if py::PyTuple_CheckExact(row) != 0 {
        if py::PyTuple_GET_SIZE(row) != count { return Ok(None); }
        for i in 0..count { result.values[i as usize] = Owned::borrowed(py::PyTuple_GET_ITEM(row, i)).take(); }
    } else if py::PyList_CheckExact(row) != 0 {
        if py::PyList_GET_SIZE(row) != count { return Ok(None); }
        for i in 0..count { result.values[i as usize] = Owned::borrowed(py::PyList_GET_ITEM(row, i)).take(); }
    } else {
        if py::Py_TYPE(row) != row_type.cast() { return Ok(None); }
        let length = py::PySequence_Size(row);
        if length < 0 { return Err(()); }
        if length != count { return Ok(None); }
        for i in 0..count { result.values[i as usize] = Owned::new(py::PySequence_GetItem(row, i))?.take(); }
    }
    Ok(Some(result))
}
unsafe fn pair(a: Obj, b: Obj) -> R<Owned> { Owned::new(py::PyTuple_Pack(2, a, b)) }

unsafe fn statement(prefix: &str, placeholder: &str, suffix: &str, count: usize) -> R<Owned> {
    let length = prefix.len().checked_add(suffix.len())
        .and_then(|n| count.checked_mul(placeholder.len()).and_then(|m| n.checked_add(m)))
        .and_then(|n| n.checked_add(count.saturating_sub(1)));
    let Some(length) = length.filter(|n| *n <= isize::MAX as usize) else {
        py::PyErr_NoMemory(); return Err(());
    };
    let mut bytes = Vec::new();
    if bytes.try_reserve_exact(length).is_err() { py::PyErr_NoMemory(); return Err(()); }
    bytes.extend_from_slice(prefix.as_bytes());
    for i in 0..count {
        if i != 0 { bytes.push(b','); }
        bytes.extend_from_slice(placeholder.as_bytes());
    }
    bytes.extend_from_slice(suffix.as_bytes());
    Owned::new(py::PyUnicode_DecodeASCII(bytes.as_ptr().cast(), length as isize, std::ptr::null()))
}
unsafe fn fetchall(state: &State, db: Obj, sql: Obj, parameters: Obj) -> R<Owned> {
    let cursor = Owned::new(py::PyObject_CallMethodObjArgs(db, state.key(Key::Execute), sql, parameters, null_mut::<py::PyObject>()))?;
    Owned::new(py::PyObject_CallMethodObjArgs(cursor.0, state.key(Key::Fetchall), null_mut::<py::PyObject>()))
}

enum Prepared { None, Continue, Pairs(Owned) }
unsafe fn prepare_pairs(rows: Obj, light: Obj, row_type: Obj) -> R<Prepared> {
    let length = py::PyObject_Length(light);
    if length < 0 { return Err(()); }
    if length != py::PyDict_Size(rows) { return Ok(Prepared::None); }
    let identities = Owned::new(py::PySet_New(null_mut()))?;
    let unique = Owned::new(py::PyDict_New())?;
    let iterator = iter(light)?;
    while let Some(row) = next(iterator.0)? {
        let Some(part) = fields(row.0, row_type, 4)? else { return Ok(Prepared::Continue); };
        for i in 0..4 {
            // Nonordinary IDs may have arbitrary hashing/iteration. Resume the
            // exact original validation before touching such values.
            if py::PyUnicode_CheckExact(part.values[i]) == 0 { return Ok(Prepared::Continue); }
        }
        status(py::PySet_Add(identities.0, part.values[0]))?;
    }
    if py::PySet_Size(identities.0) != py::PyDict_Size(rows) { return Ok(Prepared::None); }
    let (mut offset, mut key, mut value) = (0, null_mut(), null_mut());
    while py::PyDict_Next(rows, &mut offset, &mut key, &mut value) != 0 {
        match py::PySet_Contains(identities.0, key) {
            -1 => return Err(()), 0 => return Ok(Prepared::None), _ => (),
        }
    }
    let iterator = iter(light)?;
    while let Some(row) = next(iterator.0)? {
        let Some(part) = fields(row.0, row_type, 4)? else { return Ok(Prepared::Continue); };
        let item = pair(part.values[2], part.values[3])?;
        status(py::PyDict_SetItem(unique.0, item.0, py::Py_None()))?;
    }
    Ok(Prepared::Pairs(Owned::new(py::PyDict_Keys(unique.0))?))
}

unsafe fn bounded_impl(state: &State, arguments: Obj) -> R<Owned> {
    let (mut book, mut rows, mut relevance, mut count_object, mut env) =
        (null_mut(), null_mut(), null_mut(), null_mut(), null_mut());
    if py::PyArg_UnpackTuple(arguments, c"bounded_metadata".as_ptr(), 5, 5,
            &mut book, &mut rows, &mut relevance, &mut count_object, &mut env) == 0 { return Err(()); }
    if py::PyDict_CheckExact(env) == 0 || py::PyDict_CheckExact(relevance) == 0 || py::PyLong_CheckExact(count_object) == 0 {
        return Ok(unsupported());
    }
    let Some(store) = state.entry(env, Key::Store)? else { return Ok(unsupported()); };
    let Some(ready_function) = state.entry(env, Key::Ready)? else { return Ok(unsupported()); };
    let Some(after_light) = state.entry(env, Key::AfterLight)? else { return Ok(unsupported()); };
    let Some(after_dirs) = state.entry(env, Key::AfterDirs)? else { return Ok(unsupported()); };
    if py::PyModule_CheckExact(store.0) == 0 || py::PyCallable_Check(ready_function.0) == 0
            || py::PyCallable_Check(after_light.0) == 0 || py::PyCallable_Check(after_dirs.0) == 0 {
        return Ok(unsupported());
    }
    let count = py::PyLong_AsSsize_t(count_object);
    if count == -1 && !py::PyErr_Occurred().is_null() { py::PyErr_Clear(); return Ok(unsupported()); }
    if count <= 0 { return Ok(unsupported()); }
    let book_type = state.attr(store.0, Key::Book)?;
    let rows_type = state.attr(store.0, Key::Rows)?;
    if py::PyType_Check(book_type.0) == 0 || py::PyType_Check(rows_type.0) == 0 || py::Py_TYPE(book) != book_type.0.cast() {
        return Ok(unsupported());
    }
    let original_rows_type = py::Py_TYPE(rows);
    let use_carried = original_rows_type == rows_type.0.cast();
    if (py::PyDict_CheckExact(rows) == 0 && !use_carried) || py::PyDict_Check(rows) == 0 || !ordinary_rows(rows, state)? {
        return Ok(unsupported());
    }
    if py::PyDict_Size(rows) != py::PyDict_Size(relevance) || !exact_keys(relevance) { return Ok(unsupported()); }
    let (mut offset, mut key, mut value) = (0, null_mut(), null_mut());
    while py::PyDict_Next(relevance, &mut offset, &mut key, &mut value) != 0 {
        if py::PyFloat_CheckExact(value) == 0 { return Ok(unsupported()); }
        match py::PyDict_Contains(rows, key) { -1 => return Err(()), 0 => return Ok(unsupported()), _ => (), }
    }
    let db = state.attr(book, Key::Db)?;
    let sqlite_module = state.attr(store.0, Key::Sqlite)?;
    let connection_type = state.attr(sqlite_module.0, Key::Connection)?;
    let row_type = state.attr(sqlite_module.0, Key::Row)?;
    if py::PyType_Check(connection_type.0) == 0 || py::PyType_Check(row_type.0) == 0 || py::Py_TYPE(db.0) != connection_type.0.cast() {
        return Ok(unsupported());
    }
    let carried = if use_carried {
        let pointer = py::PyObject_GetAttr(rows, state.key(Key::Metadata));
        if pointer.is_null() { py::PyErr_Clear(); return Ok(unsupported()); }
        let mapping = Owned(pointer);
        if py::PyDict_CheckExact(mapping.0) == 0 || !carried_shape(mapping.0) { return Ok(unsupported()); }
        Some(mapping)
    } else { None };
    let length = py::PyDict_Size(rows);
    if length <= count { return Ok(none()); }
    let factory = state.attr(db.0, Key::RowFactory)?;
    if factory.0 != row_type.0 { return Ok(none()); }
    let factory = state.attr(db.0, Key::TextFactory)?;
    if factory.0 != std::ptr::addr_of_mut!(py::PyUnicode_Type).cast() { return Ok(none()); }
    let tokens = state.attr(book, Key::Tokens)?;
    let cache = state.attr(book, Key::Cache)?;
    if tokens.0 != cache.0 { return Ok(none()); }
    if py::Py_TYPE(tokens.0) != state.cache_type.cast() { return Ok(unsupported()); }
    let wrapped_pointer = py::PyObject_GetAttr(tokens.0, state.key(Key::Wrapped));
    if wrapped_pointer.is_null() {
        if py::PyErr_ExceptionMatches(py::PyExc_AttributeError) != 0 { py::PyErr_Clear(); return Ok(none()); }
        return Err(());
    }
    let wrapped = Owned(wrapped_pointer);
    let ordinary = state.attr(store.0, Key::Ordinary)?;
    if wrapped.0 != ordinary.0 { return Ok(none()); }
    offset = 0;
    while py::PyDict_Next(relevance, &mut offset, &mut key, &mut value) != 0 {
        let score = py::PyFloat_AS_DOUBLE(value);
        if !score.is_finite() || score < 0.0 { return Ok(none()); }
    }
    let mut scores = Vec::new();
    if scores.try_reserve_exact(length as usize).is_err() { py::PyErr_NoMemory(); return Err(()); }
    offset = 0;
    while py::PyDict_Next(relevance, &mut offset, &mut key, &mut value) != 0 { scores.push(py::PyFloat_AS_DOUBLE(value)); }
    // Only the kth finite value is observed, so ties retain identical bounds;
    // no candidate order is derived from this numeric work array.
    scores.sort_unstable_by(|a, b| b.partial_cmp(a).unwrap());
    let floor = scores[(count - 1) as usize];
    drop(scores);
    let retained = Owned::new(py::PySet_New(null_mut()))?;
    offset = 0;
    while py::PyDict_Next(relevance, &mut offset, &mut key, &mut value) != 0 {
        if py::PyFloat_AS_DOUBLE(value) * 1.15 >= floor { status(py::PySet_Add(retained.0, key))?; }
    }
    if py::PySet_Size(retained.0) == length { return Ok(none()); }
    let light = if let Some(mapping) = &carried {
        Owned::new(py::PyObject_CallMethodObjArgs(mapping.0, state.key(Key::Values), null_mut::<py::PyObject>()))?
    } else {
        let ids = Owned::new(py::PyList_New(length))?;
        offset = 0;
        let mut index = 0;
        while py::PyDict_Next(rows, &mut offset, &mut key, &mut value) != 0 {
            let rid = py::PyDict_GetItemWithError(value, state.key(Key::Rid));
            if rid.is_null() { return Err(()); }
            py::PyList_SET_ITEM(ids.0, index, Owned::borrowed(rid).take());
            index += 1;
        }
        let sql = statement("SELECT id,project_id,chapter_id,session_pk\n              FROM pages INDEXED BY pages_recall_metadata WHERE rid IN (", "?", ")", length as usize)?;
        let light = fetchall(state, db.0, sql.0, ids.0)?;
        if !ready(ready_function.0)? || py::PyList_CheckExact(light.0) == 0
                || py::Py_TYPE(rows) != original_rows_type || !ordinary_rows(rows, state)? {
            return call(after_light.0, &[book, rows, retained.0, light.0]);
        }
        light
    };
    let pairs = match prepare_pairs(rows, light.0, row_type.0)? {
        Prepared::None => return Ok(none()),
        Prepared::Continue => return call(after_light.0, &[book, rows, retained.0, light.0]),
        Prepared::Pairs(pairs) => pairs,
    };
    let pair_count = py::PyList_GET_SIZE(pairs.0);
    let Some(parameter_count) = pair_count.checked_mul(2) else { py::PyErr_NoMemory(); return Err(()); };
    let parameters = Owned::new(py::PyList_New(parameter_count))?;
    for i in 0..pair_count {
        let item = py::PyList_GET_ITEM(pairs.0, i);
        py::PyList_SET_ITEM(parameters.0, 2*i, Owned::borrowed(py::PyTuple_GET_ITEM(item, 0)).take());
        py::PyList_SET_ITEM(parameters.0, 2*i+1, Owned::borrowed(py::PyTuple_GET_ITEM(item, 1)).take());
    }
    let sql = statement("WITH requested(chapter_id,session_pk) AS (VALUES ", "(?,?)",
        ")\n          SELECT requested.chapter_id,requested.session_pk,c.id,s.id,\n            c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at\n          FROM requested LEFT JOIN chapters c ON c.id=requested.chapter_id\n          LEFT JOIN sessions s ON s.id=requested.session_pk", pair_count as usize)?;
    // A trace/authorizer callback from the preceding query may replace book.db.
    let current_db = state.attr(book, Key::Db)?;
    let directories = fetchall(state, current_db.0, sql.0, parameters.0)?;
    let continue_dirs = || call(after_dirs.0, &[rows, retained.0, light.0, pairs.0, directories.0]);
    if !ready(ready_function.0)? || py::PyList_CheckExact(directories.0) == 0
            || py::Py_TYPE(rows) != original_rows_type || !ordinary_rows(rows, state)? {
        return continue_dirs();
    }
    if let Some(mapping) = &carried {
        if py::PyDict_CheckExact(mapping.0) == 0 || !carried_shape(mapping.0) { return continue_dirs(); }
    }
    if py::PyList_GET_SIZE(directories.0) != pair_count { return Ok(none()); }
    let metadata = Owned::new(py::PyDict_New())?;
    for i in 0..pair_count {
        let directory = py::PyList_GET_ITEM(directories.0, i);
        let Some(part) = fields(directory, row_type.0, 8)? else { return continue_dirs(); };
        for j in 0..8 {
            if py::PyUnicode_CheckExact(part.values[j]) == 0 { return Ok(none()); }
        }
        let item = pair(part.values[0], part.values[1])?;
        status(py::PyDict_SetItem(metadata.0, item.0, directory))?;
    }
    if py::PyDict_Size(metadata.0) != pair_count { return Ok(none()); }
    for i in 0..pair_count {
        match py::PyDict_Contains(metadata.0, py::PyList_GET_ITEM(pairs.0, i)) {
            -1 => return Err(()), 0 => return Ok(none()), _ => (),
        }
    }
    // Inspect the still-live light view before the first mutation. Unsupported
    // tail data resumes the entire unstarted tail, retaining partial-update
    // behavior and errors of the actual source method.
    let iterator = iter(light.0)?;
    while let Some(row) = next(iterator.0)? {
        let Some(part) = fields(row.0, row_type.0, 4)? else { return continue_dirs(); };
        for j in 0..4 {
            if py::PyUnicode_CheckExact(part.values[j]) == 0 { return continue_dirs(); }
        }
        let wanted = py::PySet_Contains(retained.0, part.values[0]);
        if wanted < 0 { return Err(()); }
        if wanted != 0 {
            let target = py::PyDict_GetItemWithError(rows, part.values[0]);
            if target.is_null() || py::PyDict_CheckExact(target) == 0 {
                if !py::PyErr_Occurred().is_null() { return Err(()); }
                return continue_dirs();
            }
            let item = pair(part.values[2], part.values[3])?;
            match py::PyDict_Contains(metadata.0, item.0) {
                -1 => return Err(()), 0 => return continue_dirs(), _ => (),
            }
        }
    }
    let iterator = iter(light.0)?;
    while let Some(row) = next(iterator.0)? {
        let Some(part) = fields(row.0, row_type.0, 4)? else {
            py::PyErr_SetString(py::PyExc_SystemError, c"Metadata shape changed without a callback".as_ptr()); return Err(());
        };
        let wanted = py::PySet_Contains(retained.0, part.values[0]);
        if wanted < 0 { return Err(()); }
        if wanted != 0 {
            let item = pair(part.values[2], part.values[3])?;
            let directory = Owned::new(py::PyObject_GetItem(metadata.0, item.0))?;
            let target = Owned::new(py::PyObject_GetItem(rows, part.values[0]))?;
            status(py::PyDict_SetItem(target.0, state.key(Key::ProjectId), part.values[1]))?;
            status(py::PyDict_SetItem(target.0, state.key(Key::ChapterId), part.values[2]))?;
            for (column, key) in [(4, Key::ChapterTitle), (5, Key::SessionId), (6, Key::SessionTitle), (7, Key::CreatedAt)] {
                let field = Owned::new(py::PySequence_GetItem(directory.0, column))?;
                status(py::PyDict_SetItem(target.0, state.key(key), field.0))?;
            }
        }
    }
    let result = Owned::new(py::PyDict_New())?;
    offset = 0;
    while py::PyDict_Next(rows, &mut offset, &mut key, &mut value) != 0 {
        let present = py::PySet_Contains(retained.0, key);
        if present < 0 { return Err(()); }
        if present != 0 { status(py::PyDict_SetItem(result.0, key, value))?; }
    }
    Ok(result)
}

unsafe extern "C" fn bounded_metadata(module: Obj, arguments: Obj) -> Obj {
    let state = &*(py::PyModule_GetState(module).cast::<State>());
    output(bounded_impl(state, arguments))
}
unsafe extern "C" fn traverse(module: Obj, visit: py::visitproc, argument: *mut c_void) -> c_int {
    let state = &*(py::PyModule_GetState(module).cast::<State>());
    for value in state.keys.into_iter().chain([state.cache_type]) {
        if !value.is_null() { let result = visit(value, argument); if result != 0 { return result; } }
    }
    0
}
unsafe extern "C" fn clear(module: Obj) -> c_int {
    let state = &mut *(py::PyModule_GetState(module).cast::<State>());
    for value in state.keys.iter_mut().chain(std::iter::once(&mut state.cache_type)) {
        let old = *value; *value = null_mut(); py::Py_XDECREF(old);
    }
    0
}
static mut METHODS: [py::PyMethodDef; 2] = [
    py::PyMethodDef {
        ml_name: c"bounded_metadata".as_ptr(),
        ml_meth: py::PyMethodDefPointer { PyCFunction: bounded_metadata },
        ml_flags: py::METH_VARARGS,
        ml_doc: c"Complete ordinary bounded metadata method.".as_ptr(),
    },
    py::PyMethodDef::zeroed(),
];
static mut MODULE: py::PyModuleDef = py::PyModuleDef {
    m_base: py::PyModuleDef_HEAD_INIT,
    m_name: c"_language_rust_metadata".as_ptr(),
    m_doc: c"Isolated Rust candidate metadata experiment.".as_ptr(),
    m_size: std::mem::size_of::<State>() as isize,
    m_methods: std::ptr::addr_of_mut!(METHODS).cast(),
    m_slots: null_mut(), m_traverse: Some(traverse), m_clear: Some(clear), m_free: None,
};
#[no_mangle]
pub unsafe extern "C" fn PyInit__language_rust_metadata() -> Obj {
    output((|| {
        let module = Owned::new(py::PyModule_Create(std::ptr::addr_of_mut!(MODULE)))?;
        let state = &mut *(py::PyModule_GetState(module.0).cast::<State>());
        for (index, name) in NAMES.iter().enumerate() {
            state.keys[index] = Owned::new(py::PyUnicode_InternFromString(name.as_ptr()))?.take();
        }
        let functools = Owned::new(py::PyImport_ImportModule(c"functools".as_ptr()))?;
        state.cache_type = Owned::new(py::PyObject_GetAttrString(functools.0, c"_lru_cache_wrapper".as_ptr()))?.take();
        if py::PyType_Check(state.cache_type) == 0 {
            py::PyErr_SetString(py::PyExc_TypeError, c"Unexpected functools cache type".as_ptr()); return Err(());
        }
        Ok(module)
    })())
}
