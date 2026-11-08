# Jity 仓库内的评测工具

`eval/` 纳入评测代码、示例、测试、v1.1/v1.2 题库及冻结证据，保留独立 Python 包 `jity_eval`。游戏服务不导入或启动评测工具。

## 环境与路径

从 Jity 仓库根目录进入 `eval/`，使用安装了 `backend/requirements.txt` 的 Python 3.11+ 环境。基础模拟器仅用标准库；完整测试需要后端依赖。文件锁依赖 `fcntl`，请使用 macOS/Linux。

- `--jity-root ..` 指向父目录中的游戏代码。
- 新的真实组件回放、录制、问答试测输出放在 `../../jity-eval-runs/<新运行名>`，即 Jity 仓库外。
- 仅基础离线模拟器可以使用本地 `eval/runs/`；该目录被忽略。
- 不把 `.env`、数据库、缓存、嵌套 `.git` 或本地运行目录提交到 Git。
- v1.1/v1.2 题库逐字复制，保留原始校验和、来源路径和待审标签。`private/` 表示禁止作为模型输入的评分材料，不表示 GitHub 访问控制。

## 无付费调用的验证

```bash
cd eval
python -m jity_eval validate examples/pilot.json
python -m jity_eval run examples/pilot.json --output runs/my-first-run
python -m jity_eval.question_bank validate question_banks/full-games-20261106-v1.1
python -m jity_eval.question_bank_revision validate question_banks/full-games-20261106-v1.2
python -m jity_eval capture plan --jity-root ..
python -m unittest discover -s tests -v
```

录制回归测试需要本地 `cl100k_base` tokenizer 缓存。首次安装环境时可执行 `python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'` 下载 tokenizer 资源；这不是模型 API 请求。GitHub CI 在测试前准备此缓存，测试中的模型响应使用离线夹具。

新问答试测的准备命令如下，仅生成冻结请求，不调用模型：

```bash
python -m jity_eval.qa_pilot prepare \
  --bank question_banks/full-games-20261106-v1.2 \
  --config examples/qa-pilot-20261106.json \
  --output ../../jity-eval-runs/qa-new-preflight \
  --jity-root ..
```

真实 `capture record/resume` 与问答 `run/resume` 仍需各自实验的明确预算与批准记录。将代码纳入仓库不构成新的付费实验授权。

## 历史运行与证据

原本地项目 `../jity-eval/`（相对于 Jity 仓库根目录）保留原样，历史数据库、响应和报告仍在其 `runs/` 下，没有搬移或重新封存。已有运行应使用其冻结代码和原依赖版本恢复或核验，不能用迁移后的代码冒充原版本。

`qa-pilot.md`、`question-bank.md`、`phase-1-validation.md` 以及冻结题库内的报告包含 2026-11-05/06 的历史记录和本机路径。它们不代表当前执行状态，也不保证在其他电脑上存在对应原始运行。无 `--check-original` 的题库验证仅依赖已提交的冻结副本。

历史动作上限续跑附件的源码保留在 `tools/jity_capture_continue.py`，供离线测试和显式指定的历史运行使用；原运行附件与冻结代码没有改动。
