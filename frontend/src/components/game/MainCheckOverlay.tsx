"use client";

import { Check, CircleAlert, Dices, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { DiceCanvas } from "@/components/dice-demo/DiceCanvas";
import { getOutcome, type CheckSpec, type Outcome } from "@/components/dice-demo/dice-rules";

type CheckPhase = "prepared" | "rolling" | "docking" | "revealed";

export type MainCheckCommit = {
  roll: number;
  outcome: Outcome;
  degree: string;
};

type MainCheckOverlayProps = {
  action: string;
  check: CheckSpec;
  busy: boolean;
  onCancel: () => void;
  onCommit: (result: MainCheckCommit) => Promise<void> | void;
};

export function MainCheckOverlay({ action, check, busy, onCancel, onCommit }: MainCheckOverlayProps) {
  const [phase, setPhase] = useState<CheckPhase>("prepared");
  const [roll, setRoll] = useState<number | null>(null);
  const [result, setResult] = useState<MainCheckCommit | null>(null);
  const [error, setError] = useState("");

  function startRoll() {
    if (phase !== "prepared") return;
    setError("");
    setResult(null);
    setRoll(Math.floor(Math.random() * 20) + 1);
    setPhase("rolling");
  }

  function handleSettled() {
    setPhase((current) => (current === "rolling" ? "docking" : current));
  }

  function handleDocked() {
    if (roll === null) return;
    const evaluation = getOutcome(roll, check);
    setResult({ roll, outcome: evaluation.outcome, degree: evaluation.degree });
    setPhase("revealed");
  }

  function handleDiceError(message: string) {
    setError(message);
    setRoll(null);
    setResult(null);
    setPhase("prepared");
  }

  const canCancel = phase === "prepared" || phase === "revealed";
  const isCritical = result?.outcome === "critical";
  const isFailure = result?.outcome === "failure" || result?.outcome === "fumble";

  return (
    <section className="main-check-overlay" aria-label={`${check.name}：${action}`}>
      {roll !== null ? (
        <DiceCanvas
          value={roll}
          docking={phase === "docking" || phase === "revealed"}
          onSettled={handleSettled}
          onDocked={handleDocked}
          onError={handleDiceError}
        />
      ) : null}

      <div className="main-check-card">
        <div className="main-check-card-head">
          <div>
            <span className="main-check-overline">{check.name} · {check.expression}</span>
            <h2>{phase === "prepared" ? "确认行动判定" : phase === "rolling" ? "骰子滚动中" : phase === "docking" ? "结果确认中" : "判定完成"}</h2>
          </div>
          {canCancel ? (
            <button className="main-check-close" onClick={onCancel} type="button" aria-label="关闭判定">
              <X size={17} />
            </button>
          ) : (
            <span className="main-check-lock"><ShieldCheck size={14} />结果已锁定</span>
          )}
        </div>

        <p className="main-check-action">{action}</p>

        {phase === "prepared" ? (
          <>
            <div className="main-check-meta">
              <span><Dices size={15} />{check.skill} · {check.system}</span>
              <span>目标 ≤ {check.target}</span>
            </div>
            <p className="main-check-stakes">{check.stakes}</p>
            {error ? <p className="main-check-error"><CircleAlert size={15} />{error}</p> : null}
            <div className="main-check-actions">
              <button className="main-check-secondary" onClick={onCancel} type="button">返回</button>
              <button className="primary-button main-check-primary" onClick={startRoll} type="button">
                <Dices size={17} />掷骰
              </button>
            </div>
          </>
        ) : null}

        {phase === "rolling" ? <p className="main-check-status">物理骰子正在碰撞、翻滚并寻找停面…</p> : null}
        {phase === "docking" ? <p className="main-check-status">骰面已停下，正在滑入结果位置…</p> : null}

        {phase === "revealed" && result ? (
          <div className={`main-check-result ${isCritical ? "critical" : isFailure ? "failure" : "success"}`}>
            <div className="main-check-result-title">
              <Check size={17} />
              <strong>{result.degree}</strong>
            </div>
            <p>骰面上的数字就是本次行动判定结果。</p>
            <button
              className="primary-button main-check-primary"
              disabled={busy}
              onClick={() => onCommit(result)}
              type="button"
            >
              {busy ? "提交剧情中" : "应用结果并继续"}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
