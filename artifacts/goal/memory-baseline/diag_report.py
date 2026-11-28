# -*- coding: utf-8 -*-
"""Summarize one diagnostic run: system memory, per-process memory, GPU memory
and the browser page's own JS/WASM accounting.

Inputs (both written by frontend/scripts/lab, both optional):
  artifacts/goal/lab/diag-monitor.csv   t,kind,pid,ppid,name,privateMB,wsMB,
                                        freeMB,commitMB,limitMB,pagefileMB,
                                        gpuDedicatedMB,gpuSharedMB,cmd
  artifacts/goal/lab/diag-browser.jsonl at,phase,jsHeap,wasmEstimate,event

Output: one JSON object on stdout. Missing or unreadable inputs are reported
under "inputs" and "notes" instead of failing.

Standard library only; run with: python -X utf8 diag_report.py
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / 'lab'
DEFAULT_PROC = LAB / 'diag-monitor.csv'
DEFAULT_BROWSER = LAB / 'diag-browser.jsonl'

TOP_N = 5


def num(value):
    """CSV/JSON cell -> float or None. Blank means 'not recorded'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in ('null', 'none', 'nan', '-', 'n/a'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def mb(value):
    return None if value is None else round(value, 1)


def read_csv_rows(path, notes, label):
    """Returns (present, fieldnames, rows). Rows are dicts of raw strings."""
    if not path.exists():
        notes.append('%s missing: %s' % (label, path))
        return False, [], []
    try:
        # utf-8-sig: PowerShell Out-File utf8 writes a BOM on the header line.
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            fields = [f.strip() for f in (reader.fieldnames or [])]
            rows = []
            bad = 0
            for raw in reader:
                if not raw:
                    continue
                if any(k is None for k in raw) or raw.get(None):
                    bad += 1
                    continue
                rows.append({(k or '').strip(): v for k, v in raw.items()})
    except OSError as exc:
        notes.append('%s unreadable: %s (%s)' % (label, path, exc))
        return False, [], []
    if bad:
        notes.append('%s: skipped %d malformed rows' % (label, bad))
    return True, fields, rows


def read_jsonl_rows(path, notes, label):
    """One JSON object per line; unparsable lines are skipped and counted."""
    if not path.exists():
        notes.append('%s missing: %s' % (label, path))
        return False, [], 0
    rows = []
    bad = 0
    try:
        with path.open('r', encoding='utf-8-sig') as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except ValueError:
                    bad += 1
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    bad += 1
    except OSError as exc:
        notes.append('%s unreadable: %s (%s)' % (label, path, exc))
        return False, [], 0
    if bad:
        notes.append('%s: skipped %d unparsable lines' % (label, bad))
    return True, rows, bad


def summarize_monitor(path, notes):
    present, fields, rows = read_csv_rows(path, notes, 'process file')
    out = {
        'path': str(path),
        'present': present,
        'columns': fields,
        'rows': len(rows),
    }
    if not present or not rows:
        out.update({
            'samples': 0,
            'system': None,
            'peakPrivateSample': None,
            'maxProcessPrivateMB': None,
        })
        return out

    frees, commits, pagefiles, limits = [], [], [], []
    by_t = {}            # t -> list of process rows
    gpu_by_t = {}        # t -> list of gpu rows
    orphans = 0
    max_proc = None      # (privateMB, row)

    for row in rows:
        frees.append(num(row.get('freeMB')))
        commits.append(num(row.get('commitMB')))
        pagefiles.append(num(row.get('pagefileMB')))
        limits.append(num(row.get('limitMB')))

        kind = (row.get('kind') or '').strip().lower()
        t = num(row.get('t'))
        if t is None:
            orphans += 1
            continue
        if kind == 'gpu':
            gpu_by_t.setdefault(t, []).append(row)
            continue
        if kind and kind != 'proc':
            continue
        private = num(row.get('privateMB'))
        if private is None:
            continue
        by_t.setdefault(t, []).append(row)
        if max_proc is None or private > max_proc[0]:
            max_proc = (private, row)

    def known(values):
        return [v for v in values if v is not None]

    frees_known, commits_known = known(frees), known(commits)
    pagefiles_known, limits_known = known(pagefiles), known(limits)

    out['samples'] = len(by_t)
    if orphans:
        notes.append('process file: %d rows had no usable t and only fed system stats' % orphans)
    out['system'] = {
        'rowsWithMemory': len(frees_known),
        'minFreeMB': mb(min(frees_known)) if frees_known else None,
        'maxCommitMB': mb(max(commits_known)) if commits_known else None,
        'maxPagefileMB': mb(max(pagefiles_known)) if pagefiles_known else None,
        'maxCommitLimitMB': mb(max(limits_known)) if limits_known else None,
    }
    out['maxProcessPrivateMB'] = mb(max_proc[0]) if max_proc else None

    if not by_t:
        out['peakPrivateSample'] = None
        notes.append('process file: no per-process privateMB samples found')
        return out

    # "Highest privateMB sample": the instant (distinct t) with the largest
    # summed private memory across tracked processes.
    totals = {t: sum(num(r.get('privateMB')) or 0.0 for r in group) for t, group in by_t.items()}
    peak_t = max(totals, key=lambda t: (totals[t], t))
    group = by_t[peak_t]

    top = sorted(group, key=lambda r: num(r.get('privateMB')) or 0.0, reverse=True)[:TOP_N]
    top_out = []
    for row in top:
        top_out.append({
            'pid': (row.get('pid') or '').strip() or None,
            'ppid': (row.get('ppid') or '').strip() or None,
            'name': (row.get('name') or '').strip() or None,
            'privateMB': mb(num(row.get('privateMB'))),
            'wsMB': mb(num(row.get('wsMB'))),
        })

    # GPU counters are sampled every few seconds, so the peak t often has no
    # gpu row of its own. Use the newest gpu sample at or before peak t, else
    # the earliest one after it; report which t was used.
    gpu_t = None
    exact = False
    if gpu_by_t:
        if peak_t in gpu_by_t:
            gpu_t, exact = peak_t, True
        else:
            earlier = [t for t in gpu_by_t if t <= peak_t]
            gpu_t = max(earlier) if earlier else min(gpu_by_t)
    gpu_out = []
    if gpu_t is not None:
        for row in sorted(gpu_by_t[gpu_t], key=lambda r: num(r.get('pid')) or 0):
            gpu_out.append({
                'pid': (row.get('pid') or '').strip() or None,
                'gpuDedicatedMB': mb(num(row.get('gpuDedicatedMB'))),
                'gpuSharedMB': mb(num(row.get('gpuSharedMB'))),
            })
        # Only keep pids that actually reported a GPU number.
        gpu_out = [g for g in gpu_out if g['gpuDedicatedMB'] or g['gpuSharedMB']]
        if not exact:
            notes.append('GPU rows for t=%g absent; used nearest GPU sample t=%g' % (peak_t, gpu_t))
    else:
        notes.append('process file: no GPU rows found')

    out['peakPrivateSample'] = {
        't': round(peak_t, 1),
        'processes': len(group),
        'totalPrivateMB': mb(totals[peak_t]),
        'maxProcessPrivateMB': mb(max(num(r.get('privateMB')) or 0.0 for r in group)),
        'topProcesses': top_out,
        'gpuSampleT': None if gpu_t is None else round(gpu_t, 1),
        'gpuExactSample': exact,
        'gpuByPid': gpu_out,
    }
    return out


def summarize_browser(path, notes):
    present, rows, _ = read_jsonl_rows(path, notes, 'browser file')
    out = {
        'path': str(path),
        'present': present,
        'rows': len(rows),
        'phases': [],
        'pageByPhase': {},
        'peakWasmEstimateBytes': None,
        'peakWasmEstimateMB': None,
        'peakJsHeapMB': None,
        'turnSubmitted': False,
        'submitFailed': False,
        'events': [],
        'lastPhase': None,
        'lastAtMs': None,
    }
    if not present or not rows:
        return out

    per_phase = {}
    events = []
    peak_wasm = None
    peak_heap = None
    order = []
    for row in rows:
        phase = row.get('phase')
        phase = str(phase) if phase not in (None, '') else 'unknown'
        if phase not in per_phase:
            per_phase[phase] = {
                'samples': 0,
                'wasmSamples': 0,
                'peakWasmMB': None,
                'peakJsHeapMB': None,
                'lastWasmMB': None,
            }
            order.append(phase)
        bucket = per_phase[phase]
        bucket['samples'] += 1

        heap = num(row.get('jsHeap'))
        if heap is not None:
            heap_mb = heap / 1e6
            if bucket['peakJsHeapMB'] is None or heap_mb > bucket['peakJsHeapMB']:
                bucket['peakJsHeapMB'] = round(heap_mb, 1)
            if peak_heap is None or heap_mb > peak_heap:
                peak_heap = heap_mb

        wasm = num(row.get('wasmEstimate'))
        if wasm is not None:
            wasm_mb = wasm / 1e6
            bucket['wasmSamples'] += 1
            bucket['lastWasmMB'] = round(wasm_mb, 1)
            if bucket['peakWasmMB'] is None or wasm_mb > bucket['peakWasmMB']:
                bucket['peakWasmMB'] = round(wasm_mb, 1)
            if peak_wasm is None or wasm > peak_wasm:
                peak_wasm = wasm

        event = row.get('event')
        if event not in (None, ''):
            event = str(event)
            if event not in events:
                events.append(event)

    out['phases'] = order
    out['pageByPhase'] = per_phase
    out['events'] = events
    out['turnSubmitted'] = 'turn-submitted' in events
    out['submitFailed'] = 'submit-failed' in events
    if peak_wasm is not None:
        out['peakWasmEstimateBytes'] = int(peak_wasm)
        out['peakWasmEstimateMB'] = round(peak_wasm / 1e6, 1)
    if peak_heap is not None:
        out['peakJsHeapMB'] = round(peak_heap, 1)
    out['lastPhase'] = order[-1] if order else None
    last_at = num(rows[-1].get('at'))
    out['lastAtMs'] = None if last_at is None else round(last_at, 0)

    if not events:
        notes.append('browser file: no event rows (turn-submitted/submit-failed unseen)')
    if peak_wasm is None:
        notes.append('browser file: no non-null wasmEstimate values')
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    proc_path = Path(argv[0]) if len(argv) > 0 else DEFAULT_PROC
    browser_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_BROWSER

    notes = []
    report = {
        'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'inputs': {
            'processFile': proc_path.exists(),
            'browserFile': browser_path.exists(),
        },
        'process': summarize_monitor(proc_path, notes),
        'browser': summarize_browser(browser_path, notes),
        'notes': notes,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
