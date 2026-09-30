import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
  id: "2026-09-18-slot-delete",
  date: "2026-09-18",
  title: "存档栏显式删除存档",
  summary: "侧栏存档栏新增删除按钮：当前存档置灰不可删，其余存档二次确认后按 id 删除；后端删除接口从按名全局删除改为按 id 精确删除。",
  developer: "zjr",
  areas: ["backend", "frontend", "save-slots", "tests"],
  changes: [
    "侧栏「存档:」行在 + 旁新增 Trash2 删除按钮：未选中或当前（active）存档时置灰并提示，删除前 window.confirm 二次确认。",
    "删除范围限定为当前选中槽所在会话的那一行：deleteSlot(id) → DELETE /campaigns/slots/{slot_id}，删除后 refreshSlots 保持当前选中不变。",
    "后端删除接口从 DELETE /campaigns/slots/{slot_name}（全库按名删除，会把所有会话同名槽一起删掉，且无任何调用方）改为按 id 删除；路由层校验 404（槽不存在）与 409（active 槽不可删）。",
    "仓储层 delete_slot(slot_name) 替换为 delete_slot_by_id(slot_id)，删除条件从 slot_name 改为 id。",
    "已知交互含义：新建存档立即成为当前存档，此时删除按钮置灰，需先切回其他存档再删；其他会话的 active 槽同样显示不可删。",
    "验证：新增 4 个集成用例（删非 active 200 且列表移除、删 active 409 且保留、不存在 404、跨会话同名声按 id 删除互不影响），test_campaign_wiring.py 8 项通过；前端构建通过。",
  ],
  relatedFiles: [
    "backend/app/routers/slots.py",
    "backend/app/repositories/campaign_progress.py",
    "backend/tests/test_campaign_wiring.py",
    "frontend/src/components/game/SidePanel.tsx",
    "frontend/src/components/game/useGameActions.ts",
    "frontend/src/lib/api.ts",
  ],
  nextSteps: [
    "考虑批量清理 auto_ 时间戳槽（多选删除或按前缀清理）。",
    "设置菜单的存档行目前仍只有新增，如需与侧栏对齐可复用同一个删除入口。",
  ],
};
