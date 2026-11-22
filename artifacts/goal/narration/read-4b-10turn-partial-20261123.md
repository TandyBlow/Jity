# WebLLM 4B 十输入（部分，2026-11-23，run93）

## 状态

- 运行到 t4 后被宿主内存回收停止（系统通知：low memory，任务被 kill），状态 `IN_PROGRESS`，未自行重启。
- 页面 `runtime=webllm`、`webllmModel=Qwen3-4B-q4f16_1-MLC`、本地权重、持久 profile `edge-profile-4b-10turn`；`schedHandback=player&offscreenPolicy=skip&settlementUnknownRule=1`。
- 驱动 problems：t4 `accepted_over_60s`；其余 0。检查器 4 回合 0 命中。

## 正文

- t1：复述状态清单（护目镜/背心/赛区图/红痕）两遍；「看清规则牌」来自输入，不是结算。文风不合格（复述+重复）。
- t2：继续复述清单；「他走向林亦舟的位置」把未在场的林亦舟当作目标位置；状态里只有诺诺。位置/在场存疑。
- t3：结算只有诺诺修短讯机。正文「路明非蹲下问林亦舟脚踝」后「伸手摸了摸脚踝。林亦舟的脚踝有些肿」——把未结算的人物与伤情写进正文，硬错（4.2 未结算事件/在场）。
- t4：廊柱、蓝布带、林亦舟左脚踝与演习枪均为状态事实，正文基本忠实；「诺诺…嘴角微扬」来自结算。问题是整段复述清单。

## 判定

- 4B 基座没有消除复述（与 run83/84 一致），并出现未结算人物（t3）；不改变 D-022 的未通过判定。
- 本机 4B 连续回合仍受宿主内存限制：十输入未跑完，t4 已超 60 秒。
- 证据：`artifacts/goal/narration/run93-webllm-4b-10turn.json`（部分）、`prose-facts-check-run93-partial.json`。
