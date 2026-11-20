---
pipeline_tag: text-generation
license: other
---
# InternLM 

<div align="center">

<img src="https://github.com/InternLM/InternLM/assets/22529082/b9788105-8892-4398-8b47-b513a292378e" width="200"/>
  <div>&nbsp;</div>
  <div align="center">
    <b><font size="5">InternLM</font></b>
    <sup>
      <a href="https://internlm.intern-ai.org.cn/">
        <i><font size="4">HOT</font></i>
      </a>
    </sup>
    <div>&nbsp;</div>
  </div>
  
[![evaluation](https://github.com/InternLM/InternLM/assets/22529082/f80a2a58-5ddf-471a-8da4-32ab65c8fd3b)](https://github.com/internLM/OpenCompass/)

[💻Github Repo](https://github.com/InternLM/InternLM) • [🤔Reporting Issues](https://github.com/InternLM/InternLM/issues/new) • [📜Technical Report](https://arxiv.org/abs/2403.17297)

</div>

<p align="center">
    👋 join us on <a href="https://discord.gg/xa29JuW87d" target="_blank">Discord</a> and <a href="https://github.com/InternLM/InternLM/assets/25839884/a6aad896-7232-4220-ac84-9e070c2633ce" target="_blank">WeChat</a>
</p>



## Introduction

InternLM2.5 has open-sourced a 1.8 billion parameter base model and a chat model tailored for practical scenarios. The model has the following characteristics:

- **Outstanding reasoning capability**: State-of-the-art performance on Math reasoning, surpassing models like MiniCPM-2 and Qwen2-1.5B.

- **Stronger tool use**: InternLM2.5 supports gathering information from more than 100 web pages, corresponding implementation has be released in [MindSearch](https://github.com/InternLM/MindSearch). InternLM2.5 has better tool utilization-related capabilities in instruction following, tool selection and reflection. See [examples](https://github.com/InternLM/InternLM/blob/main/agent/lagent.md).

## InternLM2.5-1.8B-Chat

### Performance Evaluation

We conducted a comprehensive evaluation of InternLM using the open-source evaluation tool [OpenCompass](https://github.com/internLM/OpenCompass/). The evaluation covered five dimensions of capabilities: disciplinary competence, language competence, knowledge competence, inference competence, and comprehension competence. Here are some of the evaluation results, and you can visit the [OpenCompass leaderboard](https://rank.opencompass.org.cn) for more evaluation results.

| Benchmark          | InternLM2.5-1.8B-Chat | MiniCPM-2 | Qwen2-1.5B-Instruct |
| ------------------ | --------------------- | --------- | ------------------- |
| MMLU (5-shot)      | 50.7                  | 54.2      | 55.7                |
| CMMLU (5-shot)     | 62.2                  | 50.6      | 65.2                |
| BBH (3-shot CoT)   | **41.9**              | 41.5      | 36.5                |
| MATH (0-shot CoT)  | **40.2**              | 15.5      | 21.4                |
| GPQA (0-shot)      | **27.8**              | 23.7      | 27.3                |

- The evaluation results were obtained from [OpenCompass](https://github.com/internLM/OpenCompass/), and evaluation configuration can be found in the configuration files provided by [OpenCompass](https://github.com/internLM/OpenCompass/). 
- The evaluation data may have numerical differences due to the version iteration of [OpenCompass](https://github.com/internLM/OpenCompass/), so please refer to the latest evaluation results of [OpenCompass](https://github.com/internLM/OpenCompass/).


**Limitations:** Although we have made efforts to ensure the safety of the model during the training process and to encourage the model to generate text that complies with ethical and legal requirements, the model may still produce unexpected outputs due to its size and probabilistic generation paradigm. For example, the generated responses may contain biases, discrimination, or other harmful content. Please do not propagate such content. We are not responsible for any consequences resulting from the dissemination of harmful information.

### Import from Transformers

To load the InternLM2.5 1.8B Chat model using Transformers, use the following code:

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
tokenizer = AutoTokenizer.from_pretrained("internlm/internlm2_5-1_8b-chat", trust_remote_code=True)
# Set `torch_dtype=torch.float16` to load model in float16, otherwise it will be loaded as float32 and cause OOM Error.
model = AutoModelForCausalLM.from_pretrained("internlm/internlm2_5-1_8b-chat", torch_dtype=torch.float16, trust_remote_code=True).cuda()
model = model.eval()
response, history = model.chat(tokenizer, "hello", history=[])
print(response)
# Hello! How can I help you today?
response, history = model.chat(tokenizer, "please provide three suggestions about time management", history=history)
print(response)
```

The responses can be streamed using `stream_chat`:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "internlm/internlm2_5-1_8b-chat"
model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float16, trust_remote_code=True).cuda()
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

model = model.eval()
length = 0
for response, history in model.stream_chat(tokenizer, "Hello", history=[]):
    print(response[length:], flush=True, end="")
    length = len(response)
```

## Deployment

### llama.cpp

[internlm/internlm2_5-1_8b-chat-gguf](https://huggingface.co/internlm/internlm2_5-1_8b-chat-gguf) offers `internlm2_5-1_8b-chat` models in GGUF format in both half precision and various low-bit quantized versions, including `q5_0`, `q5_k_m`, `q6_k`, and `q8_0`.

### LMDeploy

LMDeploy is a toolkit for compressing, deploying, and serving LLM, developed by the MMRazor and MMDeploy teams.

```bash
pip install lmdeploy
```

You can run batch inference locally with the following python code:

```python
import lmdeploy
pipe = lmdeploy.pipeline("internlm/internlm2_5-1_8b-chat")
response = pipe(["Hi, pls intro yourself", "Shanghai is"])
print(response)
```

Or you can launch an OpenAI compatible server with the following command:

```bash
lmdeploy serve api_server internlm/internlm2_5-1_8b-chat --model-name internlm2_5-1_8b-chat --server-port 23333 
```

Then you can send a chat request to the server:

```bash
curl http://localhost:23333/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
    "model": "internlm2_5-1_8b-chat",
    "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Introduce deep learning to me."}
    ]
    }'
```

Find more details in the [LMDeploy documentation](https://lmdeploy.readthedocs.io/en/latest/)

### vLLM

Launch OpenAI compatible server with `vLLM>=0.3.2`:

```bash
pip install vllm
```

```bash
python -m vllm.entrypoints.openai.api_server --model internlm/internlm2_5-1_8b-chat --served-model-name internlm2_5-1_8b-chat --trust-remote-code
```

Then you can send a chat request to the server:

```bash
curl http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
    "model": "internlm2_5-1_8b-chat",
    "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Introduce deep learning to me."}
    ]
    }'
```

Find more details in the [vLLM documentation](https://docs.vllm.ai/en/latest/index.html)

## Open Source License

The code is licensed under Apache-2.0, while model weights are fully open for academic research and also allow **free** commercial usage. To apply for a commercial license, please fill in the [application form (English)](https://wj.qq.com/s2/12727483/5dba/)/[申请表（中文）](https://wj.qq.com/s2/12725412/f7c1/). For other questions or collaborations, please contact <internlm@pjlab.org.cn>.

## Citation

```
@misc{cai2024internlm2,
      title={InternLM2 Technical Report},
      author={Zheng Cai and Maosong Cao and Haojiong Chen and Kai Chen and Keyu Chen and Xin Chen and Xun Chen and Zehui Chen and Zhi Chen and Pei Chu and Xiaoyi Dong and Haodong Duan and Qi Fan and Zhaoye Fei and Yang Gao and Jiaye Ge and Chenya Gu and Yuzhe Gu and Tao Gui and Aijia Guo and Qipeng Guo and Conghui He and Yingfan Hu and Ting Huang and Tao Jiang and Penglong Jiao and Zhenjiang Jin and Zhikai Lei and Jiaxing Li and Jingwen Li and Linyang Li and Shuaibin Li and Wei Li and Yining Li and Hongwei Liu and Jiangning Liu and Jiawei Hong and Kaiwen Liu and Kuikun Liu and Xiaoran Liu and Chengqi Lv and Haijun Lv and Kai Lv and Li Ma and Runyuan Ma and Zerun Ma and Wenchang Ning and Linke Ouyang and Jiantao Qiu and Yuan Qu and Fukai Shang and Yunfan Shao and Demin Song and Zifan Song and Zhihao Sui and Peng Sun and Yu Sun and Huanze Tang and Bin Wang and Guoteng Wang and Jiaqi Wang and Jiayu Wang and Rui Wang and Yudong Wang and Ziyi Wang and Xingjian Wei and Qizhen Weng and Fan Wu and Yingtong Xiong and Chao Xu and Ruiliang Xu and Hang Yan and Yirong Yan and Xiaogui Yang and Haochen Ye and Huaiyuan Ying and Jia Yu and Jing Yu and Yuhang Zang and Chuyu Zhang and Li Zhang and Pan Zhang and Peng Zhang and Ruijie Zhang and Shuo Zhang and Songyang Zhang and Wenjian Zhang and Wenwei Zhang and Xingcheng Zhang and Xinyue Zhang and Hui Zhao and Qian Zhao and Xiaomeng Zhao and Fengzhe Zhou and Zaida Zhou and Jingming Zhuo and Yicheng Zou and Xipeng Qiu and Yu Qiao and Dahua Lin},
      year={2024},
      eprint={2403.17297},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```

## 简介

InternLM2.5 ，即书生·浦语大模型第 2.5 代，开源了面向实用场景的 18 亿参数基础模型与对话模型 （InternLM2.5-20B-Chat）。模型具有以下特点：

- 卓越的推理性能：在数学推理方面取得了同量级模型最优精度，超越了 MiniCPM-2 和 Qwen2-1.5B。
- 工具调用能力整体升级：InternLM2.5 支持从上百个网页搜集有效信息进行分析推理，相关实现已开源到 [MindSearch](https://github.com/InternLM/MindSearch)。InternLM2.5 具有更强和更具有泛化性的指令理解、工具筛选与结果反思等能力，新版模型可以更可靠地支持复杂智能体的搭建，支持对工具进行有效的多轮调用，完成较复杂的任务。可以查看更多[样例](https://github.com/InternLM/InternLM/blob/main/agent/lagent.md)。

## InternLM2.5-1.8B-Chat

### 性能评测

我们使用开源评测工具 [OpenCompass](https://github.com/internLM/OpenCompass/) 从学科综合能力、语言能力、知识能力、推理能力、理解能力五大能力维度对InternLM开展全面评测，部分评测结果如下表所示，欢迎访问[ OpenCompass 榜单 ](https://rank.opencompass.org.cn)获取更多的评测结果。

| Benchmark          | InternLM2.5-1.8B-Chat | MiniCPM-2 | Qwen2-1.5B-Instruct |
| ------------------ | --------------------- | --------- | ------------------- |
| MMLU (5-shot)      | 50.7                  | 54.2      | 55.7                |
| CMMLU (5-shot)     | 62.2                  | 50.6      | 65.2                |
| BBH (3-shot CoT)   | **41.9**              | 41.5      | 36.5                |
| MATH (0-shot CoT)  | **40.2**              | 15.5      | 21.4                |
| GPQA (0-shot)      | **27.8**              | 23.7      | 27.3                |

- 以上评测结果基于 [OpenCompass](https://github.com/internLM/OpenCompass/) 获得，具体测试细节可参见 [OpenCompass](https://github.com/internLM/OpenCompass/) 中提供的配置文件。
- 评测数据会因 [OpenCompass](https://github.com/internLM/OpenCompass/) 的版本迭代而存在数值差异，请以 [OpenCompass](https://github.com/internLM/OpenCompass/) 最新版的评测结果为主。

**局限性：** 尽管在训练过程中我们非常注重模型的安全性，尽力促使模型输出符合伦理和法律要求的文本，但受限于模型大小以及概率生成范式，模型可能会产生各种不符合预期的输出，例如回复内容包含偏见、歧视等有害内容，请勿传播这些内容。由于传播不良信息导致的任何后果，本项目不承担责任。

### 通过 Transformers 加载

通过以下的代码加载 InternLM2.5 1.8B Chat 模型

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
tokenizer = AutoTokenizer.from_pretrained("internlm/internlm2_5-1_8b-chat", trust_remote_code=True)
# `torch_dtype=torch.float16` 可以令模型以 float16 精度加载，否则 transformers 会将模型加载为 float32，导致显存不足
model = AutoModelForCausalLM.from_pretrained("internlm/internlm2_5-1_8b-chat", torch_dtype=torch.float16, trust_remote_code=True).cuda()
model = model.eval()
response, history = model.chat(tokenizer, "你好", history=[])
print(response)
# 你好！有什么我可以帮助你的吗？
response, history = model.chat(tokenizer, "请提供三个管理时间的建议。", history=history)
print(response)
```

如果想进行流式生成，则可以使用 `stream_chat` 接口：

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "internlm/internlm2_5-1_8b-chat"
model = AutoModelForCausalLM.from_pretrained(model_path, torch_dype=torch.float16, trust_remote_code=True).cuda()
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

model = model.eval()
length = 0
for response, history in model.stream_chat(tokenizer, "你好", history=[]):
    print(response[length:], flush=True, end="")
    length = len(response)
```

## 部署

### LMDeploy

LMDeploy 由 MMDeploy 和 MMRazor 团队联合开发，是涵盖了 LLM 任务的全套轻量化、部署和服务解决方案。

```bash
pip install lmdeploy
```

你可以使用以下 python 代码进行本地批量推理:

```python
import lmdeploy
pipe = lmdeploy.pipeline("internlm/internlm2_5-1_8b-chat")
response = pipe(["Hi, pls intro yourself", "Shanghai is"])
print(response)
```

或者你可以使用以下命令启动兼容 OpenAI API 的服务:

```bash
lmdeploy serve api_server internlm/internlm2_5-1_8b-chat --model-name internlm2_5-1_8b-chat --server-port 23333
```

然后你可以向服务端发起一个聊天请求:

```bash
curl http://localhost:23333/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
    "model": "internlm2_5-1_8b-chat",
    "messages": [
    {"role": "system", "content": "你是个友善的AI助手。"},
    {"role": "user", "content": "介绍一下深度学习。"}
    ]
    }'
```

更多信息请查看 [LMDeploy 文档](https://lmdeploy.readthedocs.io/en/latest/)

### vLLM

使用`vLLM>=0.3.2`启动兼容 OpenAI API 的服务:

```bash
pip install vllm
```

```bash
python -m vllm.entrypoints.openai.api_server --model internlm/internlm2_5-1_8b-chat --served-model-name internlm2_5-1_8b-chat --trust-remote-code
```

然后你可以向服务端发起一个聊天请求:

```bash
curl http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
    "model": "internlm2_5-1_8b-chat",
    "messages": [
    {"role": "system", "content": "你是个友善的AI助手。"},
    {"role": "user", "content": "介绍一下深度学习。"}
    ]
    }'
```

更多信息请查看 [vLLM 文档](https://docs.vllm.ai/en/latest/index.html)

## 开源许可证

本仓库的代码依照 Apache-2.0 协议开源。模型权重对学术研究完全开放，也可申请免费的商业使用授权（[申请表](https://wj.qq.com/s2/12725412/f7c1/)）。其他问题与合作请联系 <internlm@pjlab.org.cn>。

## 引用

```
@misc{cai2024internlm2,
      title={InternLM2 Technical Report},
      author={Zheng Cai and Maosong Cao and Haojiong Chen and Kai Chen and Keyu Chen and Xin Chen and Xun Chen and Zehui Chen and Zhi Chen and Pei Chu and Xiaoyi Dong and Haodong Duan and Qi Fan and Zhaoye Fei and Yang Gao and Jiaye Ge and Chenya Gu and Yuzhe Gu and Tao Gui and Aijia Guo and Qipeng Guo and Conghui He and Yingfan Hu and Ting Huang and Tao Jiang and Penglong Jiao and Zhenjiang Jin and Zhikai Lei and Jiaxing Li and Jingwen Li and Linyang Li and Shuaibin Li and Wei Li and Yining Li and Hongwei Liu and Jiangning Liu and Jiawei Hong and Kaiwen Liu and Kuikun Liu and Xiaoran Liu and Chengqi Lv and Haijun Lv and Kai Lv and Li Ma and Runyuan Ma and Zerun Ma and Wenchang Ning and Linke Ouyang and Jiantao Qiu and Yuan Qu and Fukai Shang and Yunfan Shao and Demin Song and Zifan Song and Zhihao Sui and Peng Sun and Yu Sun and Huanze Tang and Bin Wang and Guoteng Wang and Jiaqi Wang and Jiayu Wang and Rui Wang and Yudong Wang and Ziyi Wang and Xingjian Wei and Qizhen Weng and Fan Wu and Yingtong Xiong and Chao Xu and Ruiliang Xu and Hang Yan and Yirong Yan and Xiaogui Yang and Haochen Ye and Huaiyuan Ying and Jia Yu and Jing Yu and Yuhang Zang and Chuyu Zhang and Li Zhang and Pan Zhang and Peng Zhang and Ruijie Zhang and Shuo Zhang and Songyang Zhang and Wenjian Zhang and Wenwei Zhang and Xingcheng Zhang and Xinyue Zhang and Hui Zhao and Qian Zhao and Xiaomeng Zhao and Fengzhe Zhou and Zaida Zhou and Jingming Zhuo and Yicheng Zou and Xipeng Qiu and Yu Qiao and Dahua Lin},
      year={2024},
      eprint={2403.17297},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```
