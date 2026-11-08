# c10 新小模型资料核实与最小运行验证：MNN-Pocket-0.3B

| 字段 | 值 |
|---|---|
| 编号 | `c10` |
| 分支 | `exp/c-model-scout`（父分支 `world-components` @ `6440534`） |
| 日期 | 2026-11-08 |
| 本轮范围 | 资料是否可靠、能否跑通；**不做质量结论**，不替换现有模型，不改页面 |
| 独占目录 | `experiments/world-components/parallel/model_scout/` |

## 0. 结论（按三类写）

**已证明（有原始文件可复查）**

1. 模型来源、版本、许可、GGUF 文件都存在，且和官方仓库对得上：`taobao-mnn/MNN-Pocket-0.3B-GGUF` 是阿里巴巴 MNN 团队（GitHub `alibaba/MNN`）在 2026-11-04 发布的 0.3B 中英文指令模型；Apache-2.0；三个 GGUF 文件都在，大小与下载后算出的 sha256 与 Hugging Face 给出的 `X-Linked-ETag` 完全一致。
2. 无 WebGPU 的浏览器路径能跑通：Edge 157 headless（`--disable-gpu --disable-features=WebGPU,Vulkan`，页面里 `navigator.gpu` 被删除）里，wllama 3.8.1（WASM，4 线程，`n_gpu_layers=0`，交叉隔离已开）加载 Q4_1 与 Q8_0，各跑两次，全部正常 `stop` 结束，页面错误 0、请求失败 0。
3. 同一条固定输入（275 字、179 个提示 token），同参数（temperature 0、seed 42、`cache_prompt=false`）跑两次，输出逐字相同，可复跑。
4. 资源与延迟量级（本机，机器忙闲不一的条件下，见 §3 的噪声说明）：Q4_1（上下文 2048）加载 13.5 s、加载后进程内存 707.5 MB、预填 8.1–9.4 token/s、解码 6.0 token/s；同一文件按世界页面设置（上下文 2048 + `enable_thinking` 参数）加载 17.7 s、707.5 MB、预填 7.5–7.6 token/s、解码 4.2–4.5 token/s；上下文 4096 时 18.4 s、727.5 MB、预填 7.2 token/s、解码 4.3 token/s；Q8_0 加载 28.2 s、1101.2 MB、预填 12.2–12.7 token/s、解码 6.5–7.0 token/s。Q4_1 单次总耗时 25.0–33.3 s。

**已失败**

- 产品层失败：无。
- 过程失败（都修了，记录在 §4）：前两次运行是探针脚本自己的 bug（动态 import 裸路径、没导航页面），不是模型失败；自定义 logger 缺 `log` 方法触发 1 次页面异常；favicon 404。

**无法判断（本轮没有数据，不能算通过）**

- 文本质量、事实对齐：本轮只记录输出，不判分。
- 接入正式世界页面后的循环（页面读模型端口、六阶段、叙事门）：没接。
- 统一浏览器验收队列里的页面级验收、20 条输入验收：没排上。
- 移动端/低内存设备、长上下文、多轮 KV 复用、长时间稳定性：没测。

## 1. 这次具体怎么做的（谁给了谁什么，程序做了什么，结果存在哪）

### 1.1 抓官方来源

`sources/capture.mjs` 用系统 `curl`（这台机器 Node 的 `fetch` 不走代理，`curl` 走）把 8 个地址的原始字节抓下来，写进 `sources/*.body`，并把 HTTP 状态、内容类型、字节数、抓取时间和 sha256 记到 `sources/capture.json`。报告里引用的每一句话都能在这些 `.body` 文件里对上。

抓的 8 个地址：Hugging Face 两个模型仓库的 API 与模型卡、`config.json`、GGUF 仓库的 `LICENSE.txt`、GitHub `alibaba/MNN` 的中英文 README。

### 1.2 下载权重并核对哈希

`curl` 下载到仓库外的本地模型缓存 `D:/others/Jity/.local/models/`（`.local/` 已被 `.gitignore` 忽略，192 MB / 387 MB 的权重不进 git）。

下载完在本地算 sha256，再和 Hugging Face 对同一个文件返回的 `X-Linked-ETag`（HEAD 请求，原始结果在 `sources/heads.json`）比对：

| 文件 | 字节数 | 本地 sha256 = HF `X-Linked-ETag` |
|---|---|---|
| `MNN-Pocket-0.3B-Instruct-Q4_1.gguf` | 191,896,672 | `a281c127e388b16537fd3f5d31ab32d3f87739e6dc514ac1093c80d9eac8d097` |
| `MNN-Pocket-0.3B-Instruct-Q8_0.gguf` | 386,751,520 | `31eb5db92b2e02a80e9e3a9316aa83120cbee98e4f4a22ca19015ba601dbd690` |
| `MNN-Pocket-0.3B-Instruct-F16.gguf` | 725,654,560 | `7c08939950b370dac6bc5e83725d6039b5af285656440b968818305c674abd0a`（只取了官方声明，未下载） |

### 1.3 固定输入从哪来

用已登记的固定输入，不临时手写：从 `artifacts/narration-eval/run.json` 里取样本 `nv-move-1` 第一次调用的完整提示词（275 字，sha256 `75753343aa1edaed986b03d2326216de148e8a410e8ba6565b6d1db3c4461c8a`），原样落到 `inputs/nv-move-1.prompt.txt`。这份输入是冻结夹具，之后谁复跑都用它，不会漂移。

### 1.4 浏览器最小运行

`run/probe.mjs` 做四件事：

1. 起一个本地 HTTP 服务，返回时带上 COOP/COEP 头。这两个头是浏览器的开关：开了才允许用 `SharedArrayBuffer`，wllama 的多线程推理才成立。
2. 用 Playwright 启动系统 Edge（headless），并加参数 `--disable-gpu --disable-features=WebGPU,Vulkan`；在任何页面脚本运行前，把 `navigator.gpu` 定义成 `undefined`。这样页面里根本没有 WebGPU 可用。
3. 在页面里动态加载 wllama 的浏览器包，用 `loadModelFromUrl` 读 GGUF（`n_ctx` 2048 或 4096、4 线程、`n_gpu_layers=0`）。GGUF 是单文件格式：权重、分词器、对话模板都在里面；wllama 是 llama.cpp 编译成 WebAssembly 的版本，所以推理跑在 CPU 上。
4. 用同一段提示词连续调两次 `createChatCompletion`（`temperature 0`、`seed 42`、`cache_prompt=false`、`max_tokens=96`），记录每次的：首 token 时间、预填耗时、解码耗时、token 数、结束原因、原始文本；同时记录加载进度、加载后的进程内存、控制台日志、页面异常、请求失败。

一次调用在程序里的样子（这就是 §3 表格里的数字从哪来）：提示词 275 字 → wllama 用 GGUF 内嵌的 ChatML 模板包成对话 → 分词得到 179 个提示 token → 预填（把整段提示算一遍，耗时约 19–25 s）→ 逐 token 生成 37 个 token（约 5.4–8.5 s）→ 模型输出结束符，`finish_reason=stop`。这些耗时是 llama.cpp 自己报的 `timings`，存在每次运行的 JSON 里。

### 1.5 汇总

`evidence/summarize.mjs` 只读上面 5 个原始运行文件，生成 `evidence/summary.json`、`evidence/summary.md`（表）和 `evidence/outputs.txt`（提示词 + 每次的原始输出）。报告里的表格数字就是从这三个文件抄的，没有手算。

## 2. 资料核实明细

| 项目 | 核实结果 | 证据 |
|---|---|---|
| 发布方 | 阿里巴巴 MNN 团队（Hugging Face 组织 `taobao-mnn`）；GitHub `alibaba/MNN` 的 News 段写明 2026/11/04 发布，并链接到 `huggingface.co/collections/taobao-mnn/mnn-pocket-03b` | `sources/mnn-github-readme.body`、`sources/mnn-github-readme-cn.body` |
| 发布日 | 2026-11-04（GitHub News）；HF 两仓库 `lastModified` 分别为 2026-11-05、2026-11-04 | 同上；`sources/capture.json` |
| 仓库版本 | 基座 `taobao-mnn/MNN-Pocket-0.3B` commit `087a52fd9ff0dee9a2a0b2605172fd55d8af9e85`；GGUF 仓库 commit `9073b9efa602be7d0167d586727974f4419e1e41` | `sources/hf-api-base.body`、`sources/hf-api-gguf.body` |
| 许可 | Apache-2.0。仓库 `LICENSE.txt` 正文是 Apache License 2.0；两仓库元数据 `license: apache-2.0`；模型卡与 GitHub News 都写 Apache 2.0 | `sources/hf-license-gguf.body`、`sources/hf-card-base.body`、`sources/mnn-github-readme.body` |
| 规模/结构 | ~303M 参数（元数据 `general.size_label=303M`）；qwen3 结构：28 层、hidden 896、14 个注意力头、2 个 KV 头、head_dim 64、FFN 2560、词表 65536、输入输出嵌入共享、训练上下文 40960 | `sources/hf-config-base.body`；运行时 `modelMetadata`（在 evidence 的每个运行文件里） |
| GGUF 是否存在 | 存在，三个：F16 725,654,560 B、Q8_0 386,751,520 B、Q4_1 191,896,672 B | `sources/hf-api-gguf.body`（含每个文件大小）；本地哈希见 §1.2 |
| 量化来源 | Q4_1 来自 QAT（量化感知训练）权重，F16/Q8_0 来自 BF16 权重；GGUF 元数据里写着 `pocket.qat_conversion` 和 QAT 源检查点 sha256 `790692d5…` | 运行时 `modelMetadata.meta`（`probe-Q4_1-ctx2048-r2.json`） |
| 对话模板 | ChatML 风格，模板内嵌在 GGUF 元数据里；运行时 `getChatTemplate()` 能读到完整 jinja 模板 | 同上（`chatTemplate` 字段） |
| 可信度限制 | 发布仅 4 天，HF 下载量约 676（基座）/934（GGUF），没有第三方独立评测；本轮也没有做质量评测 | `sources/hf-api-base.body`、`sources/hf-api-gguf.body` |

## 3. 最小运行结果

五个配置（最后一行为对照），都是同一段固定输入、同一台机器、Edge 157.0.4341.42 headless、wllama 3.8.1、4 线程、`n_gpu_layers=0`、temperature 0、seed 42、`max_tokens=96`、每次连跑两遍：

| 运行 | 加载 s | 内存 MB | 预填 token/s | 解码 token/s | 单次总耗时 s | 结束原因 |
|---|---|---|---|---|---|---|
| MNN-Pocket Q4_1，ctx 2048 | 13.5 | 707.5 | 8.07 / 9.44 | 6.00 / 6.03 | 28.3 / 25.0 | stop / stop |
| MNN-Pocket Q4_1，世界页面同配置（ctx 2048 + `enable_thinking`） | 17.7 | 707.5 | 7.51 / 7.61 | 4.23 / 4.45 | 32.4 / 31.7 | stop / stop |
| MNN-Pocket Q4_1，叙事评测脚本同配置（ctx 4096 + `enable_thinking`） | 18.4 | 727.5 | 7.21 / 7.26 | 4.26 / 4.27 | 33.3 / 33.1 | stop / stop |
| MNN-Pocket Q8_0，ctx 2048 | 28.2 | 1101.2 | 12.69 / 12.18 | 6.53 / 6.99 | 20.0 / 20.2 | stop / stop |
| 对照：Qwen3-0.6B Q4_K_M（现有基线），ctx 2048 | 32.3 | 1337.5 | 10.29 / 10.65 | 5.14 / 5.14 | 19.3 / 18.6 | stop / stop |

怎么读这张表：

- **内存**是 `performance.measureUserAgentSpecificMemory()` 报告的进程总字节（含 WASM 线性内存），不是“模型文件大小 + 某常数”。所以 192 MB 的 Q4_1 文件对应约 707 MB 进程内存，387 MB 的 Q8_0 对应约 1101 MB。
- **预填/解码**是 llama.cpp 自报的 `prompt_per_second` / `predicted_per_second`；单次调用总耗时包含预填、解码和框架开销。每次运行都写了两次，两列是第一次/第二次。
- **对照行**只用来确认探针和环境本身没有明显异常；它的输出只有 8 个 token，解码样本很小，不能拿来给模型排名。
- **噪声**：这台机器上同时有后台浏览器、TIM、微信在跑，采样到的 CPU 负载 4%–79% 不等；同一个 Q4_1 文件在三个配置/三次测量里，单次总耗时 25.0 s 到 33.3 s（预填 7.2–9.4 token/s，解码 4.2–6.0 token/s），采集时 CPU 负载高的一次反而更快。可见波动不完全是“后台占 CPU”，我也没有把原因隔离出来。所以上面的延迟只能当数量级参考，不能当基准分。
- **确定性**：同配置两次输出逐字相同（见 `evidence/outputs.txt`），temperature 0 + 固定 seed 在这个运行时上确实可复跑。
- **无 WebGPU 的证据**：运行时日志里有一行 `ggml_webgpu: Failed to get an adapter: WebGPU not available on this browser (requestAdapter returned null)`，之后推理照常完成；同时 `environment.webgpuVisible=false`、`webgpuSupported=false`。也就是说这次运行没有可用的 WebGPU，仍然跑通了。

## 4. 失败与异常日志（包括过程失败）

| 时间点 | 现象 | 是谁的问题 | 处理 |
|---|---|---|---|
| 第一次运行 | `Failed to resolve module specifier '/wllama/index.min.js'` | 探针脚本：页面里动态 import 用了裸路径 | 改成用 `location.origin` 拼绝对 URL |
| 第二次运行 | `Failed to construct 'URL': Invalid base URL` | 探针脚本：只建了 page，没导航到本地服务，`location.origin` 是 `null` | 加载 `http://127.0.0.1:<port>/` 再执行 |
| 第三次运行 | 页面异常 `this.logger.log is not a function`；控制台一条 favicon 404 | 自定义 logger 缺 `log` 方法；没处理 `/favicon.ico` | logger 补齐 `log/debug/info/warn/error/trace`；favicon 返回 204 |
| 之后 5 个正式运行 | 页面异常 0、请求失败 0、控制台错误 0 | — | — |

完整的控制台/页面异常/请求失败都原样存在每个 `evidence/probe-*.json` 的 `console`、`pageErrors`、`requestFailures` 字段里。

## 5. 结论分类（严格对照任务验收）

- **已证明**：官方来源、版本、许可、GGUF 存在与哈希一致；无 WebGPU 的 Edge + wllama WASM 路径能加载并生成；加载/内存/延迟有原始记录；同参数可复跑。
- **已失败**：无产品层失败；两次过程失败是探针脚本 bug，已修复并记录。
- **无法判断**：文本质量与事实对齐（本轮不判分）；接入正式页面后的循环；统一队列中的页面级浏览器验收与 20 条输入验收；移动端/低内存设备；长上下文与多轮 KV 复用；长时间稳定性。

## 6. 下一步（排队，不在本轮做）

1. 把 MNN-Pocket 接进现有 `wllama-engine` 模型端口，再走统一浏览器验收队列做页面级验收。已经验证过的接入前提：世界页面的推理参数是上下文 2048 加 `enable_thinking:false`，这一组参数本轮跑通，提示 token 数仍是 179（说明该参数不影响 MNN-Pocket 的 ChatML 模板）。
2. 用 B 侧已冻结的 narration 判分器，在同样 10 条固定样本上打分——那才是质量判断，本轮明确没做。
3. Q4_1 与 Q8_0 的取舍：本轮只看到 Q8_0 预填更快、内存多约 394 MB，样本太少且机器有噪声，不下结论。
4. 移动端或 4 GB 内存设备的加载验证（本轮只有本机 16 GB）。

## 7. 文件清单与复跑命令

```
experiments/world-components/parallel/model_scout/
├── README.md                      # 本报告
├── sources/capture.mjs            # 抓官方来源
├── sources/capture.json           # 每个来源的 URL/状态/字节数/sha256
├── sources/heads.json             # 三个 GGUF 的官方 X-Linked-ETag / 大小
├── sources/*.body                 # 8 份原始响应字节
├── inputs/nv-move-1.prompt.txt    # 已登记的固定输入（275 字）
├── run/probe.mjs                  # 浏览器最小运行探针
├── evidence/probe-Q4_1-ctx2048-r2.json
├── evidence/probe-Q4_1-ctx2048-pagekw.json
├── evidence/probe-Q4_1-ctx4096-pagekw.json
├── evidence/probe-Q8_0-ctx2048.json
├── evidence/control-qwen3-0.6b.json
├── evidence/summarize.mjs         # 从原始运行生成汇总
├── evidence/summary.json|md       # 汇总表
└── evidence/outputs.txt           # 提示词 + 每次原始输出
```

复跑（在本目录、已 `npm ci` 过 `frontend/` 的前提下）：

```bash
node sources/capture.mjs
node run/probe.mjs --model D:/others/Jity/.local/models/MNN-Pocket-0.3B-Instruct-Q4_1.gguf \
  --n-ctx 2048 --chat-kwargs '{"enable_thinking":false}' \
  --out evidence/probe-Q4_1-ctx2048-pagekw.json
# 叙事评测脚本同配置：把 --n-ctx 改成 4096，输出文件名改成 probe-Q4_1-ctx4096-pagekw.json
node evidence/summarize.mjs
```

权重不在 git 里（`.local/models/` 被忽略）；重新下载后按 §1.2 的 sha256 核对，不一致就不要用。
