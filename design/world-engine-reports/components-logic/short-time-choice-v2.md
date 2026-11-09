# D08 时间选择依赖修复与同源输入迁移

已将 `LifecycleHeads.time()` 改为 **boundary → unit → amount**。此前两个 D08 数值任务均直接读取原 payload，既不知道已选边界，也不知道单位；单位头同样不知道边界。现在单位头接收完整原输入与 `timeChoice={boundary}`，数值头再接收完整原输入与 `timeChoice={boundary,unit}`。这两个值只来自本次真实前序预测，程序不填写时间语义，不从草稿或历史输出取值。

`D08.1` 和 `D08.2.time` 共用该实现。instant 仍按现有协议固定为 0 second，不调用单位/数值头；已锁时间仍由 `propose_time()` 原样复用，不调用模型。公开 `timeAdvance`、`pointPlan` 形状、分段顺序和实际访问记录没有改变。失败仍为 incomplete，不能转为 0、instant 或 handback；非法单位、非整数和超安全整数范围继续拒绝。

实现位置是 [short_heads_lifecycle.py](../../../experiments/world-components-logic/short_heads_lifecycle.py:46)，两个调用点在 D08.1 和 D08.2 分支。迁移前 SHA 为 `5c84b372639ded25ce9dc306051e146a1f95c363fc45e89edee5f5045dcc1fd7`，迁移后为 `62c12feba54d169e3eb595853fad17b19c1fb76ecdb7da601141add9d3d365c8`。外置补丁及创建时身份保留于 `artifacts/world-components-logic/time-choice-v2/`；补丁是在 r4 训练和 base r5 浏览器批次结束、协调解锁后合入，没有修改冻结批次快照。

## 数据与证明

从 r4 固定监督包重新调用原 `project_annotations()`，通过现有真实组装逻辑捕获新的依赖输入。仅迁移下列四个组件，每个12行（train8/development2/test2），合计48行：

- `D08.1.unit`
- `D08.1.amount`
- `D08.2.time.unit`
- `D08.2.time.amount`

全部4750个 exampleId、target、labels、来源组、split、derivedFromAnnotation、derivedFromSha256 及其它元数据不变。只有这48行的 input 加入实际选择字段，并重算 contentSha256；其余4702行不仅全字段相等，原始 JSONL 字节也完全保留。来源文件原字节相同。新数据仍为助手草稿、人审0、来源未核的同源修订，不产生新独立来源。

新包：`experiments/world-components-logic/data/short-semantics/time-choice-v2/supervision.jsonl.gz`。

| 身份 | SHA-256 |
| --- | --- |
| 原 r4 gzip | `9587fdf90ecf675705a47ad6bdfccd85879143f2446f2116ec02e455a922fc5a` |
| 新 gzip | `8aa0875d0268e921142cfab5c2fe42df049193bca2d70b08358cbe909f4abe16` |
| 原解压字节 | `8d61152d5c8bbe1ef32deec849538858e147b71fce9aa7873ecc9edcfa9ad781` |
| 新解压字节 | `8fc1127b30da66ab84d970c3fdb35547c872e6bfa93f4fe88f9364637ddf9c2b` |
| 全行迁移证明 | `849eea3e8034dce4814facaa4259febb696bc8481fdc3db2a0020ee376f8a007` |

同目录 `migration-proof.json` 的 schema 是 `jity-d-time-choice-input-migration-v1`。顶层提供 sourceDataset/targetDataset 的 path、gzip 与解压 SHA、allowedChangedComponents、允许变化字段及总数。rows 含全部4750行的 old/new exampleId、component、sourceGroup、split、old/new canonical input/target/content/full-row SHA，以及是否改变。完整证明约4.34MB，只保本地；[小摘要和48行变化映射](../../../artifacts/world-components-logic/time-choice-v2/migration-summary.json) 用于交付索引。

监督中的已选单位来自作者参考上游返回的标签，属于有来源的正确中间输入；它不是数值 target，也没有把目标数值放入 input。运行时相同接口只读取真实模型的前序选择。迁移证明本身不证明语义正确，训练与验证仍须另跑。

公共验证器 [short_data_migration.py](../../../experiments/world-components-logic/short_data_migration.py) 重新读取两份数据并逐行核验，不直接信任证明中的布尔标记。规范化哈希区分 `1`、`true` 和 `1.0`；完整原输入不得在增加 `timeChoice` 时改变。新边界/单位还必须与同一注解、同一完整输入中的前序选择相符。新增10项反例覆盖标签、来源、split、字段类型、原世界内容、伪造逐行证明和合法但错误的单位替换。

r6 四个聚焦头沿用原训练数据身份；新 Mixed provider 只有在完整迁移证明确认其任务输入未变时才接收它们。D08 四个变化任务不能使用这项资格继承，必须另行实训。资格来源绑定不构成语义验收。

## 验证与后续训练边界

新增 [10项针对性测试](../../../experiments/world-components-logic/tests/test_short_time_choice.py) 全通过，覆盖两个时间前缀、完整上下文与真实选择绑定、分段候选传递、instant、锁定复用、上游/单位/数值失败、非法数值与溢出、陈旧输入选择和不变性。既有生命周期/交接45项测试也全部通过。测试低级提供器是显式工程替身，不是模型能力证据。

旧 r4 的128基线、128训后首次输出和原模型全部保留。新生成修复按协调方案在 r4 共享适配器继续32步训练两项 amount，并重验全部128例；共享权重改变，因此其余12项生成任务也必须重新验证，不能称行为不变。两项 unit 头独立实训，其余60头应逐张量核验继承。此处只交接口、数据和工程结果，不预签修复训练、语义质量或整链性能通过。
