# E25 真机：单引擎 0.6B + CPU 的两回合

**Question.** 红米 K70E（Mali G615 / Dimensity 8300）的 Chrome 上，浏览器本地
内核能否完成两回合、计时多少；WebGPU 与 CPU 两条路各自死在哪。

**Setup.** 手机 Chrome 158（Android UA），8 核、`navigator.deviceMemory` 8、
WebGPU 适配器 `arm valhall`；`next start` on 3177 经自签 HTTPS 前置
（`scripts/phone-https-proxy.mjs`），无线 adb + CDP 驱动。URL
`?cpu=1&narrationModel=semantic`：单 0.6B 引擎兼语义与叙事，GPU 层 0。
证据 `artifacts/goal/micro-workflow/evidence-phone-5.json`，日志
`frontend/phone-play12.log`。

**基础设施结论（都是这次踩出来的）.**
- 明文 HTTP 没安全上下文：wllama CacheManager 抛 `No supported storage
  backend found`，引擎根本起不来；必须 HTTPS（D-132）。
- CDP 的证书豁免随会话失效：驱动一断开，页面所有 fetch 报 `Failed to
  fetch`；自动化驱动必须整程持有一条 CDP 会话。
- 3177 是 `next start`（生产包）：源码改动不 rebuild+restart 不会上手机。
  此前两次"CPU 模式"实际是旧包 WebGPU 路径，计时作废（旧包 1.7B 双引擎在
  生成时 `wllama has crashed`，复现 2 次）。

**Results.**
- 引擎加载 26.8 s（fetch 18.6 + compile 8.0；Cache API 未命中，caches 为空，
  走了网络重下 396 MB）。
- 回合 1：总 25.2 s，首个可读正文 10.3 s，246 字，来源 model，微模型 0 行。
- 回合 2：总 193.3 s，首段 91.8 s，131 字，来源 model，微模型 23 行、语义
  调用 1 次；295 s 时限停掉后续自动回合，已接受正文保留。
- 两回合的引擎记录都是 `gpuLayers: 0`（真 CPU）。

**Quality note.** 0.6B 叙事偏清单化（"屋里有路明非的护目镜，镜片无裂纹…"），
明显低于 1.7B LoRA 默认臂；它是评估臂，不是发布默认（G6 不变）。

**Conditions.** 单设备、单存档（存档里还留着更早的失败回合条目）；LAN 自签
HTTPS；每回合一次。不是五臂对比，不含质量评分。

**Principle.** 手机至少有一条能跑通的配置：单引擎 0.6B + CPU，短结算回合
25 s 达标（首段 10.3 s），带语义 LLM 调用的回合 193 s（首段 91.8 s）。没有
WebGPU 时移动档 60 s 门槛不成立；GPU 稳定性是下一道前置门槛（D-133）。

**Artifacts.** `evidence-phone-5.json`、`phone-play12.log`、D-131..D-133。

**GPU follow-up (same session).** 同一单引擎 0.6B 去掉 `?cpu=1`（Mali
WebGPU，gpuLayers 99999，加载 61 s，进度条 64%→100% 正常）：worker 不再崩，
但回合 1 以 `fix_request:request_malformed` 停止（语义输出连续两轮未过校验），
回合 2 以 `narration_failed` 在 13.3 s 停止。证据
`evidence-phone-6.json`。结论：Mali 的 WebGPU 计算路径不可信；手机默认改为
CPU + 单 0.6B（`?cpu=0` 可强制 GPU 做实验），桌面默认不变。
