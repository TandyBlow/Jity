# 训练前复看表（assistant 复看，不是独立人工金标）

- examples: 261
- confirm: 125
- train/dev targeted: 56
- general sample: 188

## Flags

- n5:v2-a-quay:alternating-20minute:v0:f0:auth:unsup: residual-overlap:F3:0.73

## Items

### n5:v2-c-salt:alternating-6minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。六分钟过去了，柳拂衣从团盐棚来到了老盐滩。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=秦叔完成了任务「盘点官仓的存盐」；F3=柳拂衣从团盐棚来到了老盐滩；F4=前后大约6分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:alternating-6minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。六分钟过去了，柳拂衣从团盐棚来到了老盐滩。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=柳拂衣从团盐棚来到了老盐滩；F4=前后大约6分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:co-presence:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了团盐棚。柳拂衣已在团盐棚。官秤已在团盐棚。五分钟过去了，旧苫席已在团盐棚。
- candidate: 闻人镜从老盐滩来到了团盐棚。
- facts: F1=闻人镜从老盐滩来到了团盐棚；F2=柳拂衣已在团盐棚；F3=官秤已在团盐棚；F4=旧苫席已在团盐棚；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:co-presence:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了团盐棚。柳拂衣已在团盐棚。官秤已在团盐棚。五分钟过去了，旧苫席已在团盐棚。
- candidate: 闻人镜从老盐滩来到了团盐棚。
- facts: F2=柳拂衣已在团盐棚；F3=官秤已在团盐棚；F4=旧苫席已在团盐棚；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了老盐滩。她办妥了任务「数清盐埠头的筐」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 阿葵从盐埠头来到了老盐滩。
- facts: F1=阿葵从盐埠头来到了老盐滩；F2=阿葵完成了任务「数清盐埠头的筐」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了老盐滩。她办妥了任务「数清盐埠头的筐」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 阿葵从盐埠头来到了老盐滩。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了老盐滩。她办妥了任务「数清盐埠头的筐」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 阿葵从盐埠头来到了老盐滩。
- facts: F1=阿葵从盐埠头来到了老盐滩；F2=阿葵完成了任务「数清盐埠头的筐」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了老盐滩。她办妥了任务「数清盐埠头的筐」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 阿葵从盐埠头来到了老盐滩。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了官仓。她办妥了任务「数清盐埠头的筐」。三分钟过去了，秦叔已在官仓。
- candidate: 阿葵从盐埠头来到了官仓。
- facts: F1=阿葵从盐埠头来到了官仓；F2=阿葵完成了任务「数清盐埠头的筐」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了官仓。她办妥了任务「数清盐埠头的筐」。三分钟过去了，秦叔已在官仓。
- candidate: 阿葵从盐埠头来到了官仓。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了官仓。她办妥了任务「数清盐埠头的筐」。五分钟过去了，秦叔已在官仓。
- candidate: 阿葵从盐埠头来到了官仓。
- facts: F1=阿葵从盐埠头来到了官仓；F2=阿葵完成了任务「数清盐埠头的筐」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了官仓。她办妥了任务「数清盐埠头的筐」。五分钟过去了，秦叔已在官仓。
- candidate: 阿葵从盐埠头来到了官仓。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_windmill-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了风车埠。她办妥了任务「数清盐埠头的筐」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 阿葵从盐埠头来到了风车埠。
- facts: F1=阿葵从盐埠头来到了风车埠；F2=阿葵完成了任务「数清盐埠头的筐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_windmill-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了风车埠。她办妥了任务「数清盐埠头的筐」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 阿葵从盐埠头来到了风车埠。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_windmill-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿葵从盐埠头来到了风车埠。她办妥了任务「数清盐埠头的筐」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 阿葵从盐埠头来到了风车埠。
- facts: F1=阿葵从盐埠头来到了风车埠；F2=阿葵完成了任务「数清盐埠头的筐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_akui-c_windmill-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 阿葵从盐埠头来到了风车埠。她办妥了任务「数清盐埠头的筐」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 阿葵从盐埠头来到了风车埠。
- facts: F2=阿葵完成了任务「数清盐埠头的筐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了老盐滩。她办妥了任务「苫盖盐垛的草席」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 柳拂衣从团盐棚来到了老盐滩。
- facts: F1=柳拂衣从团盐棚来到了老盐滩；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了老盐滩。她办妥了任务「苫盖盐垛的草席」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 柳拂衣从团盐棚来到了老盐滩。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了老盐滩。她办妥了任务「苫盖盐垛的草席」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 柳拂衣从团盐棚来到了老盐滩。
- facts: F1=柳拂衣从团盐棚来到了老盐滩；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了老盐滩。她办妥了任务「苫盖盐垛的草席」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 柳拂衣从团盐棚来到了老盐滩。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了官仓。她办妥了任务「苫盖盐垛的草席」。三分钟过去了，秦叔已在官仓。
- candidate: 柳拂衣从团盐棚来到了官仓。
- facts: F1=柳拂衣从团盐棚来到了官仓；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了官仓。她办妥了任务「苫盖盐垛的草席」。三分钟过去了，秦叔已在官仓。
- candidate: 柳拂衣从团盐棚来到了官仓。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了官仓。她办妥了任务「苫盖盐垛的草席」。五分钟过去了，秦叔已在官仓。
- candidate: 柳拂衣从团盐棚来到了官仓。
- facts: F1=柳拂衣从团盐棚来到了官仓；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了官仓。她办妥了任务「苫盖盐垛的草席」。五分钟过去了，秦叔已在官仓。
- candidate: 柳拂衣从团盐棚来到了官仓。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_wharf-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了盐埠头。她办妥了任务「苫盖盐垛的草席」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 柳拂衣从团盐棚来到了盐埠头。
- facts: F1=柳拂衣从团盐棚来到了盐埠头；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_wharf-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了盐埠头。她办妥了任务「苫盖盐垛的草席」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 柳拂衣从团盐棚来到了盐埠头。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_wharf-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了盐埠头。她办妥了任务「苫盖盐垛的草席」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 柳拂衣从团盐棚来到了盐埠头。
- facts: F1=柳拂衣从团盐棚来到了盐埠头；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_wharf-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了盐埠头。她办妥了任务「苫盖盐垛的草席」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 柳拂衣从团盐棚来到了盐埠头。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_windmill-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了风车埠。她办妥了任务「苫盖盐垛的草席」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 柳拂衣从团盐棚来到了风车埠。
- facts: F1=柳拂衣从团盐棚来到了风车埠；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_windmill-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了风车埠。她办妥了任务「苫盖盐垛的草席」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 柳拂衣从团盐棚来到了风车埠。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_windmill-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 柳拂衣从团盐棚来到了风车埠。她办妥了任务「苫盖盐垛的草席」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 柳拂衣从团盐棚来到了风车埠。
- facts: F1=柳拂衣从团盐棚来到了风车埠；F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_liufuyi-c_windmill-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 柳拂衣从团盐棚来到了风车埠。她办妥了任务「苫盖盐垛的草席」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 柳拂衣从团盐棚来到了风车埠。
- facts: F2=柳拂衣完成了任务「苫盖盐垛的草席」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了老盐滩。他办妥了任务「盘点官仓的存盐」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F1=秦叔从官仓来到了老盐滩；F2=秦叔完成了任务「盘点官仓的存盐」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了老盐滩。他办妥了任务「盘点官仓的存盐」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了老盐滩。他办妥了任务「盘点官仓的存盐」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F1=秦叔从官仓来到了老盐滩；F2=秦叔完成了任务「盘点官仓的存盐」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了老盐滩。他办妥了任务「盘点官仓的存盐」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_wharf-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了盐埠头。秦叔办妥了任务「盘点官仓的存盐」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 秦叔从官仓来到了盐埠头。
- facts: F1=秦叔从官仓来到了盐埠头；F2=秦叔完成了任务「盘点官仓的存盐」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_wharf-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了盐埠头。秦叔办妥了任务「盘点官仓的存盐」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 秦叔从官仓来到了盐埠头。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_wharf-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了盐埠头。秦叔办妥了任务「盘点官仓的存盐」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 秦叔从官仓来到了盐埠头。
- facts: F1=秦叔从官仓来到了盐埠头；F2=秦叔完成了任务「盘点官仓的存盐」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_wharf-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了盐埠头。秦叔办妥了任务「盘点官仓的存盐」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 秦叔从官仓来到了盐埠头。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_windmill-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了风车埠。他办妥了任务「盘点官仓的存盐」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从官仓来到了风车埠。
- facts: F1=秦叔从官仓来到了风车埠；F2=秦叔完成了任务「盘点官仓的存盐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_windmill-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了风车埠。他办妥了任务「盘点官仓的存盐」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从官仓来到了风车埠。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_windmill-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了风车埠。他办妥了任务「盘点官仓的存盐」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从官仓来到了风车埠。
- facts: F1=秦叔从官仓来到了风车埠；F2=秦叔完成了任务「盘点官仓的存盐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_a-c_windmill-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了风车埠。他办妥了任务「盘点官仓的存盐」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从官仓来到了风车埠。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了老盐滩。他办妥了任务「码好盐埠头的盐包」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从盐埠头来到了老盐滩。
- facts: F1=秦叔从盐埠头来到了老盐滩；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了老盐滩。他办妥了任务「码好盐埠头的盐包」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从盐埠头来到了老盐滩。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了老盐滩。他办妥了任务「码好盐埠头的盐包」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从盐埠头来到了老盐滩。
- facts: F1=秦叔从盐埠头来到了老盐滩；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了老盐滩。他办妥了任务「码好盐埠头的盐包」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 秦叔从盐埠头来到了老盐滩。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了官仓。秦叔办妥了任务「码好盐埠头的盐包」。三分钟过去了，秦叔已在官仓。
- candidate: 秦叔从盐埠头来到了官仓。
- facts: F1=秦叔从盐埠头来到了官仓；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了官仓。秦叔办妥了任务「码好盐埠头的盐包」。三分钟过去了，秦叔已在官仓。
- candidate: 秦叔从盐埠头来到了官仓。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了官仓。秦叔办妥了任务「码好盐埠头的盐包」。五分钟过去了，秦叔已在官仓。
- candidate: 秦叔从盐埠头来到了官仓。
- facts: F1=秦叔从盐埠头来到了官仓；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了官仓。秦叔办妥了任务「码好盐埠头的盐包」。五分钟过去了，秦叔已在官仓。
- candidate: 秦叔从盐埠头来到了官仓。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_windmill-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了风车埠。他办妥了任务「码好盐埠头的盐包」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从盐埠头来到了风车埠。
- facts: F1=秦叔从盐埠头来到了风车埠；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_windmill-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了风车埠。他办妥了任务「码好盐埠头的盐包」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从盐埠头来到了风车埠。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_windmill-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从盐埠头来到了风车埠。他办妥了任务「码好盐埠头的盐包」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从盐埠头来到了风车埠。
- facts: F1=秦叔从盐埠头来到了风车埠；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_qinshu_b-c_windmill-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从盐埠头来到了风车埠。他办妥了任务「码好盐埠头的盐包」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 秦叔从盐埠头来到了风车埠。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了官仓。他办妥了任务「收拢三畦盐卤」。三分钟过去了，秦叔已在官仓。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了官仓。他办妥了任务「收拢三畦盐卤」。三分钟过去了，秦叔已在官仓。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了官仓。他办妥了任务「收拢三畦盐卤」。五分钟过去了，秦叔已在官仓。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了官仓。他办妥了任务「收拢三畦盐卤」。五分钟过去了，秦叔已在官仓。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_wharf-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了盐埠头。他办妥了任务「收拢三畦盐卤」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 闻人镜从老盐滩来到了盐埠头。
- facts: F1=闻人镜从老盐滩来到了盐埠头；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_wharf-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了盐埠头。他办妥了任务「收拢三畦盐卤」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 闻人镜从老盐滩来到了盐埠头。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_wharf-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了盐埠头。他办妥了任务「收拢三畦盐卤」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 闻人镜从老盐滩来到了盐埠头。
- facts: F1=闻人镜从老盐滩来到了盐埠头；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_wharf-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了盐埠头。他办妥了任务「收拢三畦盐卤」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 闻人镜从老盐滩来到了盐埠头。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_windmill-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了风车埠。他办妥了任务「收拢三畦盐卤」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 闻人镜从老盐滩来到了风车埠。
- facts: F1=闻人镜从老盐滩来到了风车埠；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_windmill-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了风车埠。他办妥了任务「收拢三畦盐卤」。小满已在风车埠。三分钟过去了，盐伯已在风车埠。
- candidate: 闻人镜从老盐滩来到了风车埠。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_windmill-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了风车埠。他办妥了任务「收拢三畦盐卤」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 闻人镜从老盐滩来到了风车埠。
- facts: F1=闻人镜从老盐滩来到了风车埠；F2=闻人镜完成了任务「收拢三畦盐卤」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_wenrenjing-c_windmill-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了风车埠。他办妥了任务「收拢三畦盐卤」。小满已在风车埠。五分钟过去了，盐伯已在风车埠。
- candidate: 闻人镜从老盐滩来到了风车埠。
- facts: F2=闻人镜完成了任务「收拢三畦盐卤」；F3=小满已在风车埠；F4=盐伯已在风车埠；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了老盐滩。TA办妥了任务「给风车上油」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 小满从风车埠来到了老盐滩。
- facts: F1=小满从风车埠来到了老盐滩；F2=小满完成了任务「给风车上油」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了老盐滩。TA办妥了任务「给风车上油」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 小满从风车埠来到了老盐滩。
- facts: F2=小满完成了任务「给风车上油」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了老盐滩。TA办妥了任务「给风车上油」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 小满从风车埠来到了老盐滩。
- facts: F1=小满从风车埠来到了老盐滩；F2=小满完成了任务「给风车上油」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了老盐滩。TA办妥了任务「给风车上油」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 小满从风车埠来到了老盐滩。
- facts: F2=小满完成了任务「给风车上油」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。三分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F1=小满从风车埠来到了官仓；F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。三分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。五分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F1=小满从风车埠来到了官仓；F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。五分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_wharf-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了盐埠头。TA办妥了任务「给风车上油」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 小满从风车埠来到了盐埠头。
- facts: F1=小满从风车埠来到了盐埠头；F2=小满完成了任务「给风车上油」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_wharf-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了盐埠头。TA办妥了任务「给风车上油」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 小满从风车埠来到了盐埠头。
- facts: F2=小满完成了任务「给风车上油」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_wharf-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了盐埠头。TA办妥了任务「给风车上油」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 小满从风车埠来到了盐埠头。
- facts: F1=小满从风车埠来到了盐埠头；F2=小满完成了任务「给风车上油」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_xiaoman-c_wharf-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了盐埠头。TA办妥了任务「给风车上油」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 小满从风车埠来到了盐埠头。
- facts: F2=小满完成了任务「给风车上油」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_flats-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了老盐滩。他办妥了任务「查看风车叶片」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 盐伯从风车埠来到了老盐滩。
- facts: F1=盐伯从风车埠来到了老盐滩；F2=盐伯完成了任务「查看风车叶片」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_flats-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了老盐滩。他办妥了任务「查看风车叶片」。三分钟过去了，闻人镜已在老盐滩。
- candidate: 盐伯从风车埠来到了老盐滩。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=闻人镜已在老盐滩；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_flats-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了老盐滩。他办妥了任务「查看风车叶片」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 盐伯从风车埠来到了老盐滩。
- facts: F1=盐伯从风车埠来到了老盐滩；F2=盐伯完成了任务「查看风车叶片」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_flats-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了老盐滩。他办妥了任务「查看风车叶片」。五分钟过去了，闻人镜已在老盐滩。
- candidate: 盐伯从风车埠来到了老盐滩。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=闻人镜已在老盐滩；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_granary-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了官仓。他办妥了任务「查看风车叶片」。三分钟过去了，秦叔已在官仓。
- candidate: 盐伯从风车埠来到了官仓。
- facts: F1=盐伯从风车埠来到了官仓；F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_granary-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了官仓。他办妥了任务「查看风车叶片」。三分钟过去了，秦叔已在官仓。
- candidate: 盐伯从风车埠来到了官仓。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在官仓；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_granary-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了官仓。他办妥了任务「查看风车叶片」。五分钟过去了，秦叔已在官仓。
- candidate: 盐伯从风车埠来到了官仓。
- facts: F1=盐伯从风车埠来到了官仓；F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_granary-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了官仓。他办妥了任务「查看风车叶片」。五分钟过去了，秦叔已在官仓。
- candidate: 盐伯从风车埠来到了官仓。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在官仓；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_wharf-3minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了盐埠头。他办妥了任务「查看风车叶片」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 盐伯从风车埠来到了盐埠头。
- facts: F1=盐伯从风车埠来到了盐埠头；F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_wharf-3minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了盐埠头。他办妥了任务「查看风车叶片」。秦叔已在盐埠头。三分钟过去了，阿葵已在盐埠头。
- candidate: 盐伯从风车埠来到了盐埠头。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_wharf-5minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 盐伯从风车埠来到了盐埠头。他办妥了任务「查看风车叶片」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 盐伯从风车埠来到了盐埠头。
- facts: F1=盐伯从风车埠来到了盐埠头；F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:core-move-task-c_yanbo-c_wharf-5minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 盐伯从风车埠来到了盐埠头。他办妥了任务「查看风车叶片」。秦叔已在盐埠头。五分钟过去了，阿葵已在盐埠头。
- candidate: 盐伯从风车埠来到了盐埠头。
- facts: F2=盐伯完成了任务「查看风车叶片」；F3=秦叔已在盐埠头；F4=阿葵已在盐埠头；F5=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:cross-reference-8minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了官仓。他的精神值从10涨到了14。八分钟过去了，秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=闻人镜的精神值从10升到了14；F3=秦叔完成了任务「盘点官仓的存盐」；F4=前后大约8分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:cross-reference-8minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了官仓。他的精神值从10涨到了14。八分钟过去了，秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F2=闻人镜的精神值从10升到了14；F3=秦叔完成了任务「盘点官仓的存盐」；F4=前后大约8分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:gender-unknown-7minute:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。七分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F1=小满从风车埠来到了官仓；F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约7分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:gender-unknown-7minute:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 小满从风车埠来到了官仓。TA办妥了任务「给风车上油」。七分钟过去了，秦叔已在官仓。
- candidate: 小满从风车埠来到了官仓。
- facts: F2=小满完成了任务「给风车上油」；F3=秦叔已在官仓；F4=前后大约7分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:group-order-0:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔从官仓来到了老盐滩。五分钟过去了，闻人镜完成了任务「封存团盐棚的盐垛」。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F1=秦叔从官仓来到了老盐滩；F2=闻人镜完成了任务「封存团盐棚的盐垛」；F3=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:group-order-0:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔从官仓来到了老盐滩。五分钟过去了，闻人镜完成了任务「封存团盐棚的盐垛」。
- candidate: 秦叔从官仓来到了老盐滩。
- facts: F2=闻人镜完成了任务「封存团盐棚的盐垛」；F3=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:new-subtask:v0:f1:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F2']
- full: 三分钟过去了，闻人镜完成了任务「收拢三畦盐卤」。他接到了新任务「先借到长梯」（隶属「收拢三畦盐卤」）。
- candidate: 他接到了新任务「先借到长梯」（隶属「收拢三畦盐卤」）。
- facts: F1=闻人镜完成了任务「收拢三畦盐卤」；F2=闻人镜接到了新任务「先借到长梯」（隶属「收拢三畦盐卤」）；F3=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:new-subtask:v0:f1:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 三分钟过去了，闻人镜完成了任务「收拢三畦盐卤」。他接到了新任务「先借到长梯」（隶属「收拢三畦盐卤」）。
- candidate: 他接到了新任务「先借到长梯」（隶属「收拢三畦盐卤」）。
- facts: F1=闻人镜完成了任务「收拢三畦盐卤」；F3=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:same-name:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 秦叔完成了任务「盘点官仓的存盐」。四分钟过去了，秦叔完成了任务「码好盐埠头的盐包」。
- candidate: 秦叔完成了任务「盘点官仓的存盐」。
- facts: F1=秦叔完成了任务「盘点官仓的存盐」；F2=秦叔完成了任务「码好盐埠头的盐包」；F3=前后大约4分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:same-name:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 秦叔完成了任务「盘点官仓的存盐」。四分钟过去了，秦叔完成了任务「码好盐埠头的盐包」。
- candidate: 秦叔完成了任务「盘点官仓的存盐」。
- facts: F2=秦叔完成了任务「码好盐埠头的盐包」；F3=前后大约4分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-lead-9:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F2']
- full: 前后大约九分钟。闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=前后大约9分钟；F2=闻人镜从老盐滩来到了官仓；F3=秦叔完成了任务「盘点官仓的存盐」
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-lead-9:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 前后大约九分钟。闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=前后大约9分钟；F3=秦叔完成了任务「盘点官仓的存盐」
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-mid-9:v0:f1:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F3']
- full: 九分钟过去了，闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。
- candidate: 秦叔完成了任务「盘点官仓的存盐」。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=前后大约9分钟；F3=秦叔完成了任务「盘点官仓的存盐」
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-mid-9:v0:f1:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 九分钟过去了，闻人镜从老盐滩来到了官仓。秦叔完成了任务「盘点官仓的存盐」。
- candidate: 秦叔完成了任务「盘点官仓的存盐」。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=前后大约9分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-tail-9:v0:f0:auth:sup
- split/category: confirm / general / authorization
- label: **supported**; gold: ['F1']
- full: 闻人镜从老盐滩来到了官仓。九分钟过去了，秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F1=闻人镜从老盐滩来到了官仓；F2=秦叔完成了任务「盘点官仓的存盐」；F3=前后大约9分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-c-salt:time-tail-9:v0:f0:auth:unsup
- split/category: confirm / general / authorization
- label: **unsupported**; gold: []
- full: 闻人镜从老盐滩来到了官仓。九分钟过去了，秦叔完成了任务「盘点官仓的存盐」。
- candidate: 闻人镜从老盐滩来到了官仓。
- facts: F2=秦叔完成了任务「盘点官仓的存盐」；F3=前后大约9分钟
- scene: 无
- visible: 无
- flags: none

### syn:background:auth:6:sup
- split/category: confirm / background / authorization
- label: **supported**; gold: ['S2']
- full: 浓雾里，沈川把木箱扶正。
- candidate: 浓雾里
- facts: F1=把木箱扶正
- scene: S1=夜；S2=浓雾
- visible: V1=木箱
- flags: none

### syn:background:auth:6:unsup
- split/category: confirm / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 浓雾里，沈川把木箱扶正。
- candidate: 浓雾里
- facts: F1=把木箱扶正
- scene: S1=夜
- visible: V1=木箱
- flags: none

### syn:background:stmt:confirm:sup
- split/category: confirm / background / statement
- label: **supported**; gold: ['S2']
- full: 浓雾里，韩青把石阶搬起。
- candidate: 浓雾里
- facts: F1=把石阶搬起
- scene: S1=夜；S2=浓雾
- visible: V1=石阶
- flags: none

### syn:background:stmt:confirm:unsup
- split/category: confirm / background / statement
- label: **unsupported**; gold: ['S2']
- full: 细雨里，韩青把石阶搬起。
- candidate: 细雨里
- facts: F1=把石阶搬起
- scene: S1=夜；S2=浓雾
- visible: V1=石阶
- flags: none

### syn:body:auth:6:sup
- split/category: confirm / body / authorization
- label: **supported**; gold: ['F1']
- full: 叶舟把石阶推开，袖口湿透。
- candidate: 袖口湿透
- facts: F1=袖口湿透；F2=把石阶推开
- scene: S1=夜
- visible: V1=石阶
- flags: none

### syn:body:auth:6:unsup
- split/category: confirm / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 叶舟把石阶推开，袖口湿透。
- candidate: 袖口湿透
- facts: F1=脸色发白；F2=把石阶推开
- scene: S1=夜
- visible: V1=石阶
- flags: none

### syn:body:stmt:confirm:sup
- split/category: confirm / body / statement
- label: **supported**; gold: ['F1']
- full: 江晚把竹筐拖回，指节发白。
- candidate: 指节发白
- facts: F1=指节发白；F2=把竹筐拖回
- scene: S1=夜
- visible: V1=竹筐
- flags: none

### syn:body:stmt:confirm:unsup
- split/category: confirm / body / statement
- label: **unsupported**; gold: ['F1']
- full: 江晚把竹筐拖回，掌心出汗。
- candidate: 掌心出汗
- facts: F1=指节发白；F2=把竹筐拖回
- scene: S1=夜
- visible: V1=竹筐
- flags: none

### syn:extra-action:auth:6:sup
- split/category: confirm / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 段禾把纸伞挂好。
- candidate: 段禾把纸伞挂好。
- facts: F1=把纸伞挂好
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:6:unsup
- split/category: confirm / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 段禾把纸伞挂好。
- candidate: 段禾把纸伞挂好。
- facts: F1=把纸伞收紧
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:confirm:sup
- split/category: confirm / extra-action / statement
- label: **supported**; gold: ['F1']
- full: 闻溪把木箱挂好。
- candidate: 把木箱挂好
- facts: F1=把木箱挂好
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:confirm:unsup
- split/category: confirm / extra-action / statement
- label: **unsupported**; gold: ['F1']
- full: 闻溪把木箱系紧。
- candidate: 把木箱系紧
- facts: F1=把木箱挂好
- scene: S1=夜
- visible: 无
- flags: none

### syn:uncertain:confirm
- split/category: confirm / uncertain / none
- label: **uncertain**; gold: ['S3']
- full: 棚下散着光，唐屿把铜灯系紧。
- candidate: 棚下散着光
- facts: F1=把铜灯系紧
- scene: S1=清晨；S2=薄雾；S3=棚下散光
- visible: V1=铜灯
- flags: none

### syn:visible-state:auth:6:sup
- split/category: confirm / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 纸灯笼已点亮，宋岚把门闩搬起。
- candidate: 纸灯笼已点亮
- facts: F1=把门闩搬起
- scene: S1=夜；S2=纸灯笼已点亮
- visible: V1=纸灯笼
- flags: none

### syn:visible-state:auth:6:unsup
- split/category: confirm / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 纸灯笼已点亮，宋岚把门闩搬起。
- candidate: 纸灯笼已点亮
- facts: F1=把门闩搬起
- scene: S1=夜
- visible: V1=纸灯笼
- flags: none

### syn:visible-state:stmt:confirm:sup
- split/category: confirm / visible-state / statement
- label: **supported**; gold: ['S2']
- full: 铜灯亮着，林渡把灯罩擦亮。
- candidate: 铜灯亮着
- facts: F1=把灯罩擦亮
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### syn:visible-state:stmt:confirm:unsup
- split/category: confirm / visible-state / statement
- label: **unsupported**; gold: ['S2']
- full: 铜灯熄了，林渡把灯罩擦亮。
- candidate: 铜灯熄了
- facts: F1=把灯罩擦亮
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### n5:v2-a-quay:core-move-task-a_ahe-a_dryyard-3minute:v0:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿禾从鱼行来到了晒场。她办妥了任务「清点鲞货」。陈九已在晒场。三分钟过去了，渔丸已在晒场。
- candidate: 阿禾从鱼行来到了晒场。
- facts: F1=阿禾从鱼行来到了晒场；F2=阿禾完成了任务「清点鲞货」；F3=陈九已在晒场；F4=渔丸已在晒场；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_ahe-a_dryyard-3minute:v0:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 阿禾从鱼行来到了晒场。她办妥了任务「清点鲞货」。陈九已在晒场。三分钟过去了，渔丸已在晒场。
- candidate: 阿禾从鱼行来到了晒场。
- facts: F2=阿禾完成了任务「清点鲞货」；F3=陈九已在晒场；F4=渔丸已在晒场；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_fishshop-2hour:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九离开了咸水澳，抵达了鱼行。他已达成任务「把咸鱼坯搬上晒场」。两小时过去了，阿禾已经在鱼行了。
- candidate: 陈九离开了咸水澳，抵达了鱼行。
- facts: F1=陈九从咸水澳来到了鱼行；F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_fishshop-2hour:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 陈九离开了咸水澳，抵达了鱼行。他已达成任务「把咸鱼坯搬上晒场」。两小时过去了，阿禾已经在鱼行了。
- candidate: 陈九离开了咸水澳，抵达了鱼行。
- facts: F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_stilt-90second:v2:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九从咸水澳进入了高脚棚。他完成了任务「把咸鱼坯搬上晒场」。水生已在高脚棚。九十秒过去了，三号帆已在高脚棚。
- candidate: 陈九从咸水澳进入了高脚棚。
- facts: F1=陈九从咸水澳来到了高脚棚；F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_stilt-90second:v2:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 陈九从咸水澳进入了高脚棚。他完成了任务「把咸鱼坯搬上晒场」。水生已在高脚棚。九十秒过去了，三号帆已在高脚棚。
- candidate: 陈九从咸水澳进入了高脚棚。
- facts: F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_quay-2hour:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九离开了晒场，抵达了咸水澳。陈九已达成任务「翻晒场上的鱼干」。顾北汀已经在咸水澳了。两小时过去了，陈九已经在咸水澳了。
- candidate: 陈九离开了晒场，抵达了咸水澳。
- facts: F1=陈九从晒场来到了咸水澳；F2=陈九完成了任务「翻晒场上的鱼干」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_quay-2hour:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 陈九离开了晒场，抵达了咸水澳。陈九已达成任务「翻晒场上的鱼干」。顾北汀已经在咸水澳了。两小时过去了，陈九已经在咸水澳了。
- candidate: 陈九离开了晒场，抵达了咸水澳。
- facts: F2=陈九完成了任务「翻晒场上的鱼干」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_gubeiting-a_fishshop-5minute:v0:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 顾北汀从咸水澳来到了鱼行。他办妥了任务「熬一锅灯油」。五分钟过去了，阿禾已在鱼行。
- candidate: 顾北汀从咸水澳来到了鱼行。
- facts: F1=顾北汀从咸水澳来到了鱼行；F2=顾北汀完成了任务「熬一锅灯油」；F3=阿禾已在鱼行；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_gubeiting-a_fishshop-5minute:v0:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 顾北汀从咸水澳来到了鱼行。他办妥了任务「熬一锅灯油」。五分钟过去了，阿禾已在鱼行。
- candidate: 顾北汀从咸水澳来到了鱼行。
- facts: F2=顾北汀完成了任务「熬一锅灯油」；F3=阿禾已在鱼行；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_fishshop-1hour:v2:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 海满从灯寮进入了鱼行。他完成了任务「给灯寮换灯芯」。一小时过去了，阿禾已在鱼行。
- candidate: 海满从灯寮进入了鱼行。
- facts: F1=海满从灯寮来到了鱼行；F2=海满完成了任务「给灯寮换灯芯」；F3=阿禾已在鱼行；F4=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_fishshop-1hour:v2:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 海满从灯寮进入了鱼行。他完成了任务「给灯寮换灯芯」。一小时过去了，阿禾已在鱼行。
- candidate: 海满从灯寮进入了鱼行。
- facts: F2=海满完成了任务「给灯寮换灯芯」；F3=阿禾已在鱼行；F4=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_stilt-2hour:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 海满离开了灯寮，抵达了高脚棚。他已达成任务「给灯寮换灯芯」。水生已经在高脚棚了。两小时过去了，三号帆已经在高脚棚了。
- candidate: 海满离开了灯寮，抵达了高脚棚。
- facts: F1=海满从灯寮来到了高脚棚；F2=海满完成了任务「给灯寮换灯芯」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_stilt-2hour:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 海满离开了灯寮，抵达了高脚棚。他已达成任务「给灯寮换灯芯」。水生已经在高脚棚了。两小时过去了，三号帆已经在高脚棚了。
- candidate: 海满离开了灯寮，抵达了高脚棚。
- facts: F2=海满完成了任务「给灯寮换灯芯」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_shuisheng-a_quay-12minute:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 水生离开了高脚棚，抵达了咸水澳。TA已达成任务「修高脚棚的梯子」。顾北汀已经在咸水澳了。十二分钟过去了，陈九已经在咸水澳了。
- candidate: 水生离开了高脚棚，抵达了咸水澳。
- facts: F1=水生从高脚棚来到了咸水澳；F2=水生完成了任务「修高脚棚的梯子」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约12分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_shuisheng-a_quay-12minute:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 水生离开了高脚棚，抵达了咸水澳。TA已达成任务「修高脚棚的梯子」。顾北汀已经在咸水澳了。十二分钟过去了，陈九已经在咸水澳了。
- candidate: 水生离开了高脚棚，抵达了咸水澳。
- facts: F2=水生完成了任务「修高脚棚的梯子」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约12分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_fishshop-90second:v2:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 渔丸从晒场进入了鱼行。她完成了任务「缝补晒场的苫布」。九十秒过去了，阿禾已在鱼行。
- candidate: 渔丸从晒场进入了鱼行。
- facts: F1=渔丸从晒场来到了鱼行；F2=渔丸完成了任务「缝补晒场的苫布」；F3=阿禾已在鱼行；F4=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_fishshop-90second:v2:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 渔丸从晒场进入了鱼行。她完成了任务「缝补晒场的苫布」。九十秒过去了，阿禾已在鱼行。
- candidate: 渔丸从晒场进入了鱼行。
- facts: F2=渔丸完成了任务「缝补晒场的苫布」；F3=阿禾已在鱼行；F4=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:gender-unknown-25minute:v0:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 水生从高脚棚来到了鱼行。TA办妥了任务「修高脚棚的梯子」。二十五分钟过去了，阿禾已在鱼行。
- candidate: 水生从高脚棚来到了鱼行。
- facts: F1=水生从高脚棚来到了鱼行；F2=水生完成了任务「修高脚棚的梯子」；F3=阿禾已在鱼行；F4=前后大约25分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:gender-unknown-25minute:v0:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 水生从高脚棚来到了鱼行。TA办妥了任务「修高脚棚的梯子」。二十五分钟过去了，阿禾已在鱼行。
- candidate: 水生从高脚棚来到了鱼行。
- facts: F2=水生完成了任务「修高脚棚的梯子」；F3=阿禾已在鱼行；F4=前后大约25分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_douzi-b_post-3minute:v0:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 豆子从后山道来到了青枫驿。他办妥了任务「背柴到后山道茶灶」。沈书白已在青枫驿。三分钟过去了，双喜已在青枫驿。
- candidate: 豆子从后山道来到了青枫驿。
- facts: F1=豆子从后山道来到了青枫驿；F2=豆子完成了任务「背柴到后山道茶灶」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_douzi-b_post-3minute:v0:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 豆子从后山道来到了青枫驿。他办妥了任务「背柴到后山道茶灶」。沈书白已在青枫驿。三分钟过去了，双喜已在青枫驿。
- candidate: 豆子从后山道来到了青枫驿。
- facts: F2=豆子完成了任务「背柴到后山道茶灶」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_guyu-b_pass-40second:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 谷雨离开了茶灶房，抵达了碑坳。她已达成任务「烫一壶接风酒」。刘金已经在碑坳了。四十秒过去了，雁七已经在碑坳了。
- candidate: 谷雨离开了茶灶房，抵达了碑坳。
- facts: F1=谷雨从茶灶房来到了碑坳；F2=谷雨完成了任务「烫一壶接风酒」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_guyu-b_pass-40second:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 谷雨离开了茶灶房，抵达了碑坳。她已达成任务「烫一壶接风酒」。刘金已经在碑坳了。四十秒过去了，雁七已经在碑坳了。
- candidate: 谷雨离开了茶灶房，抵达了碑坳。
- facts: F2=谷雨完成了任务「烫一壶接风酒」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_post-2hour:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 刘金离开了马厩，抵达了青枫驿。他已达成任务「钉牢马厩门轴」。沈书白已经在青枫驿了。两小时过去了，双喜已经在青枫驿了。
- candidate: 刘金离开了马厩，抵达了青枫驿。
- facts: F1=刘金从马厩来到了青枫驿；F2=刘金完成了任务「钉牢马厩门轴」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_post-2hour:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 刘金离开了马厩，抵达了青枫驿。他已达成任务「钉牢马厩门轴」。沈书白已经在青枫驿了。两小时过去了，双喜已经在青枫驿了。
- candidate: 刘金离开了马厩，抵达了青枫驿。
- facts: F2=刘金完成了任务「钉牢马厩门轴」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_b-b_backhill-40second:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 刘金离开了碑坳，抵达了后山道。他已达成任务「清点碑坳的路签」。四十秒过去了，豆子已经在后山道了。
- candidate: 刘金离开了碑坳，抵达了后山道。
- facts: F1=刘金从碑坳来到了后山道；F2=刘金完成了任务「清点碑坳的路签」；F3=豆子已在后山道；F4=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_b-b_backhill-40second:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 刘金离开了碑坳，抵达了后山道。他已达成任务「清点碑坳的路签」。四十秒过去了，豆子已经在后山道了。
- candidate: 刘金离开了碑坳，抵达了后山道。
- facts: F2=刘金完成了任务「清点碑坳的路签」；F3=豆子已在后山道；F4=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shenshubai-b_kitchen-2hour:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 沈书白离开了青枫驿，抵达了茶灶房。他已达成任务「封发驿传文书」。谷雨已经在茶灶房了。两小时过去了，铜汤婆子已经在茶灶房了。
- candidate: 沈书白离开了青枫驿，抵达了茶灶房。
- facts: F1=沈书白从青枫驿来到了茶灶房；F2=沈书白完成了任务「封发驿传文书」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shenshubai-b_kitchen-2hour:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 沈书白离开了青枫驿，抵达了茶灶房。他已达成任务「封发驿传文书」。谷雨已经在茶灶房了。两小时过去了，铜汤婆子已经在茶灶房了。
- candidate: 沈书白离开了青枫驿，抵达了茶灶房。
- facts: F2=沈书白完成了任务「封发驿传文书」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_kitchen-15minute:v2:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 双喜从青枫驿进入了茶灶房。TA完成了任务「扫净正堂灯火」。谷雨已在茶灶房。十五分钟过去了，铜汤婆子已在茶灶房。
- candidate: 双喜从青枫驿进入了茶灶房。
- facts: F1=双喜从青枫驿来到了茶灶房；F2=双喜完成了任务「扫净正堂灯火」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_kitchen-15minute:v2:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 双喜从青枫驿进入了茶灶房。TA完成了任务「扫净正堂灯火」。谷雨已在茶灶房。十五分钟过去了，铜汤婆子已在茶灶房。
- candidate: 双喜从青枫驿进入了茶灶房。
- facts: F2=双喜完成了任务「扫净正堂灯火」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_pass-3minute:v0:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 双喜从青枫驿来到了碑坳。TA办妥了任务「扫净正堂灯火」。刘金已在碑坳。三分钟过去了，雁七已在碑坳。
- candidate: 双喜从青枫驿来到了碑坳。
- facts: F1=双喜从青枫驿来到了碑坳；F2=双喜完成了任务「扫净正堂灯火」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_pass-3minute:v0:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 双喜从青枫驿来到了碑坳。TA办妥了任务「扫净正堂灯火」。刘金已在碑坳。三分钟过去了，雁七已在碑坳。
- candidate: 双喜从青枫驿来到了碑坳。
- facts: F2=双喜完成了任务「扫净正堂灯火」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_weituo-b_kitchen-40second:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 魏驼离开了马厩，抵达了茶灶房。他已达成任务「铡足三日草料」。谷雨已经在茶灶房了。四十秒过去了，铜汤婆子已经在茶灶房了。
- candidate: 魏驼离开了马厩，抵达了茶灶房。
- facts: F1=魏驼从马厩来到了茶灶房；F2=魏驼完成了任务「铡足三日草料」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_weituo-b_kitchen-40second:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 魏驼离开了马厩，抵达了茶灶房。他已达成任务「铡足三日草料」。谷雨已经在茶灶房了。四十秒过去了，铜汤婆子已经在茶灶房了。
- candidate: 魏驼离开了马厩，抵达了茶灶房。
- facts: F2=魏驼完成了任务「铡足三日草料」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_yanqi-b_kitchen-15minute:v2:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 雁七从碑坳进入了茶灶房。她完成了任务「核对碑坳的路条」。谷雨已在茶灶房。十五分钟过去了，铜汤婆子已在茶灶房。
- candidate: 雁七从碑坳进入了茶灶房。
- facts: F1=雁七从碑坳来到了茶灶房；F2=雁七完成了任务「核对碑坳的路条」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_yanqi-b_kitchen-15minute:v2:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 雁七从碑坳进入了茶灶房。她完成了任务「核对碑坳的路条」。谷雨已在茶灶房。十五分钟过去了，铜汤婆子已在茶灶房。
- candidate: 雁七从碑坳进入了茶灶房。
- facts: F2=雁七完成了任务「核对碑坳的路条」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:group-order-1:v1:f0:auth:sup
- split/category: dev / general / authorization
- label: **supported**; gold: ['F1']
- full: 谷雨离开了茶灶房，抵达了青枫驿。沈书白办妥了任务「换左辕马的掌」。五分钟过去了，双喜已经在青枫驿了。
- candidate: 谷雨离开了茶灶房，抵达了青枫驿。
- facts: F1=谷雨从茶灶房来到了青枫驿；F2=沈书白完成了任务「换左辕马的掌」；F3=双喜已在青枫驿；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:group-order-1:v1:f0:auth:unsup
- split/category: dev / general / authorization
- label: **unsupported**; gold: []
- full: 谷雨离开了茶灶房，抵达了青枫驿。沈书白办妥了任务「换左辕马的掌」。五分钟过去了，双喜已经在青枫驿了。
- candidate: 谷雨离开了茶灶房，抵达了青枫驿。
- facts: F2=沈书白完成了任务「换左辕马的掌」；F3=双喜已在青枫驿；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### syn:background:auth:4:sup
- split/category: dev / background / authorization
- label: **supported**; gold: ['S2']
- full: 夜雾里，韩青把鱼筐搬起。
- candidate: 夜雾里
- facts: F1=把鱼筐搬起
- scene: S1=夜；S2=夜雾
- visible: V1=鱼筐
- flags: none

### syn:background:auth:4:unsup
- split/category: dev / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 夜雾里，韩青把鱼筐搬起。
- candidate: 夜雾里
- facts: F1=把鱼筐搬起
- scene: S1=夜
- visible: V1=鱼筐
- flags: none

### syn:background:auth:5:sup
- split/category: dev / background / authorization
- label: **supported**; gold: ['S2']
- full: 雨后，温砚把麻绳系紧。
- candidate: 雨后
- facts: F1=把麻绳系紧
- scene: S1=夜；S2=雨后
- visible: V1=麻绳
- flags: none

### syn:background:auth:5:unsup
- split/category: dev / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 雨后，温砚把麻绳系紧。
- candidate: 雨后
- facts: F1=把麻绳系紧
- scene: S1=夜
- visible: V1=麻绳
- flags: none

### syn:background:stmt:dev:sup
- split/category: dev / background / statement
- label: **supported**; gold: ['S2']
- full: 浓雾里，许棠把铜灯收紧。
- candidate: 浓雾里
- facts: F1=把铜灯收紧
- scene: S1=夜；S2=浓雾
- visible: V1=铜灯
- flags: none

### syn:background:stmt:dev:unsup
- split/category: dev / background / statement
- label: **unsupported**; gold: ['S2']
- full: 细雨里，许棠把铜灯收紧。
- candidate: 细雨里
- facts: F1=把铜灯收紧
- scene: S1=夜；S2=浓雾
- visible: V1=铜灯
- flags: none

### syn:body:auth:4:sup
- split/category: dev / body / authorization
- label: **supported**; gold: ['F1']
- full: 白棠把纸伞扶正，肩头落着灰。
- candidate: 肩头落着灰
- facts: F1=肩头落着灰；F2=把纸伞扶正
- scene: S1=夜
- visible: V1=纸伞
- flags: none

### syn:body:auth:4:unsup
- split/category: dev / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 白棠把纸伞扶正，肩头落着灰。
- candidate: 肩头落着灰
- facts: F1=指节发白；F2=把纸伞扶正
- scene: S1=夜
- visible: V1=纸伞
- flags: none

### syn:body:auth:5:sup
- split/category: dev / body / authorization
- label: **supported**; gold: ['F1']
- full: 顾临把铜灯擦亮，手背蹭破皮。
- candidate: 手背蹭破皮
- facts: F1=手背蹭破皮；F2=把铜灯擦亮
- scene: S1=夜
- visible: V1=铜灯
- flags: none

### syn:body:auth:5:unsup
- split/category: dev / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 顾临把铜灯擦亮，手背蹭破皮。
- candidate: 手背蹭破皮
- facts: F1=掌心出汗；F2=把铜灯擦亮
- scene: S1=夜
- visible: V1=铜灯
- flags: none

### syn:body:stmt:dev:sup
- split/category: dev / body / statement
- label: **supported**; gold: ['F1']
- full: 叶舟把木箱推开，指节发白。
- candidate: 指节发白
- facts: F1=指节发白；F2=把木箱推开
- scene: S1=夜
- visible: V1=木箱
- flags: none

### syn:body:stmt:dev:unsup
- split/category: dev / body / statement
- label: **unsupported**; gold: ['F1']
- full: 叶舟把木箱推开，掌心出汗。
- candidate: 掌心出汗
- facts: F1=指节发白；F2=把木箱推开
- scene: S1=夜
- visible: V1=木箱
- flags: none

### syn:extra-action:auth:4:sup
- split/category: dev / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 罗川把木箱推开。
- candidate: 罗川把木箱推开。
- facts: F1=把木箱推开
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:4:unsup
- split/category: dev / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 罗川把木箱推开。
- candidate: 罗川把木箱推开。
- facts: F1=把木箱拖回
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:5:sup
- split/category: dev / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 邵宁把竹筐拖回。
- candidate: 邵宁把竹筐拖回。
- facts: F1=把竹筐拖回
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:5:unsup
- split/category: dev / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 邵宁把竹筐拖回。
- candidate: 邵宁把竹筐拖回。
- facts: F1=把竹筐挂好
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:dev:sup
- split/category: dev / extra-action / statement
- label: **supported**; gold: ['F1']
- full: 商陆把麻绳拖回。
- candidate: 把麻绳拖回
- facts: F1=把麻绳拖回
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:dev:unsup
- split/category: dev / extra-action / statement
- label: **unsupported**; gold: ['F1']
- full: 商陆把麻绳搬起。
- candidate: 把麻绳搬起
- facts: F1=把麻绳拖回
- scene: S1=夜
- visible: 无
- flags: none

### syn:visible-state:auth:4:sup
- split/category: dev / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 风灯已点亮，闻溪把石阶挂好。
- candidate: 风灯已点亮
- facts: F1=把石阶挂好
- scene: S1=夜；S2=风灯已点亮
- visible: V1=风灯
- flags: none

### syn:visible-state:auth:4:unsup
- split/category: dev / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 风灯已点亮，闻溪把石阶挂好。
- candidate: 风灯已点亮
- facts: F1=把石阶挂好
- scene: S1=夜
- visible: V1=风灯
- flags: none

### syn:visible-state:auth:5:sup
- split/category: dev / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 铜灯已点亮，裴照把缆绳收紧。
- candidate: 铜灯已点亮
- facts: F1=把缆绳收紧
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### syn:visible-state:auth:5:unsup
- split/category: dev / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 铜灯已点亮，裴照把缆绳收紧。
- candidate: 铜灯已点亮
- facts: F1=把缆绳收紧
- scene: S1=夜
- visible: V1=铜灯
- flags: none

### syn:visible-state:stmt:dev:sup
- split/category: dev / visible-state / statement
- label: **supported**; gold: ['S2']
- full: 铜灯亮着，沈川把门闩扶正。
- candidate: 铜灯亮着
- facts: F1=把门闩扶正
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### syn:visible-state:stmt:dev:unsup
- split/category: dev / visible-state / statement
- label: **unsupported**; gold: ['S2']
- full: 铜灯熄了，沈川把门闩扶正。
- candidate: 铜灯熄了
- facts: F1=把门闩扶正
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### n5:v2-a-quay:alternating-20minute:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 顾北汀从咸水澳来到了鱼行。阿禾完成了任务「清点鲞货」。二十分钟过去了，陈九从咸水澳来到了鱼行。
- candidate: 顾北汀从咸水澳来到了鱼行。
- facts: F1=顾北汀从咸水澳来到了鱼行；F2=阿禾完成了任务「清点鲞货」；F3=陈九从咸水澳来到了鱼行；F4=前后大约20分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:alternating-20minute:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 顾北汀从咸水澳来到了鱼行。阿禾完成了任务「清点鲞货」。二十分钟过去了，陈九从咸水澳来到了鱼行。
- candidate: 顾北汀从咸水澳来到了鱼行。
- facts: F2=阿禾完成了任务「清点鲞货」；F3=陈九从咸水澳来到了鱼行；F4=前后大约20分钟
- scene: 无
- visible: 无
- flags: residual-overlap:F3:0.73

### n5:v2-a-quay:core-move-task-a_ahe-a_quay-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 阿禾离开了鱼行，抵达了咸水澳。她已达成任务「清点鲞货」。顾北汀已经在咸水澳了。两小时过去了，陈九已经在咸水澳了。
- candidate: 阿禾离开了鱼行，抵达了咸水澳。
- facts: F1=阿禾从鱼行来到了咸水澳；F2=阿禾完成了任务「清点鲞货」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_ahe-a_quay-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 阿禾离开了鱼行，抵达了咸水澳。她已达成任务「清点鲞货」。顾北汀已经在咸水澳了。两小时过去了，陈九已经在咸水澳了。
- candidate: 阿禾离开了鱼行，抵达了咸水澳。
- facts: F2=阿禾完成了任务「清点鲞货」；F3=顾北汀已在咸水澳；F4=陈九已在咸水澳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_fishshop-1hour:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九从咸水澳进入了鱼行。他完成了任务「把咸鱼坯搬上晒场」。一小时过去了，阿禾已在鱼行。
- candidate: 陈九从咸水澳进入了鱼行。
- facts: F1=陈九从咸水澳来到了鱼行；F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=阿禾已在鱼行；F4=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_a-a_fishshop-1hour:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 陈九从咸水澳进入了鱼行。他完成了任务「把咸鱼坯搬上晒场」。一小时过去了，阿禾已在鱼行。
- candidate: 陈九从咸水澳进入了鱼行。
- facts: F2=陈九完成了任务「把咸鱼坯搬上晒场」；F3=阿禾已在鱼行；F4=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_fishshop-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九离开了晒场，抵达了鱼行。他已达成任务「翻晒场上的鱼干」。两小时过去了，阿禾已经在鱼行了。
- candidate: 陈九离开了晒场，抵达了鱼行。
- facts: F1=陈九从晒场来到了鱼行；F2=陈九完成了任务「翻晒场上的鱼干」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_fishshop-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 陈九离开了晒场，抵达了鱼行。他已达成任务「翻晒场上的鱼干」。两小时过去了，阿禾已经在鱼行了。
- candidate: 陈九离开了晒场，抵达了鱼行。
- facts: F2=陈九完成了任务「翻晒场上的鱼干」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_stilt-3minute:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 陈九从晒场来到了高脚棚。他办妥了任务「翻晒场上的鱼干」。水生已在高脚棚。三分钟过去了，三号帆已在高脚棚。
- candidate: 陈九从晒场来到了高脚棚。
- facts: F1=陈九从晒场来到了高脚棚；F2=陈九完成了任务「翻晒场上的鱼干」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_chenjiu_b-a_stilt-3minute:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 陈九从晒场来到了高脚棚。他办妥了任务「翻晒场上的鱼干」。水生已在高脚棚。三分钟过去了，三号帆已在高脚棚。
- candidate: 陈九从晒场来到了高脚棚。
- facts: F2=陈九完成了任务「翻晒场上的鱼干」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_gubeiting-a_lamp-90second:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 顾北汀从咸水澳进入了灯寮。他完成了任务「熬一锅灯油」。海满已在灯寮。九十秒过去了，灯油瓮已在灯寮。
- candidate: 顾北汀从咸水澳进入了灯寮。
- facts: F1=顾北汀从咸水澳来到了灯寮；F2=顾北汀完成了任务「熬一锅灯油」；F3=海满已在灯寮；F4=灯油瓮已在灯寮；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_gubeiting-a_lamp-90second:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 顾北汀从咸水澳进入了灯寮。他完成了任务「熬一锅灯油」。海满已在灯寮。九十秒过去了，灯油瓮已在灯寮。
- candidate: 顾北汀从咸水澳进入了灯寮。
- facts: F2=顾北汀完成了任务「熬一锅灯油」；F3=海满已在灯寮；F4=灯油瓮已在灯寮；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_fishshop-5minute:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 海满从灯寮来到了鱼行。他办妥了任务「给灯寮换灯芯」。五分钟过去了，阿禾已在鱼行。
- candidate: 海满从灯寮来到了鱼行。
- facts: F1=海满从灯寮来到了鱼行；F2=海满完成了任务「给灯寮换灯芯」；F3=阿禾已在鱼行；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_haiman-a_fishshop-5minute:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 海满从灯寮来到了鱼行。他办妥了任务「给灯寮换灯芯」。五分钟过去了，阿禾已在鱼行。
- candidate: 海满从灯寮来到了鱼行。
- facts: F2=海满完成了任务「给灯寮换灯芯」；F3=阿禾已在鱼行；F4=前后大约5分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_shuisheng-a_fishshop-15minute:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 水生从高脚棚进入了鱼行。TA完成了任务「修高脚棚的梯子」。十五分钟过去了，阿禾已在鱼行。
- candidate: 水生从高脚棚进入了鱼行。
- facts: F1=水生从高脚棚来到了鱼行；F2=水生完成了任务「修高脚棚的梯子」；F3=阿禾已在鱼行；F4=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_shuisheng-a_fishshop-15minute:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 水生从高脚棚进入了鱼行。TA完成了任务「修高脚棚的梯子」。十五分钟过去了，阿禾已在鱼行。
- candidate: 水生从高脚棚进入了鱼行。
- facts: F2=水生完成了任务「修高脚棚的梯子」；F3=阿禾已在鱼行；F4=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_fishshop-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 渔丸离开了晒场，抵达了鱼行。她已达成任务「缝补晒场的苫布」。两小时过去了，阿禾已经在鱼行了。
- candidate: 渔丸离开了晒场，抵达了鱼行。
- facts: F1=渔丸从晒场来到了鱼行；F2=渔丸完成了任务「缝补晒场的苫布」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_fishshop-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 渔丸离开了晒场，抵达了鱼行。她已达成任务「缝补晒场的苫布」。两小时过去了，阿禾已经在鱼行了。
- candidate: 渔丸离开了晒场，抵达了鱼行。
- facts: F2=渔丸完成了任务「缝补晒场的苫布」；F3=阿禾已在鱼行；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_stilt-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 渔丸离开了晒场，抵达了高脚棚。她已达成任务「缝补晒场的苫布」。水生已经在高脚棚了。两小时过去了，三号帆已经在高脚棚了。
- candidate: 渔丸离开了晒场，抵达了高脚棚。
- facts: F1=渔丸从晒场来到了高脚棚；F2=渔丸完成了任务「缝补晒场的苫布」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-a-quay:core-move-task-a_yuwan-a_stilt-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 渔丸离开了晒场，抵达了高脚棚。她已达成任务「缝补晒场的苫布」。水生已经在高脚棚了。两小时过去了，三号帆已经在高脚棚了。
- candidate: 渔丸离开了晒场，抵达了高脚棚。
- facts: F2=渔丸完成了任务「缝补晒场的苫布」；F3=水生已在高脚棚；F4=三号帆已在高脚棚；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_douzi-b_kitchen-40second:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 豆子离开了后山道，抵达了茶灶房。他已达成任务「背柴到后山道茶灶」。谷雨已经在茶灶房了。四十秒过去了，铜汤婆子已经在茶灶房了。
- candidate: 豆子离开了后山道，抵达了茶灶房。
- facts: F1=豆子从后山道来到了茶灶房；F2=豆子完成了任务「背柴到后山道茶灶」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_douzi-b_kitchen-40second:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 豆子离开了后山道，抵达了茶灶房。他已达成任务「背柴到后山道茶灶」。谷雨已经在茶灶房了。四十秒过去了，铜汤婆子已经在茶灶房了。
- candidate: 豆子离开了后山道，抵达了茶灶房。
- facts: F2=豆子完成了任务「背柴到后山道茶灶」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约40秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_guyu-b_backhill-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 谷雨离开了茶灶房，抵达了后山道。她已达成任务「烫一壶接风酒」。两小时过去了，豆子已经在后山道了。
- candidate: 谷雨离开了茶灶房，抵达了后山道。
- facts: F1=谷雨从茶灶房来到了后山道；F2=谷雨完成了任务「烫一壶接风酒」；F3=豆子已在后山道；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_guyu-b_backhill-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 谷雨离开了茶灶房，抵达了后山道。她已达成任务「烫一壶接风酒」。两小时过去了，豆子已经在后山道了。
- candidate: 谷雨离开了茶灶房，抵达了后山道。
- facts: F2=谷雨完成了任务「烫一壶接风酒」；F3=豆子已在后山道；F4=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_backhill-3minute:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 刘金从马厩来到了后山道。他办妥了任务「钉牢马厩门轴」。三分钟过去了，豆子已在后山道。
- candidate: 刘金从马厩来到了后山道。
- facts: F1=刘金从马厩来到了后山道；F2=刘金完成了任务「钉牢马厩门轴」；F3=豆子已在后山道；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_backhill-3minute:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 刘金从马厩来到了后山道。他办妥了任务「钉牢马厩门轴」。三分钟过去了，豆子已在后山道。
- candidate: 刘金从马厩来到了后山道。
- facts: F2=刘金完成了任务「钉牢马厩门轴」；F3=豆子已在后山道；F4=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_post-1hour:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 刘金从马厩进入了青枫驿。他完成了任务「钉牢马厩门轴」。沈书白已在青枫驿。一小时过去了，双喜已在青枫驿。
- candidate: 刘金从马厩进入了青枫驿。
- facts: F1=刘金从马厩来到了青枫驿；F2=刘金完成了任务「钉牢马厩门轴」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_a-b_post-1hour:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 刘金从马厩进入了青枫驿。他完成了任务「钉牢马厩门轴」。沈书白已在青枫驿。一小时过去了，双喜已在青枫驿。
- candidate: 刘金从马厩进入了青枫驿。
- facts: F2=刘金完成了任务「钉牢马厩门轴」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约1小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_b-b_post-90second:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 刘金从碑坳进入了青枫驿。他完成了任务「清点碑坳的路签」。沈书白已在青枫驿。九十秒过去了，双喜已在青枫驿。
- candidate: 刘金从碑坳进入了青枫驿。
- facts: F1=刘金从碑坳来到了青枫驿；F2=刘金完成了任务「清点碑坳的路签」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_liujin_b-b_post-90second:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 刘金从碑坳进入了青枫驿。他完成了任务「清点碑坳的路签」。沈书白已在青枫驿。九十秒过去了，双喜已在青枫驿。
- candidate: 刘金从碑坳进入了青枫驿。
- facts: F2=刘金完成了任务「清点碑坳的路签」；F3=沈书白已在青枫驿；F4=双喜已在青枫驿；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shenshubai-b_kitchen-90second:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 沈书白从青枫驿进入了茶灶房。他完成了任务「封发驿传文书」。谷雨已在茶灶房。九十秒过去了，铜汤婆子已在茶灶房。
- candidate: 沈书白从青枫驿进入了茶灶房。
- facts: F1=沈书白从青枫驿来到了茶灶房；F2=沈书白完成了任务「封发驿传文书」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shenshubai-b_kitchen-90second:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 沈书白从青枫驿进入了茶灶房。他完成了任务「封发驿传文书」。谷雨已在茶灶房。九十秒过去了，铜汤婆子已在茶灶房。
- candidate: 沈书白从青枫驿进入了茶灶房。
- facts: F2=沈书白完成了任务「封发驿传文书」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约90秒
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_pass-15minute:v2:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 双喜从青枫驿进入了碑坳。TA完成了任务「扫净正堂灯火」。刘金已在碑坳。十五分钟过去了，雁七已在碑坳。
- candidate: 双喜从青枫驿进入了碑坳。
- facts: F1=双喜从青枫驿来到了碑坳；F2=双喜完成了任务「扫净正堂灯火」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_shuangxi-b_pass-15minute:v2:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 双喜从青枫驿进入了碑坳。TA完成了任务「扫净正堂灯火」。刘金已在碑坳。十五分钟过去了，雁七已在碑坳。
- candidate: 双喜从青枫驿进入了碑坳。
- facts: F2=双喜完成了任务「扫净正堂灯火」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约15分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_weituo-b_pass-2hour:v1:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 魏驼离开了马厩，抵达了碑坳。他已达成任务「铡足三日草料」。刘金已经在碑坳了。两小时过去了，雁七已经在碑坳了。
- candidate: 魏驼离开了马厩，抵达了碑坳。
- facts: F1=魏驼从马厩来到了碑坳；F2=魏驼完成了任务「铡足三日草料」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_weituo-b_pass-2hour:v1:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 魏驼离开了马厩，抵达了碑坳。他已达成任务「铡足三日草料」。刘金已经在碑坳了。两小时过去了，雁七已经在碑坳了。
- candidate: 魏驼离开了马厩，抵达了碑坳。
- facts: F2=魏驼完成了任务「铡足三日草料」；F3=刘金已在碑坳；F4=雁七已在碑坳；F5=前后大约2小时
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_yanqi-b_kitchen-3minute:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 雁七从碑坳来到了茶灶房。她办妥了任务「核对碑坳的路条」。谷雨已在茶灶房。三分钟过去了，铜汤婆子已在茶灶房。
- candidate: 雁七从碑坳来到了茶灶房。
- facts: F1=雁七从碑坳来到了茶灶房；F2=雁七完成了任务「核对碑坳的路条」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:core-move-task-b_yanqi-b_kitchen-3minute:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 雁七从碑坳来到了茶灶房。她办妥了任务「核对碑坳的路条」。谷雨已在茶灶房。三分钟过去了，铜汤婆子已在茶灶房。
- candidate: 雁七从碑坳来到了茶灶房。
- facts: F2=雁七完成了任务「核对碑坳的路条」；F3=谷雨已在茶灶房；F4=铜汤婆子已在茶灶房；F5=前后大约3分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:time-tail-9:v0:f0:auth:sup
- split/category: train / general / authorization
- label: **supported**; gold: ['F1']
- full: 沈书白从青枫驿来到了茶灶房。谷雨完成了任务「烫一壶接风酒」。九分钟过去了，铜汤婆子已在茶灶房。
- candidate: 沈书白从青枫驿来到了茶灶房。
- facts: F1=沈书白从青枫驿来到了茶灶房；F2=谷雨完成了任务「烫一壶接风酒」；F3=铜汤婆子已在茶灶房；F4=前后大约9分钟
- scene: 无
- visible: 无
- flags: none

### n5:v2-b-post:time-tail-9:v0:f0:auth:unsup
- split/category: train / general / authorization
- label: **unsupported**; gold: []
- full: 沈书白从青枫驿来到了茶灶房。谷雨完成了任务「烫一壶接风酒」。九分钟过去了，铜汤婆子已在茶灶房。
- candidate: 沈书白从青枫驿来到了茶灶房。
- facts: F2=谷雨完成了任务「烫一壶接风酒」；F3=铜汤婆子已在茶灶房；F4=前后大约9分钟
- scene: 无
- visible: 无
- flags: none

### syn:background:auth:1:sup
- split/category: train / background / authorization
- label: **supported**; gold: ['S2']
- full: 浓雾里，江晚把缆绳拖回。
- candidate: 浓雾里
- facts: F1=把缆绳拖回
- scene: S1=夜；S2=浓雾
- visible: V1=缆绳
- flags: none

### syn:background:auth:1:unsup
- split/category: train / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 浓雾里，江晚把缆绳拖回。
- candidate: 浓雾里
- facts: F1=把缆绳拖回
- scene: S1=夜
- visible: V1=缆绳
- flags: none

### syn:background:auth:2:sup
- split/category: train / background / authorization
- label: **supported**; gold: ['S2']
- full: 细雨里，程野把门闩挂好。
- candidate: 细雨里
- facts: F1=把门闩挂好
- scene: S1=夜；S2=细雨
- visible: V1=门闩
- flags: none

### syn:background:auth:2:unsup
- split/category: train / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 细雨里，程野把门闩挂好。
- candidate: 细雨里
- facts: F1=把门闩挂好
- scene: S1=夜
- visible: V1=门闩
- flags: none

### syn:background:auth:3:sup
- split/category: train / background / authorization
- label: **supported**; gold: ['S2']
- full: 薄雾里，许棠把灯罩收紧。
- candidate: 薄雾里
- facts: F1=把灯罩收紧
- scene: S1=夜；S2=薄雾
- visible: V1=灯罩
- flags: none

### syn:background:auth:3:unsup
- split/category: train / background / authorization
- label: **unsupported**; gold: ['S1']
- full: 薄雾里，许棠把灯罩收紧。
- candidate: 薄雾里
- facts: F1=把灯罩收紧
- scene: S1=夜
- visible: V1=灯罩
- flags: none

### syn:background:stmt:train:sup
- split/category: train / background / statement
- label: **supported**; gold: ['S2']
- full: 浓雾里，程野把纸伞挂好。
- candidate: 浓雾里
- facts: F1=把纸伞挂好
- scene: S1=夜；S2=浓雾
- visible: V1=纸伞
- flags: none

### syn:background:stmt:train:unsup
- split/category: train / background / statement
- label: **unsupported**; gold: ['S2']
- full: 细雨里，程野把纸伞挂好。
- candidate: 细雨里
- facts: F1=把纸伞挂好
- scene: S1=夜；S2=浓雾
- visible: V1=纸伞
- flags: none

### syn:body:auth:1:sup
- split/category: train / body / authorization
- label: **supported**; gold: ['F1']
- full: 祁岸把麻绳收紧，指节发白。
- candidate: 指节发白
- facts: F1=指节发白；F2=把麻绳收紧
- scene: S1=夜
- visible: V1=麻绳
- flags: none

### syn:body:auth:1:unsup
- split/category: train / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 祁岸把麻绳收紧，指节发白。
- candidate: 指节发白
- facts: F1=肩头落着灰；F2=把麻绳收紧
- scene: S1=夜
- visible: V1=麻绳
- flags: none

### syn:body:auth:2:sup
- split/category: train / body / authorization
- label: **supported**; gold: ['F1']
- full: 苏禾把木箱搬起，掌心出汗。
- candidate: 掌心出汗
- facts: F1=掌心出汗；F2=把木箱搬起
- scene: S1=夜
- visible: V1=木箱
- flags: none

### syn:body:auth:2:unsup
- split/category: train / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 苏禾把木箱搬起，掌心出汗。
- candidate: 掌心出汗
- facts: F1=手背蹭破皮；F2=把木箱搬起
- scene: S1=夜
- visible: V1=木箱
- flags: none

### syn:body:auth:3:sup
- split/category: train / body / authorization
- label: **supported**; gold: ['F1']
- full: 陆行把竹筐系紧，脸色发白。
- candidate: 脸色发白
- facts: F1=脸色发白；F2=把竹筐系紧
- scene: S1=夜
- visible: V1=竹筐
- flags: none

### syn:body:auth:3:unsup
- split/category: train / body / authorization
- label: **unsupported**; gold: ['F1']
- full: 陆行把竹筐系紧，脸色发白。
- candidate: 脸色发白
- facts: F1=袖口湿透；F2=把竹筐系紧
- scene: S1=夜
- visible: V1=竹筐
- flags: none

### syn:body:stmt:train:sup
- split/category: train / body / statement
- label: **supported**; gold: ['F1']
- full: 顾临把麻绳擦亮，指节发白。
- candidate: 指节发白
- facts: F1=指节发白；F2=把麻绳擦亮
- scene: S1=夜
- visible: V1=麻绳
- flags: none

### syn:body:stmt:train:unsup
- split/category: train / body / statement
- label: **unsupported**; gold: ['F1']
- full: 顾临把麻绳擦亮，掌心出汗。
- candidate: 掌心出汗
- facts: F1=指节发白；F2=把麻绳擦亮
- scene: S1=夜
- visible: V1=麻绳
- flags: none

### syn:extra-action:auth:1:sup
- split/category: train / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 唐屿把灯罩系紧。
- candidate: 唐屿把灯罩系紧。
- facts: F1=把灯罩系紧
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:1:unsup
- split/category: train / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 唐屿把灯罩系紧。
- candidate: 唐屿把灯罩系紧。
- facts: F1=把灯罩扶正
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:2:sup
- split/category: train / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 方序把鱼筐扶正。
- candidate: 方序把鱼筐扶正。
- facts: F1=把鱼筐扶正
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:2:unsup
- split/category: train / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 方序把鱼筐扶正。
- candidate: 方序把鱼筐扶正。
- facts: F1=把鱼筐擦亮
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:3:sup
- split/category: train / extra-action / authorization
- label: **supported**; gold: ['F1']
- full: 霍青把麻绳擦亮。
- candidate: 霍青把麻绳擦亮。
- facts: F1=把麻绳擦亮
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:auth:3:unsup
- split/category: train / extra-action / authorization
- label: **unsupported**; gold: ['F1']
- full: 霍青把麻绳擦亮。
- candidate: 霍青把麻绳擦亮。
- facts: F1=把麻绳推开
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:train:sup
- split/category: train / extra-action / statement
- label: **supported**; gold: ['F1']
- full: 谢迟把鱼筐推开。
- candidate: 把鱼筐推开
- facts: F1=把鱼筐推开
- scene: S1=夜
- visible: 无
- flags: none

### syn:extra-action:stmt:train:unsup
- split/category: train / extra-action / statement
- label: **unsupported**; gold: ['F1']
- full: 谢迟把鱼筐收紧。
- candidate: 把鱼筐收紧
- facts: F1=把鱼筐推开
- scene: S1=夜
- visible: 无
- flags: none

### syn:visible-state:auth:1:sup
- split/category: train / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 铜灯已点亮，林渡把竹筐擦亮。
- candidate: 铜灯已点亮
- facts: F1=把竹筐擦亮
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### syn:visible-state:auth:1:unsup
- split/category: train / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 铜灯已点亮，林渡把竹筐擦亮。
- candidate: 铜灯已点亮
- facts: F1=把竹筐擦亮
- scene: S1=夜
- visible: V1=铜灯
- flags: none

### syn:visible-state:auth:2:sup
- split/category: train / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 纸灯笼已点亮，谢迟把纸伞推开。
- candidate: 纸灯笼已点亮
- facts: F1=把纸伞推开
- scene: S1=夜；S2=纸灯笼已点亮
- visible: V1=纸灯笼
- flags: none

### syn:visible-state:auth:2:unsup
- split/category: train / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 纸灯笼已点亮，谢迟把纸伞推开。
- candidate: 纸灯笼已点亮
- facts: F1=把纸伞推开
- scene: S1=夜
- visible: V1=纸灯笼
- flags: none

### syn:visible-state:auth:3:sup
- split/category: train / visible-state / authorization
- label: **supported**; gold: ['S2']
- full: 警示灯已点亮，商陆把铜灯拖回。
- candidate: 警示灯已点亮
- facts: F1=把铜灯拖回
- scene: S1=夜；S2=警示灯已点亮
- visible: V1=警示灯
- flags: none

### syn:visible-state:auth:3:unsup
- split/category: train / visible-state / authorization
- label: **unsupported**; gold: ['V1']
- full: 警示灯已点亮，商陆把铜灯拖回。
- candidate: 警示灯已点亮
- facts: F1=把铜灯拖回
- scene: S1=夜
- visible: V1=警示灯
- flags: none

### syn:visible-state:stmt:train:sup
- split/category: train / visible-state / statement
- label: **supported**; gold: ['S2']
- full: 铜灯亮着，温砚把缆绳系紧。
- candidate: 铜灯亮着
- facts: F1=把缆绳系紧
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none

### syn:visible-state:stmt:train:unsup
- split/category: train / visible-state / statement
- label: **unsupported**; gold: ['S2']
- full: 铜灯熄了，温砚把缆绳系紧。
- candidate: 铜灯熄了
- facts: F1=把缆绳系紧
- scene: S1=夜；S2=铜灯已点亮
- visible: V1=铜灯
- flags: none
