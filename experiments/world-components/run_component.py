"""Named, isolated runs with pinned inputs and a code-byte manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from component_paths import ComponentPaths, PATHS, WORKTREE

TASKS = {
    'smoke': 'n4_narrative_dev/smoke_component_runtime.py',
    'organize': 'n4_narrative_dev/run_organize_v2.py',
    'semantic': 'n4_narrative_dev/run_semantic_correct.py',
    'background': 'n4_narrative_dev/run_background_select.py',
    'cohesion': 'n4_narrative_dev/run_cohesion_split.py',
    'split-dw': 'n4_narrative_dev/run_split_dw.py',
    'planner': 'n4_narrative_dev/run_planner_split.py',
    'score-organize': 'n4_narrative_dev/score_organize_v2.py',
    'score-semantic': 'n4_narrative_dev/score_semantic_correct.py',
    'score-cohesion': 'n4_narrative_dev/score_cohesion_split.py',
    'score-dw': 'n4_narrative_dev/score_split_dw.py',
    'decode': 'n4_narrative_dev/decode_compare.py',
    'verify-binary': 'n4_corpus_v2/train_verify_binary.py',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=TASKS)
    parser.add_argument('--run-dir', required=True, help='Unique directory under artifacts/next-runs')
    args, forwarded = parser.parse_known_args()
    run_dir = PATHS.output(args.run_dir)
    isolated = ComponentPaths(WORKTREE, PATHS.inputs, run_dir)
    verified = isolated.verify_inputs()
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / f'{args.task}-run.json'
    command = [sys.executable, '-X', 'utf8', '-B', str(Path(__file__).parent / TASKS[args.task]), *forwarded]
    code = {path.relative_to(WORKTREE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(__file__).parent.rglob('*.py')
            if '__pycache__' not in path.parts and '_ext' not in path.parts}
    report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'task': args.task,
              'worktree': str(WORKTREE), 'command': command, 'inputVerification': verified,
              'inputPinSha256': hashlib.sha256((PATHS.inputs / 'pin.json').read_bytes()).hexdigest(),
              'codeSha256': code, 'outputDirectory': str(run_dir), 'status': 'running'}
    # Exclusive creation prevents two runs of the same task sharing evidence.
    with manifest_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    env = dict(os.environ, N4_INPUT_ROOT=str(PATHS.inputs), N4_OUTPUT_ROOT=str(run_dir))
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=WORKTREE, env=env)
        report.update(exitCode=result.returncode, status='passed' if result.returncode == 0 else 'failed')
    except BaseException as exc:
        report.update(status='interrupted', error=type(exc).__name__, exitCode=130)
        raise
    finally:
        report['elapsedSeconds'] = round(time.perf_counter() - started, 3)
        report['finishedAt'] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return report['exitCode']


if __name__ == '__main__':
    raise SystemExit(main())
