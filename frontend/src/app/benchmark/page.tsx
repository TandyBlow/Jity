"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { collectEnvironment } from "@/lib/benchmark/environment";
import {
  ACCEPT_TARGET_MS,
  runAbortTests,
  runDecodeMatrix,
  runExit,
  runLoadFromBlobs,
  runLoadFromUrl,
  runMemoryCheckpoint,
  runPrefillMatrix,
  runAcceptMatrix,
  type RunnerHooks,
} from "@/lib/benchmark/runner";
import {
  DEFAULT_CONFIG,
  validCombos,
  type BenchmarkConfig,
  type EnvironmentInfo,
  type ExportPayload,
  type RunRecord,
  type RuntimeInfo,
  type SuiteRecord,
} from "@/lib/benchmark/types";
import { createWllama } from "@/lib/benchmark/wllama-loader";

type Phase = "idle" | "loading" | "ready" | "running" | "exited";

function formatMs(value?: number): string {
  return value != null ? `${value.toLocaleString()} ms` : "—";
}

export default function BenchmarkPage() {
  const [environment, setEnvironment] = useState<EnvironmentInfo | null>(null);
  const [config, setConfig] = useState<BenchmarkConfig>(DEFAULT_CONFIG);
  const [phase, setPhase] = useState<Phase>("idle");
  const [status, setStatus] = useState("选择一个 GGUF 模型文件开始。");
  const [suites, setSuites] = useState<SuiteRecord[]>([]);
  const [model, setModel] = useState<RuntimeInfo | null>(null);
  const [modelUrl, setModelUrl] = useState("");
  const stopRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const wllamaRef = useRef<import("@wllama/wllama").Wllama | null>(null);
  const suiteCounterRef = useRef(0);

  useEffect(() => {
    setEnvironment(collectEnvironment());
    return () => {
      wllamaRef.current?.exit().catch(() => undefined);
    };
  }, []);

  const combos = useMemo(() => validCombos(config), [config]);
  const allRuns = useMemo(
    () => suites.flatMap((suite) => suite.runs.map((run) => ({ suite, run }))),
    [suites],
  );

  // n_ctx / threads only take effect at load time; surface divergence.
  const loadMismatch = model
    && (model.loadParams.n_ctx !== config.nCtx || model.loadParams.n_threads !== config.nThreads);

  function updateConfig(patch: Partial<BenchmarkConfig>) {
    setConfig((current) => ({ ...current, ...patch }));
  }

  async function ensureWllama() {
    if (wllamaRef.current) return wllamaRef.current;
    const instance = await createWllama();
    wllamaRef.current = instance;
    return instance;
  }

  function beginSuite(): SuiteRecord {
    suiteCounterRef.current += 1;
    return {
      id: `suite-${suiteCounterRef.current}-${Date.now()}`,
      label: `套件 ${suiteCounterRef.current}`,
      startedAt: new Date().toISOString(),
      config: { ...config },
      // Full snapshot: after a model switch, older suites must still carry
      // their own quant metadata, runtime version and load params.
      model: model
        ? { ...model, generalMeta: { ...model.generalMeta }, loadParams: { ...model.loadParams } }
        : null,
      modelLabel: model?.sourceLabel ?? null,
      runs: [],
    };
  }

  function hooksFor(suite: SuiteRecord, collected?: RunRecord[]): RunnerHooks {
    return {
      onStatus: setStatus,
      onRun: (record: RunRecord) => {
        record.suiteId = suite.id;
        collected?.push(record);
        setSuites((current) =>
          current.map((item) =>
            item.id === suite.id ? { ...item, runs: [...item.runs, record] } : item,
          ),
        );
        const parts = [`${record.label}: ${formatMs(record.wallMs)}`];
        if (record.promptPerSecond) parts.push(`prefill ${record.promptPerSecond.toFixed(1)} tok/s`);
        if (record.predictedPerSecond) parts.push(`decode ${record.predictedPerSecond.toFixed(1)} tok/s`);
        if (record.withinTarget != null) {
          parts.push(record.withinTarget ? "≤4s ✓" : ">4s ✗");
        }
        if (record.error) parts.push(record.error);
        setStatus(parts.join(" · "));
      },
      shouldStop: () => stopRef.current,
      onController: (controller) => {
        abortRef.current = controller;
      },
    };
  }

  async function handleLoadFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    stopRef.current = false;
    setPhase("loading");
    setStatus(`加载 ${files.length} 个模型文件（共 ${(files[0].size / 1048576).toFixed(0)} MB）…`);
    try {
      const wllama = await ensureWllama();
      const info = await runLoadFromBlobs(
        wllama,
        Array.from(files),
        files[0].name,
        config,
        hooksForLoad(),
      );
      setModel(info);
      setPhase("ready");
      setStatus(`模型已加载：${files[0].name} · ${info.numThreads} 线程 · ctx ${info.nCtx}`);
      await runMemoryCheckpoint("加载后内存采样", hooksForLoad());
    } catch (error) {
      setPhase("idle");
      setStatus(`加载失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function handleLoadUrl() {
    if (!modelUrl.trim()) return;
    stopRef.current = false;
    setPhase("loading");
    try {
      const wllama = await ensureWllama();
      const info = await runLoadFromUrl(wllama, modelUrl.trim(), config, hooksForLoad());
      setModel(info);
      setPhase("ready");
      setStatus(`模型已加载：${modelUrl} · ${info.numThreads} 线程 · ctx ${info.nCtx}`);
      await runMemoryCheckpoint("加载后内存采样", hooksForLoad());
    } catch (error) {
      setPhase("idle");
      setStatus(`加载失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /** Load-time checkpoints belong to no suite; they append to a scratch one. */
  function hooksForLoad(): RunnerHooks {
    return {
      onStatus: setStatus,
      onRun: (record) => {
        setSuites((current) => {
          const scratch = current.find((suite) => suite.id === "checkpoints");
          if (scratch) {
            return current.map((suite) =>
              suite.id === "checkpoints" ? { ...suite, runs: [...suite.runs, record] } : suite,
            );
          }
          return [
            ...current,
            {
              id: "checkpoints",
              label: "检查点",
              startedAt: record.startedAt,
              config: { ...config },
              model: null,
              modelLabel: null,
              runs: [record],
            },
          ];
        });
      },
      shouldStop: () => stopRef.current,
      onController: (controller) => {
        abortRef.current = controller;
      },
    };
  }

  async function handleRunSuite() {
    if (!wllamaRef.current) return;
    stopRef.current = false;
    setPhase("running");
    const suite = beginSuite();
    const localRuns: RunRecord[] = [];
    setSuites((current) => [...current, suite]);
    const runnerHooks = hooksFor(suite, localRuns);
    try {
      setStatus("运行 prefill 档位矩阵…");
      const charRatio = await runPrefillMatrix(wllamaRef.current, config, runnerHooks);

      setStatus("运行 decode 基准…");
      await runDecodeMatrix(wllamaRef.current, config, charRatio, runnerHooks);

      if (config.acceptEnabled) {
        setStatus("运行 4 秒实测（每组合完整调用）…");
        await runAcceptMatrix(wllamaRef.current, config, charRatio, runnerHooks);
      }

      setStatus("运行中断测试…");
      // localRuns mirrors what the suite collected; the immutable state array
      // is not readable back synchronously.
      const prefillRef = localRuns.find(
        (run) => run.kind === "prefill" && run.promptPerSecond,
      );
      const decodeMs = prefillRef?.promptPerSecond
        ? Math.round(((prefillRef.promptTokens ?? 0) / prefillRef.promptPerSecond) * 1000) + 400
        : null;
      await runAbortTests(wllamaRef.current, config, charRatio, runnerHooks, {
        shortMs: 200,
        decodeMs,
      });

      await runMemoryCheckpoint("套件后内存采样", runnerHooks);
      setStatus(stopRef.current ? "套件被手动停止。" : "套件完成。");
    } catch (error) {
      setStatus(`套件中断：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSuites((current) =>
        current.map((item) =>
          item.id === suite.id ? { ...item, finishedAt: new Date().toISOString() } : item,
        ),
      );
      abortRef.current = null;
      setPhase("ready");
    }
  }

  async function handleExit() {
    if (!wllamaRef.current) return;
    stopRef.current = false;
    // model intentionally kept: the report must retain what was measured.
    await runExit(wllamaRef.current, hooksForLoad());
    await runMemoryCheckpoint("卸载后内存采样", hooksForLoad());
    wllamaRef.current = null;
    setPhase("exited");
    setStatus("模型已卸载；报告中的模型信息与历史套件保留。");
  }

  function handleStop() {
    stopRef.current = true;
    abortRef.current?.abort();
  }

  function clearHistory() {
    setSuites([]);
    suiteCounterRef.current = 0;
  }

  function exportJson() {
    const payload: ExportPayload = {
      environment: environment ?? ({} as EnvironmentInfo),
      model,
      suites,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `inference-benchmark-${new Date().toISOString().slice(0, 19).replaceAll(":", "")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const decodeRef = allRuns.find(
    ({ run }) => run.kind === "decode" && run.promptPerSecond,
  )?.run;

  return (
    <div className="bench-page">
      <div className="bench-header">
        <h1 className="bench-title">端侧推理基准 · wllama CPU 路径</h1>
        <Link className="bench-back" href="/">← 返回控制台</Link>
      </div>
      <p className="bench-intro">
        测量模型加载、输入处理（prefill）、文本生成（decode）、4 秒实测、中断与内存。prefill/decode
        取自 llama.cpp 自带计时；wall 时钟含分词、采样与 worker 往返，两者都会记录。
      </p>

      <section className="bench-panel">
        <h2 className="bench-panel-title">环境</h2>
        {environment ? (
          <div className="bench-meta">
            <div>CPU 线程（hardwareConcurrency）：{environment.hardwareConcurrency ?? "未知"}</div>
            <div>设备内存（deviceMemory）：{environment.deviceMemoryGB ? `${environment.deviceMemoryGB} GB（粗档）` : "不可用"}</div>
            <div>
              跨源隔离：{environment.crossOriginIsolated ? "是（多线程可用）" : "否——将回退单线程，结果偏低"}
            </div>
            <div>WebGPU 暴露：{environment.webgpuExposed ? "是（本基准强制 n_gpu_layers=0，走 CPU）" : "否"}</div>
            <div>
              wasm SIMD：{environment.wasmSimd ? "支持" : "不支持"} · wasm 线程检测：{environment.wasmThreadsPossible ? "支持" : "不支持"}
              {model ? (
                <>
                  {" "}· 实际运行：{model.multithread ? "多线程" : "单线程"}（{model.numThreads} 线程）
                  {environment.wasmThreadsPossible && !model.multithread
                    ? "——检测支持但未启用，检查 COOP/COEP 隔离头"
                    : ""}
                  {!environment.wasmThreadsPossible && model.multithread
                    ? "——检测与实际不符，以实际为准"
                    : ""}
                </>
              ) : (
                "（加载模型后与实际线程交叉核对）"
              )}
            </div>
            <div className="bench-dim">{environment.userAgent}</div>
          </div>
        ) : (
          <p className="bench-dim">读取中…</p>
        )}
      </section>

      <section className="bench-panel">
        <h2 className="bench-panel-title">1 · 模型</h2>
        <div className="bench-row">
          <input
            accept=".gguf"
            disabled={phase === "loading" || phase === "running"}
            multiple
            onChange={(event) => handleLoadFiles(event.target.files)}
            type="file"
          />
          <span className="bench-dim">
            推荐：Qwen3-0.6B GGUF Q4_K_M；小模型冒烟测试可用 stories260K。
          </span>
        </div>
        <div className="bench-row">
          <input
            className="bench-input bench-input-wide"
            onChange={(event) => setModelUrl(event.target.value)}
            placeholder="或输入模型 URL（同源 /models/xxx.gguf 最稳；远端需 CORS）"
            value={modelUrl}
          />
          <button className="bench-button" disabled={phase === "loading" || phase === "running" || !modelUrl.trim()} onClick={handleLoadUrl} type="button">
            从 URL 加载
          </button>
        </div>
        {model ? (
          <div className="bench-meta">
            <div>
              模型：{model.sourceLabel}
              {model.sourceBytes ? ` · ${(model.sourceBytes / 1048576).toFixed(0)} MB` : ""}
              {phase === "exited" ? "（已卸载，信息保留在报告中）" : ""}
            </div>
            <div>
              运行时：{model.multithread ? "多线程" : "单线程"} · {model.numThreads} 线程 ·
              libllama {model.libllamaVersion} · 实际 n_ctx {model.nCtx}（训练 {model.nCtxTrain}）
              · 加载参数 n_batch {model.loadParams.n_batch} / n_ubatch {model.loadParams.n_ubatch}
            </div>
            <div>
              结构：n_vocab={model.nVocab} · n_embd={model.nEmbd} · n_layer={model.nLayer}
            </div>
            <div className="bench-dim">
              {Object.entries(model.generalMeta).map(([key, value]) => `${key}=${value}`).join(" · ")}
            </div>
          </div>
        ) : null}
      </section>

      <section className="bench-panel">
        <h2 className="bench-panel-title">2 · 档位与运行</h2>
        <div className="bench-config-row">
          <label>
            总输入 token：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({
                totalTokens: event.target.value.split(",").map((value) => parseInt(value.trim(), 10)).filter((value) => value > 0),
              })}
              value={config.totalTokens.join(",")}
            />
          </label>
          <label>
            记忆注入 token：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({
                memoryTokens: event.target.value.split(",").map((value) => parseInt(value.trim(), 10)).filter((value) => value > 0),
              })}
              value={config.memoryTokens.join(",")}
            />
          </label>
          <label>
            生成长度：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ decodeTokens: parseInt(event.target.value, 10) || 1 })}
              value={config.decodeTokens}
            />
          </label>
          <label>
            prefill 遍数：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ prefillRepeats: parseInt(event.target.value, 10) || 1 })}
              value={config.prefillRepeats}
            />
          </label>
          <label>
            n_ctx：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ nCtx: parseInt(event.target.value, 10) || 512 })}
              value={config.nCtx}
            />
          </label>
          <label>
            线程：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => {
                const value = parseInt(event.target.value, 10);
                updateConfig({ nThreads: value > 0 ? value : null });
              }}
              placeholder="默认"
              value={config.nThreads ?? ""}
            />
          </label>
          <label>
            n_batch：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ nBatch: parseInt(event.target.value, 10) || 2048 })}
              value={config.nBatch}
            />
          </label>
          <label>
            n_ubatch：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ nUbatch: parseInt(event.target.value, 10) || 512 })}
              value={config.nUbatch}
            />
          </label>
          <label>
            4s 生成 token：
            <input
              className="bench-input"
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ acceptOutputTokens: parseInt(event.target.value, 10) || 1 })}
              value={config.acceptOutputTokens}
            />
          </label>
          <label>
            <input
              checked={config.acceptEnabled}
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ acceptEnabled: event.target.checked })}
              type="checkbox"
            />
            4 秒实测（每组合完整调用，慢）
          </label>
          <label>
            <input
              checked={config.chatReference}
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ chatReference: event.target.checked })}
              type="checkbox"
            />
            chat 模板对照
          </label>
        </div>
        {loadMismatch ? (
          <p className="bench-note">
            注意：模型按加载时参数运行（n_ctx {model?.loadParams.n_ctx}
            · 线程 {model?.loadParams.n_threads ?? "默认"}）；修改 n_ctx/线程仅在下次加载后生效。
          </p>
        ) : null}
        <p className="bench-note">
          将运行 {combos.length} 个档位组合（记忆注入必须小于总输入，无效组合已跳过）：
          {combos.map((combo) => `${combo.total}/${combo.memory}`).join("、")}
        </p>
        <div className="bench-actions">
          <button
            className="primary-button fitted"
            disabled={phase !== "ready"}
            onClick={handleRunSuite}
            type="button"
          >
            {phase === "running" ? "运行中…" : "运行基准套件"}
          </button>
          {phase === "running" ? (
            <button className="bench-button" onClick={handleStop} type="button">
              停止（含中断当前推理）
            </button>
          ) : null}
          <button className="bench-button" disabled={phase !== "ready" && phase !== "exited"} onClick={handleExit} type="button">
            卸载模型
          </button>
          <button className="bench-button" disabled={allRuns.length === 0} onClick={exportJson} type="button">
            导出 JSON 报告
          </button>
          <button className="bench-button" disabled={suites.length === 0} onClick={clearHistory} type="button">
            清空记录
          </button>
        </div>
        <p className="bench-status">{status}</p>
      </section>

      <section className="bench-panel">
        <h2 className="bench-panel-title">3 · 结果（{suites.length} 个套件 / {allRuns.length} 条记录）</h2>
        {allRuns.length === 0 ? (
          <p className="bench-dim">尚无记录。</p>
        ) : (
          <table className="bench-table">
            <thead>
              <tr>
                <th>套件</th>
                <th>项目</th>
                <th>实测输入 tok</th>
                <th>prefill</th>
                <th>生成 tok</th>
                <th>decode</th>
                <th>wall</th>
                <th>4s</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {allRuns.map(({ suite, run }) => (
                <tr key={run.id}>
                  <td>{suite.label}</td>
                  <td>{run.label}</td>
                  <td>{run.promptTokens ?? "—"}</td>
                  <td>
                    {formatMs(run.promptMs)}{run.promptPerSecond ? ` · ${run.promptPerSecond.toFixed(1)}/s` : ""}
                  </td>
                  <td>{run.predictedTokens ?? "—"}</td>
                  <td>
                    {formatMs(run.predictedMs)}{run.predictedPerSecond ? ` · ${run.predictedPerSecond.toFixed(1)}/s` : ""}
                  </td>
                  <td>{formatMs(run.wallMs)}</td>
                  <td>
                    {run.kind === "accept"
                      ? run.withinTarget == null
                        ? "—"
                        : run.withinTarget
                          ? "✓"
                          : "✗"
                      : "—"}
                  </td>
                  <td className={run.error ? "bench-error" : "bench-dim"}>
                    {run.error
                      ?? (run.kind === "accept" && run.completedLoad === false
                        ? `提前结束 ${run.predictedTokens ?? 0}/${run.maxTokens ?? "?"} tok（${run.finishReason ?? "未知原因"}），未完成目标负载，不判达标`
                        : run.kind === "abort"
                          ? abortNote(run)
                          : run.kind === "memory"
                            ? memoryNote(run)
                            : run.cachedTokens
                              ? `缓存命中 ${run.cachedTokens}`
                              : "")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {decodeRef ? (
          <div className="bench-meta">
            <strong>参考投影（仅外推，非达标判断）：</strong>
            {[512, 1024, 2048].map((inputTokens) => {
              const promptRate = decodeRef.promptPerSecond;
              const decodeRate = decodeRef.predictedPerSecond;
              if (!promptRate || !decodeRate) return null;
              const projected = Math.round((inputTokens / promptRate + 512 / decodeRate) * 1000);
              return (
                <div key={inputTokens}>
                  {inputTokens} tok 输入 + 512 tok 叙事 ≈ {formatMs(projected)}（外推值）
                </div>
              );
            })}
            <div className="bench-note">
              达标判断以「4 秒实测」行的 ✓/✗ 为准（目标 {ACCEPT_TARGET_MS} ms，含实际输入处理与实际生成）。
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function abortNote(run: RunRecord): string {
  const outcome = run.abortOutcome;
  const parts: string[] = [];
  if (outcome === "cancelled") parts.push("按计划取消");
  if (outcome === "completed_early") parts.push("提前完成（未触及取消）");
  if (outcome === "context_overflow") parts.push("上下文超限");
  if (run.cancelledByUser) parts.push("用户停止");
  if (run.streamedChunks != null) {
    parts.push(`取消前 ${run.streamedChunks} 块 / ${run.generatedChars ?? 0} 字`);
  }
  if (run.abortPhase) parts.push(`落在${run.abortPhase === "prefill" ? "输入处理" : "生成"}阶段`);
  if (run.stopLatencyMs != null) parts.push(`停机 ${formatMs(run.stopLatencyMs)}`);
  return parts.join(" · ") || "";
}

function memoryNote(run: RunRecord): string {
  const memory = run.memory;
  if (!memory) return "";
  const parts: string[] = [];
  if (memory.preciseMB != null) parts.push(`全页 ${memory.preciseMB} MB`);
  if (memory.usedMB != null) parts.push(`JS 堆 ${memory.usedMB} MB`);
  if (memory.breakdownMB) {
    const webassembly = Object.entries(memory.breakdownMB)
      .filter(([key]) => /webassembly/i.test(key));
    if (webassembly.length) {
      parts.push(`WASM ${webassembly.map(([, value]) => `${value} MB`).join("/")}`);
    }
  }
  return parts.join(" · ") || "采样不可用";
}
