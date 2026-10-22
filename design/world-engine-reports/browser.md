# B：消费侧核对与共同接口基线交付

日期：2026-10-22。共同接口实现：`e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`；S1：`cabb04c`；v1：`26011c8`。接口摘要：`480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。本报告及 change-list 在随后文档提交中正式验收该实现；两条开发分支从包含冻结记录的同一提交建立并推送。

环境：Windows / PowerShell；Python 3.12.3、SQLite 3.50.4、Pydantic 2.13.4、jsonschema 4.26.0；Node 22.20.0、npm 10.9.3、TypeScript 5.9.3、Ajv 8.20.0、Vitest 5.0.1。CI 配置 Python 3.12、Node 22；Node 升级匹配现有 Vitest 5 的 engines 要求。

统一验收入口：`python -X utf8 backend/scripts/check_world_interface_baseline.py`。在原工作区和从该提交新建的干净 worktree 中运行，后者先执行全新 `npm ci`，均通过。统一入口覆盖 v1/v2 只读生成核对、Python 426 项（109+317）、TS 类型、契约 38 项、轨迹 65 项，以及四类故意破坏探针。默认 v1 导出仍是原 12 个产物字节；v2 为 5 个生成物，manifest 共 147 项。生成与检查不重写手写夹具，pin 由 Python 生成。

`npm --prefix frontend test` 为 10 文件、165 项通过；S1 JS 复核 60/0；lint 与生产 build 通过，保留既有 useBrowserAutoPlay hook 依赖 warning。额外全量 backend（`python -X utf8 -m pytest -q`）为 **923 passed、0 failed**，此前记录的 `test_campaign_wiring.py` 创建会话与 slot 过滤两例 404 已不存在。frontend 在 `07924f3` 的远端运行中失败于 npm ci；本验收提交 `05c213e` 是首次带 world-interface 作业的运行，backend、frontend、world-interface 三个作业全部 success。

CI 保留既有 backend pytest 与 frontend lint/build，新增 npm test 与 world-interface。统一入口中的聚焦消费测试和 frontend 作业全套有意重叠；空集、缺依赖或跳过必需检查均不计通过。

交付位于 `frontend/src/lib/world-engine/`：手写完整操作类型和判别联合、共享 Ajv2020 校验、transport 接口及可配置 HTTP、严格固定响应、固定模型输出端口、trace 读取/捕获/断言。package.json 提供 typecheck:world、test:world-contract、test:world-traces，隔离 tsconfig 覆盖模块及测试。

32 个操作分别消费共享 request/success/error；18 个错误码均有确定恢复动作。HTTP 处理路径/查询、协议头、请求与响应身份、JSON、HTTP 状态、超时和调用方取消，不自动重试；超时后保留原 requestId/载荷。resume 成功但 canCompute=false 时不调度。restore 从只读来源清单直接构造请求，无客户端目标 attempt；成功结果可读回服务端复制身份。

11 份 T01～T09 轨迹的两组样本分别经过固定响应与受控 HTTP；65 项验证正常消费及错令牌/顺序/作用域、schema 先于捕获、未来/重复/缺失引用、业务预期篡改、epoch 差值及旧摘要。固定响应绝不执行 apply 或补造未声明结果。模型端口按预设 task/key/input 顺序返回隔离副本，可保留 localRef；不分配持久化 ID/roll，不代表真实模型提示词或质量已验证。

消费核对结论：S2 与 IF-05/IF-06 通过，未发现共同接口剩余字段/权限/恢复构造缺口；IF-08 正式验收，B0 前置关闭。下一步 B1 从固定输出实现浏览器调度，H1 用 T01 连 A2；B2/A3 就绪后 H2 用 T07 验证真实刷新/接管。浏览器设备、双心跳、推理取消、模型提示词/质量与页面仍按 B1～B4 后续交付。
