#!/bin/bash
set -u
P=.venv/bin/python
run () {
  echo "=== $1 $2 $3 ==="
  $P src/classify.py --backend ollama --model "$2" --rung "$1" \
     --strategy "$3" --split dev 2>&1 | tail -12
}
run t1 qwen3:4b        perblock
run t2 qwen3:14b       perblock
run t3 qwen3.6:35b-mlx perblock
run t2 qwen3:14b       whole
run t3 qwen3.6:35b-mlx whole
echo "=== ladder complete ==="
