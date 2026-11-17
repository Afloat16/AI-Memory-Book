//! Larger-boundary experiment: ordinary-query window selection owns its
//! numeric state in Rust. No Python frequency/score/unit objects are built.
//! This is a separate implementation boundary, not the six-loop translation.
use super::*;

#[link(name = "m")]
extern "C" { fn log1p(value: f64) -> f64; }

#[derive(Clone, Copy)]
struct Hit { position: isize, term: usize }
#[derive(Clone, Copy)]
struct Unit { lo: isize, hi: isize, mask: u64 }

fn reserved<T>(count: usize) -> R<Vec<T>> {
    let mut result = Vec::new();
    if result.try_reserve_exact(count).is_err() {
        unsafe { py::PyErr_NoMemory(); } return Err(());
    }
    Ok(result)
}
fn push<T>(target: &mut Vec<T>, value: T) -> R<()> {
    if target.len() == target.capacity() && target.try_reserve(1).is_err() {
        unsafe { py::PyErr_NoMemory(); } return Err(());
    }
    target.push(value); Ok(())
}
unsafe fn unsupported() -> R<Owned> { Ok(Owned::borrowed(py::Py_NotImplemented())) }

// Error-free partial summation with the same final half-even correction used
// by the shared JavaScript experiment. Restricted to at most 64 finite positive
// frequency values; no NaN/infinity or arbitrary user-number arithmetic.
fn positive_sum(values: &[f64]) -> f64 {
    let mut partials = [0.0f64; 64];
    let mut n = 0;
    for &value in values {
        let mut x = value;
        let mut i = 0;
        for j in 0..n {
            let mut y = partials[j];
            if x.abs() < y.abs() { std::mem::swap(&mut x, &mut y); }
            let hi = x+y;
            let lo = y-(hi-x);
            if lo != 0.0 { partials[i] = lo; i += 1; }
            x = hi;
        }
        n = i;
        if x != 0.0 { partials[n] = x; n += 1; }
    }
    let mut hi = 0.0;
    let mut lo = 0.0;
    if n > 0 { n -= 1; hi = partials[n]; }
    while n > 0 {
        let x = hi;
        n -= 1;
        let y = partials[n];
        hi = x+y;
        lo = y-(hi-x);
        if lo != 0.0 { break; }
    }
    if n > 0 && ((lo < 0.0 && partials[n-1] < 0.0) || (lo > 0.0 && partials[n-1] > 0.0)) {
        let y = lo*2.0;
        let x = hi+y;
        if x-hi == y { hi = x; }
    }
    hi
}

unsafe fn units(view: View, width: isize) -> R<Vec<Unit>> {
    let mut result = reserved(16)?;
    let mut cursor = 0;
    while cursor < view.len {
        if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        if view.at(cursor) == 10 { cursor += 1; continue; }
        let lo = cursor;
        while cursor < view.len && view.at(cursor) != 10 {
            cursor += 1;
            if cursor & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
        }
        let hi = cursor;
        if hi-lo <= width { push(&mut result, Unit { lo, hi, mask: 0 })?; continue; }
        let mut start = lo;
        for boundary in lo..hi {
            let ch = view.at(boundary);
            let mut end = ch == 0x3002 || ch == 0xff01 || ch == 0xff1f;
            if boundary & 65535 == 0 { status(py::PyErr_CheckSignals())?; }
            if !end && (ch == 46 || ch == 33 || ch == 63) {
                end = boundary+1 == hi || whitespace(view.at(boundary+1));
            }
            if !end { continue; }
            if boundary+1-start <= width { push(&mut result, Unit { lo: start, hi: boundary+1, mask: 0 })?; }
            start = boundary+1;
            while start < hi && whitespace(view.at(start)) { start += 1; }
        }
        if start < hi && hi-start <= width { push(&mut result, Unit { lo: start, hi, mask: 0 })?; }
    }
    Ok(result)
}

fn bisect_lo(units: &[Unit], value: isize, right: bool) -> usize {
    let (mut lo, mut hi) = (0, units.len());
    while lo < hi {
        let mid = lo+(hi-lo)/2;
        if units[mid].lo < value || (right && units[mid].lo == value) { lo=mid+1; }
        else { hi=mid; }
    }
    lo
}
fn bisect_hi(units: &[Unit], value: isize) -> usize {
    let (mut lo, mut hi) = (0, units.len());
    while lo < hi {
        let mid = lo+(hi-lo)/2;
        if units[mid].hi <= value { lo=mid+1; } else { hi=mid; }
    }
    lo
}

unsafe fn render(text: Obj, start: isize, end: isize) -> R<Owned> {
    let piece = Owned::new(py::PyUnicode_Substring(text,start,end))?;
    let ellipsis = Owned::new(py::PyUnicode_FromOrdinal(0x2026))?;
    let mut rendered = if start != 0 { Owned::new(py::PyUnicode_Concat(ellipsis.0,piece.0))? }
        else { Owned::borrowed(piece.0) };
    if end < py::PyUnicode_GET_LENGTH(text) { rendered=Owned::new(py::PyUnicode_Concat(rendered.0,ellipsis.0))?; }
    let span = Owned::new(py::Py_BuildValue(c"(nn)".as_ptr(),start,end))?;
    let spans = Owned::new(py::PyList_New(1))?;
    py::PyList_SET_ITEM(spans.0,0,span.take());
    Owned::new(py::PyTuple_Pack(2,rendered.0,spans.0))
}

unsafe fn window_impl(args: Obj) -> R<Owned> {
    let (mut text,mut query,mut positions,mut width_obj) = (null_mut(),null_mut(),null_mut(),null_mut());
    if py::PyArg_ParseTuple(args,c"OOOO:excerpt_window_owned".as_ptr(),&mut text,&mut query,&mut positions,&mut width_obj)==0 { return Err(()); }
    if py::PyUnicode_CheckExact(text)==0 || py::PyList_CheckExact(query)==0 || py::PyList_CheckExact(positions)==0 || py::PyLong_CheckExact(width_obj)==0 {
        return unsupported();
    }
    exact_text(text)?;
    let view=View::new(text);
    let width=py::PyLong_AsSsize_t(width_obj);
    if width == -1 && !py::PyErr_Occurred().is_null() { py::PyErr_Clear(); return unsupported(); }
    let hit_count=py::PyList_GET_SIZE(positions);
    let safe_sum=9_007_199_254_740_991u128.min(isize::MAX as u128);
    if width<=0 || width>=view.len || py::PyList_GET_SIZE(query)>64 || hit_count>2560 || view.len as u128*(hit_count.max(1) as u128)>safe_sum {
        return unsupported();
    }
    let snapshot=Owned::new(py::PyList_AsTuple(query))?;
    let q_count=py::PyTuple_GET_SIZE(snapshot.0);
    if q_count>64 { return unsupported(); }
    let term_ids=Owned::new(py::PyDict_New())?;
    for i in 0..q_count {
        let term=py::PyTuple_GET_ITEM(snapshot.0,i);
        if py::PyUnicode_CheckExact(term)==0 { return unsupported(); }
        let existing=py::PyDict_GetItemWithError(term_ids.0,term);
        if !existing.is_null() { return unsupported(); }
        if !py::PyErr_Occurred().is_null() { return Err(()); }
        let id=Owned::new(py::PyLong_FromSsize_t(i))?;
        status(py::PyDict_SetItem(term_ids.0,term,id.0))?;
    }
    let hit_count=py::PyList_GET_SIZE(positions) as usize;
    if hit_count>2560 || view.len as u128*hit_count.max(1) as u128>safe_sum { return unsupported(); }
    let mut per_term=[0usize;64];
    for i in 0..hit_count {
        let pair=py::PyList_GET_ITEM(positions,i as isize);
        if py::PyTuple_CheckExact(pair)==0 || py::PyTuple_GET_SIZE(pair)!=2 { return unsupported(); }
        let position=py::PyTuple_GET_ITEM(pair,0);
        let term=py::PyTuple_GET_ITEM(pair,1);
        if py::PyLong_CheckExact(position)==0 || py::PyUnicode_CheckExact(term)==0 { return unsupported(); }
        let pos=py::PyLong_AsSsize_t(position);
        if pos == -1 && !py::PyErr_Occurred().is_null() { py::PyErr_Clear(); return unsupported(); }
        if pos<0 || pos>view.len { return unsupported(); }
        let id=py::PyDict_GetItemWithError(term_ids.0,term);
        if id.is_null() { if !py::PyErr_Occurred().is_null() { return Err(()); } return unsupported(); }
        let id=py::PyLong_AsSsize_t(id) as usize;
        per_term[id]+=1;
        if per_term[id]>40 { return unsupported(); }
    }
    // All fallback checks precede the observable in-place sort.
    status(py::PyList_Sort(positions))?;
    let mut hits=reserved(hit_count)?;
    let mut starts=reserved(hit_count*3+2)?;
    let last_start=view.len-width;
    starts.push(0); starts.push(last_start);
    for i in 0..hit_count {
        let pair=py::PyList_GET_ITEM(positions,i as isize);
        let pos=py::PyLong_AsSsize_t(py::PyTuple_GET_ITEM(pair,0));
        let id=py::PyDict_GetItemWithError(term_ids.0,py::PyTuple_GET_ITEM(pair,1));
        if id.is_null() {
            if py::PyErr_Occurred().is_null() { py::PyErr_SetString(py::PyExc_RuntimeError,c"excerpt positions changed during sorting".as_ptr()); }
            return Err(());
        }
        hits.push(Hit{position:pos,term:py::PyLong_AsSsize_t(id) as usize});
        starts.push((pos-width/3).max(0).min(last_start));
    }
    let all_units=if hit_count>0 { units(view,width)? } else { Vec::new() };
    let mut matched: Vec<Unit>=reserved(hit_count)?;
    for hit in &hits {
        let index=bisect_lo(&all_units,hit.position,true);
        if index==0 { continue; }
        let unit=all_units[index-1];
        if hit.position>=unit.hi { continue; }
        if matched.last().map_or(true,|old|old.lo!=unit.lo) { matched.push(unit); }
        matched.last_mut().unwrap().mask|=1u64<<hit.term;
    }
    for unit in &matched {
        starts.push(unit.lo.min(last_start));
        starts.push((unit.hi-width).max(0));
    }
    starts.sort_unstable();
    starts.dedup();
    let mut counts=[0usize;64];
    let mut next=[-1isize;64];
    let mut previous=[-1isize;64];
    let (mut head,mut tail)=(-1isize,-1isize);
    let (mut left,mut right,mut position_sum,mut active)=(0usize,0usize,0isize,0isize);
    let mut best_start=0;
    let mut best_score=(-1isize,-1isize,-1.0f64,-1.0f64,-1isize);
    for start in starts {
        status(py::PyErr_CheckSignals())?;
        let end=start+width;
        while right<hit_count && hits[right].position<end {
            let term=hits[right].term;
            if counts[term]==0 {
                previous[term]=tail; next[term]=-1;
                if tail>=0 { next[tail as usize]=term as isize; } else { head=term as isize; }
                tail=term as isize; active+=1;
            }
            counts[term]+=1; position_sum+=hits[right].position; right+=1;
        }
        while left<right && hits[left].position<start {
            let term=hits[left].term;
            counts[term]-=1;
            if counts[term]==0 {
                if previous[term]>=0 { next[previous[term] as usize]=next[term]; } else { head=next[term]; }
                if next[term]>=0 { previous[next[term] as usize]=previous[term]; } else { tail=previous[term]; }
                next[term]=-1; previous[term]=-1; active-=1;
            }
            position_sum-=hits[left].position; left+=1;
        }
        let mut whole=0u64;
        for unit in &matched[bisect_lo(&matched,start,false)..bisect_hi(&matched,end)] { whole|=unit.mask; }
        let count=right-left;
        // Every integer is exactly representable because the input guard
        // limits length*hit_count to 2**53-1. No fast-math is enabled.
        let placement=if count>0 { ((position_sum as f64/count as f64-start as f64)/width as f64-1.0/3.0).abs() } else { 1.0 };
        let mut logs=[0.0f64;64];
        let mut n=0;
        let mut term=head;
        while term>=0 {
            logs[n]=log1p(counts[term as usize] as f64); n+=1; term=next[term as usize];
        }
        let frequency=positive_sum(&logs[..n]);
        let score=(active,whole.count_ones() as isize,frequency,-placement,-start);
        if score>best_score { best_score=score; best_start=start; }
    }
    render(text,best_start,best_start+width)
}

#[no_mangle]
pub unsafe extern "C" fn rust_excerpt_window_owned(_self: Obj,args: Obj)->Obj { output(window_impl(args)) }

unsafe fn log_values_impl(args: Obj)->R<Owned> {
    let mut values=null_mut();
    if py::PyArg_ParseTuple(args,c"O:log1p_values".as_ptr(),&mut values)==0 { return Err(()); }
    if py::PyList_CheckExact(values)==0 { return unsupported(); }
    let n=py::PyList_GET_SIZE(values);
    let result=Owned::new(py::PyList_New(n))?;
    for i in 0..n {
        let value=py::PyFloat_AsDouble(py::PyList_GET_ITEM(values,i));
        if value == -1.0 && !py::PyErr_Occurred().is_null() { return Err(()); }
        let logged=Owned::new(py::PyFloat_FromDouble(log1p(value)))?;
        py::PyList_SET_ITEM(result.0,i,logged.take());
    }
    Ok(result)
}
#[no_mangle]
pub unsafe extern "C" fn rust_log1p_values(_self: Obj,args: Obj)->Obj { output(log_values_impl(args)) }

unsafe fn sum_impl(args: Obj)->R<Owned> {
    let mut values=null_mut();
    if py::PyArg_ParseTuple(args,c"O:positive_fsum".as_ptr(),&mut values)==0 { return Err(()); }
    if py::PyList_CheckExact(values)==0 { return unsupported(); }
    let n=py::PyList_GET_SIZE(values) as usize;
    if n>64 { return unsupported(); }
    let mut numbers=[0.0f64;64];
    for i in 0..n {
        numbers[i]=py::PyFloat_AsDouble(py::PyList_GET_ITEM(values,i as isize));
        if numbers[i] == -1.0 && !py::PyErr_Occurred().is_null() { return Err(()); }
        if !numbers[i].is_finite() || numbers[i]<0.0 { return unsupported(); }
    }
    Owned::new(py::PyFloat_FromDouble(positive_sum(&numbers[..n])))
}
#[no_mangle]
pub unsafe extern "C" fn rust_positive_fsum(_self: Obj,args: Obj)->Obj { output(sum_impl(args)) }
