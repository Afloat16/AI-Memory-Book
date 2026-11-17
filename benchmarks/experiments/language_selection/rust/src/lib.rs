//! Isolated, same-boundary translation of six released CPython C loops.
//! No Rust UTF-8 string conversion, new persistent cache, or GIL release.
//! The GIL and the owning input references protect every borrowed Unicode view.
#![allow(non_snake_case)]

use pyo3_ffi as py;
use std::ffi::{c_int, c_uint, c_void};
use std::ptr::{null, null_mut};

type Obj = *mut py::PyObject;
type R<T> = Result<T, ()>;

// These are the same CPython predicates called by Py_UNICODE_ISALNUM/ISSPACE.
// The original C extension already requires the full CPython API.
extern "C" {
    fn _PyUnicode_IsAlpha(ch: u32) -> c_int;
    fn _PyUnicode_IsDecimalDigit(ch: u32) -> c_int;
    fn _PyUnicode_IsDigit(ch: u32) -> c_int;
    fn _PyUnicode_IsNumeric(ch: u32) -> c_int;
    fn _PyUnicode_IsWhitespace(ch: u32) -> c_int;
    static _Py_ascii_whitespace: [u8; 128];
}

/// Own exactly one CPython reference; no Rust heap allocation is involved.
struct Owned(Obj);
impl Owned {
    #[inline]
    unsafe fn new(p: Obj) -> R<Self> {
        if p.is_null() { Err(()) } else { Ok(Self(p)) }
    }
    #[inline]
    unsafe fn borrowed(p: Obj) -> Self { py::Py_INCREF(p); Self(p) }
    #[inline]
    fn take(self) -> Obj { let p = self.0; std::mem::forget(self); p }
}
impl Drop for Owned {
    #[inline]
    fn drop(&mut self) { unsafe { py::Py_DECREF(self.0) } }
}

struct AsciiCache([Obj; 128]);
impl Drop for AsciiCache {
    fn drop(&mut self) { unsafe { for p in self.0 { py::Py_XDECREF(p); } } }
}

#[derive(Clone, Copy)]
struct View { kind: c_uint, data: *mut c_void, len: isize }
impl View {
    #[inline]
    unsafe fn new(s: Obj) -> Self {
        Self { kind: py::PyUnicode_KIND(s), data: py::PyUnicode_DATA(s), len: py::PyUnicode_GET_LENGTH(s) }
    }
    #[inline(always)]
    unsafe fn at(self, i: isize) -> u32 {
        match self.kind {
            1 => *self.data.cast::<u8>().offset(i) as u32,
            2 => *self.data.cast::<u16>().offset(i) as u32,
            _ => *self.data.cast::<u32>().offset(i),
        }
    }
    #[inline(always)]
    unsafe fn put(self, i: isize, value: u32) {
        match self.kind {
            1 => *self.data.cast::<u8>().offset(i) = value as u8,
            2 => *self.data.cast::<u16>().offset(i) = value as u16,
            _ => *self.data.cast::<u32>().offset(i) = value,
        }
    }
}

#[inline]
unsafe fn exact_text(s: Obj) -> R<()> {
    if py::PyUnicode_CheckExact(s) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"text must be an exact str".as_ptr());
        return Err(());
    }
    if py::PyUnicode_READY(s) < 0 { Err(()) } else { Ok(()) }
}
#[inline]
unsafe fn status(s: c_int) -> R<()> { if s < 0 { Err(()) } else { Ok(()) } }
#[inline]
fn output(r: R<Owned>) -> Obj { match r { Ok(x) => x.take(), Err(()) => null_mut() } }
#[inline]
fn lower(c: u32) -> bool { c >= 97 && c <= 122 }
#[inline]
fn upper(c: u32) -> bool { c >= 65 && c <= 90 }
#[inline]
fn digit(c: u32) -> bool { c >= 48 && c <= 57 }
#[inline]
fn cjk(c: u32) -> bool { (0x3400..=0x4dbf).contains(&c) || (0x4e00..=0x9fff).contains(&c) || (0xf900..=0xfaff).contains(&c) }
#[inline]
unsafe fn alnum(c: u32) -> bool {
    _PyUnicode_IsAlpha(c) != 0 || _PyUnicode_IsDecimalDigit(c) != 0
        || _PyUnicode_IsDigit(c) != 0 || _PyUnicode_IsNumeric(c) != 0
}
#[inline]
unsafe fn whitespace(c: u32) -> bool {
    if c < 128 { _Py_ascii_whitespace[c as usize] != 0 } else { _PyUnicode_IsWhitespace(c) != 0 }
}

unsafe fn append_ascii(result: Obj, view: View, start: isize, end: isize,
                       fold: bool, query: bool, stop: Obj) -> R<()> {
    let token = Owned::new(py::PyUnicode_New(end - start, 127))?;
    let dest = py::PyUnicode_1BYTE_DATA(token.0);
    for i in start..end {
        let c = view.at(i);
        *dest.offset(i-start) = if fold && upper(c) { (c+32) as u8 } else { c as u8 };
    }
    if query {
        match py::PySequence_Contains(stop, token.0) { -1 => return Err(()), 0 => (), _ => return Ok(()) }
    }
    status(py::PyList_Append(result, token.0))
}

unsafe fn ascii_impl(args: Obj, original: bool) -> R<Owned> {
    let (mut text, mut query, mut stop) = (null_mut(), null_mut(), null_mut());
    if py::PyArg_ParseTuple(args, c"OOO".as_ptr(), &mut text, &mut query, &mut stop) == 0 { return Err(()); }
    exact_text(text)?;
    if py::PyUnicode_IS_ASCII(text) == 0 {
        py::PyErr_SetString(py::PyExc_ValueError, c"text must contain only ASCII code points".as_ptr()); return Err(());
    }
    if py::PyBool_Check(query) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"query must be an exact bool".as_ptr()); return Err(());
    }
    let query = query == py::Py_True();
    let result = Owned::new(py::PyList_New(0))?;
    let v = View::new(text);
    let mut start = -1;
    for i in 0..v.len {
        let c = v.at(i);
        let word = lower(c) || digit(c) || (original && upper(c));
        let boundary = original && i > 0 && lower(v.at(i-1)) && upper(c);
        if i & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        if start >= 0 && (!word || boundary) {
            append_ascii(result.0, v, start, i, original, query, stop)?;
            start = -1;
        }
        if word && start < 0 { start = i; }
    }
    if start >= 0 { append_ascii(result.0, v, start, v.len, original, query, stop)?; }
    Ok(result)
}

#[no_mangle]
pub unsafe extern "C" fn rust_terms_ascii(_self: Obj, args: Obj) -> Obj { output(ascii_impl(args, true)) }
#[no_mangle]
pub unsafe extern "C" fn rust_ascii_tokens(_self: Obj, args: Obj) -> Obj { output(ascii_impl(args, false)) }

unsafe fn append_unicode(result: Obj, text: Obj, start: isize, end: isize, query: bool, stop: Obj) -> R<()> {
    let token = Owned::new(py::PyUnicode_Substring(text, start, end))?;
    if query {
        match py::PySequence_Contains(stop, token.0) { -1 => return Err(()), 0 => (), _ => return Ok(()) }
    }
    status(py::PyList_Append(result, token.0))
}
unsafe fn unicode_impl(args: Obj) -> R<Owned> {
    let (mut text, mut query, mut stop, mut zh_stop) = (null_mut(), null_mut(), null_mut(), null_mut());
    if py::PyArg_ParseTuple(args, c"OOOO:unicode_tokens".as_ptr(), &mut text, &mut query, &mut stop, &mut zh_stop) == 0 { return Err(()); }
    exact_text(text)?;
    if py::PyBool_Check(query) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"query must be an exact bool".as_ptr()); return Err(());
    }
    let query = query == py::Py_True();
    let v = View::new(text);
    let result = Owned::new(py::PyList_New(0))?;
    let mut cursor = 0;
    while cursor < v.len {
        let start = cursor;
        let ch = v.at(cursor);
        if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        if cjk(ch) {
            loop {
                cursor += 1;
                if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
                if cursor == v.len || !cjk(v.at(cursor)) { break; }
            }
            if cursor-start == 1 { append_unicode(result.0, text, start, cursor, query, zh_stop)?; }
            else { for i in start..cursor-1 {
                if i & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
                append_unicode(result.0, text, i, i+2, query, zh_stop)?;
            }}
        } else if alnum(ch) {
            loop {
                cursor += 1;
                if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
                if cursor == v.len { break; }
                let c = v.at(cursor);
                if !alnum(c) || cjk(c) { break; }
            }
            append_unicode(result.0, text, start, cursor, query, stop)?;
        } else { cursor += 1; }
    }
    Ok(result)
}
#[no_mangle]
pub unsafe extern "C" fn rust_unicode_tokens(_self: Obj, args: Obj) -> Obj { output(unicode_impl(args)) }

unsafe fn fold_character(character: Obj, normalize: Obj, category: Obj, nfkd: Obj, mn: Obj) -> R<Owned> {
    let normalized = Owned::new(py::PyObject_CallFunctionObjArgs(normalize, nfkd, character, null_mut::<py::PyObject>()))?;
    let folded = Owned::new(py::PyObject_CallMethod(normalized.0, c"casefold".as_ptr(), null()))?;
    exact_text(folded.0)?;
    let v = View::new(folded.0);
    let maxchar = if py::PyUnicode_IS_ASCII(folded.0) != 0 { 127 } else { match v.kind { 1 => 255, 2 => 65535, _ => 0x10ffff } };
    let piece = Owned::new(py::PyUnicode_New(v.len, maxchar))?;
    let dest = View::new(piece.0);
    let mut written = 0;
    for i in 0..v.len {
        let cp = v.at(i);
        let unit = Owned::new(py::PyUnicode_FromOrdinal(cp as c_int))?;
        let unit_category = Owned::new(py::PyObject_CallOneArg(category, unit.0))?;
        drop(unit);
        let keep = py::PyObject_RichCompareBool(unit_category.0, mn, py::Py_NE);
        drop(unit_category);
        if keep < 0 { return Err(()); }
        if keep != 0 { dest.put(written, cp); written += 1; }
    }
    if written == v.len { Ok(piece) }
    else { Owned::new(py::PyUnicode_FromKindAndData(dest.kind as c_int, dest.data, written)) }
}

unsafe fn fold_impl(args: Obj) -> R<Owned> {
    let (mut text, mut normalize, mut category) = (null_mut(), null_mut(), null_mut());
    if py::PyArg_ParseTuple(args, c"OOO:fold_excerpt_source".as_ptr(), &mut text, &mut normalize, &mut category) == 0 { return Err(()); }
    exact_text(text)?;
    if py::PyCallable_Check(normalize) == 0 || py::PyCallable_Check(category) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"normalize and category must be callable".as_ptr()); return Err(());
    }
    let v = View::new(text);
    let folds = Owned::new(py::PyList_New(v.len))?;
    let positions = Owned::new(py::PyList_New(0))?;
    let cache = Owned::new(py::PyDict_New())?;
    let nfkd = Owned::new(py::PyUnicode_FromString(c"NFKD".as_ptr()))?;
    let mn = Owned::new(py::PyUnicode_FromString(c"Mn".as_ptr()))?;
    let mut ascii = AsciiCache([null_mut(); 128]);
    for i in 0..v.len {
        let cp = v.at(i);
        if i & 4095 == 0 { status(py::PyErr_CheckSignals())?; }
        let mut character: Option<Owned> = None;
        let p = if cp < 128 { ascii.0[cp as usize] } else {
            character = Some(Owned::new(py::PyUnicode_FromOrdinal(cp as c_int))?);
            let borrowed = py::PyDict_GetItemWithError(cache.0, character.as_ref().unwrap().0);
            if borrowed.is_null() && !py::PyErr_Occurred().is_null() { return Err(()); }
            borrowed
        };
        let piece = if p.is_null() {
            if character.is_none() { character = Some(Owned::new(py::PyUnicode_FromOrdinal(cp as c_int))?); }
            let piece = fold_character(character.as_ref().unwrap().0, normalize, category, nfkd.0, mn.0)?;
            if cp < 128 { ascii.0[cp as usize] = Owned::borrowed(piece.0).take(); }
            else { status(py::PyDict_SetItem(cache.0, character.as_ref().unwrap().0, piece.0))?; }
            piece
        } else { Owned::borrowed(p) };
        drop(character);
        let size = py::PyUnicode_GET_LENGTH(piece.0);
        py::PyList_SET_ITEM(folds.0, i, piece.take());
        if size > 0 {
            let position = Owned::new(py::PyLong_FromSsize_t(i))?;
            for _ in 0..size { status(py::PyList_Append(positions.0, position.0))?; }
        }
    }
    let empty = Owned::new(py::PyUnicode_New(0, 0))?;
    let joined = Owned::new(py::PyUnicode_Join(empty.0, folds.0))?;
    Owned::new(py::PyTuple_Pack(2, joined.0, positions.0))
}
#[no_mangle]
pub unsafe extern "C" fn rust_fold_excerpt_source(_self: Obj, args: Obj) -> Obj { output(fold_impl(args)) }

unsafe fn literal_impl(args: Obj) -> R<Owned> {
    let (mut lower, mut terms, mut positions) = (null_mut(), null_mut(), null_mut());
    if py::PyArg_ParseTuple(args, c"OOO:literal_positions".as_ptr(), &mut lower, &mut terms, &mut positions) == 0 { return Err(()); }
    exact_text(lower)?;
    if py::PyList_CheckExact(terms) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"terms must be an exact list".as_ptr()); return Err(());
    }
    if positions != py::Py_None() && py::PyList_CheckExact(positions) == 0 {
        py::PyErr_SetString(py::PyExc_TypeError, c"source_positions must be None or an exact list".as_ptr()); return Err(());
    }
    let length = py::PyUnicode_GET_LENGTH(lower);
    let result = Owned::new(py::PyList_New(0))?;
    let mut i = 0;
    while i < py::PyList_GET_SIZE(terms) {
        status(py::PyErr_CheckSignals())?;
        if i >= py::PyList_GET_SIZE(terms) { break; }
        let term = Owned::borrowed(py::PyList_GET_ITEM(terms, i));
        exact_text(term.0)?;
        let term_len = py::PyUnicode_GET_LENGTH(term.0);
        let mut cursor = 0;
        for _ in 0..40 {
            let found = py::PyUnicode_Find(lower, term.0, cursor, length, 1);
            if found == -2 { return Err(()); }
            if found < 0 { break; }
            let pos = Owned::new(if positions == py::Py_None() { py::PyLong_FromSsize_t(found) }
                else { py::PySequence_GetItem(positions, found) })?;
            let entry = Owned::new(py::PyTuple_Pack(2, pos.0, term.0))?;
            drop(pos);
            status(py::PyList_Append(result.0, entry.0))?;
            drop(entry);
            if term_len == 0 {
                if found == length { break; }
                cursor = found+1;
            } else { cursor = found+term_len; }
        }
        i += 1;
    }
    Ok(result)
}
#[no_mangle]
pub unsafe extern "C" fn rust_literal_positions(_self: Obj, args: Obj) -> Obj { output(literal_impl(args)) }

unsafe fn append_span(result: Obj, start: isize, end: isize) -> R<()> {
    let span = Owned::new(py::Py_BuildValue(c"(nn)".as_ptr(), start, end))?;
    status(py::PyList_Append(result, span.0))
}
unsafe fn evidence_impl(args: Obj) -> R<Owned> {
    let mut text = null_mut();
    let mut width: isize = 0;
    if py::PyArg_ParseTuple(args, c"On:evidence_units".as_ptr(), &mut text, &mut width) == 0 { return Err(()); }
    exact_text(text)?;
    let v = View::new(text);
    let result = Owned::new(py::PyList_New(0))?;
    let mut cursor = 0;
    while cursor < v.len {
        if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        if v.at(cursor) == 10 { cursor += 1; continue; }
        let lo = cursor;
        while cursor < v.len && v.at(cursor) != 10 {
            cursor += 1;
            if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        }
        let hi = cursor;
        if hi-lo <= width { append_span(result.0, lo, hi)?; continue; }
        let mut start = lo;
        for boundary in lo..hi {
            let c = v.at(boundary);
            let mut sentence_end = c == 0x3002 || c == 0xff01 || c == 0xff1f;
            if boundary & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
            if !sentence_end && (c == 46 || c == 33 || c == 63) {
                sentence_end = boundary+1 == hi || whitespace(v.at(boundary+1));
            }
            if !sentence_end { continue; }
            if boundary+1-start <= width { append_span(result.0, start, boundary+1)?; }
            start = boundary+1;
            while start < hi && whitespace(v.at(start)) { start += 1; }
        }
        if start < hi && hi-start <= width { append_span(result.0, start, hi)?; }
    }
    Ok(result)
}
#[no_mangle]
pub unsafe extern "C" fn rust_evidence_units(_self: Obj, args: Obj) -> Obj { output(evidence_impl(args)) }

// Larger-boundary candidate, controlled by the identical C-table module guard.
// C and Rust consume this exact table and use the same two-pass allocation
// strategy. This is measured separately from the same-boundary translation.
#[cfg(feature = "table")]
mod table {
use super::*;
const FOLD_TABLE: &[u8] = include_bytes!("../data/unicode_fold.bin");
const fn header_u32(at: usize) -> usize {
    u32::from_le_bytes([FOLD_TABLE[at], FOLD_TABLE[at+1], FOLD_TABLE[at+2], FOLD_TABLE[at+3]]) as usize
}
const FOLD_ENTRIES_OFFSET: usize = 64 + header_u32(8) * 2;
const FOLD_VALUES_OFFSET: usize = FOLD_ENTRIES_OFFSET + header_u32(12) * 1024;
const _: () = {
    assert!(FOLD_TABLE.len() >= 64);
    assert!(header_u32(8) == 4352);
    assert!(FOLD_TABLE.len() == FOLD_VALUES_OFFSET + header_u32(16)*4);
    let mut i = 0;
    while i < 8 { assert!(FOLD_TABLE[i] == b"MBFOLD01"[i]); i += 1; }
    i = 0;
    while i < 4352 {
        let at = 64+i*2;
        let page = u16::from_le_bytes([FOLD_TABLE[at],FOLD_TABLE[at+1]]) as usize;
        assert!(page == 65535 || page < header_u32(12)); i += 1;
    }
    i = FOLD_ENTRIES_OFFSET;
    while i < FOLD_VALUES_OFFSET {
        let entry = header_u32(i);
        assert!(entry == 0xffffffff || (entry & 0xffffff)+(entry >> 24) <= header_u32(16)); i += 4;
    }
    while i < FOLD_TABLE.len() { assert!(header_u32(i) <= 0x10ffff); i += 4; }
};

#[inline(always)]
unsafe fn table_u16(offset: usize) -> u16 {
    u16::from_le(FOLD_TABLE.as_ptr().add(offset).cast::<u16>().read_unaligned())
}
#[inline(always)]
unsafe fn table_u32(offset: usize) -> u32 {
    u32::from_le(FOLD_TABLE.as_ptr().add(offset).cast::<u32>().read_unaligned())
}
#[inline(always)]
unsafe fn table_mapping(cp: u32) -> (u32, usize, bool) {
    let page = table_u16(64 + (cp as usize >> 8)*2);
    if page == 0xffff { return (cp, 1, true); }
    let entry = table_u32(FOLD_ENTRIES_OFFSET + (page as usize*256 + (cp as usize & 255))*4);
    if entry == 0xffffffff { (cp, 1, true) }
    else { (entry & 0xffffff, (entry >> 24) as usize, false) }
}
#[inline(always)]
unsafe fn table_value(start: u32, index: usize, identity: bool) -> u32 {
    if identity { start } else { table_u32(FOLD_VALUES_OFFSET + (start as usize + index)*4) }
}
unsafe fn fold_table_impl(text: Obj) -> R<Owned> {
    // The only caller is the common C-table shim, which has already validated
    // exact str and Unicode readiness before it selects either C or Rust.
    let v = View::new(text);
    let mut count = 0isize;
    let mut max_cp = 0;
    for i in 0..v.len {
        if i & 4095 == 0 { status(py::PyErr_CheckSignals())?; }
        let (start, length, identity) = table_mapping(v.at(i));
        count = match count.checked_add(length as isize) {
            Some(n) => n,
            None => { py::PyErr_NoMemory(); return Err(()); }
        };
        for j in 0..length { max_cp = max_cp.max(table_value(start, j, identity)); }
    }
    let folded = Owned::new(py::PyUnicode_New(count, max_cp))?;
    let positions = Owned::new(py::PyList_New(count))?;
    let dest = View::new(folded.0);
    let mut written = 0;
    for i in 0..v.len {
        if i & 4095 == 0 { status(py::PyErr_CheckSignals())?; }
        let (start, length, identity) = table_mapping(v.at(i));
        if length == 0 { continue; }
        let position = Owned::new(py::PyLong_FromSsize_t(i))?;
        for j in 0..length {
            dest.put(written, table_value(start, j, identity));
            py::PyList_SET_ITEM(positions.0, written, Owned::borrowed(position.0).take());
            written += 1;
        }
    }
    Owned::new(py::PyTuple_Pack(2, folded.0, positions.0))
}

/// This symbol is called only after the shared C-table guard certifies the
/// exact interpreter UCD version and original normalization/category callables.
#[no_mangle]
pub unsafe extern "C" fn rust_fold_table(text: Obj) -> Obj { output(fold_table_impl(text)) }
}

#[cfg(feature = "owned-window")]
mod window;

macro_rules! method {
    ($name:literal, $func:ident) => { py::PyMethodDef {
        ml_name: concat!($name, "\0").as_ptr().cast(),
        ml_meth: py::PyMethodDefPointer { PyCFunction: $func },
        ml_flags: py::METH_VARARGS,
        ml_doc: c"Isolated Rust translation with the released CPython contract.".as_ptr(),
    } };
}
static mut METHODS: [py::PyMethodDef; 7 + if cfg!(feature = "owned-window") { 3 } else { 0 }] = [
    method!("terms_ascii", rust_terms_ascii),
    method!("ascii_tokens", rust_ascii_tokens),
    method!("unicode_tokens", rust_unicode_tokens),
    method!("literal_positions", rust_literal_positions),
    method!("fold_excerpt_source", rust_fold_excerpt_source),
    method!("evidence_units", rust_evidence_units),
    #[cfg(feature = "owned-window")]
    method!("excerpt_window_owned", rust_excerpt_window_owned),
    #[cfg(feature = "owned-window")]
    method!("log1p_values", rust_log1p_values),
    #[cfg(feature = "owned-window")]
    method!("positive_fsum", rust_positive_fsum),
    py::PyMethodDef::zeroed(),
];
#[cfg(feature = "owned-window")]
use window::{rust_excerpt_window_owned, rust_log1p_values, rust_positive_fsum};
static mut MODULE: py::PyModuleDef = py::PyModuleDef {
    m_base: py::PyModuleDef_HEAD_INIT,
    m_name: c"_language_rust".as_ptr(),
    m_doc: c"Experimental same-boundary Rust kernels; not a released backend.".as_ptr(),
    m_size: -1,
    m_methods: std::ptr::addr_of_mut!(METHODS).cast(),
    m_slots: null_mut(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
};
#[no_mangle]
pub unsafe extern "C" fn PyInit__language_rust() -> Obj {
    py::PyModule_Create(std::ptr::addr_of_mut!(MODULE))
}
