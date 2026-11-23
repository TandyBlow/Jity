# Design: goal-mobile-compact

## results 清单压缩

- `buildResultsPrompt` 的 sceneIds 在 compact 下取：成员 + 骰点目标 + 行动文本里点名的人物/物品；不再列全部可见人物与房间物品。
- 页面 `?compactSettlement=1`，记入 `__worldArm`；默认关闭。

## 容器目录压缩（已回退）

- 试过把位置/外貌提示的容器目录过滤到相关容器；run104 的 position 调用 64.4 s、2 次尝试，模型把被裁掉的容器当目的地。净效果 229.9 s > 基线 210.5 s，已回退。

## 结果

- run103（只压 results）：s05 189.1 s；s06 27.4 s 中止。
- run104（再压目录）：s05 229.9 s；s06 135.9 s。
- 60 秒仍需约 3 倍；当前 0.6B + 核显上限 190–230 s。
