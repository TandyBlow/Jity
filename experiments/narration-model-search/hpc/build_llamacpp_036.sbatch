#!/bin/bash
#SBATCH --job-name=llamacpp_036
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=24
#SBATCH --mem=32G
#SBATCH --time=01:20:00
#SBATCH --output=%x_%j.out
#
# Build llama-server/llama-cli/llama-quantize with qwen35 support.
# 0.3.16 vendors llama.cpp 4227c9b (2025-08-14) and has no qwen35.
# 0.3.36 vendors 0c1e5709 (2026-10-01), which has qwen35/qwen35moe.
# In this tree llama-server lives under tools/, so LLAMA_BUILD_TOOLS=ON and
# LLAMA_BUILD_SERVER=ON are required; examples can stay OFF.
set -x
source ~/miniconda3/etc/profile.d/conda.sh && conda activate crf
export CUDACXX=/usr/local/cuda-12.4/bin/nvcc
export PATH=/usr/local/cuda-12.4/bin:$PATH
SRC="$HOME/scratch/llamacpp-src-036"
mkdir -p "$SRC" "$HOME/bin"
cd "$SRC" || exit 1
if [ ! -f llama_cpp_python-0.3.36.tar.gz ]; then
  pip download "llama-cpp-python==0.3.36" --no-binary :all: --no-deps -d "$SRC" || exit 1
fi
rm -rf extract && mkdir extract && tar xf llama_cpp_python-0.3.36.tar.gz -C extract || exit 1
LLAMA=$(find extract -maxdepth 3 -type d -name llama.cpp | head -1)
echo "vendor tree: $LLAMA"
git -C "$LLAMA" log -1 --format='llamacpp_commit=%H %ci' 2>/dev/null || { echo "no git metadata"; exit 1; }
cmake -B "$SRC/build" -S "$LLAMA" \
  -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="70;89" \
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_COMMON=ON \
  -DCMAKE_BUILD_TYPE=Release || exit 1
cmake --build "$SRC/build" -j 24 --target llama-server llama-cli llama-quantize || exit 1
cp "$SRC/build/bin/llama-server" "$SRC/build/bin/llama-cli" "$SRC/build/bin/llama-quantize" "$HOME/bin/" || exit 1
sha256sum "$HOME/bin/llama-server" "$HOME/bin/llama-cli" "$HOME/bin/llama-quantize"
"$HOME/bin/llama-server" --version 2>&1 | head -3
"$HOME/bin/llama-server" --list-devices 2>&1 | head -5
echo BUILD_OK "$(date)"
