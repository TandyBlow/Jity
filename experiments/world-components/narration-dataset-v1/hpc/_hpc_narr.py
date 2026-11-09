# -*- coding: utf-8 -*-
"""Submit the narration-rows training to the cluster and bring the report back.

Same harness as docs/_hpc_crf.py: credentials are read at runtime from
D:/others/yuginu/run_hpc_now.py and never printed; the login node rate-limits
new connections, so uploads reuse the SSH transport.

  python _hpc_narr.py check                 # node, GPU, python env, which bases exist
  python _hpc_narr.py deploy [--epochs N]   # tar + upload + sbatch, prints JOB_ID
  python _hpc_narr.py poll <JOB_ID>         # wait for the job, tail the log
  python _hpc_narr.py fetch <JOB_ID>        # fetch report.json (+ log tail), scrub, save
  python _hpc_narr.py go [--epochs N]       # deploy + poll + fetch

Run with the python that has paramiko:
  D:/others/Jity/.local/world-components-next-worktree/.local/n4-env/Scripts/python.exe
"""

import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import time
import warnings

warnings.filterwarnings("ignore")
import paramiko

SRC = r"D:/others/yuginu/run_hpc_now.py"
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)                       # narration-dataset-v1
REPO = os.path.abspath(os.path.join(PKG, "..", "..", ".."))
REMOTE_DIR = "narr_rows"
CAMPUS_DNS = "172.16.240.10"
# Cluster fallback IP comes from the environment, not from this repository.
LAST_KNOWN_IP = os.environ.get("NARR_HPC_LAST_IP", "")
PY = "~/miniconda3/envs/crf/bin/python"
BASE_CANDIDATES = ["n4v2_run/base/randeng-t5-77m", "rw100_run/base", "narration_run/base/randeng-t5-77m"]
JOB_NAME = "narr_rows"
SENSITIVE_RE = re.compile(r"hpc\.bnbu\.edu\.cn|/home/student/\S+")


def creds():
    src = io.open(SRC, encoding="utf-8").read()
    user = re.search(r"USER\s*=\s*'([^']+)'", src).group(1)
    password = re.search(r"PASS\s*=\s*'([^']+)'", src).group(1)
    hostname = re.search(r"HOST\s*=\s*'([^']+)'", src).group(1)
    return user, password, hostname


def resolve_host(name):
    if not name:
        return LAST_KNOWN_IP
    try:
        return socket.gethostbyname(name)
    except OSError:
        pass
    try:
        out_b = subprocess.run(["nslookup", name, CAMPUS_DNS], capture_output=True, timeout=20).stdout
        out = out_b.decode("gbk", errors="replace")
        addrs = [a for a in re.findall(r"[Aa]ddress:\s+(\d+\.\d+\.\d+\.\d+)", out) if a != CAMPUS_DNS]
        if addrs:
            return addrs[-1]
    except Exception as error:  # noqa: BLE001
        print(f"[resolve] nslookup failed: {error}")
    print(f"[resolve] falling back to last known IP {LAST_KNOWN_IP}")
    return LAST_KNOWN_IP


class Hpc:
    def __init__(self, attempts=6, backoff=180):
        self.user, self.password, self.hostname = creds()
        self.host = resolve_host(self.hostname)
        print(f"host: {self.hostname} -> {self.host}")
        last = None
        for attempt in range(1, attempts + 1):
            try:
                self.c = paramiko.SSHClient()
                self.c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.c.connect(self.host, username=self.user, password=self.password, timeout=30)
                print(f"connected (attempt {attempt})", flush=True)
                return
            except Exception as error:  # noqa: BLE001
                last = error
                print(f"connect {attempt}/{attempts} failed: {error}", flush=True)
                if attempt < attempts:
                    time.sleep(backoff)
        raise SystemExit(f"ssh failed after {attempts} attempts: {last}")

    def do(self, cmd, timeout=600, show=True):
        _, stdout, stderr = self.c.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        rc = stdout.channel.recv_exit_status()
        if show:
            print(out.strip())
            if err.strip():
                print("[stderr]", err.strip()[-500:])
        return out, err, rc

    def _sftp(self):
        return paramiko.SFTPClient.from_transport(self.c.get_transport())

    def put(self, local, remote):
        s = self._sftp()
        try:
            s.put(local, f"/home/student/{self.user}/{remote}")
        finally:
            s.close()
        print(f"uploaded {remote} ({os.path.getsize(local) / 1048576:.2f} MB)")

    def get(self, remote, local):
        s = self._sftp()
        tmp = local + ".part"
        try:
            s.get(f"/home/student/{self.user}/{remote}", tmp)
        finally:
            s.close()
        text = io.open(tmp, encoding="utf-8", errors="replace").read()
        hits = [text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                for m in SENSITIVE_RE.finditer(text)]
        if hits:
            print(f"[SCRUB-FAIL] {remote}: {len(hits)} hits, left at {tmp}")
            for sample in hits[:3]:
                print("   ...", sample)
            raise SystemExit(2)
        os.replace(tmp, local)
        print(f"fetched {local} ({os.path.getsize(local)} bytes, scrub PASS)")


def check(h):
    h.do(f"echo HOME=$HOME; hostname; {PY} -V 2>&1 | tail -1")
    h.do(f"{PY} -c \"import torch,transformers,sentencepiece;print('torch',torch.__version__,'tf',transformers.__version__,'sp',sentencepiece.__version__)\" 2>&1 | tail -2")
    for candidate in BASE_CANDIDATES:
        out, _, _ = h.do(f"ls -la ~/{candidate}/config.json ~/{candidate}/model.safetensors "
                         f"~/{candidate}/spiece.model 2>/dev/null | wc -l", show=False)
        print(f"base ~/{candidate}: {out.strip()} of 3 files present")
    h.do("squeue -u $USER -h -o '%i %T %j %M' | head -10", show=False)


def build_tar(path, extra=()):
    with tarfile.open(path, "w") as tar:
        for name in ("rows-xy.jsonl", "train_narration_rows.py", "preflight.py", "narration_text.py") + tuple(extra):
            tar.add(os.path.join(HERE, name), arcname=name)
    return path


def remote_script(base, epochs, lr, wd="0.01", rp="1.05", ngram="4"):
    base_path = "~/" + base
    return f"""#!/bin/bash
#SBATCH --job-name={JOB_NAME}
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:30:00
#SBATCH --mem=24G
#SBATCH --output={JOB_NAME}_%j.out
#SBATCH --error={JOB_NAME}_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
{PY} -X utf8 preflight.py --data rows-xy.jsonl --base {base_path} || exit 1
{PY} -X utf8 train_narration_rows.py   --data rows-xy.jsonl --base {base_path} --out run-{JOB_NAME}   --epochs {epochs} --lr {lr} --holdout row-0010,row-0017 --save-ckpt   --weight-decay {wd} --repetition-penalty {rp} --no-repeat-ngram {ngram}   --snapshot-epochs 2,4,6,9,12,16,20,24,30 --snapshot-rows row-0017,row-0065
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


GRID_LIMIT = "02:30:00"


def remote_script_probe(base, out):
    base_path = "~/" + base
    return f"""#!/bin/bash
#SBATCH --job-name={JOB_NAME}_probe
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --mem=24G
#SBATCH --output={JOB_NAME}_probe_%j.out
#SBATCH --error={JOB_NAME}_probe_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
{PY} -X utf8 probe_x_ablation.py --data rows-xy.jsonl --base {base_path} --out {out}
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


def deploy_probe(h, base, out="probe-01"):
    tarball = os.path.join(HERE, "_narr_pkg.tar")
    build_tar(tarball, extra=("probe_x_ablation.py",))
    h.do(f"mkdir -p ~/{REMOTE_DIR} && rm -rf ~/{REMOTE_DIR}/*", show=False)
    h.put(tarball, f"{REMOTE_DIR}/pkg.tar")
    h.do(f"cd ~/{REMOTE_DIR} && tar xf pkg.tar", show=False)
    script = remote_script_probe(base, out)
    assert script.endswith("\n")
    h.do("cd ~/" + REMOTE_DIR + " && cat > run_probe.sh <<'NARR_EOF'\n" + script + "NARR_EOF",
         show=False)
    out_text, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch run_probe.sh", show=False)
    print("sbatch:", out_text.strip(), err.strip())
    match = re.search(r"(\d+)", out_text)
    if not match:
        raise SystemExit("sbatch did not return a job id")
    return match.group(1)


def remote_script_grid(base, out):
    base_path = "~/" + base
    return f"""#!/bin/bash
#SBATCH --job-name={JOB_NAME}_grid
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time={GRID_LIMIT}
#SBATCH --mem=24G
#SBATCH --output={JOB_NAME}_grid_%j.out
#SBATCH --error={JOB_NAME}_grid_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
{PY} -X utf8 grid_narration_rows.py --data rows-xy.jsonl --base {base_path} --out {out}
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


def remote_script_run(base, out, epochs, lr, wd, rp, ngram, snapshots, snap_rows, tag):
    base_path = "~/" + base
    return f"""#!/bin/bash
#SBATCH --job-name={JOB_NAME}_{tag}
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:30:00
#SBATCH --mem=24G
#SBATCH --output={JOB_NAME}_{tag}_%j.out
#SBATCH --error={JOB_NAME}_{tag}_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
{PY} -X utf8 preflight.py --data rows-xy.jsonl --base {base_path} || exit 1
{PY} -X utf8 train_narration_rows.py   --data rows-xy.jsonl --base {base_path} --out {out}   --epochs {epochs} --lr {lr} --holdout row-0010,row-0017 --save-ckpt   --weight-decay {wd} --repetition-penalty {rp} --no-repeat-ngram {ngram}   --snapshot-epochs {snapshots} --snapshot-rows {snap_rows}
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


def remote_script_yuyan(mode, out, epochs, lr, batch, rank, alpha,
                        holdout="row-0010,row-0017", tag=None):
    tag = tag or mode
    return f"""#!/bin/bash
#SBATCH --job-name={JOB_NAME}_yuyan_{tag}
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --output={JOB_NAME}_yuyan_{tag}_%j.out
#SBATCH --error={JOB_NAME}_yuyan_{tag}_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
{PY} -X utf8 train_yuyan.py   --data rows-yuyan.jsonl --base checkpoint_best.pt --dict dict.txt --out {out}   --mode {mode} --epochs {epochs} --lr {lr} --batch {batch}   --rank {rank} --alpha {alpha} --save --retention-file retention_prompt.txt   --split-file splits/v1.json --holdout {holdout}
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


CE_SCRIPT = """#!/bin/bash
#SBATCH --job-name={job}_ce
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --mem=32G
#SBATCH --output={job}_ce_%j.out
#SBATCH --error={job}_ce_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
echo "node=$(hostname) start=$(date)"
{python} -X utf8 ce_variants.py --data rows-yuyan.jsonl --split splits/v1.json --base checkpoint_best.pt --dict dict.txt --adapter yu-split-6ep/lora_adapter.pt --out ce-variants.json
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
"""


def deploy_ce(h):
    h.put(os.path.join(PKG, "yuyan", "ce_variants.py"), f"{REMOTE_DIR}/ce_variants.py")
    script = CE_SCRIPT.format(job=JOB_NAME, python=PY)
    name = "run_ce.sh"
    h.do("cd ~/" + REMOTE_DIR + " && cat > " + name + " <<'NARR_EOF'" + "\n"
         + script + "NARR_EOF", show=False)
    out_text, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch {name}", show=False)
    print("ce", out_text.strip(), err.strip())
    match = re.search(r"(\d+)", out_text)
    return match.group(1) if match else None


def deploy_yuyan(h, specs):
    """No wipe here: ~/{REMOTE_DIR} already holds the 3 GB checkpoint."""
    for local in ("rows-yuyan.jsonl", "train_yuyan.py", "retention_prompt.txt",
                  "score_rows.py", "ce_probe.py"):
        h.put(os.path.join(PKG, "yuyan", local), f"{REMOTE_DIR}/{local}")
    h.do(f"mkdir -p ~/{REMOTE_DIR}/splits", show=False)
    h.put(os.path.join(PKG, "splits", "v1.json"), f"{REMOTE_DIR}/splits/v1.json")
    ids = {}
    for spec in specs:
        script = remote_script_yuyan(**spec)
        name = "run_yuyan_" + (spec.get("tag") or spec["mode"]) + ".sh"
        h.do("cd ~/" + REMOTE_DIR + " && cat > " + name + " <<'NARR_EOF'" + "\n"
             + script + "NARR_EOF", show=False)
        out_text, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch {name}", show=False)
        label = spec.get("tag") or spec["mode"]
        print(label, out_text.strip(), err.strip())
        match = re.search(r"(\d+)", out_text)
        if match:
            ids[label] = match.group(1)
    return ids


def deploy_two(h, base, specs):
    """Upload once, submit several runs. Each run writes its own --out dir, and the
    deploy clears ~/{REMOTE_DIR} first, so the jobs must be submitted together."""
    tarball = os.path.join(HERE, "_narr_pkg.tar")
    build_tar(tarball)
    h.do(f"mkdir -p ~/{REMOTE_DIR} && rm -rf ~/{REMOTE_DIR}/*", show=False)
    h.put(tarball, f"{REMOTE_DIR}/pkg.tar")
    h.do(f"cd ~/{REMOTE_DIR} && tar xf pkg.tar", show=False)
    ids = {}
    for spec in specs:
        script = remote_script_run(base, **spec)
        assert script.endswith("\n")
        name = f"run_{spec['tag']}.sh"
        h.do("cd ~/" + REMOTE_DIR + " && cat > " + name + " <<'NARR_EOF'" + "\n" + script + "NARR_EOF",
             show=False)
        out_text, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch {name}", show=False)
        match = re.search(r"(\d+)", out_text)
        print(f"{spec['tag']}: {out_text.strip()} {err.strip()}")
        if match:
            ids[spec["tag"]] = match.group(1)
    return ids


def deploy_grid(h, base, out="grid-01"):
    tarball = os.path.join(HERE, "_narr_pkg.tar")
    build_tar(tarball, extra=("grid_narration_rows.py",))
    h.do(f"mkdir -p ~/{REMOTE_DIR} && rm -rf ~/{REMOTE_DIR}/*", show=False)
    h.put(tarball, f"{REMOTE_DIR}/pkg.tar")
    h.do(f"cd ~/{REMOTE_DIR} && tar xf pkg.tar && ls", show=False)
    script = remote_script_grid(base, out)
    assert script.endswith("\n")
    h.do("cd ~/" + REMOTE_DIR + " && cat > run_grid.sh <<'NARR_EOF'\n" + script + "NARR_EOF",
         show=False)
    out_text, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch run_grid.sh", show=False)
    print("sbatch:", out_text.strip(), err.strip())
    match = re.search(r"(\d+)", out_text)
    if not match:
        raise SystemExit("sbatch did not return a job id")
    return match.group(1)


def deploy(h, epochs, lr, base, wd="0.01", rp="1.3", ngram="4"):
    tarball = os.path.join(HERE, "_narr_pkg.tar")
    build_tar(tarball)
    h.do(f"mkdir -p ~/{REMOTE_DIR} && rm -rf ~/{REMOTE_DIR}/*", show=False)
    h.put(tarball, f"{REMOTE_DIR}/pkg.tar")
    h.do(f"cd ~/{REMOTE_DIR} && tar xf pkg.tar && ls -la")
    script = remote_script(base, epochs, lr, wd, rp, ngram)
    assert script.endswith("\n")
    h.do(f"cd ~/{REMOTE_DIR} && cat > run.sh <<'NARR_EOF'\n" + script + "NARR_EOF", show=False)
    out, _, _ = h.do(f"wc -c < ~/{REMOTE_DIR}/run.sh", show=False)
    print(f"run.sh {out.strip()} bytes")
    out, err, _ = h.do(f"cd ~/{REMOTE_DIR} && sbatch run.sh", show=False)
    print("sbatch:", out.strip(), err.strip())
    match = re.search(r"(\d+)", out)
    if not match:
        raise SystemExit("sbatch did not return a job id")
    return match.group(1)


def poll(h, job_id, timeout=3600):
    started = time.time()
    while time.time() - started < timeout:
        out, _, _ = h.do(f"squeue -u $USER -h -j {job_id} -o '%T %M'", show=False)
        state = out.strip()
        print(f"[poll {int(time.time() - started)}s] {state or 'not in queue'}", flush=True)
        if not state or state.startswith(("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT")):
            break
        time.sleep(60)
    h.do(f"cd ~/{REMOTE_DIR} && tail -25 {JOB_NAME}_{job_id}.out 2>/dev/null; "
         f"tail -15 {JOB_NAME}_{job_id}.err 2>/dev/null")


def fetch(h, job_id):
    local = os.path.join(HERE, f"report-{job_id}.json")
    h.get(f"{REMOTE_DIR}/run-{JOB_NAME}/report.json", local)
    print(io.open(local, encoding="utf-8").read()[:1200])
    return local


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    epochs = "8"
    lr = "3e-4"
    base = BASE_CANDIDATES[0]
    if "--epochs" in sys.argv:
        epochs = sys.argv[sys.argv.index("--epochs") + 1]
    if "--lr" in sys.argv:
        lr = sys.argv[sys.argv.index("--lr") + 1]
    wd, rp, ngram = "0.01", "1.05", "4"
    if "--wd" in sys.argv:
        wd = sys.argv[sys.argv.index("--wd") + 1]
    if "--rp" in sys.argv:
        rp = sys.argv[sys.argv.index("--rp") + 1]
    if "--ngram" in sys.argv:
        ngram = sys.argv[sys.argv.index("--ngram") + 1]
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1]

    if action == "check":
        h = Hpc()
        check(h)
        return

    if action == "deploy":
        h = Hpc()
        job_id = deploy(h, epochs, lr, base, wd, rp, ngram)
        print("JOB_ID", job_id)
        return

    if action == "poll":
        h = Hpc()
        poll(h, sys.argv[2])
        return

    if action == "fetch":
        h = Hpc()
        fetch(h, sys.argv[2])
        return

    if action == "deploy-yuyan":
        h = Hpc()
        specs = [
            {"mode": "lora", "tag": "split6", "out": "yu-split-6ep", "epochs": "6", "lr": "1e-4",
             "batch": "1", "rank": "16", "alpha": "32",
             "holdout": "split"},
            {"mode": "lora", "tag": "lora_h10", "out": "yu-lora-h10", "epochs": "6", "lr": "1e-4",
             "batch": "1", "rank": "16", "alpha": "32",
             "holdout": "row-0008,row-0010,row-0017,row-0042,row-0097,row-0121,row-0127,row-0149,row-0160,row-0177"},
        ]
        print("JOBS", deploy_yuyan(h, specs))
        return

    if action == "deploy-ce":
        h = Hpc()
        print("JOBS", {"ce": deploy_ce(h)})
        return

    if action == "deploy-two":
        h = Hpc()
        specs = [
            {"tag": "a", "out": "run-a", "epochs": "30", "lr": "1e-4", "wd": "0",
             "rp": "1.05", "ngram": "4",
             "snapshots": "3,6,9,12,16,20,24,30", "snap_rows": "row-0017,row-0065"},
            {"tag": "b", "out": "run-b", "epochs": "40", "lr": "3e-5", "wd": "0",
             "rp": "1.05", "ngram": "4",
             "snapshots": "5,10,20,30,40", "snap_rows": "row-0017,row-0065"},
        ]
        print("JOBS", deploy_two(h, base, specs))
        return

    if action == "deploy-probe":
        h = Hpc()
        print("JOB_ID", deploy_probe(h, base))
        return

    if action == "go-probe":
        h = Hpc()
        job_id = deploy_probe(h, base)
        print("JOB_ID", job_id, flush=True)
        poll(h, job_id)
        local = os.path.join(HERE, f"runs/probe-{job_id}.json")
        h.get(f"{REMOTE_DIR}/probe-01/probe.json", local)
        return

    if action == "deploy-grid":
        h = Hpc()
        print("JOB_ID", deploy_grid(h, base))
        return

    if action == "go-grid":
        h = Hpc()
        job_id = deploy_grid(h, base)
        print("JOB_ID", job_id, flush=True)
        poll(h, job_id)
        local = os.path.join(HERE, f"grid-{job_id}.json")
        h.get(f"{REMOTE_DIR}/grid-01/grid.json", local)
        return

    if action == "go":
        h = Hpc()
        job_id = deploy(h, epochs, lr, base, wd, rp, ngram)
        print("JOB_ID", job_id, flush=True)
        poll(h, job_id)
        fetch(h, job_id)
        return

    raise SystemExit(f"unknown action {action!r}")


if __name__ == "__main__":
    main()
