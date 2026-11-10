/** Types for the deployable narration-model runtime (A-group route).
 *
 * The model runtime is the part 03/09 do not each rebuild: it says which
 * local GGUF is a candidate, which chat template it needs, how it is loaded
 * on this machine (WebGPU vs CPU), and how to turn a committed narration
 * point into a real streamed completion with the model's own template. The
 * prose policy stays in the candidate layer (03) — this module only supplies
 * the model, template, loading path and evidence. */
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { CompletionEvidence, InferenceEngine } from '../../../runtime/engine';
import type { TimeAdvance, Id, WorldState } from '../../../types';

/** A local checkpoint that actually exists on this machine. `gguf` is the
 * file name under a model root served at /models; the probe/run scripts
 * resolve it against the read-only shared model directories. */
export interface ModelSpec {
  id: string;
  label: string;
  gguf: string;
  /** SHA-256 of the exact file, computed from the local asset. */
  sha256: string;
  bytes: number;
  family: 'qwen2.5' | 'qwen3' | 'qwen3-2507' | 'generic';
  architecture: string;
  parametersB: number;
  base: string;
  /** Thinking is a Qwen3 hybrid-template feature; when true the adapter must
   * pass enable_thinking=false and strip any residual think block. */
  thinking: 'hybrid' | 'none';
  /** Exact template the adapter drives. */
  template: {
    id: string;
    /** A system message is required for these instruct checkpoints. */
    systemMessage: boolean;
    /** What the adapter passes to chat_template_kwargs. */
    templateKwargs: Record<string, unknown>;
    /** Extra stop strings the checkpoint needs beyond its EOS token. */
    stop: string[];
  };
  /** Loading defaults for this machine, verified by the probe. */
  recommended: {
    contextSize: number;
    numThreads: number;
    gpuLayers: number;
  };
  /** True for trained/raw-completion checkpoints (not a chat model). */
  rawCompletion?: boolean;
}

export interface ChatTurn {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/** An InferenceEngine that can take a real message list. wllama engines do;
 * a fake or legacy engine may not, in which case the adapter composes the
 * system turn into the user prompt. */
export interface ChatCapableEngine extends InferenceEngine {
  chat?(messages: ChatTurn[], options?: {
    signal?: AbortSignal;
    maxTokens?: number;
    temperature?: number;
    seed?: number;
    stop?: string[];
    timeoutMs?: number;
    cachePrompt?: boolean;
    jsonSchema?: unknown;
    onProgress?: (progress: { raw: string; elapsedMs: number }) => void;
    onCompletion?: (completion: CompletionEvidence) => void;
  }): Promise<string>;
}

/** Scene material supplied by the caller's projection. It is display data,
 * never a new fact source: the candidate may only mention what the input
 * carries. */
export interface CandidateScene {
  location: string;
  placeNotes?: string[];
  present?: { name: string; note?: string | null }[];
  objects?: { name: string; note?: string | null }[];
}

/** The task's shared policy shape (see QUALITY-TEAMS "候选调用约定"). Fields
 * after `maxTokensCeiling` are our own additive controls. */
export interface CandidatePolicy {
  mode?: 'beats' | 'scene';
  scene?: CandidateScene | null;
  viewpoint?: { id: Id; name: string } | null;
  roster?: string[];
  locations?: string[];
  knownPositions?: { name: string; location: string }[];
  knownEntities?: string[];
  visibleEntities?: string[];
  /** Either the plain duration or a settled TimeAdvance ({duration:{...}});
   * 09's driver passes the latter. */
  time?: { amount: number; unit: TimeAdvance['duration']['unit'] } | { duration: { amount: number; unit: TimeAdvance['duration']['unit'] } } | null;
  /** Require the passage to state the elapsed time even without a TimeAdvance. */
  requireTime?: boolean;
  /** How many paragraphs to ask for; default 3. */
  paragraphs?: number;
  minChars?: number;
  targetChars?: number;
  temperature?: number;
  /** Soft instruction from the caller (style, length, register). */
  instruction?: string;
  /** Include the caller's raw serializer string in the prompt. Off by
   * default: instruction models copy field labels from it instead of writing
   * prose. Kept for debugging and for candidates that expect it. */
  includeInputText?: boolean;
  /** Prior accepted prose, for continuity turns. */
  priorText?: string | null;
  /** Additive runtime controls. */
  maxTokens?: number;
  maxTokensCeiling?: number;
  timeoutMs?: number;
  seed?: number;
  /** Attempts per point; a failed verification retries with a repair note. */
  attempts?: number;
  /** Keep the caller's exact prompt instead of the built beat prompt. */
  prompt?: string;
}

export interface CandidateIssue {
  kind: string;
  detail: string;
  severity: 'hard' | 'soft';
}

export interface CandidateAttempt {
  index: number;
  prompt: string;
  promptChars: number;
  text: string;
  completion: CompletionEvidence | null;
  verification: CandidateVerification | null;
  accepted: boolean;
  issueKinds: string[];
  temperature: number;
}

export interface CandidateVerification {
  ok: boolean;
  violations: { kind: string; sentence: string; detail: string }[];
  omissions: string[];
  unverified: string[];
  timeExpressed: boolean | null;
  coverage: { id: string; kind: string; expressed: boolean }[];
}

export interface CandidateTimings {
  /** Model load, when the adapter performed it (null if the caller loaded). */
  loadMs: number | null;
  /** Request start → first streamed, displayable character. */
  firstReadableMs: number | null;
  /** Request start → the first onProgress event (may be empty). */
  firstProgressMs: number | null;
  /** Every model call in this point, including retries. */
  calls: number;
  totalMs: number;
  perAttemptMs: number[];
}

export interface CandidateProgress {
  text: string;
  status: 'streaming' | 'retry' | 'done';
  verified: boolean;
  elapsedMs: number;
}

export interface CandidateArgs {
  engine: ChatCapableEngine;
  committed: CommittedNarration;
  inputText: string;
  priorText?: string | null;
  signal?: AbortSignal;
  onProgress?: (progress: CandidateProgress) => void;
  policy?: CandidatePolicy;
}

export interface CandidateResult {
  text: string;
  accepted: boolean;
  /** Why this text is (not) accepted. `timeout`/`error` are terminal: the
   * candidate never retries a dead engine with the same prompt. */
  status: 'accepted' | 'rejected' | 'cancelled' | 'timeout' | 'error';
  rawAttempts: CandidateAttempt[];
  issues: CandidateIssue[];
  timings: CandidateTimings;
  strategyVersion: string;
  /** Additive: which model/template was driven, and whether the text was
   * fact-verified (unverified text must be shown as unverified). */
  model?: { id: string; templateId: string } | null;
  verification: CandidateVerification | null;
}

/** Narrator persona + hard fact rules. This is the system turn for the
 * instruct models; the scenario material and committed changes are the user
 * turn. Keeping the rules identical across candidate models lets 03 compare
 * prose without changing the semantics. */
export const NARRATOR_SYSTEM_PROMPT = [
  '你是一位中文小说作者，为跑团游戏写这一段叙事正文。',
  '只输出正文，不要解释、不要列点、不要标题、不要用「玩家」「系统」这类游戏术语。',
  '正文用第三人称，贴着视角人物写，可以写动作、对话、环境与感受。',
  '必须写到下面列出的每一条已发生事实；不得反转方向、换人物、改数字。',
  '不得新增下面没有的人物、地点、物品、任务、往事或线索；不得替任何角色做出未提交的新行动。',
  '没有提交的变化就写等待、环境或延续状态，不要编造事件。',
].join('\n');

/** One-line-per-fact rendering of the committed packet. Deterministic and
 * model-independent: 03's own policy may pass its own prompt instead. */
export function describeCommitted(committed: CommittedNarration): string[] {
  return committed.facts.map((fact) => {
    switch (fact.kind) {
      case 'moved': return `${fact.name}从${fact.from}移动到${fact.to}。`;
      case 'at': return `${fact.name}现在位于${fact.location}。`;
      case 'sanity_changed': return `${fact.name}的精神值从${fact.from}变为${fact.to}。`;
      case 'sanity': return `${fact.name}的精神值是${fact.value}。`;
      case 'task_achieved': return `${fact.name}达成了任务「${fact.goal}」。`;
      case 'personality_changed': return `${fact.name}的个性变为「${fact.text}」。`;
    }
  });
}

export type { CommittedNarration, TimeAdvance, WorldState };
