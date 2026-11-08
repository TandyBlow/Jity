| run | load s | mem MB | prefill tok/s | decode tok/s | wall s | finish |
|---|---|---|---|---|---|---|
| MNN-Pocket-0.3B Q4_1 (QAT, recommended) | 13.5 | 707.5 | 8.07 / 9.44 | 6 / 6.03 | 28.26 / 24.95 | stop / stop |
| MNN-Pocket-0.3B Q4_1, world-page settings (ctx 2048, enable_thinking kwarg) | 17.7 | 707.5 | 7.51 / 7.61 | 4.23 / 4.45 | 32.446 / 31.654 | stop / stop |
| MNN-Pocket-0.3B Q4_1, narration-eval settings (ctx 4096, enable_thinking kwarg) | 18.4 | 727.5 | 7.21 / 7.26 | 4.26 / 4.27 | 33.342 / 33.124 | stop / stop |
| MNN-Pocket-0.3B Q8_0 | 28.2 | 1101.2 | 12.69 / 12.18 | 6.53 / 6.99 | 19.993 / 20.165 | stop / stop |
| control: Qwen3-0.6B Q4_K_M (existing baseline) | 32.3 | 1337.5 | 10.29 / 10.65 | 5.14 / 5.14 | 19.258 / 18.592 | stop / stop |
