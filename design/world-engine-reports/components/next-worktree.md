# 独立叙事组件开发工作树

日期：2026-11-05。分支 `world-components-next`，工作树 `.local/world-components-next-worktree`。

目标是让叙事组件有可引用的开发基线、固定输入和独立结果目录，使后续实验能比较、能合并。
这次交付不增加算力，不宣称模型质量提升，也没有追加训练或重启已失败的提示词试验。

## 分支与合并边界

- `world-components`：继续开发。未清理、未冻结、未改写其未提交内容。
- `world-components-next`：从 `f725d12` 创建，快照提交为 `714f171`；路径与输入隔离另行提交。
- `world-components-logic`：保留独立 `experiments/world-components-logic/` 研究线，未合并进这里。

原分支继续提交后，两边按共同祖先正常三方合并；相同快照不是自动的共同提交。
后续优先把新实验放进独立脚本，并用独立 run-dir 保存结果；公共契约或服务行为的修改单独提交，
方便另一条线选择性合入。不要把这里的新运行结果复制覆盖另一条线的证据。

## 基线字节与证据

`artifacts/world-components/next-baseline/manifest.json` 保留原始复制清单。
`byte-audit.json` 按文件列出 EOL 策略：原有文本使用明确的 checkout EOL，新入库文件使用 `-text`。
没有用 Python 文件通配符统一换行。外部 `_ext` 原始语料、模型、依赖环境和缓存留在 Git 之外。

`checkout-verification.json` 记录关闭 `core.autocrlf` 的干净检出验证：342 个入库快照文件逐字节一致；
`n4-run-freeze-r1.json` 的 8 项代码和 8 项数据引用全部匹配。
另解析到 121 处可定位的历史 SHA-256 引用，74 处匹配、47 处与当前文件不同；差异保留在审计中，
没有改写历史冻结记录。这不是所有归档均可用当前代码复现的声明；无路径的嵌入哈希未强行解释。

被证据引用的旧训练/解码文件保留字节；新路径行为集中在 `component_paths.py` 和当前实验入口。
旧成绩只按当时的代码、输入和版本解释，不能把当前修改后的脚本当成旧运行的源文件。

## 输入、结果、模型

`component_paths.py` 提供三个解析入口：

| 资源 | 默认 / 配置 | 行为 |
| --- | --- | --- |
| 固定输入 | `artifacts/next-inputs` / `N4_INPUT_ROOT` | 必须在当前工作树内，读取前检查 pin.json 中的 SHA-256；缺失或篡改立即失败 |
| 新结果 | `artifacts/next-runs` / `N4_OUTPUT_ROOT` | 输出必须在当前工作树的结果目录内；拒绝解析到目录外的 `..`、绝对路径或链接；不得覆盖输入目录 |
| 共享模型 | `--model`（兼容 `--ckpt`） / `N4_MODEL_DIR` | 无隐式的其他工作树路径；只读加载，缺少本地模型文件时失败 |

404 个固定输入含原快照诊断材料、10 个授权回合、回合原始输出、A1、背景候选、核对材料和确认集排除来源。
`pin.json` 逐项保存来源工作树、来源路径、字节数和 SHA-256。两份同名证据不一致时保留快照副本，
把另一个来源的哈希另记，不覆盖；`pairs/` 等快照没有的输入从主工作树只读复制。

这些输入是离线字节快照，不与服务端实时同步。另一条线改变世界状态、授权算法或请求契约后，
不能假设冻结回合仍满足新服务端契约；需要单独审核并创建新的输入版本，不能静默刷新现有 pin。

本次已接入路径解析的范围是常驻服务、整回合流水线、解码对照、协同/组织/背景/纠错试验及其评分、
材料构建和二分类训练入口。旧归档训练脚本未统一改写，直接运行它们不享有新的输出护栏；
它们不属于下面的当前运行入口。二分类训练必须传 `--base` 和 `--out`，输出限定在当前运行目录，
不能覆盖基座；共享的叙事权重不会被用作二分类基座。

## 本机运行

当前已建立 `.local/n4-env`：继承本机 Anaconda 的 torch/transformers，单独使用 numpy 1.26.4，
避免系统 NumPy 2.2 与旧二进制依赖冲突。该环境不入 Git，实际版本写入运行验收报告。
换机器时需准备同类依赖和本地模型；不自动下载、不通过 junction 隐式寻找资源。

在本工作树执行：

```powershell
$env:N4_MODEL_DIR = 'D:/others/Jity/.local/models'
$env:USE_TF = '0'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
& .local/n4-env/Scripts/python.exe -X utf8 -B experiments/world-components/component_paths.py
& .local/n4-env/Scripts/python.exe -X utf8 -B experiments/world-components/run_component.py smoke --run-dir my-smoke-01
```

路径与模型目录都可显式配置；以上机器路径只作为本机命令示例，不进入脚本默认值。
需要重建本机隔离环境时：

```powershell
& D:/software/Anaconda/python.exe -m venv --system-site-packages .local/n4-env
uv pip install --python .local/n4-env/Scripts/python.exe numpy==1.26.4
```

`run_component.py` 为每个任务写入独立运行清单，包含代码文件字节哈希、输入 pin 哈希、命令、时间和退出码。
同一个 run-dir 中的同名任务不得重复运行覆盖证据；比较两轮实验时使用不同目录。
上下游任务（例如 organize 与 score-organize）使用相同 run-dir；评分只读该目录的当前输出。
历史失败试验作为诊断入口保留，这次没有再运行它们或把程序守卫效果当成模型能力。

启动独立常驻服务可用：

```powershell
& .local/n4-env/Scripts/python.exe -X utf8 -B experiments/world-components/n4_narrative_dev/narration_service.py --port 8032
```

服务使用固定回合；没有连接主工作树的数据库或页面，也没有启动其他分支上既有的服务。

## 验收

真实模型加载、单事实生成和整回合生成已经通过，结果保存在
`artifacts/next-runs/acceptance-final/`；共享模型文件运行前后哈希一致。
整回合包含 5 条事实；完成状态只表示生成完成，`quality.status` 仍为 `unverified`。
这是运行链路验收，不是语义质量、浏览器性能或模型改进结论。

路径测试覆盖缺失/字节篡改输入、越界写入、模型配置和训练目录分离。
Windows 没有创建符号链接的权限，因此真实符号链接案例跳过；护栏对最终解析路径执行检查。
额外的回归结果与干净检出核验写入独立验收记录，不能把跳过项写成已实测通过。
