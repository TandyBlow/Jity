# WebLLM 1.7B：链路跑通（2026-11-22，run57）

## 结果

- 本地权重 + OPFS 缓存：1.7B 在约 5 秒内加载完成（30/30 分片、924 MB、WebGPU nvidia）。
- 单回合（s02）**22.0 秒**完成，驱动 problems 为空（此前的「no model file」是驱动的 .gguf 匹配盲区，已修正为同时认 `.bin/.json`）。
- 分调用：results 3.0 s、position 5.0 s、appearance 1.9 s、narration 2.0–2.3 s。对比 wllama 同类的 65–180 s/回合，量级完全不同。
- 代价与缺陷：正文里夹了空的 `<think> </think>` 标记（思考开关已关，仍偶尔输出空标记）；部分 targets/action JSON 解码失败走 fallback（1.7B 的格式能力）；这两项在 4B 上要重测。

## 结论

- 运行时这条路是通的，而且性能上限比 wllama 高一个量级。
- 下一步：4B（下载中）在 OPFS 上跑 s05/s06，量质量门与时间；若 4B 的 JSON 与事实表现达标，D-022 的推荐路线就从「换运行时」的假设变成实测。


## s05/s06 追加（run58）

- 两回合都在 11.8/12.6 秒内完成，但结算被 codec 拒绝：模型把 `label` 写成 `completed`（合法值是 achieved/partial/not_achieved/blocked/no_change）。这是 1.7B 的格式能力，不是运行时。
- 正文里仍夹空的 `<think> </think>` 标记。
- 结论不变：1.7B 证明运行时快，但结算格式需要 4B；4B 下载完成后直接测。


## 4B 加载（run59–61）

- 4B（2.2 GB、83 文件）已本地化到 `public/models/webllm/Qwen3-4B-q4f16_1-MLC/resolve/main/`。
- OPFS 后端：在 768 MB 报 `QuotaExceededError`；但页面实测 `navigator.storage.estimate()` 的配额是 10 GB、usage 0——所以是 OPFS 后端自身的坑，不是真的没空间。
- Cache API 后端的 4B 测试被宿主内存回收杀掉（系统 low memory），按回收规则未自行重启。
- 当前结论：4B 的加载路径还差最后一步验证；1.7B 已证明运行时可用（22 s/回合）。等用户允许后再试 Cache API 或持久化 profile。


## 4B 打通（run63，持久化 profile）

- 独立探针：4B 完整加载（74/74、2.2 GB、WebGPU）并生成「你好！」。
- 验收驱动加 `--profile` 后，4B 在同一 profile 的缓存上 6 秒加载完成（2.16 GB）。
- 产品单回合仍失败：`results` codec 报 `fact text must be non-empty`，28.6 秒结束——不是运行时问题，是 4B 的首轮输出格式/内容问题，下一步看 s05/s06 的原始输出再决定是否修提示。


## 4B s05/s06（run66/67）

- 结算解析与事实字段修正后，4B 能提交 s05：整轮 131.2 s，唯一问题是超 60 秒；正文里出现大段 `<think>` 推理文字（narration 的 chatml 提示走了 bare completion，模型把思考写进正文）。
- s06：`strictKnownEntities` 校验命中 `results_unknown_entity:阿豹`，回合可见失败——程序门在 4B 上也生效。
- 修正：narration 的 ChatML 提示改走 chat API + `extra_body.enable_thinking:false`；结算仍走 bare completion。重测在 run68。


## 4B 稳定性（run69–71）

- run69：4B 在开场叙事之后卡死 30 分钟，已停止；给适配器加了 150 秒生成上限。
- run70：复用旧持久化 profile 时撞上残留的写入租约（「另一个标签页仍持有存档写入权」），页面未加载模型即失败。
- run71：换全新 profile 重跑，被宿主内存回收杀掉（第二次 low memory），按规则未重启。
- 结论：4B 的加载能力已证明（run63 + 探针），但在这台机器上连续跑产品回合会反复触发宿主内存保护；拿到完整 s05/s06 数据需要内存更宽裕的窗口。


## 1.7B 修复后复跑（run72）

- s05：results 仍报 `model output is not JSON`（裸 completion 下 1.7B 不守 JSON）。
- s06：`strictKnownEntities` 命中 `unknown entity 阿豹`（程序门生效）。
- 结论：1.7B 的速度（22–44 秒/回合）不能抵消它的格式能力；质量路线要 4B，而 4B 在 2.2 GB 内存占用上被宿主保护挡住。


## 3B + 约束解码 + think 剥离（run74/75）

- s05 完整回合 45.0 秒、驱动 problems 为空；正文不再夹 `<think>`。
- 但正文**复述序列化事实**（「屋里有路明非的护目镜…时间到了15:21…」），开发检查器报 `input_echo` + `band_claim`。
- s06 仍由 `strictKnownEntities` 拦下（`results_unknown_entity:阿豹`），回合可见失败。
- 结论：换运行时在 3B 上解决了速度与 JSON 格式，**没有解决质量**；4B 是唯一未测的质量希望，但受宿主内存限制。


## 3B 的候选扫测（run76/77）

- `constrained`：s05 40.2 秒，正文原样重复输入句两遍（检查器 echo 1）。
- `trained`（beats）：s05 39.7 秒，表面通顺、检查器 0 命中，但**凭空添加**了「夕阳、汗与泥土、机械运转声、诺诺握规则牌」等事实里没有的细节——撞「无捏造」这条人工读评硬门。
- 三种候选（builtin 复述、constrained 回声、trained 编造）在 3B 上都不合格；运行时的速度与格式优势救不了叙事质量。


## 移动模拟档（run78，WebLLM 3B + 核显 + 4× CPU）

- s05 整轮 **264.9 秒**（唯一问题是超 60 秒）；s06 125.4 秒后被结算门拦下。
- 对比 wllama 的 268–298 秒：换运行时在核显上并没有质变，瓶颈仍是 iGPU 的 prefill。
- 结论：移动档 60 秒用 WebLLM 3B 也到不了；D-023 的移动目标在当前硬件上仍不可达。


## 4B 公平复跑（run79/80，修复后的栈）

- run79：旧 profile 残留写入租约，未加载模型即失败（基础设施问题）。
- run80（全新 profile）：s05 33.8 秒但 `narration_failed`/`prose_not_identical`，正文尾部带出「The current Object has already been disposed」；s06 2.6 秒失败。4B 的 WebLLM 引擎在产品回合里不稳定（引擎被释放/内存压力）。
- 结论：4B 可加载、可出字，但在本机的产品回合里不稳定；3B 稳定但质量不合格。


## 定向微调准备（2026-11-23）

- 已从所有语义证据抽取**真实叙事提示 111 条（84 条唯一）**，落 `.local/narr-train/prompts.jsonl`，覆盖复述/回声/编造/未知实体的失败样本。
- 集群 SSH 当前不可达（WinError 10060），教师模型生成与 MLC 转换要等集群窗口；本地无同级教师模型。
- 下一步（集群可达时）：教师生成目标正文/结算 → 开发门过滤 → LoRA 微调 3B/1.7B → 转 MLC → WebLLM 同题对照。


## 4B 稳定复跑与结算门修正（run81/82）

- run81：s05 95.8 s 完成、复述；s06 的事实为「阿豹不在场，未能转交」——**模型判对了**，却被 `strictKnownEntities` 以「出现未登记名字」误杀。
- 修门：只拒绝 `outcome=completed` 且未被否认的事实；blocked 事实允许点名。settlement 测试 99 passed。
- run82：s05 93.6 s、s06 **45.0 s**，两回合驱动 problems 均为空（结算通过）；但 s06 的**叙事**仍把「把红色电台递给阿豹」写成已发生，开发检查器报 `unknown_entity_claim`。
- 结论：4B 的结算问题被程序门修正解决；剩下的唯一失败层是叙事（复述/编造）。质量路线现在明确指向叙事数据。
