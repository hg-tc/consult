export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download BAAI/bge-large-zh-v1.5 \
    --local-dir models/bge-large-zh/default-v1.5 \
    --local-dir-use-symlinks False