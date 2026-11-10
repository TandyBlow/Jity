#!/bin/bash
# Login-node build, no Slurm queue. CPU-only, like 10's working 0.3.16 build.
# 0.3.36 vendors llama.cpp 0c1e5709 (2026-10-01) with qwen35.
set -x
source ~/miniconda3/etc/profile.d/conda.sh && conda activate crf
SRC=/tmp/llamacpp-src-036
mkdir -p "$SRC" "$HOME/bin"
cd "$SRC" || exit 1
if [ ! -f llama_cpp_python-0.3.36.tar.gz ]; then
  pip download "llama-cpp-python==0.3.36" --no-binary :all: --no-deps -d "$SRC" || exit 1
fi
rm -rf extract && mkdir extract && tar xf llama_cpp_python-0.3.36.tar.gz -C extract || exit 1
LLAMA=$(find extract -maxdepth 3 -type d -name llama.cpp | head -1)
echo "vendor tree: $LLAMA"
git -C "$LLAMA" log -1 --format='llamacpp_commit=%H %ci'
cmake -B "$SRC/build" -S "$LLAMA" \
  -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DBUILD_SHARED_LIBS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_COMMON=ON \
  -DCMAKE_CXX_STANDARD_LIBRARIES=-lstdc++fs -DCMAKE_SHARED_LINKER_FLAGS=-lstdc++fs \
  -DCMAKE_BUILD_TYPE=Release || exit 1
cmake --build "$SRC/build" -j 8 --target llama-server llama-cli llama-quantize || exit 1
cp "$SRC/build/bin/llama-server" "$HOME/bin/llama-server-036" || exit 1
cp "$SRC/build/bin/llama-cli" "$HOME/bin/llama-cli-036" || exit 1
cp "$SRC/build/bin/llama-quantize" "$HOME/bin/llama-quantize-036" || exit 1
sha256sum "$HOME/bin/llama-server-036"
"$HOME/bin/llama-server-036" --version 2>&1 | head -3
"$HOME/bin/llama-server-036" --list-devices 2>&1 | head -5
echo BUILD_036_OK "$(date)"
