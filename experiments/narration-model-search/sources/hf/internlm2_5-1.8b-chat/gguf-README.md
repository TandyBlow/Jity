---
license: apache-2.0
language:
- en
pipeline_tag: text-generation
tags:
- chat
---
# InternLM2.5-1.8B-Chat GGUF Model

## Introduction

The `internlm2_5-1_8b-chat` model in GGUF format can be utilized by [llama.cpp](https://github.com/ggerganov/llama.cpp), a highly popular open-source framework for Large Language Model (LLM) inference, across a variety of hardware platforms, both locally and in the cloud.
This repository offers `internlm2_5-1_8b-chat` models in GGUF format in both half precision and various low-bit quantized versions, including `q5_0`, `q5_k_m`, `q6_k`, and `q8_0`.

In the subsequent sections, we will first present the installation procedure, followed by an explanation of the model download process. 
And finally we will illustrate the methods for model inference and service deployment through specific examples.

## Installation

We recommend building `llama.cpp` from source. The following code snippet provides an example for the Linux CUDA platform. For instructions on other platforms, please refer to the [official guide](https://github.com/ggerganov/llama.cpp?tab=readme-ov-file#build).

- Step 1: create a conda environment and install cmake

```shell
conda create --name internlm2 python=3.10 -y
conda activate internlm2
pip install cmake
```

- Step 2: clone the source code and build the project 

```shell
git clone --depth=1 https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j
```

All the built targets can be found in the sub directory `build/bin`

In the following sections, we assume that the working directory is at the root directory of `llama.cpp`.

## Download models

In the [introduction section](#introduction), we mentioned that this repository includes several models with varying levels of computational precision. You can download the appropriate model based on your requirements.
For instance, `internlm2_5-1_8b-chat-fp16.gguf` can be downloaded as below：

```shell
pip install huggingface-hub
huggingface-cli download internlm/internlm2_5-1_8b-chat-gguf internlm2_5-1_8b-chat-fp16.gguf --local-dir . --local-dir-use-symlinks False
```

## Inference

You can use `llama-cli` for conducting inference. For a detailed explanation of `llama-cli`, please refer to [this guide](https://github.com/ggerganov/llama.cpp/blob/master/examples/main/README.md)

### chat example

```shell
build/bin/llama-cli \
    --model internlm2_5-1_8b-chat-fp16.gguf  \
    --predict 512 \
    --ctx-size 4096 \
    --gpu-layers 24 \
    --temp 0.8 \
    --top-p 0.8 \
    --top-k 50 \
    --seed 1024 \
    --color \
    --prompt "<|im_start|>system\nYou are an AI assistant whose name is InternLM (书生·浦语).\n- InternLM (书生·浦语) is a conversational language model that is developed by Shanghai AI Laboratory (上海人工智能实验室). It is designed to be helpful, honest, and harmless.\n- InternLM (书生·浦语) can understand and communicate fluently in the language chosen by the user such as English and 中文.<|im_end|>\n" \
    --interactive \
    --multiline-input \
    --conversation \
    --verbose \
    --logdir workdir/logdir \
    --in-prefix "<|im_start|>user\n" \
    --in-suffix "<|im_end|>\n<|im_start|>assistant\n"
```

### Function call example

`llama-cli` example:

```shell
build/bin/llama-cli \
    --model internlm2_5-1_8b-chat-fp16.gguf \
    --predict 512 \
    --ctx-size 4096 \
    --gpu-layers 24 \
    --temp 0.8 \
    --top-p 0.8 \
    --top-k 50 \
    --seed 1024 \
    --color \
    --prompt '<|im_start|>system\nYou are InternLM2-Chat, a harmless AI assistant.<|im_end|>\n<|im_start|>system name=<|plugin|>[{"name": "get_current_weather", "parameters": {"required": ["location"], "type": "object", "properties": {"location": {"type": "string", "description": "The city and state, e.g. San Francisco, CA"}, "unit": {"type": "string"}}}, "description": "Get the current weather in a given location"}]<|im_end|>\n<|im_start|>user\n' \
    --interactive \
    --multiline-input \
    --conversation \
    --verbose \
    --in-suffix "<|im_end|>\n<|im_start|>assistant\n" \
    --special
```

Conversation results:

```text
<s><|im_start|>system
You are InternLM2-Chat, a harmless AI assistant.<|im_end|>
<|im_start|>system name=<|plugin|>[{"name": "get_current_weather", "parameters": {"required": ["location"], "type": "object", "properties": {"location": {"type": "string", "description": "The city and state, e.g. San Francisco, CA"}, "unit": {"type": "string"}}}, "description": "Get the current weather in a given location"}]<|im_end|>
<|im_start|>user

> I want to know today's weather in Shanghai
I need to use the get_current_weather function to get the current weather in Shanghai.<|action_start|><|plugin|>
{"name": "get_current_weather", "parameters": {"location": "Shanghai"}}<|action_end|>32
<|im_end|>

> <|im_start|>environment name=<|plugin|>\n{"temperature": 22}
The current temperature in Shanghai is 22 degrees Celsius.<|im_end|>

> 
```

## Serving

`llama.cpp` provides an OpenAI API compatible server - `llama-server`. You can deploy `internlm2_5-1_8b-chat-fp16.gguf` into a service like this:

```shell
./build/bin/llama-server -m ./internlm2_5-1_8b-chat-fp16.gguf -ngl 24
```

At the client side, you can access the service through OpenAI API:

```python
from openai import OpenAI
client = OpenAI(
    api_key='YOUR_API_KEY',
    base_url='http://localhost:8080/v1'
)
model_name = client.models.list().data[0].id
response = client.chat.completions.create(
  model=model_name,
  messages=[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": " provide three suggestions about time management"},
  ],
  temperature=0.8,
  top_p=0.8
)
print(response)
```
