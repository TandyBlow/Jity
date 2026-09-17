"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Dices,
  Eye,
  Footprints,
  History,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  MapPin,
  PenTool,
} from "lucide-react";
import { DiceCanvas } from "@/components/dice-demo/DiceCanvas";
import { defineCheck, getOutcome, type CheckSpec, type Outcome } from "@/components/dice-demo/dice-rules";

type Phase = "idle" | "prepared" | "rolling" | "docking" | "revealed" | "resolved";
type ActionId = "inspect" | "observe" | "leave" | "follow" | "take" | "return" | "retry";

type Scene = {
  chapter: string;
  location: string;
  title: string;
  narration: string;
  dialogue?: { speaker: string; text: string }[];
  options: ActionId[];
};

type DemoAction = {
  id: ActionId;
  label: string;
  hint: string;
  check?: CheckSpec;
  directScene?: Scene;
};

type DemoResult = {
  actionLabel: string;
  spec: CheckSpec;
  roll: number;
  outcome: Outcome;
  degree: string;
  delta: Delta;
};

type Delta = {
  sanity: number;
  health: number;
  clues: number;
  minutes: number;
  danger: number;
};

type JournalEntry = {
  label: string;
  detail: string;
  kind: "action" | "check" | "roll" | "result" | "commit";
};

const INITIAL_SCENE: Scene = {
  chapter: "第一幕 · 雨中的访客",
  location: "卡塞尔学院 · 档案室外",
  title: "门后的刮擦声",
  narration:
    "雨水顺着窗框流进走廊。你在档案室门口停下，听见门后传来一下极轻的刮擦声。门缝里没有灯光，只有一股潮湿的纸张气味。",
  dialogue: [{ speaker: "陌生女孩", text: "你也听见了吗？" }],
  options: ["inspect", "observe", "leave"],
};

const ACTIONS: Record<ActionId, DemoAction> = {
  inspect: {
    id: "inspect",
    label: "检查档案柜",
    hint: "侦查 · 困难检定",
    check: defineCheck({
      name: "侦查检定",
      skill: "侦查",
      system: "通用 d20",
      normalTarget: 12,
      difficulty: "困难",
      stakes: "成功会发现隐藏线索；失败会浪费时间并提高危险。",
    }),
  },
  observe: {
    id: "observe",
    label: "观察走廊",
    hint: "无需判定",
    directScene: {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 档案室外",
      title: "银色徽章",
      narration:
        "你没有立刻碰门，而是借着窗外的闪电观察走廊。女孩袖口下露出一枚银色徽章，图案像一条被火焰咬住尾巴的蛇。她察觉到你的目光，慢慢把手收回袖中。",
      dialogue: [{ speaker: "陌生女孩", text: "先别急着进去。里面的东西，今天不太安静。" }],
      options: ["follow", "take", "leave"],
    },
  },
  leave: {
    id: "leave",
    label: "离开档案室",
    hint: "无需判定",
    directScene: {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 主楼走廊",
      title: "你暂时离开",
      narration:
        "你决定先离开门口。走廊尽头的灯闪了两次，档案室里传来的刮擦声也随之停下。那种被注视的感觉，却没有消失。",
      options: ["return", "observe"],
    },
  },
  follow: {
    id: "follow",
    label: "跟随拖痕",
    hint: "追踪 · 普通检定",
    check: defineCheck({
      name: "追踪检定",
      skill: "侦查",
      system: "通用 d20",
      normalTarget: 10,
      difficulty: "普通",
      stakes: "成功会找到拖痕的尽头；失败会让目标消失在雨幕里。",
    }),
  },
  take: {
    id: "take",
    label: "带走值班记录",
    hint: "无需判定",
    directScene: {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 档案室",
      title: "一张不该存在的记录",
      narration:
        "你把那张发黄的值班记录折进外套。纸张背面写着一个日期：三年前的今天。值班人一栏没有姓名，只有一个像被擦掉一半的黑色圆印。",
      options: ["follow", "return"],
    },
  },
  return: {
    id: "return",
    label: "回到档案室",
    hint: "回到上一个场景",
    directScene: INITIAL_SCENE,
  },
  retry: {
    id: "retry",
    label: "再检查一次",
    hint: "侦查 · 普通检定",
    check: defineCheck({
      name: "再次侦查检定",
      skill: "侦查",
      system: "通用 d20",
      normalTarget: 14,
      difficulty: "普通",
      stakes: "你花费更多时间搜索柜底，可能会引起门后东西的注意。",
    }),
  },
};

const INITIAL_JOURNAL: JournalEntry[] = [
  { label: "等待行动", detail: "选择一个行动开始体验", kind: "action" },
];

const PHASES: { id: Phase; label: string }[] = [
  { id: "idle", label: "选择行动" },
  { id: "prepared", label: "确认判定" },
  { id: "rolling", label: "掷骰" },
  { id: "docking", label: "滑入结果" },
  { id: "revealed", label: "揭示结果" },
  { id: "resolved", label: "继续剧情" },
];

const OUTCOME_META: Record<Outcome, { label: string; description: string; className: string }> = {
  critical: { label: "大成功", description: "骰点触发了极佳结果。", className: "critical" },
  success: { label: "成功", description: "骰点达到判定目标。", className: "success" },
  failure: { label: "失败", description: "骰点没有达到判定目标。", className: "failure" },
  fumble: { label: "大失败", description: "骰点触发了危险结果。", className: "fumble" },
};

function getDelta(outcome: Outcome, actionId: ActionId): Delta {
  if (outcome === "critical") return { sanity: 0, health: 0, clues: 2, minutes: 5, danger: -1 };
  if (outcome === "success") return { sanity: 0, health: 0, clues: 1, minutes: 10, danger: 0 };
  if (outcome === "fumble") return { sanity: -5, health: -1, clues: 0, minutes: 20, danger: 2 };
  return { sanity: actionId === "follow" ? 0 : -2, health: 0, clues: 0, minutes: 20, danger: 1 };
}

function getResultScene(actionId: ActionId, outcome: Outcome): Scene {
  const positive = outcome === "success" || outcome === "critical";

  if (actionId === "follow") {
    if (positive) {
      return {
        chapter: "第一幕 · 雨中的访客",
        location: "卡塞尔学院 · 西侧回廊",
        title: outcome === "critical" ? "雨幕中的第二道影子" : "拖痕的尽头",
        narration:
          outcome === "critical"
            ? "你沿着拖痕追到回廊尽头，提前察觉到墙后传来的呼吸声。雨幕中有两道影子，而女孩身后原本只有一道。"
            : "拖痕在一扇落灰的铁门前停下。门把手上还残留着温度，像有人刚刚从里面离开。",
        dialogue: [{ speaker: "陌生女孩", text: "看来它已经知道我们来了。" }],
        options: ["take", "return"],
      };
    }
    return {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 西侧回廊",
      title: "拖痕消失了",
      narration:
        "你追到回廊尽头，地面上的痕迹却在一滩积水前凭空断掉。远处传来关门声，等你回头时，女孩已经不见了。",
      options: ["retry", "return"],
    };
  }

  if (positive) {
    return {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 档案室",
      title: outcome === "critical" ? "柜底的火漆印" : "被移动过的档案柜",
      narration:
        outcome === "critical"
          ? "你几乎立刻看见柜底的火漆印。它封着一枚薄薄的金属片，上面刻着和女孩徽章相同的蛇形图案。"
          : "你蹲下检查柜脚，终于发现了一道被灰尘掩盖的拖痕。柜底压着半张值班记录，纸上写着一个不属于任何人的名字。",
      dialogue: [{ speaker: "系统记录", text: "线索已加入记忆。" }],
      options: ["follow", "take", "return"],
    };
  }

  if (outcome === "fumble") {
    return {
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 档案室",
      title: "门后回应了",
      narration:
        "你的手肘撞上柜门，整排档案同时向前倾倒。门后的刮擦声骤然变成了敲击声——三下，停顿，再三下。",
      dialogue: [{ speaker: "陌生女孩", text: "别出声。它在数我们有几个人。" }],
      options: ["return", "leave"],
    };
  }

  return {
    chapter: "第一幕 · 雨中的访客",
    location: "卡塞尔学院 · 档案室",
    title: "灰尘下什么也没有",
    narration:
      "你把档案柜的每一层都检查了一遍。除了发霉的旧报纸和一枚断掉的纽扣，里面什么也没有。门后的刮擦声也不再出现。",
    options: ["retry", "leave"],
  };
}

function phaseIndex(phase: Phase) {
  return PHASES.findIndex((item) => item.id === phase);
}

export function DiceDemo() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [scene, setScene] = useState<Scene>(INITIAL_SCENE);
  const [activeAction, setActiveAction] = useState<DemoAction | null>(null);
  const [freeAction, setFreeAction] = useState("");
  const [pendingRoll, setPendingRoll] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<DemoResult | null>(null);
  const [diceError, setDiceError] = useState<string | null>(null);
  const [stats, setStats] = useState({ sanity: 55, health: 10, clues: 0, minutes: 0, danger: 1 });
  const [journal, setJournal] = useState<JournalEntry[]>(INITIAL_JOURNAL);
  const [rollCount, setRollCount] = useState(0);

  const currentPhaseIndex = phaseIndex(phase);
  const resultMeta = lastResult ? OUTCOME_META[lastResult.outcome] : null;

  const addJournal = (entry: JournalEntry) => {
    setJournal((items) => [...items, entry]);
  };

  const beginAction = (actionId: ActionId, displayLabel?: string) => {
    const action = ACTIONS[actionId];
    const nextAction = displayLabel ? { ...action, label: displayLabel } : action;
    setActiveAction(nextAction);
    setLastResult(null);
    setPendingRoll(null);
    setDiceError(null);

    if (!action.check) {
      setPhase("resolved");
      if (action.directScene) setScene(action.directScene);
      addJournal({ label: "无需判定", detail: `${nextAction.label} · 直接进入剧情`, kind: "commit" });
      return;
    }

    setPhase("prepared");
    addJournal({ label: "判定已准备", detail: `${nextAction.label} · ${action.check.expression}`, kind: "check" });
  };

  const chooseFreeAction = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = freeAction.trim();
    if (!text || phase === "prepared" || phase === "rolling" || phase === "docking" || phase === "revealed") return;

    setFreeAction("");
    if (/检查|调查|搜索|寻找|观察|翻|阅读|查看/.test(text)) {
      beginAction("inspect", text);
      return;
    }

    setActiveAction(null);
    setLastResult(null);
    setPhase("resolved");
    setScene({
      chapter: "第一幕 · 雨中的访客",
      location: "卡塞尔学院 · 档案室外",
      title: "你的自由行动",
      narration: `你决定：${text}\n\n女孩没有阻止你，只是侧过身，让出了一条通往走廊深处的路。这个行动暂时没有触发需要掷骰的规则判定。`,
      dialogue: [{ speaker: "陌生女孩", text: "有些答案，不一定要在档案里找。" }],
      options: ["observe", "inspect", "leave"],
    });
    addJournal({ label: "无需判定", detail: `${text} · 直接进入剧情`, kind: "commit" });
  };

  const reveal = (value: number) => {
    if (!activeAction?.check) return;
    const evaluation = getOutcome(value, activeAction.check);
    const delta = getDelta(evaluation.outcome, activeAction.id);
    const result: DemoResult = {
      actionLabel: activeAction.label,
      spec: activeAction.check,
      roll: value,
      outcome: evaluation.outcome,
      degree: evaluation.degree,
      delta,
    };
    setLastResult(result);
    setPhase("revealed");
    addJournal({ label: "骰面已揭示", detail: "结果已显示在落地骰面上", kind: "result" });
  };

  const startRoll = () => {
    if (!activeAction?.check || phase !== "prepared") return;

    // 固定第一次档案检定的结果，保证第一次打开 demo 就能完整看到成功链路。
    // 困难检定阈值为 6，5 落在困难成功档，顺便展示分级成功度。
    const scriptedFirstRoll = rollCount === 0 && activeAction.id === "inspect" ? 5 : null;
    const result = scriptedFirstRoll ?? Math.floor(Math.random() * 20) + 1;
    setRollCount((count) => count + 1);
    setPendingRoll(result);
    setDiceError(null);
    setPhase("rolling");
    addJournal({ label: "结果已锁定", detail: "判定结果已锁定，动画正在回放", kind: "roll" });
  };

  const handleDiceSettled = () => {
    if (phase !== "rolling" || pendingRoll === null) return;
    setPhase("docking");
    addJournal({ label: "物理骰子已停止", detail: "骰子保持原尺寸，正在滑入结果区域", kind: "roll" });
  };

  const handleDiceDocked = () => {
    if (phase !== "docking" || pendingRoll === null) return;
    reveal(pendingRoll);
  };

  const handleDiceError = (message: string) => {
    setDiceError(message);
    setPendingRoll(null);
    setPhase("prepared");
    addJournal({ label: "3D 骰子失败", detail: "可以点击掷骰重试", kind: "result" });
  };

  const commitResult = () => {
    if (!lastResult || !activeAction) return;
    const { delta, outcome } = lastResult;
    setStats((current) => ({
      sanity: Math.max(0, Math.min(60, current.sanity + delta.sanity)),
      health: Math.max(0, Math.min(10, current.health + delta.health)),
      clues: current.clues + delta.clues,
      minutes: current.minutes + delta.minutes,
      danger: Math.max(0, Math.min(5, current.danger + delta.danger)),
    }));
    setScene(getResultScene(activeAction.id, outcome));
    setPhase("resolved");
    addJournal({ label: "状态已提交", detail: `${lastResult.degree} · 可以继续剧情`, kind: "commit" });
  };

  const resetDemo = () => {
    setPhase("idle");
    setScene(INITIAL_SCENE);
    setActiveAction(null);
    setFreeAction("");
    setPendingRoll(null);
    setLastResult(null);
    setDiceError(null);
    setStats({ sanity: 55, health: 10, clues: 0, minutes: 0, danger: 1 });
    setJournal(INITIAL_JOURNAL);
    setRollCount(0);
  };

  const progressLabel = useMemo(() => {
    if (phase === "prepared" && activeAction?.check) return `等待你确认：${activeAction.check.name}`;
    if (phase === "rolling") return "骰子正在滚动";
    if (phase === "docking") return "骰子停止，正在滑入结果区域";
    if (phase === "revealed") return "结果已经揭示，等待提交";
    if (phase === "resolved") return "结果已提交，可以继续行动";
    return "选择一个行动开始";
  }, [activeAction, phase]);

  const phaseLocked = phase === "prepared" || phase === "rolling" || phase === "docking" || phase === "revealed";

  return (
    <main className="app-shell dice-demo-app-shell">
      <aside className="side-panel dice-demo-control-panel">
        <div className="brand-row">
          <div>
            <Link href="/">
              <div className="brand-mark">Jity</div>
            </Link>
            <div className="brand-subtitle">GM scenario console</div>
          </div>
          <div className="brand-actions">
            <Link className="icon-button" href="/" title="返回主控制台"><ArrowLeft size={17} /></Link>
            <Link className="icon-button" href="/timeline" title="发现时间线"><MapPin size={17} /></Link>
            <Link className="icon-button" href="/curator" title="战役编辑器"><PenTool size={17} /></Link>
            <Link className="icon-button" href="/dev-log" title="开发日志"><History size={17} /></Link>
          </div>
        </div>

        <div className="source-pill scripted dice-demo-console-badge">Playable judgment demo</div>

        <label className="label" htmlFor="dice-demo-system">规则系统</label>
        <select className="select" id="dice-demo-system" disabled value="generic-d20" onChange={() => undefined}>
          <option value="generic-d20">通用 d20</option>
        </select>

        <label className="label" htmlFor="dice-demo-mode">判定模式</label>
        <select className="select" id="dice-demo-mode" disabled value="roll-under" onChange={() => undefined}>
          <option value="roll-under">1d20 roll-under</option>
        </select>

        <div className="section-title">
          <span>当前流程</span>
          <ShieldCheck size={16} />
        </div>
        <div className="memory-item dice-demo-flow-summary">
          <strong>{progressLabel}</strong>
          <p>结果先锁定，动画只负责回放。</p>
        </div>

        <div className="section-title">
          <span>判定流程</span>
          <span className="dice-demo-phase-count">{Math.max(1, currentPhaseIndex + 1)}/{PHASES.length}</span>
        </div>
        <div className="dice-demo-phase-list" aria-label="判定流程">
          {PHASES.map((item, index) => {
            const isDone = currentPhaseIndex > index;
            const isActive = currentPhaseIndex === index;
            return (
              <div className={`dice-demo-phase-item ${isActive ? "active" : ""} ${isDone ? "done" : ""}`} key={item.id}>
                <span>{isDone ? <Check size={13} /> : index + 1}</span>
                <strong>{item.label}</strong>
              </div>
            );
          })}
        </div>

        <div className="section-title">
          <span>调查员状态</span>
          <CircleAlert size={16} />
        </div>
        <div className="stat-block">
          <div className="stat-row"><span>理智</span><strong>{stats.sanity}<small>/60</small></strong></div>
          <div className="bar"><div className="bar-fill" style={{ width: `${(stats.sanity / 60) * 100}%` }} /></div>
        </div>
        <div className="stat-block">
          <div className="stat-row"><span>生命</span><strong>{stats.health}<small>/10</small></strong></div>
          <div className="bar"><div className="bar-fill health" style={{ width: `${(stats.health / 10) * 100}%` }} /></div>
        </div>
        <div className="dice-demo-side-facts">
          <span><BookOpen size={14} />线索 <b>{stats.clues}</b></span>
          <span><Clock3 size={14} />用时 <b>{stats.minutes} 分</b></span>
          <span><CircleAlert size={14} />危险 <b>{stats.danger}/5</b></span>
        </div>

        <label className="label" htmlFor="dice-demo-free-action">玩家行动</label>
        <form className="dice-demo-action-form" onSubmit={chooseFreeAction}>
          <textarea
            className="textarea small-textarea"
            id="dice-demo-free-action"
            disabled={phaseLocked}
            onChange={(event) => setFreeAction(event.target.value)}
            placeholder="输入玩家行动、当前场景或 GM 限制"
            value={freeAction}
          />
          <button className="primary-button dice-demo-action-submit" disabled={!freeAction.trim() || phaseLocked} type="submit">
            <BookOpen size={17} /> 发送自由行动
          </button>
        </form>
      </aside>

      <section className="story-panel dice-demo-story-panel">
        <div className="toolbar-row">
          <div className="meta">Session dice-demo</div>
          <div className="meta">Turn {rollCount + 1}</div>
          <div className="source-pill scripted">本地演示</div>
          <button className="icon-button dice-demo-toolbar-reset" onClick={resetDemo} title="重新开始" type="button"><RotateCcw size={16} /></button>
        </div>

        <article className="scene-output dice-demo-scene-output">
          <div className="dice-demo-scene-kicker">
            <span className="meta">{scene.chapter}</span>
            <span className="meta">{scene.location}</span>
          </div>
          <h1 className="dice-demo-scene-title">{scene.title}</h1>
          <div className="narration">{scene.narration}</div>
          <div className="dialogue-list">
            {scene.dialogue?.map((line, index) => (
              <div className="dialogue-line" key={`${line.speaker}-${index}`}>
                <span className="speaker">{line.speaker}：</span>
                <span className="dialogue-text">“{line.text}”</span>
              </div>
            ))}
          </div>

          {phase === "resolved" && lastResult ? (
            <div className={`status-hint ${resultMeta?.className === "failure" || resultMeta?.className === "fumble" ? "loss" : "gain"}`}>
              <span>判定已提交</span>
              <strong>{lastResult.degree}</strong>
              <span>骰面结果已确认</span>
            </div>
          ) : null}

          {phase === "idle" || phase === "resolved" ? (
            <div className="option-list dice-demo-option-list">
              {scene.options.map((actionId) => {
                const action = ACTIONS[actionId];
                const needsCheck = Boolean(action.check);
                return (
                  <button className={`option-button dice-demo-option-button ${needsCheck ? "needs-check" : ""}`} key={actionId} onClick={() => beginAction(actionId)} type="button">
                    <span className="dice-demo-option-icon">{needsCheck ? <Dices size={17} /> : actionId === "observe" ? <Eye size={17} /> : actionId === "follow" ? <Footprints size={17} /> : <ChevronRight size={17} />}</span>
                    <span className="dice-demo-option-copy"><strong>{action.label}</strong><small>{action.hint}</small></span>
                    <ChevronRight className="dice-demo-option-arrow" size={16} />
                  </button>
                );
              })}
            </div>
          ) : null}
        </article>

        {phase === "prepared" && activeAction?.check ? (
          <section className="dice-demo-interaction-card check-card dice-demo-check-card">
            <div className="dice-demo-interaction-icon"><Dices size={22} /></div>
            <div className="dice-demo-interaction-content">
              <div className="dice-demo-check-heading">
                <div><span className="dice-demo-overline">需要进行判定</span><h3>{activeAction.check.name}</h3></div>
                <span className="dice-demo-system-pill">{activeAction.check.system}</span>
              </div>
              <div className="dice-demo-check-facts">
                <div><span>骰式</span><strong>{activeAction.check.expression}</strong></div>
                <div><span>难度</span><strong>{activeAction.check.difficulty}</strong></div>
                <div><span>目标</span><strong>{activeAction.check.target}</strong></div>
              </div>
              <p className="dice-demo-stakes">{activeAction.check.stakes}</p>
              {diceError ? <p className="dice-demo-3d-error">{diceError} · 请再次点击“掷骰”。</p> : null}
              <div className="dice-demo-actions-row">
                <button className="primary-button dice-demo-check-primary" onClick={startRoll} type="button"><Dices size={17} /> 掷骰</button>
                <button className="dice-demo-secondary-button" onClick={() => { setActiveAction(null); setPhase("idle"); }} type="button">取消行动</button>
              </div>
            </div>
          </section>
        ) : null}

        {(phase === "rolling" || phase === "docking" || phase === "revealed") && activeAction?.check && pendingRoll !== null ? (
          <section className={`dice-demo-interaction-card roll-card ${phase !== "rolling" ? "dice-roll-docked" : ""}`} aria-live="polite">
            <div className="dice-demo-roll-head">
              <div><span className="dice-demo-overline">{activeAction.check.expression}</span><h3>{phase === "rolling" ? "骰子滚动中" : phase === "docking" ? "骰子滑入结果区域" : "骰面已经停下"}</h3></div>
              <span className="dice-demo-lock-pill"><ShieldCheck size={14} />{phase === "rolling" ? "结果已锁定" : phase === "docking" ? "物理已停止" : "结果已落定"}</span>
            </div>
            <div className="dice-stage">
              <DiceCanvas value={pendingRoll} docking={phase === "docking" || phase === "revealed"} onError={handleDiceError} onSettled={handleDiceSettled} onDocked={handleDiceDocked} />
            </div>
            <div className="dice-demo-roll-caption">{phase === "rolling" ? "真实 3D 物理骰子正在碰撞、翻滚并寻找停面" : phase === "docking" ? "骰子保持原尺寸，正在缓慢滑入结果区域" : "只读骰面查看本次结果"}</div>
          </section>
        ) : null}

        {phase === "revealed" && lastResult && resultMeta ? (
          <section className={`dice-demo-interaction-card result-card ${resultMeta.className}`} aria-live="polite">
            <div className="dice-demo-result-banner">
              <div className="dice-demo-result-orb"><Sparkles size={22} /></div>
              <div><span className="dice-demo-overline">骰面已揭示</span><h3>{resultMeta.label}</h3><p>{resultMeta.description}</p></div>
            </div>
            <div className="dice-demo-result-face-note"><Dices size={16} /><span>骰面上的数字就是本次判定结果</span><strong>{lastResult.degree}</strong></div>
            <p className="dice-demo-result-note">机械效果将在你确认后提交，之后才会生成后续剧情。</p>
            <button className="primary-button dice-demo-result-primary" onClick={commitResult} type="button"><ChevronRight size={17} /> 应用结果并继续剧情</button>
          </section>
        ) : null}
      </section>

      <aside className="memory-panel dice-demo-memory-panel">
        <div className="section-title"><span>Context Memory</span><Sparkles size={16} /></div>
        <div className="memory-list">
          <div className="memory-item">
            <div className="memory-head"><strong>当前场景</strong><span className="memory-status">active</span></div>
            <div>地点：{scene.location}</div>
            <div>章节：{scene.chapter}</div>
            <div>目标：完成当前行动并确认结果</div>
          </div>
          <div className="memory-item">
            <div className="memory-head"><strong>当前判定</strong><span className="memory-status">{phase}</span></div>
            <div>{activeAction?.check?.name ?? "等待玩家选择行动"}</div>
            {activeAction?.check ? <p>{activeAction.check.expression} · 目标 {activeAction.check.target}</p> : null}
          </div>
        </div>

        <div className="section-title"><span>状态</span><CircleAlert size={16} /></div>
        <div className="stat-block"><div className="stat-row"><span>理智</span><strong>{stats.sanity}/60</strong></div><div className="bar"><div className="bar-fill" style={{ width: `${(stats.sanity / 60) * 100}%` }} /></div></div>
        <div className="stat-block"><div className="stat-row"><span>生命</span><strong>{stats.health}/10</strong></div><div className="bar"><div className="bar-fill health" style={{ width: `${(stats.health / 10) * 100}%` }} /></div></div>
        <div className="memory-list dice-demo-memory-facts">
          <div className="memory-item"><span>线索</span><strong>{stats.clues}</strong></div>
          <div className="memory-item"><span>用时</span><strong>{stats.minutes} 分</strong></div>
          <div className="memory-item"><span>危险等级</span><strong>{stats.danger}/5</strong></div>
        </div>

        <div className="section-title"><span>最近事件</span><Clock3 size={16} /></div>
        <div className="memory-list dice-demo-memory-journal">
          {journal.map((entry, index) => (
            <div className="memory-item" key={`${entry.label}-${index}`}>
              <div className="memory-head"><strong>{entry.label}</strong><span className="memory-status">{entry.kind}</span></div>
              <p>{entry.detail}</p>
            </div>
          ))}
        </div>

        <div className="section-title"><span>Demo Notes</span><BookOpen size={16} /></div>
        <div className="chunk-list">
          <div className="chunk-item"><div className="chunk-head"><span className="chunk-badge scripted">renderer</span><span className="chunk-score">d20</span></div><div className="chunk-title">真实物理骰面</div><p>使用 open-dice-dnd 的 Three.js + Cannon-es d20，并把预先锁定的结果绘制到停面上。</p></div>
          <div className="chunk-item"><div className="chunk-head"><span className="chunk-badge llm">flow</span><span className="chunk-score">gated</span></div><div className="chunk-title">结果确认门</div><p>只有玩家点击确认后，判定结果才会写入状态并推进剧情。</p></div>
        </div>
      </aside>
    </main>
  );
}
