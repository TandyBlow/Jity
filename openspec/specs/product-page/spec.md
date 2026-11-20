# product-page Specification

## Purpose

`/world-local` 产品页对玩家的交互契约：暂停可恢复、历史只读、叙事可重生且不改状态、隔离可见、离线可玩。

## Requirements

### Requirement: Pause and resume are player controls

The page SHALL expose a pause control and MUST resume the same session without re-rolling dice or replaying frozen work. 页面必须提供暂停与继续控件，恢复后不得重掷骰或重放已冻结行动。

#### Scenario: Pause then resume

- **WHEN** 玩家在空闲或结算中点击暂停，稍后点击继续
- **THEN** 会话继续推进，已提交状态与骰点与暂停前一致

### Requirement: History is read-only

Selecting a committed point in the history MUST only display the committed record; it MUST NOT change the head, state or narration. 历史选中只读，不回写状态、不改 head、不重写正文。

#### Scenario: Select an old point

- **WHEN** 玩家在历史里选中一个旧点
- **THEN** 页面显示该点的状态与正文，当前 head 与状态摘要不变

### Requirement: Narration can be regenerated without changing state

Regenerating a point's narration MUST delete the cached text and produce new text from the committed state only; it MUST NOT read the old text. 重生只读已提交的 S_{t-1}/Δ/S_t，必须删除旧正文缓存，不把旧正文喂回模型。

#### Scenario: Delete and regenerate

- **WHEN** 玩家对已提交点选择删除叙事并重生
- **THEN** 旧正文被删除，新正文只基于已提交状态生成，状态摘要不变

### Requirement: Cross-origin isolation is visible

The page SHALL verify `crossOriginIsolated` and show a persistent warning when it is false. 隔离失效必须持久告警，而不是静默降级。

#### Scenario: Isolation off

- **WHEN** 页面在缺少 COOP/COEP 的响应下加载
- **THEN** 页面显示持久告警并记录 `crossOriginIsolated=false`

### Requirement: The page plays without the save service

With every `/api/**` request refused, the page MUST still accept inputs, settle, narrate and save locally. 禁用服务器后仍可游玩与本地保存。

#### Scenario: Server blocked

- **WHEN** 所有 `/api/**` 请求被拒绝
- **THEN** 玩家可以提交行动、看到正文，进度保存在 IndexedDB
