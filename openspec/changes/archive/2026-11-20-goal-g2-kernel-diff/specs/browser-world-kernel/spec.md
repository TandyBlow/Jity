# Spec Delta

## Purpose

浏览器本地内核在失败回合、存档恢复与回放时的可观察行为契约：失败回合经取消后必须可继续，损坏存档必须拒绝开局，同一 S0+Δ 的规范摘要必须与冻结预言机一致。

## ADDED Requirements

### Requirement: A failed settlement can be terminated

A failed settlement MUST be terminable by a cancel, and the next submission SHALL be accepted. 当结算在提交点之前失败并收到取消时，内核必须关闭该 advance；下一次提交必须被接受，而不是无限返回 `turn_in_progress`。

#### Scenario: Next submit after a failed settlement

- **GIVEN** 一个已打开且结算在提交点前失败的 advance
- **WHEN** 玩家取消并提交新的输入
- **THEN** 旧 advance 关闭，新 advance 正常开始

### Requirement: Corrupt restore is refused

A corrupt record SHALL be refused at restore and MUST NOT be played. 当存档记录违反 point-continuity、任务层级或可见性不变量时，恢复必须拒绝继续游玩并报告失败的不变量代码。

#### Scenario: Corrupt record rejected

- **GIVEN** 一个 point 链断裂的存档记录
- **WHEN** 会话尝试恢复
- **THEN** 恢复被拒绝并返回不变量代码，且不应用任何状态

### Requirement: Replay digest matches the frozen oracle

The TS kernel's canonical `stateDigest` MUST equal the frozen Python oracle digest. 对冻结的 S0+Δ 向量，TS 内核重算的 canonical `stateDigest` 必须与 Python 预言机的摘要逐字节相同。

#### Scenario: Digest parity

- **GIVEN** 一个冻结向量及其 Python 摘要
- **WHEN** TS 内核应用该向量并重放
- **THEN** 重算的 `stateDigest` 等于冻结值
