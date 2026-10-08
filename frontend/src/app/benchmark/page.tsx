"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { collectEnvironment } from "@/lib/benchmark/environment";
import {
  runAbortTest,
  runDecodeMatrix,
  runExit,
  runLoadFromBlobs,
  runLoadFromUrl,
  runPrefillMatrix,
  type RunnerHooks,
} from "@/lib/benchmark/runner";
import {
  DEFAULT_CONFIG,
  validCombos,
  type BenchmarkConfig,
  type EnvironmentInfo,
  type RunRecord,
  type RuntimeInfo,
  type Suite,
} from "@/lib/benchmark/types";
import { createWllama } from "@/lib/benchmark/wllama-loader";

type Phase = "idle" | "loading" | "ready" | "running" | "exited";

function formatMs(value?: number): string {
  return value != null ? `${value.toLocaleString()} ms` : "—";
}

/** Projected wall time for a realistic narration call at measured rates. */
function projectCall(record: RunRecord, inputTokens: number, outputTokens: number): number | undefined {
  const promptRate = record.promptPerSecond;
  const decodeRate = record.predictedPerSecond;
  if (!promptRate || !decodeRate) return undefined;
  return Math.round((inputTokens / promptRate + outputTokens / decodeRate) * 1000);
}

export default function BenchmarkPage() {
  const [environment, setEnvironment] = useState<EnvironmentInfo | null>(null);
  const [config, setConfig] = useState<BenchmarkConfig>(DEFAULT_CONFIG);
  const [phase, setPhase] = useState<Phase>("idle");
  const [status, setStatus] = useState("选择一个 GGUF 模型文件开始。");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [modelUrl, setModelUrl] = useState("");
  const stopRef = useRef(false);
  const wllamaRef = useRef<import("@wllama/wllama").Wllama | null>(null);

  useEffect(() => {
    setEnvironment(collectEnvironment());
    return () => {
      wllamaRef.current?.exit().catch(() => undefined);
    };
  }, []);

  const suite: Suite = useMemo(
    () => ({ environment: environment ?? ({} as EnvironmentInfo), runtime, config, runs }),
    [environment, runtime, config, runs],
  );

  const combos = useMemo(() => validCombos(config), [config]);

  function updateConfig(patch: Partial<BenchmarkConfig>) {
    setConfig((current) => ({ ...current, ...patch }));
  }

  async function ensureWllama() {
    if (wllamaRef.current) return wllamaRef.current;
    const instance = await createWllama();
    wllamaRef.current = instance;
    return instance;
  }

  function hooks(): RunnerHooks {
    return {
      onStatus: setStatus,
      onRun: (record) => {
        setRuns((current) => [...current, record]);
        const parts = [`${record.label}: ${formatMs(record.wallMs)}`];
        if (record.promptPerSecond) parts.push(`prefill ${record.promptPerSecond.toFixed(1)} tok/s`);
        if (record.predictedPerSecond) parts.push(`decode ${record.predictedPerSecond.toFixed(1)} tok/s`);
        if (record.error) parts.push(`错误: ${record.error}`);
        setStatus(parts.join(" · "));
      },
      shouldStop: () => stopRef.current,
    };
  }

  async function handleLoadFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    stopRef.current = false;
    setPhase("loading");
    setRuns([]);
    setRuntime(null);
    setStatus(`加载 ${files.length} 个模型文件（共 ${(files[0].size / 1048576).toFixed(0)} MB）…`);
    try {
      const wllama = await ensureWllama();
      const info = await runLoadFromBlobs(
        wllama,
        Array.from(files),
        files[0].name,
        config,
        hooks(),
      );
      setRuntime(info);
      setPhase("ready");
      setStatus(`模型已加载：${files[0].name} · ${info.numThreads} 线程 · ctx ${info.nCtx}`);
    } catch (error) {
      setPhase("idle");
      setStatus(`加载失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function handleLoadUrl() {
    if (!modelUrl.trim()) return;
    stopRef.current = false;
    setPhase("loading");
    setRuns([]);
    setRuntime(null);
    try {
      const wllama = await ensureWllama();
      const info = await runLoadFromUrl(wllama, modelUrl.trim(), config, hooks());
      setRuntime(info);
      setPhase("ready");
      setStatus(`模型已加载：${modelUrl} · ${info.numThreads} 线程 · ctx ${info.nCtx}`);
    } catch (error) {
      setPhase("idle");
      setStatus(`加载失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function handleRunSuite() {
    if (!wllamaRef.current) return;
    stopRef.current = false;
    setPhase("running");
    setRuns([]);
    const runnerHooks = hooks();
    try {
      setStatus("运行 prefill 档位矩阵…");
      await runPrefillMatrix(wllamaRef.current, config, runnerHooks);
      setStatus("运行 decode 基准…");
      await runDecodeMatrix(wllamaRef.current, config, runnerHooks);
      setStatus("运行中断测试…");
      await runAbortTest(wllamaRef.current, config, runnerHooks, 1500);
      setStatus("套件完成。");
    } catch (error) {
      setStatus(`套件中断：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setPhase("ready");
    }
  }

  async function handleExit() {
    if (!wllamaRef.current) return;
    stopRef.current = false;
    await runExit(wllamaRef.current, hooks());
    wllamaRef.current = null;
    setPhase("exited");
    setRuntime(null);
    setStatus("模型已卸载。");
  }

  function exportJson() {
    const payload: Suite = { ...suite, finishedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `inference-benchmark-${new Date().toISOString().slice(0, 19).replaceAll(":", "")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const decodeRef = runs.find((run) => run.kind === "decode" && run.promptPerSecond);

  return (
    <div className="bench-page">
      <div className="bench-header">
        <h1 className="bench-title">端侧推理基准 · wllama CPU 路径</h1>
        <Link className="bench-back" href="/">← 返回控制台</Link>
      </div>
      <p className="bench-intro">
        测量模型加载、输入处理（prefill）、文本生成（decode）、中断与内存。prefill/decode
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
            <div>wasm SIMD：{environment.wasmSimd ? "支持" : "不支持"} · wasm 线程：{environment.wasmThreadsPossible ? "支持" : "不支持"}</div>
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
        {runtime ? (
          <div className="bench-meta">
            <div>
              模型：{runtime.sourceLabel}
              {runtime.sourceBytes ? ` · ${(runtime.sourceBytes / 1048576).toFixed(0)} MB` : ""}
            </div>
            <div>
              运行时：{runtime.multithread ? "多线程" : "单线程"} · {runtime.numThreads} 线程 ·
              libllama {runtime.libllamaVersion} · 实际 n_ctx {runtime.nCtx}（训练 {runtime.nCtxTrain}）
            </div>
            <div>
              结构：n_vocab={runtime.nVocab} · n_embd={runtime.nEmbd} · n_layer={runtime.nLayer}
            </div>
            <div className="bench-dim">
              {Object.entries(runtime.generalMeta).map(([key, value]) => `${key}=${value}`).join(" · ")}
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
            <input
              checked={config.chatReference}
              disabled={phase === "running"}
              onChange={(event) => updateConfig({ chatReference: event.target.checked })}
              type="checkbox"
            />
            chat 模板对照
          </label>
        </div>
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
            <button className="bench-button" onClick={() => { stopRef.current = true; }} type="button">
              停止
            </button>
          ) : null}
          <button className="bench-button" disabled={phase !== "ready" && phase !== "exited"} onClick={handleExit} type="button">
            卸载模型
          </button>
          <button className="bench-button" disabled={runs.length === 0} onClick={exportJson} type="button">
            导出 JSON 报告
          </button>
        </div>
        <p className="bench-status">{status}</p>
      </section>

      <section className="bench-panel">
        <h2 className="bench-panel-title">3 · 结果</h2>
        {runs.length === 0 ? (
          <p className="bench-dim">尚无记录。</p>
        ) : (
          <table className="bench-table">
            <thead>
              <tr>
                <th>项目</th>
                <th>实测输入 tok</th>
                <th>prefill</th>
                <th>生成 tok</th>
                <th>decode</th>
                <th>wall</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
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
                  <td className={run.error ? "bench-error" : "bench-dim"}>
                    {run.error
                      ?? (run.kind === "abort"
                        ? `取消前 ${run.tokensBeforeAbort ?? 0} tok · 停机 ${formatMs(run.stopLatencyMs)}`
                        : run.cachedTokens
                          ? `缓存命中 ${run.cachedTokens}`
                          : "")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {decodeRef && decodeRef.promptPerSecond && decodeRef.predictedPerSecond ? (
          <div className="bench-meta">
            <strong>对照 4 秒目标（含输入处理 + 生成的投影）：</strong>
            {[512, 1024, 2048].map((inputTokens) => {
              const projected = projectCall(decodeRef, inputTokens, 512);
              return (
                <div key={inputTokens}>
                  {inputTokens} tok 输入 + 512 tok 叙事 ≈{" "}
                  <strong className={projected != null && projected <= 4000 ? "bench-good" : "bench-bad"}>
                    {formatMs(projected)}
                  </strong>{" "}
                  （≤4000ms 为满足）
                </div>
              );
            })}
            <div className="bench-note">
              投影基于最大档位一组的实测速率；真实叙事输出契约约为 500–1200 token。
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
