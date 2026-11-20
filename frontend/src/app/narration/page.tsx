"use client";

/**
 * 本地常驻叙述服务的验收页。
 *
 * 只做三件事：把一个已提交回合发给服务、把返回的原稿/编辑稿显示出来、
 * 把「生成完成」与「质量未核验」分开显示。浏览器到正文渲染的总耗时在这里
 * 计时（点击 → 请求 → 渲染完成后的下一帧）。
 */
import { useCallback, useEffect, useRef, useState } from "react";

const API = "/narration-api";

type Fact = {
  factId: string;
  name: string;
  kind: string;
  text: string;
  pointId?: string;
  evidenceId?: string;
};

type Generation = {
  factId: string;
  name: string;
  factLine: string;
  complete: boolean;
  seconds: number;
};

type RoundResult = {
  requestId: string;
  service: string;
  components: Record<string, string>;
  worldId: string;
  facts: Fact[];
  generation: Generation[];
  sourceComplete: boolean;
  incompleteFacts: string[];
  original: string;
  edited: string;
  bodyEmpty: boolean;
  gaps: Array<{
    factId: string;
    name: string;
    position: number;
    reason: string;
    partial: string;
  }>;
  edit: {
    segments: Array<{ index: number; factIds: string[]; text: string }>;
    mergeOps: Array<Record<string, unknown>>;
    mergeDropped: Array<Record<string, unknown>>;
    connectorOps: Array<Record<string, unknown>>;
    connectorFallbacks: Array<Record<string, unknown>>;
  };
  authorization: { verdict: string; relations: Array<Record<string, unknown>> };
  quality: { status: string; repeatHints: string[]; note: string };
  timing: { assemble: number; generate: number; edit: number; serverTotal: number };
};

type Health = {
  ok: boolean;
  service: string;
  coldStartSeconds: number;
  device: string;
  rounds: string[];
};

export default function NarrationPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [roundId, setRoundId] = useState("train-r1");
  const budgetRef = useRef<HTMLInputElement | null>(null);
  const timeoutRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState<RoundResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [browserMs, setBrowserMs] = useState<number | null>(null);
  const [transportMs, setTransportMs] = useState<number | null>(null);
  const renderResolver = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setError("叙述服务未启动（127.0.0.1:8031）"));
  }, []);

  // 渲染结束后再记一次时间：点击 → 正文出现在页面上
  useEffect(() => {
    if (!round || !renderResolver.current) return;
    const done = renderResolver.current;
    renderResolver.current = null;
    const frame = requestAnimationFrame(() => {
      const started = Number(document.body.dataset.narrationStarted || "0");
      if (started) setBrowserMs(Math.round(performance.now() - started));
      done();
    });
    return () => cancelAnimationFrame(frame);
  }, [round]);

  const run = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setBrowserMs(null);
    setTransportMs(null);
    const started = performance.now();
    document.body.dataset.narrationStarted = String(started);
    await new Promise<void>((resolve) => {
      renderResolver.current = resolve;
      (async () => {
        try {
          // 非受控输入：点击时直接读 DOM，避免受控 state 与自动化脚本打架
          const budgetValue = budgetRef.current?.value || "20";
          const timeoutValue = (timeoutRef.current?.value || "").trim();
          const query = new URLSearchParams({ budget: budgetValue });
          if (timeoutValue) query.set("forceTimeout", timeoutValue);
          const response = await fetch(`${API}/rounds/${roundId}?${query.toString()}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: "{}",
          });
          setTransportMs(Math.round(performance.now() - started));
          if (!response.ok) throw new Error(`${response.status}`);
          setRound(await response.json());
        } catch (cause) {
          renderResolver.current = null;
          setError(String(cause));
        } finally {
          setBusy(false);
        }
      })();
    });
  }, [busy, roundId]);

  return (
    <main className="mx-auto max-w-4xl p-6 text-sm">
      <h1 className="text-xl font-semibold">叙述服务验收</h1>
      <p className="mt-1 text-neutral-500">
        服务：{health ? `${health.service}（${health.device}，冷启动 ${health.coldStartSeconds}s）` : "未连接"}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          className="rounded border px-2 py-1"
          value={roundId}
          onChange={(event) => setRoundId(event.target.value)}
        >
          {(health?.rounds ?? ["train-r1"]).map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <label className="flex items-center gap-2">
          预算(秒)
          <input
            ref={budgetRef}
            className="w-16 rounded border px-2 py-1"
            type="number"
            defaultValue={20}
            min={0.05}
            step={0.05}
          />
        </label>
        <label className="flex items-center gap-2">
          强制超时(事实ID)
          <input
            ref={timeoutRef}
            className="w-16 rounded border px-2 py-1"
            placeholder="f3"
            defaultValue=""
          />
        </label>
        <button
          className="rounded bg-neutral-900 px-3 py-1 text-white disabled:opacity-50"
          onClick={run}
          disabled={busy}
        >
          {busy ? "处理中…" : "生成"}
        </button>
      </div>

      {error && <p className="mt-3 text-red-600">{error}</p>}

      {round && (
        <section className="mt-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded border p-3">
              <div className="text-neutral-500">生成</div>
              <div className={round.sourceComplete ? "text-green-700" : "text-amber-700"}>
                {round.sourceComplete ? "完成" : `未完成（缺 ${round.incompleteFacts.join(", ")}）`}
              </div>
            </div>
            <div className="rounded border p-3">
              <div className="text-neutral-500">质量</div>
              <div className="text-amber-700">未核验</div>
              <div className="text-xs text-neutral-500">
                自动重复提示：{round.quality.repeatHints.length
                  ? round.quality.repeatHints.join(", ")
                  : "无"}
              </div>
            </div>
          </div>

          <div className="rounded border p-3">
            <div className="text-neutral-500">原稿（逐事实）</div>
            <div className="mt-1 space-y-1">
              {round.generation.map((item) => (
                <div key={item.factId}>
                  <span className="text-neutral-400">{item.name}</span>
                  <span className="ml-2">{item.text}</span>
                  <span className="ml-2 text-xs text-neutral-400">
                    {item.complete ? "" : "未完成"} {item.seconds}s
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded border p-3">
            <div className="text-neutral-500">编辑稿</div>
            {round.bodyEmpty ? (
              <div className="mt-1 text-base text-amber-700">本回合未生成完整正文</div>
            ) : (
              <div className="mt-1 text-base">{round.edited}</div>
            )}
            {round.gaps.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-amber-700">
                {round.gaps.map((gap) => (
                  <li key={gap.factId}>
                    缺口：{gap.factId}（{gap.name}，第 {gap.position} 位，
                    {gap.reason === "not-started"
                      ? "未启动"
                      : gap.reason === "timeout"
                        ? "超时"
                        : "空输出"}）
                    {gap.partial ? ` · 部分输出：${gap.partial}` : " · 无输出"}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-1 text-xs text-neutral-400">
              分段：{round.edit.segments.map((item) => item.factIds.join("+")).join(" ／ ") || "无"}
            </div>
          </div>

          <div className="rounded border p-3 text-xs text-neutral-600">
            <div>requestId: {round.requestId}</div>
            <div>授权：{round.authorization.verdict}，连接 {round.edit.connectorOps.length} 处</div>
            <div>
              耗时：生成 {round.timing.generate}s · 编辑 {round.timing.edit}s · 服务端合计{" "}
              {round.timing.serverTotal}s
            </div>
            <div>
              浏览器：请求返回 {transportMs ?? "-"}ms · 点击到渲染 {browserMs ?? "-"}ms
            </div>
            <div>
              剩余开销（浏览器总耗时 − 服务端合计）：
              {browserMs !== null && round.timing.serverTotal
                ? `${Math.round(browserMs - round.timing.serverTotal * 1000)}ms`
                : "-"}
            </div>
            <div className="mt-1">
              组件：{Object.entries(round.components).map(([k, v]) => `${k}=${v}`).join(" · ")}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
