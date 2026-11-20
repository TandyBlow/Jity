# 最终索引 v2（可核查）

> 状态：c4 本阶段诊断完成；T1 失败；独立验收尚未开展。
> 根目录：`experiments/world-components/parallel/fact_wording/`
> 索引 JSON：`freeze/final-index-v2.json`，sha256 `3b604073703b84481b94116ddae95b8ee545969fa8e5b30161fd26529450076d`（同值见 `freeze/final-index-v2.sha256`）
> 环境目录不打包：只索引 `env/requirements.lock.txt` 与 `env/ENVIRONMENT.md`。
> 任务说明 `TASK.md` 位于本任务的独占目录之外（工作树根），不纳入本索引。

## 冲突时采用哪份

- r1 的字段口径（finishedCount 与保留数、“已穷尽”措辞）以 results/diagnostic-r1-audit-v1.md 为准
- T1 的因果表述以 results/candidate-t1-result-v1-audit.md 为准（原句“否掉了充分原因”不成立）
- 其余结论以 results/c4-stage-closure-v1.md 为准
- 所有计数以运行原文（raw.jsonl）与 analysis/candidate-analysis JSON 为准；任何摘要文档与之冲突时以原文为准
- 盲判口径以 results/blind-design-defect-v1.md 为准（v1 判词不是严格盲判）
- 耗时口径以 results/timing-scope-v1.md 为准（1.72/4.69 s 只是解码耗时）

## 文件与完整哈希

| 组 | 路径 | 字节 | sha256 |
|---|---|---|---|
| 协议 | `comparison-protocol-v1.md` | 19,086 | `9dd4979861d1af89a7dc1f055a06d6b7115502552ab93939aeef6cce4ec854fb` |
| 协议 | `comparison-protocol-v2.md` | 9,049 | `b393a5d43b588ad7623c046a220127b537926542e2544328f54f57c593a84460` |
| 协议 | `comparison-protocol-v3.md` | 7,239 | `b1644af511ee42aa9111b16d196744ddae2d4e47bb3f2e55b8b9f5e0a9691fa6` |
| 冻结记录 | `freeze/u240-identity-v1.json` | 5,998 | `3e047775b4624952d7520ce6ee0d3162f50c53abbd9cf8c6386d335b54cde302` |
| 冻结记录 | `freeze/evidence-inventory-v1.json` | 15,965 | `1ac504f2cf468a377feb836f3c8ec16f006f880868fda1a8083559ba0e3873a4` |
| 冻结记录 | `freeze/failure-taxonomy-v1.json` | 2,321 | `458daf7d1d487dae6963571a8452aec9732d52be0550bd22bee132fb3ba7ad95` |
| 冻结记录 | `freeze/failure-classification-v1.json` | 9,242 | `00d99b664d243be4391977005085da0c22939585040908bcf4bdb2bc51225315` |
| 冻结记录 | `freeze/comparison-inputs-v1.json` | 61,776 | `0cd2a888d992824413fc76c606be0d836c8f8c34eac0451828abd3e45c75867a` |
| 冻结记录 | `freeze/comparison-inputs-v2.json` | 64,621 | `bc500f66b02992cbdd8fabcd9d575ecbd86afafd47694dbf947605e282aa18c4` |
| 冻结记录 | `freeze/comparison-inputs-v3.json` | 65,327 | `101895d8c88c2f2b0b66b676ad3d2713b4041d7fbe3ef44b8e7c2238dc07bd06` |
| 冻结记录 | `freeze/acceptance-registration-v1.json` | 26,605 | `e4de093937be604414e8347c545e5451ffdaa8d730e343942c5c132ed45f8d8d` |
| 冻结记录 | `freeze/acceptance-registration-v2.json` | 29,164 | `a12c5f88dbb35cdbc7ec4c1cfab96b8d1436647fcc4bebf4b10c1e33823bf40b` |
| 冻结记录 | `freeze/candidate-t1-v1.json` | 21,318 | `b6a48318d366216f2dea3ec2da1decb843a31e888585376bac852989174724d9` |
| 冻结记录 | `freeze/candidate-t1-v2.json` | 24,622 | `d8c16de6c90bf8d433cdc86a65801f08bb3d6daf52eb9dfb64b4504b3a71228e` |
| 冻结记录 | `freeze/candidate-t1-outcome-v1.json` | 1,198 | `20d0689cf41cf58d53e2fbc4d55fbfbc661c737043baf55b62af4594e4b2cd8c` |
| 环境记录（环境目录不打包） | `env/requirements.lock.txt` | 453 | `53580846a8cb7b17d77211b3ec1605ce686034b2c49c0d720d6bdd16c48590fb` |
| 环境记录（环境目录不打包） | `env/ENVIRONMENT.md` | 3,066 | `c4f56a6d091c2bf6ccb859d639c6751ef5509d80412f0bdf300d6aa0d66c2a6f` |
| 源码与脚本 | `scripts/beam2.py` | 7,857 | `0d33797a170454c87e1824ae4b5343b653befd38ab5bc81dc9605d1aff6f109a` |
| 源码与脚本 | `scripts/preflight_beam2.py` | 17,500 | `fe2669d6b9383741daa421d5a4008410108ec053b982c4d62a453d490d93ef14` |
| 源码与脚本 | `scripts/run_preflight.py` | 13,366 | `761816792b7b38e41246b377974c69cc665d1c27e14e0607e74de58aca416bcd` |
| 源码与脚本 | `scripts/run_diagnostic.py` | 11,642 | `10467caa28fc8112d8c3ef32b7ebcec45a9847b33b3a77f1eaa813cf5e894fe5` |
| 源码与脚本 | `scripts/run_candidate.py` | 8,483 | `a2c521520c2b35a5bc71cee96bd1dd6a0b3adeb7c1cf7b50a483a74c4e0a7030` |
| 源码与脚本 | `scripts/build_comparison_manifest.py` | 21,643 | `67e7b64f8428cb8111bb9a384043b1fce928cd1fa1ecb4772d9c0b0faf6cabe2` |
| 源码与脚本 | `scripts/inventory_u240.py` | 22,357 | `0caf8bd26ba78e2500dedec24c2bc0326f8f809edcb04d2fad56753c7ced20a3` |
| 源码与脚本 | `scripts/classify_cf24.py` | 23,585 | `7a8bfbdbc41ccebc93d4606a4c8dc4a51dd60673c3c336b491094ffe20a3f28a` |
| 源码与脚本 | `scripts/copy_upstream.py` | 2,657 | `9bf9fa582105f4e6fcd8d359351ae17fdaba8680a5dde305342515ae4e7f6c99` |
| 源码与脚本 | `scripts/build_acceptance_set.py` | 22,297 | `49e8d98d3df9c7ac48b7f6012704bf52abe7c4bd189f907da3d324b50454f551` |
| 源码与脚本 | `scripts/build_blind_pack.py` | 3,978 | `9cb5f42baaf4a2cf64d8451ef5d23a4328a2f9fb1d3c6ec545c478330fc6b8ee` |
| 源码与脚本 | `scripts/build_blind_pack_r2.py` | 4,370 | `708bcfb48275f7de1b682dc07e1924527515157a331bce8ceb86c762d8ba13a8` |
| 源码与脚本 | `scripts/analyze_diagnostic.py` | 6,713 | `3ade7e401b8bef25551d77d85e3cb69033a44f41eae7ec5f89b76aade900f168` |
| 源码与脚本 | `scripts/analyze_candidate.py` | 10,303 | `efc263e6537f570388b34b1182e2865f128be6610cf198581b044dba28f41ed3` |
| 源码与脚本 | `scripts/freeze_candidate_t1.py` | 2,955 | `3b0c04caf7aee2bd5999d667c2c4c8085e59f18fb29e5abc62e8a126fa93c85e` |
| 源码与脚本 | `scripts/freeze_candidate_t1_v2.py` | 5,332 | `5d5e72939512d2d55317d487b148b779f1170bba65af9181d79e92f28fe7c5b8` |
| 源码与脚本 | `scripts/print_batches.py` | 1,485 | `946d82d64ed3ed5a6264d576393a4bf14ff43942a588626097a7d5c8ed51fc2a` |
| 源码与脚本 | `scripts/snapshots/run_diagnostic-9b4b3946.py` | 9,073 | `9b4b3946fbb679bf6a2f5570bf8cd0be617e45b54d9e16e6fd15b017320be813` |
| 源码与脚本 | `scripts/upstream/provenance.json` | 1,995 | `e9a04b967ff01c967daa9f5f9a0037ba1150855ef71cdafb5e464709a82def2d` |
| 源码与脚本 | `scripts/upstream/run_cf24_baseline.py` | 6,205 | `a7d81fc10a10ef4b450b88613b77e71b0c3e94bbb10195bfefd9c803c6aa7331` |
| 源码与脚本 | `scripts/upstream/score_cf24_baseline.py` | 9,717 | `cb3c440f5870f738bbd9e98f4363ec588156276381d1217b14647533e4b37428` |
| 源码与脚本 | `scripts/upstream/review_cf24_baseline.py` | 5,924 | `2f02fd5e8b55058b20d83ad821a7e5938a93ad6a7abcb2c25170bce9a62cbb0a` |
| 源码与脚本 | `scripts/upstream/check_cf24_overlap.py` | 4,026 | `27887a9f426e6cefc71a1fb47cac8c5b3b4aa2e187fb7583f95bf8b4ec368132` |
| 源码与脚本 | `scripts/build_blind_pack_v2.py` | 6,696 | `5368176eede85f7092307b84c94e93ef0c47477ab15c351329c057fdb61fa2dc` |
| 源码与脚本 | `scripts/build_final_index.py` | 11,132 | `1fe554b507a2951eb1718a0d478ef7aac71f0aec79ea3e8faf54720d4f6569a9` |
| 源码与脚本 | `scripts/redact_paths.py` | 3,855 | `41f9b88c34963b3c2137387be9c46a509b220e62fb588fab6d2c32d7c164a475` |
| 源码与脚本 | `scripts/run_real_state_smoke.py` | 14,155 | `7bafa7ff3b65bd64131f58a53d0417ac6201bc7e3ed907e1d5d8c868d3ba3fd5` |
| 预检产物 | `artifacts/fact-wording/preflight/preflight.json` | 8,485 | `2da60046b6968271f761531b039e0e42f1d0c2b1bcc5ea7d11fc28568ab07391` |
| 预检产物 | `artifacts/fact-wording/preflight/runs.jsonl` | 13,104 | `7d45b7cc912bfa12a7b3e34e11a11836e5f9e521d8546e53b573c1ae61fd666c` |
| 预检产物 | `artifacts/fact-wording/preflight/env.json` | 464 | `14eb102bc20cdaa73db6bb6f81cf91d48a76a4d7e3f3a27a59176445f9329209` |
| 预检产物 | `artifacts/fact-wording/preflight/p7-beam2.json` | 96 | `728d158b09f47e6efe9d5cb1f0465b5bebc86adf78ddd5dd9e618cc3f3881c08` |
| 脱敏与发布 | `REDACTION.md` | 4,092 | `62fde429e48b7aad1b97a21c3eb75e2bf84fb1e2be49d0c4d8b6d04e8d16f8a8` |
| 脱敏与发布 | `freeze/final-index-v1-pre-redaction.json` | 36,398 | `503b17a6b0819b15fdd42a4455fad8d804a8ca8307ee5dd2bfbf743578f9d9ba` |
| 报告与补注 | `README.md` | 18,823 | `e90e7fe002c3a85a4d9b137cd066b22bc7b1b106c3a32609c72b27e01b917986` |
| 报告与补注 | `results/preflight-report-v1.md` | 10,959 | `562d9e4258666d170426a561ee17bc974d25bff20c447018123609809d5b6df7` |
| 报告与补注 | `results/diagnostic-r1-report.md` | 11,237 | `a416ed2870bde40d54ea49e7a1fcc32d1ca22186d033be33bef6c284b7350818` |
| 报告与补注 | `results/diagnostic-r1-audit-v1.md` | 5,540 | `dddac5bb66761c4fcfa1bc903346c71f4e6d54b0098b64b1c1ec9ba47e3bfa48` |
| 报告与补注 | `results/t12f2-t24f3-verification-v1.md` | 3,802 | `4d82dda4d49a16c4097ab1f85d4bcf9acf4ccb930df40fe003a90efd8b49f8dc` |
| 报告与补注 | `results/extra-action-candidate-v1.md` | 7,314 | `2bb8685d5659e20f2d2b05745c12c1a14c4167d9e665afa230c7fd4f7c073839` |
| 报告与补注 | `results/extra-action-candidate-v2.md` | 2,648 | `fb471108c1f727802109c977436b60a123e4b5ff284231c179090215841a3873` |
| 报告与补注 | `results/candidate-t1-result-v1.md` | 6,217 | `3854a870587cbbbcb678d534c591b90ffea76145d5438f9b7201b7329ad084af` |
| 报告与补注 | `results/candidate-t1-result-v1-audit.md` | 1,352 | `9465679eaddb8c1c030bc7f7f2cb9505c8462b50d0fdabc789d2c989aecfde80` |
| 报告与补注 | `results/acceptance-registration-v1.md` | 4,828 | `2468b30a2b121e7c819b30640e2b4b8983e84a388886dc2821c684783c5564b1` |
| 报告与补注 | `results/run-history-v1.md` | 2,368 | `7ff13658bc7fc422e53cbb7922ce80823ac7c30d8f8cfe657d7d0ecc3390d34f` |
| 报告与补注 | `results/c4-stage-closure-v1.md` | 5,335 | `93bd07f9508d0bf1a123700b0775d4540ed1b710bbaeb3f7f63bba868242e162` |
| 报告与补注 | `results/review-findings-v1.md` | 4,333 | `69681b263247861a4590d5dd0b03a5776ae07aabdf0c41864af402e60ec1b32b` |
| 报告与补注 | `results/review-findings-v2.md` | 2,698 | `1a4c790a454122d8d3d53c0b0745840d03dc440763d40b814808a832c0fc8000` |
| 报告与补注 | `results/real-state-n3n4-smoke-v1.md` | 5,120 | `1f66a55b33666b40920de166cc36bc12b539b62839fe3b44476268407187cbc2` |
| 报告与补注 | `results/blind-design-defect-v1.md` | 1,288 | `5e1c935c9c2d9caaa09fac70fd04341d9320959cc3be0518556f5e926f2b37a2` |
| 报告与补注 | `results/timing-scope-v1.md` | 1,023 | `c318ba2721eb8500d48c2f25e0bf60af2d2eadb38f029022fb7701e57986fbef` |
| 报告与补注 | `results/next-steps-after-review-v1.md` | 1,069 | `4b8439a5fe5f3b9649b641be891d32aec411feae6dffa382666c6097796d2fbf` |
| 报告与补注 | `results/acceptance-registration-v2.md` | 5,119 | `957b1d10b6126bd09da65f0cf9d134800e7af91503aea9bc2f7b68459929b1ac` |
| cf24 失败分类产物 | `results/cf24-catalog-v1.json` | 281,260 | `b8c5ccac259c5ea9decfd2a30872b032b66a644dcab2ec4059bac0b9577cd7d6` |
| cf24 失败分类产物 | `results/cf24-moved-rule-pairs-v1.json` | 43,069 | `e1618ea120e134332351f58dca883f36f8c3b83e96714e56f6c3b80fcb74aebf` |
| cf24 失败分类产物 | `results/failure-report-v1.md` | 4,236 | `189fe1f030d6a6aac902c4ce992f7304adb4031b7cc6398ced1600075eafd128` |
| cf24 失败分类产物 | `review/batch-01.json` | 27,217 | `48ce9e44340f4c120591ca21dee89f10bfb885f1bbb1e88ca89b6317077dbad1` |
| cf24 失败分类产物 | `review/batch-02.json` | 12,401 | `82f971fc0b33bce467d83d9e21c4e1e7f4ce61453fb6e32e22d3d0664180a2f2` |
| 真实状态冒烟 | `artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/raw.jsonl` | 2,586 | `39d02c165d95935f252adb536c990ca4d1f4cc1923b14018402160a996d71dba` |
| 真实状态冒烟 | `artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/run.json` | 7,828 | `dca25d4eb58a1fa82dc1a2ac88b99618ec28418b54cd049313a039cda13fb208` |
| 真实状态冒烟 | `artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/env.json` | 202 | `b4c36179c5c951d43c93e72ecd96511c357d7e41f607ce7ba8398d7d92973b55` |
| 索引历史 | `freeze/final-index-v1.json` | 37,237 | `581426af15e845be2df730cadd6ed18ee299be6f86bdb3c9ca1da0a223137195` |
| 索引历史 | `freeze/final-index-v1.sha256` | 87 | `fac62141885b19d563bc71c0966a94833308a6e41c9e07ae5b9c026509e218d2` |
| 索引历史 | `results/final-index-v1.md` | 25,609 | `fa4ead907218d18c936600e4424394149792338a2adb0ec3d1cf1086f0c61d8a` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/raw.jsonl` | 118,291 | `616da43f6f9906afa8d30473684c078e97eaa5231b7c7e983c05343009acec21` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/order.jsonl` | 17,969 | `3c413784f69bbbcf3b81a1ff8aeb3c56e88eb1bbf27e8dc5efc56e2553cd7c5d` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/failures.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/run.json` | 1,279 | `695088b391420901bb50ace35f167183e1452d751018bea505301af334fa187d` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/env.json` | 206 | `44bd4629c909eaf16bd96cf968676b47ced33741b454a6152230488a4915d24a` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/analysis.json` | 24,495 | `a12337dcb2b827f2828b98bef6be605334ca472d375da65a0a2c581ed9314bbc` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/POSTHOC-NOTES.md` | 1,077 | `c7e0bc299cee2a1fe76187705d400dee6fe4cebed988b4be5dea6c3cba1114f9` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/index.json` | 2,201 | `5ec91f0ccbe58e9cb05fa11edae54d03f46fddc0a6d2b12dcf896a2cf45a422f` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/map.json` | 60,337 | `f024ffc249d34d85bfb463abb13dc16f6919db0dec4e89ac34685e1ab06d032c` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-01.json` | 8,678 | `932de6fd0c9c43c43483566596926e40f542a8ce2608b112793328948d075ec9` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-02.json` | 9,126 | `fde53e60218adf9e260230d7458373761d3d75f9137e5f49c52629c38afcbcb8` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-03.json` | 8,958 | `dcfb17fd7bc0d899270587f3ead59371fc217f3a5e7d778db1d4e5deae8d0e36` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-04.json` | 8,835 | `2aa93dad5d5a1d0d7bbc0e7ad64ad9ae0f3b517b5ff61e110d553755bd548419` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-05.json` | 8,748 | `d0874f3ac22434030b83276f120c23ac212b14fe06098496f5a158d62abcc96d` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-06.json` | 8,726 | `41414af9771db332ae04a2cf64f9681e86a5dbe14e2c206aa346afa4f3addab6` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-07.json` | 9,184 | `2480fbdc46056b2ef33cc6721cb9694cd205c4b12cb2d8c9ead1fc363aaac86a` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-08.json` | 9,105 | `87924d77c238151d9c27ec5baee9c03444418ef2b8cd3c1db467c7bd5b1edf94` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-09.json` | 8,666 | `591bf84dff7fe6ab271a5aa3810ebfb290666566cd83f3fb90ab59dea069f5bb` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-10.json` | 9,115 | `3bae163ec67485adf00e6e10753b63492da074d53aa6f904346a9e78c2828aca` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-11.json` | 8,782 | `1b84411f9ac6aaa50f621bb26d79ac12238d60b0a8f97257ca492e5ae36aaa96` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-12.json` | 9,062 | `df7291578a6a8c557ae47d1939da4efda45a7861dc55a9cee1e891bdcc401974` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-13.json` | 8,764 | `f79970989fe5a5ce49486d2787d516286c94f127a575816d991c4cbe41c0dd24` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-14.json` | 8,846 | `f55466171f9b7e9fd5e86bd662d3e1912b605c146cd15b8887cba75c1e4ed3cb` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-15.json` | 8,608 | `df03261e3507b04dcb3bfff6190cc792fc8b6e64463ac94260e4eefd9b34814f` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-16.json` | 9,038 | `94728670090d1633931171508bc988851b062b0bce243616ef62144c69707af3` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/batch-17.json` | 8,318 | `33c2fb57ba72521569912bb4abc2f87d637455ef4ae6bf2ba77cfcb294da2d92` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-01.json` | 1,969 | `7d51ae24747e916c857bc38a01ca482c5ff021c001ffb9c112ff64ba49024186` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-02.json` | 1,969 | `760c922a3ad243bf25d1168933d64eeacfdea234edaf9952ca4e7aae6a1c0c98` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-03.json` | 1,969 | `e9a89306ab33ef5fa3896d0ca7444f1f4bb782ea6657816f657a43c7b35e8872` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-04.json` | 2,307 | `12a8f4f9d3eeab585b0692a623b0375a2b9eb2e583de222b787ea8d304df5a19` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-05.json` | 1,969 | `5dd3299098374c8abd994240b60afd01d0223f17fef5b61b718fcacb7bac3ec0` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-06.json` | 1,969 | `a1fda3fbde5695d08f00a6b37d42e4bd7404444e01926e45fe8e2a0704cd5e12` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-07.json` | 2,240 | `c27e9e91cdbdc410fd04a0d7eade99d72e0cf78de762ff3b645b8c859047f6da` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-08.json` | 1,999 | `3c477e9b59e0598bc7010cf3bdef4fd656d89e4e4296edafb5275b28d95a1279` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-09.json` | 2,207 | `4a2441c0dce82e0108d1500bcc2e4edf4d172104dad9699fa04bf72aea5f2300` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-10.json` | 2,408 | `bdd2170ca86bc90e309cb5e359fe4591bcf1d607e94652169f742748015c68e4` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-11.json` | 2,113 | `928201da223c0c1a31b3ce19477b2501835bb3c9e0df0f22cd47ee7aa54269a6` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-12.json` | 2,257 | `4f38fd47d811646af18d3f680ba9a24d96b242d771c254c58d09338eee72431e` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-13.json` | 1,969 | `85f3c4b37a32e27e50f2379964162e5bf459ad8aff429602e7edb0c3af7a5b1d` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-14.json` | 1,963 | `bb2b87e745a2be6fb600397733f714110afb3d1303b552517aeba654df97ad6f` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-15.json` | 1,960 | `bc3f6185d634341ed36a076b26bc14a406e45d300b02c4aa47f87f84970455e3` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-16.json` | 1,959 | `815c410b06bf6c3b808ab7c4a5012ed403d8cb81f76559b36bc7b42aaf0c1b60` |
| r1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind/judged-17.json` | 2,159 | `a26e35df64c1dda723d6acc8ba622bcce24776ffa879e029e7c0756aaa3985dc` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/index.json` | 155 | `7924a369f3e219e9739e7e0b181afd5b60564b6360a11eae2843650317ed2c1b` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/map.json` | 26,649 | `9bf0ec3467944f38797787419c6810571cb41c2e1c9e2378bb2424d8cbfab99b` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-01.json` | 6,119 | `07a87f3202bcec9aac160de653559454445cddda6141412402c51fbb4e177037` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-02.json` | 6,189 | `1df5eddb111e11cba6c0d575f519ed7fe8993fccc88dd1413a582ad7a3002a4d` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-03.json` | 6,158 | `38d0a745e79671505f2e876f9b23f06aaec6d436ac65c9248b307d25635784d3` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-04.json` | 6,141 | `50e4d4a55cf4cf356aaa6a531029339f62a28d07d220cd161b1562f8de80425f` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-05.json` | 6,119 | `811666393fa030a438702d797a24ed9038c9603ea7f5253aca7ed3e5bc8c8600` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-06.json` | 5,999 | `901a6dd917b441c71a22a9bb9069d50ff80ae620361feea79d605369aabc7d81` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-07.json` | 6,049 | `22d4dfe07bc3b10519f15249bd7a28d3dc5f9922c92648e524a88b8bf9fd354a` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-08.json` | 6,399 | `63b7bdbd30177483ab143ce753de26ca77782e542cf5bb5f585e6f72a030a10a` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-09.json` | 6,208 | `e3d20b01331c4c368921c3d1924f72bbc2c4443aa80cd3b7f29e7522be26003e` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-10.json` | 6,086 | `f3c51afca785141d399637a96247583785af731c1622cc6ccf4fdb284ce6cd17` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-11.json` | 6,128 | `599db5cb9be8e6680550db87bed735465be9b0a710410a14c646d926e3ea7ee4` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-12.json` | 6,204 | `b40a10a009424b7b9de055477bb87e4f0ca467bb2f052d660336966bdb564e23` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-13.json` | 6,196 | `ff3ce683fefb81de1d11bcf596e2b4ffd4f7dfc88329f1673eb9ed6a968d8645` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-14.json` | 6,213 | `a5d58034a989cb0e2520e40e7362259bc4ff7218915894118290e757f68f137f` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-15.json` | 6,039 | `ae53ee785a09ae3ee9eea6629bbfb47446615153e3af8a6491d5b4e2897f2c61` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-16.json` | 6,384 | `c2c75a683d6efbfbddc775bb21f599c5c162b4a600998e222619c9a3e9379106` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r1/20261108T150002-a0ed91d4/blind-v2/batch-17.json` | 6,233 | `273579861c65be2b94d15eed728f0e1409a7b31aaa12e7f6c310cce8ff569783` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/raw.jsonl` | 42,568 | `a77b10e5eeb71fd0e9de999648f8bce2beb174bbb9a3ff18b9245748fbef3b60` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/order.jsonl` | 7,548 | `2c3539fb0615648eacdfb33a8bf110105cb352bcfecc926bd95f474205c53088` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/failures.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/run.json` | 1,448 | `cbe83634073eebf25c929c30014b080e8ed18206e495507cd4d22563f0ec513c` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/env.json` | 206 | `44bd4629c909eaf16bd96cf968676b47ced33741b454a6152230488a4915d24a` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/candidate-analysis.json` | 31,600 | `45f403c76f110f3d50b62d78cdf772cd83b44471ac3b1d7f0f27a9765bf98792` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/runner-snapshot.py` | 8,483 | `a2c521520c2b35a5bc71cee96bd1dd6a0b3adeb7c1cf7b50a483a74c4e0a7030` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/index.json` | 1,982 | `129d5ade4df43d6229eefbb3d00eca4dd72e385ea7b1339cd5ddeb7c24d31e97` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/map.json` | 42,641 | `b58b8de0d35a704b764173ef0093d6ddd889d8c4ea90221d53198a4a0ec7012f` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-01.json` | 8,536 | `6c54d712d99b586aebf9180c4a85ad8217f12b407b1289da6649832ddf7f8a4a` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-02.json` | 9,006 | `7c9efe0bff658d43b79cd113f5a8bcae25b4aece890d9c7a0daed3ca184b459c` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-03.json` | 8,832 | `e0725ae4a5bb168f0ca858792fd8ae380d1f431237f9f91f24f739700c73f2d9` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-04.json` | 8,727 | `e87daf531c64f1cca49c4a4b3280adf2e83c152769a774ea41c4f4aacc37aa4e` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-05.json` | 8,606 | `16d0a1e846aa39667d18170a40d333a6d8513433c67cd6f35086e4c0ab85b516` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-06.json` | 8,584 | `973bff722dfe63ddf043a530b08b940d7d45a5c5b3c99996ab999ce26c7492b2` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-07.json` | 9,042 | `42bed1dc3e3411bb04c9de3848d5fa25385c9426da4819a832637df1d7eb87bf` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-08.json` | 9,000 | `0915b1af2b0f0e0404c24a840a28e50cfdeb80736a20e2a5e335249320b6d93f` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-09.json` | 8,524 | `6d2a6866134020670148ec6ca7589fe176dccd44bbcae84744bff13175849799` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-10.json` | 8,998 | `ee762966713c920e0915b80d58130fe74dea238bc3a7866c06ff912d7a093957` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-11.json` | 8,662 | `88c60eea2420553947b5e13b14f0817bb6973346b89b991781601932a82f3207` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-12.json` | 8,942 | `355d035902bcadd5509e97d34d8e080e9f308553b051d6ff509328f6beda73f5` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-13.json` | 8,622 | `5fad4f591fb9aebd57745a555d2fbc7c3ae992194e7c17c705288ec91e1f5e71` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-14.json` | 8,704 | `b0794e7a73594778d9690501c80a24e1308af251af2ce71b4b56ecf31d6a0e99` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-15.json` | 8,466 | `fc32e894919fd5eb3adf6ae3b520f1b3e9a2371d3040ce9aef3dd6dc88350f5b` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-16.json` | 8,918 | `951ed47b41578adae4c3472e9b4b6112c1a1c862058806e9d32f39a67cc04303` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/batch-17.json` | 8,176 | `fdfe00c13b0939fc335908820c9a1b87b83b965b01c0d7a0392d0922c201ddb2` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-01.json` | 1,969 | `4f4948bdd372c8dea245121dcf5f3127b486f2eab158dfda0db8f3226982cfee` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-02.json` | 1,974 | `cd5b0a62d3293a10987e4d00f096d13c2f1f7630eb1161c8589ac2c43cf5ad00` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-03.json` | 2,000 | `edf6ff612b8a063a2fcdc5628b0a759fa1d44abf3c0151324decf2cc4caf6b6c` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-04.json` | 2,186 | `f5773847b38c318acf644b584239c000d42b05662206f7729d20658b138362bf` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-05.json` | 1,969 | `4397560a17e56e90079f16fb1c0c776755cdc5bb968466f1054028d931f9a425` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-06.json` | 1,969 | `78cb1c0e3b39ced486e12dffe03161b97be717547727f6e34556af540233d12d` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-07.json` | 2,124 | `3f1ff70299626a8fc3b5baca52c883dbf81a0868430d1e507a7a0f5b1fb175b9` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-08.json` | 2,017 | `4bc11642076d881aab52eec4cfb5734707da4475765b2a34e95137e1f76f88ca` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-09.json` | 1,992 | `4deea40a13cf0a0b40a31d3e8ed5b11cff11d24268eac7b450b9b1e4eebc3052` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-10.json` | 2,232 | `d782642da57f643cd4ff263418fde232c20ac53f1b30c5141f706f22a2763ddb` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-11.json` | 2,100 | `ef0e2d28c143fb7fdce503c289dfae4f6e5dcb8ae5f566aa477670c614e16ae3` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-12.json` | 2,136 | `c7a8463448475f158efccf364df93e8c5c9bbfff7941701e1f04cdbccc2329fc` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-13.json` | 1,969 | `fbbef09cdec18f16140876bf8c8bb3cd1bfaacfa8edcdf4cbfba8f73d6656b9a` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-14.json` | 1,927 | `00c523d6afc8a1b95ff4c66c83f85a3ceb2c45cb0924b4b69e6c6b3bdf3627aa` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-15.json` | 1,903 | `fb81f00b94ef63a5c28e86e33d2de04a86f25bf9bc5af303e03abb151587c49e` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-16.json` | 1,922 | `d9131c61d49d40f08ab28435447cd77b27e7a2c9468b9249723e83d5b9a1bfcb` |
| T1 运行原文与判词 | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind/judged-17.json` | 1,935 | `6baa21baa50daea35bdabea8f504ba484c964de5a5c1247a9d64dbf2d1dfe0c9` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/index.json` | 155 | `7924a369f3e219e9739e7e0b181afd5b60564b6360a11eae2843650317ed2c1b` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/map.json` | 17,873 | `7fb49407161a870c85ae3faad8a684d884d4c963af80b01ebe861a5ac710bc67` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-01.json` | 6,134 | `123f5aa91a2485f88c7c3b07629f56ab9da6ec139816977c82e0cb20dc1db8c0` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-02.json` | 6,189 | `3cd76124d254544a917e87fe0b83c5e21b25e7675e1b2e829b9c3eb0623f1df5` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-03.json` | 6,158 | `6fe7dda893c04f3865521cb319411f163bf89cd6f93ef06a053762275d224ac8` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-04.json` | 6,175 | `12fb06b2ccc067f504147b9ae21ede96c2a2fb4362579c665b15e6fe8c241588` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-05.json` | 6,141 | `34e515876880bccb0b4eb429179cdfcce910666ba1e7457822ff16fd79abafd1` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-06.json` | 5,999 | `c020de27cdbd291e4e55ae0cce170d1c58a05d4b8df45ccc9552b2ec686debd0` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-07.json` | 6,049 | `a11ee6921866c5a7398d745e0922f322f1dfbb5b436c2853cd74256675a960a5` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-08.json` | 6,437 | `876373697e0d9fb042d10314f69a77c7d0375cd4a9f12c80908b707d2bb31a53` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-09.json` | 6,233 | `3ff53b130e686c626230e787844735eebec1c52df4905f2e5a2a15b86c4fb2b5` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-10.json` | 6,086 | `1102d60da909728b0d3025e37f0f0129411c6f7e00a83bd2f7aff2905db325e3` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-11.json` | 6,128 | `62b15370b815e1ffbd42f4f1fd4a06fc35a33b0fb5369c5b14baf387169a07a0` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-12.json` | 6,204 | `57439abc4ed3d8302bff61a90594e41a5f6b55fd606639aa138ca3b733c161fa` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-13.json` | 6,196 | `1b3393a66feea3257cfe62088391b2efa0b2c705c815c1b83426305189d17b06` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-14.json` | 6,216 | `7a37e93b0fd9d66cd8c2b70955ce3f950db7f6a9213887ec92ccc4f35a509478` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-15.json` | 6,061 | `e5a707b641dd9539185bbf28cf031feb7716c3d3efd6ceb9b5d8bbee99e25254` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-16.json` | 6,403 | `9ed3cf2fc14f10d47e34653a5743939286e836d9c030f2dea75a5a6c9d31499a` |
| 盲判包 v2（未判） | `artifacts/fact-wording/diagnostic-r2-cand-t1/20261108T152314-d8c16de6/blind-v2/batch-17.json` | 6,255 | `e0e3e39c3a4101ee8f079adf3b517b4d5a8dd7f207e9ad685b2fc67ad0e3577c` |

缺失文件：无
