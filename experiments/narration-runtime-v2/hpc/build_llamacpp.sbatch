#!/bin/bash
#SBATCH --job-name=llamacpp_build
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=24
#SBATCH --mem=32G
#SBATCH --time=01:20:00
#SBATCH --output=%x_%j.out
#
# Build llama-server / llama-cli / llama-quantize on the cluster.
#
# Why from the pypi sdist: the login host cannot reach github.com (curl returns
# 000) but pypi is reachable, and llama-cpp-python's sdist vendors the llama.cpp
# source tree. That is the only way to get the real llama-server CLI that lane
# 11's screen.py drives, without an external download of a binary of unknown
# provenance. Recorded commit comes from the vendor tree after extraction.
set -x
source ~/miniconda3/etc/profile.d/conda.sh && conda activate crf
export CUDACXX=/usr/local/cuda-12.4/bin/nvcc
export PATH=/usr/local/cuda-12.4/bin:$PATH
SRC=~/scratch/llamacpp-src
mkdir -p "$SRC" ~/bin
cd "$SRC" || exit 1
if [ ! -f llama_cpp_python-0.3.16.tar.gz ]; then
  pip download "llama-cpp-python==0.3.16" --no-binary :all: --no-deps -d "$SRC" || exit 1
fi
rm -rf extract && mkdir extract && tar xf llama_cpp_python-0.3.16.tar.gz -C extract || exit 1
LLAMA=$(find extract -maxdepth 3 -type d -name llama.cpp | head -1)
echo "vendor tree: $LLAMA"
git -C "$LLAMA" log -1 --format='llamacpp_commit=%H %ci' 2>/dev/null || echo "llamacpp_commit=unknown-no-git-dir"
cmake -B "$SRC/build" -S "$LLAMA" \
  -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="70;89" \
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS=-lstdc++fs || exit 1
cmake --build "$SRC/build" -j 24 --target llama-server llama-cli llama-quantize || exit 1
cp "$SRC/build/bin/llama-server" "$SRC/build/bin/llama-cli" "$SRC/build/bin/llama-quantize" ~/bin/ || exit 1
~/bin/llama-server --version 2>&1 | head -3
~/bin/llama-server --list-devices 2>&1 | head -5
echo BUILD_OK "$(date)"
