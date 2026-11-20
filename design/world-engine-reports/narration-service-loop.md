# 固定版本的真实产品闭环：页面 → 常驻 u240（2026-11-04）

独立本地常驻服务 + 页面代理接入，模型与编辑规则一律没改。这一轮交付的是**实测链路**和它的已知缺陷，不是质量结论。

## 1. 接法

| 环节 | 位置 | 说明 |
| --- | --- | --- |
| 常驻服务 | `narration_service.py`，`127.0.0.1:8031` | 启动时加载 u240 一次，串行处理请求 |
| 页面 | `/narration`（Next.js） | 通过 dev 代理 `/narration-api/*` → `127.0.0.1:8031/*`，不碰 world 协议 |
| 复用 | `fact_contract` 序列化、回合里自带的权威授权结果、`n4_pipeline.two_layer_edit` | 没有另写事实拼接或关系判断 |

接口：

- `POST /rounds/{id}?budget=20[&forceTimeout=f3]` —— 整回合；
- `POST /fact` —— 单事实调试；
- `GET /health`、`GET /rounds`、`GET /rounds/{id}`。

返回里带：`requestId`、`facts`（事实引用：factId/name/kind/text/pointId/evidenceId）、`generation`（逐条完成状态与耗时）、`original`、`edited`、`edit`（blocks/mergeOps/connectorOps/回退）、`authorization`、`components`、`timing`、`quality`。

## 2. 验收结果（真实无头 Edge，页面 `/narration`）

| 轮次 | 浏览器：点击→正文渲染 | 服务端合计 | 剩余开销 | 状态 |
| --- | --- | --- | --- | --- |
| 冷请求 | **2137 ms** | 2079 ms（生成 2.079 + 编辑 0.00006） | **43 ms** | 完成 |
| 热请求 | **2010 ms** | 1974 ms | **26 ms** | 完成 |
| 单端点超时（f3） | **1671 ms** | 1634 ms | **27 ms** | **未完成（缺 f3）** |
| 整回合超时（预算 0.05s） | **392 ms** | 355 ms | **27 ms** | **未完成（缺 f0–f4）** |

- **服务冷启动**（加载 297 MB 检查点 + 初始化）：**0.289 s**（CPU）。
- 浏览器总耗时与服务端耗时**分开报**；两者差的 26–43 ms 只能叫**剩余开销**（含代理转发、JSON 序列化、React 渲染），不等于网络耗时。
- 单句生成在 CPU 上 0.35–0.5 s，整回合（5 条）稳定在 2.0 s 左右，热请求没有明显下降——瓶颈是 CPU 推理本身，不是加载。

## 3. 四条验收项

| 验收 | 结果 |
| --- | --- |
| 真实已提交回合从页面走通、能看原稿与编辑稿 | 通过：原稿逐条显示，编辑稿含合并与“随后” |
| 已知重复缺陷如实保留 | 通过：`沈砚的指节发白，指节发白。` 原样显示，`质量` 栏仍是“未核验”，只在“自动重复提示”里标 `f1` |
| 未授权关系不产生连接 | 通过：`mixed-round` 的授权结论是 `partial`（`f5→f4` 被拒），编辑只连了 `f2→f3` 一处 |
| 超时显示未完成、缺失端点的连接被取消 | 通过：`forceTimeout=f3` 时页面顶部显示“未完成（缺 f3）”，正文里**没有“随后”**；整回合 0.05s 预算时显示“未完成（缺 f0–f4）” |

`forceTimeout` 是调试参数，只让指定事实用极小预算，用来稳定复现“单端点缺失”，不参与正式判定。

## 4. 这一轮暴露的缺陷（如实记录，未修）

1. **重复没有被处理**：`指节发白，指节发白` 仍然出现在正文里。页面只把它标成提示。
2. **缺失单元会留下悬空标点**：`forceTimeout=f3` 时编辑稿是
   `…顾行舟的斗篷下摆湿了一片。，袖口湿到肘部。`
   —— 空句被合并时留下了孤立的逗号。
3. **整回合超时的正文是 `。。。。。`**：五条都超时后，编辑层把五个空句拼在一起。
4. 页面只显示“生成完成／未完成”，没有把任何一档标成“质量合格”，符合约定。

## 5. 没做的事

- 没有改模型、没有改编辑规则、没有做延迟优化；
- 没有跑并发（服务刻意串行，页面在请求期间显示“处理中…”并且按钮禁用）；
- 没有把服务挂到 world 路由，也没有动 world 协议与事实契约；
- 单事实接口只用于调试，跨事实的合并与“随后”只在整回合接口里发生。

## 6. 复现方式

```bash
# 服务（模型与回合数据都在本地）
python narration_service.py --model <u240 目录> --rounds artifacts/world-provenance --port 8031
# 页面
cd frontend && npx next dev -p 3100   # 打开 /narration
# 驱动脚本（无头 Edge，四次点击）
node artifacts/world-provenance/drive-narration-page.cjs
```

## 7. 交付物

> 本阶段已冻结：u240、常驻服务、两层编辑与页面链路不再改动；质量仍未核验，已知重复保留。未完成回合的装配见 `incomplete-round-assembly.md`。

- 服务：`experiments/world-components/n4_narrative_dev/narration_service.py`
- 页面：`frontend/src/app/narration/page.tsx`、`frontend/next.config.ts`（新增 `/narration-api` 代理）
- 实测记录：`artifacts/world-provenance/narration-page.json`（四轮点击的原始读数）
- 驱动脚本：`artifacts/world-provenance/drive-narration-page.cjs`
- 本地模型：`.local/models/`（`model.safetensors` 297 MB + tokenizer），CPU 运行
