# 时间选择输入修订材料

本包仍为 4,750 条助手草稿，来源分组、划分、目标和人审状态不变。
48 条 D08 输入增加真实前置时间选择；其余 4,702 条原始行不变。
变更证明不等于语义正确或独立泛化通过。

`migration-proof.json.gz` 是完整证明的无损交付副本。实验消费者仍读取
`migration-proof.json`；运行机器上的原件保留，未被压缩包替换。
新检出需要先恢复原件。以下命令只在目标不存在时写入；已有文件必须身份一致：

```python
from pathlib import Path
import gzip
import hashlib

directory = Path("experiments/world-components-logic/data/short-semantics/time-choice-v2")
packed = (directory / "migration-proof.json.gz").read_bytes()
assert hashlib.sha256(packed).hexdigest() == "cf5208c37bf4ff87c776de975063cab80301476cba51dcf1d5e3ff84fc6d62b9"
raw = gzip.decompress(packed)
assert hashlib.sha256(raw).hexdigest() == "849eea3e8034dce4814facaa4259febb696bc8481fdc3db2a0020ee376f8a007"
target = directory / "migration-proof.json"
if target.exists():
    assert target.read_bytes() == raw
else:
    with target.open("xb") as stream:
        stream.write(raw)
```

恢复证明不会自动搬迁清单中的绝对路径，也不会验证模型能力；重新运行仍需登记本机资源并冻结新的实验身份。
