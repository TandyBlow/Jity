# 发布前脱敏说明（v1）

本目录在提交/推送前做了一次路径脱敏：把本地绝对路径前缀替换为字面量 `<repo>`。
仅改路径字符串，**没有改任何计数、判词、哈希值或结论**。

## 1. 脱敏规则

- `D:/…/Jity`、`D:\…\Jity`、`/d/…/Jity` → `<repo>`；
- 三个脚本（`analyze_candidate.py`、`build_acceptance_set.py`、`copy_upstream.py`）的路径常量改为
  `os.environ.get("JITY_REPO", "<repo>")`，本地复跑时设置 `JITY_REPO` 即可；
- 其余脚本只在注释里出现路径，已同样替换。

## 2. 受影响的文件与前后哈希

| 文件 | 脱敏前 sha256 | 脱敏后 sha256 |
|---|---|---|
| `freeze/comparison-inputs-v1.json` | `a12b13617c13fb21ff6ebd104712e7fbab4e4ac456cc649b13a7f3b61cd78a41` | `0cd2a888d992824413fc76c606be0d836c8f8c34eac0451828abd3e45c75867a` |
| `freeze/comparison-inputs-v2.json` | `40fb82115b61684c8a620ae27254433f9fa1c329432e119537dd3b5a1802d2b8` | `bc500f66b02992cbdd8fabcd9d575ecbd86afafd47694dbf947605e282aa18c4` |
| `freeze/comparison-inputs-v3.json` | `a0ed91d4865eda518c06fe7677553f4107975b81e3858b610d794bcfbadc4608` | `101895d8c88c2f2b0b66b676ad3d2713b4041d7fbe3ef44b8e7c2238dc07bd06` |
| `freeze/u240-identity-v1.json` | `0099509df900f4e12e6310b21c1ee8d81b6a4010262ba09985488705520def07` | `3e047775b4624952d7520ce6ee0d3162f50c53abbd9cf8c6386d335b54cde302` |
| `scripts/upstream/provenance.json` | `1a591c12391599f706ec31d2eab74c657ac390d9ee8045c3bfe20d9d36d158f7` | `e9a04b967ff01c967daa9f5f9a0037ba1150855ef71cdafb5e464709a82def2d` |
| `scripts/analyze_candidate.py` | `60ef14c824630965d049992c66fc721f676c5c20ddcc653d8641747bef6022d5` | `efc263e6537f570388b34b1182e2865f128be6610cf198581b044dba28f41ed3` |
| `scripts/build_acceptance_set.py` | `8840a26b1002643111632f7dd7847e626096e0370c07d1979ec728d988deea20` | `db03224ccd83363d89e94b36aa0638e449eb7b192a369af561e53c88580b8ff2` |
| `scripts/build_comparison_manifest.py` | `c9778e64e1aa10d69d39ae7a7e5abe72d610c98d4367659477bd87d8fe61b871` | `67e7b64f8428cb8111bb9a384043b1fce928cd1fa1ecb4772d9c0b0faf6cabe2` |
| `scripts/copy_upstream.py` | `d2e39558c4cbae10d7cfc32aceefb3c9e6b486f0029f01b07dea747e773e5879` | `9bf9fa582105f4e6fcd8d359351ae17fdaba8680a5dde305342515ae4e7f6c99` |
| `scripts/inventory_u240.py` | `f38fee3c16576c488bd38823f3192a066eec04c408fc214b0f45a7b432bfbd05` | `0caf8bd26ba78e2500dedec24c2bc0326f8f809edcb04d2fad56753c7ced20a3` |
| `artifacts/fact-wording/preflight/env.json` | `87c747c4df92c381fdedd9dda4c85d6a21f74caefa8df8237fe43de622ddd25a` | `14eb102bc20cdaa73db6bb6f81cf91d48a76a4d7e3f3a27a59176445f9329209` |
| `artifacts/fact-wording/preflight/preflight.json` | `64aa7f772d297047babb6c17dd0e1d6be96b1fd343c08d445da3a6d9a07233db` | `2da60046b6968271f761531b039e0e42f1d0c2b1bcc5ea7d11fc28568ab07391` |

脱敏前索引保留在 `freeze/final-index-v1-pre-redaction.json`（sha256 `503b17a6b0819b15fdd42a4455fad8d804a8ca8307ee5dd2bfbf743578f9d9ba`），它记录的是脱敏前全目录 141 个文件的哈希。

## 3. 已知的“交叉哈希不再匹配”

运行记录里有两处 `manifestSha256` 指向**脱敏前**的 v3 清单：

| 记录文件 | 记录值 | 含义 |
|---|---|---|
| `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/run.json` | `a0ed91d4…`（完整值见文件） | 脱敏前 `freeze/comparison-inputs-v3.json` |
| `artifacts/fact-wording/preflight/preflight.json` | 同上 | 同上 |

脱敏后 v3 清单为 `101895d8c88c2f2b0b66b676ad3d2713b4041d7fbe3ef44b8e7c2238dc07bd06`，因此这两处交叉引用**按设计不再相等**；这是发布脱敏的唯一影响。其余哈希（权重、config/tokenizer、输入逐条哈希、训练池、脚本副本、盲判包、判词）都是值或未改文件，未受影响。

## 4. 未脱敏的内容

- `env/` 目录不打包（约 5 GB），只保留 `env/requirements.lock.txt` 与 `env/ENVIRONMENT.md`；
- 世界文本、事实与模型输出原样保留，它们是证据；
- `TASK.md` 位于任务目录之外，不随本目录发布。
