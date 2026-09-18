"use client";

import { Check, CircleAlert, Dices } from "lucide-react";
import { useState } from "react";

import { DiceCanvas } from "@/components/dice/DiceCanvas";
import { getOutcome, type CheckSpec, type Outcome } from "@/lib/dice/rules";

type CheckPhase = "prepared" | "rolling" | "docking" | "revealed";

export type MainCheckCommit = {
  roll: number;
  outcome: Outcome;
  degree: string;
};

type MainCheckOverlayProps = {
  action: string;
  check: CheckSpec;
  onCancel: () => void;
  onCommit: (result: MainCheckCommit) => Promise<void> | void;
};

export function MainCheckOverlay({ action, check, onCancel, onCommit }: MainCheckOverlayProps) {
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

  const isCritical = result?.outcome === "critical";
  const isFailure = result?.outcome === "failure" || result?.outcome === "fumble";
  // While the dice are in play the card stays wordless.
  const title = phase === "prepared" ? "确认行动判定" : phase === "revealed" ? "判定完成" : "";

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
            {title ? <h2>{title}</h2> : null}
          </div>
        </div>

        <p className="main-check-action">{action}</p>

        {phase === "prepared" ? (
          <>
            <div className="main-check-meta">
              <span><Dices size={15} />{check.skill} · {check.system}</span>
              <span>目标 ≥ {check.target}</span>
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

        {phase === "revealed" && result ? (
          <div className={`main-check-result ${isCritical ? "critical" : isFailure ? "failure" : "success"}`}>
            <div className="main-check-result-title">
              <Check size={17} />
              <strong>{result.degree}</strong>
            </div>
            <button
              className="primary-button main-check-primary"
              onClick={() => onCommit(result)}
              type="button"
            >
              继续
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
