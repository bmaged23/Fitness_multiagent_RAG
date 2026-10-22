"""Bundle the MIT-licensed BGE encoder at a fixed upstream revision."""
from huggingface_hub import snapshot_download

snapshot_download(
    'BAAI/bge-large-en-v1.5',
    revision='d4aa6901d3a41ba39fb536a557fa166f842b0e09',
    local_dir='/opt/models/bge-large-en-v1.5',
    allow_patterns=['*.json', '*.txt', 'README.md', 'model.safetensors', '1_Pooling/*'],
)
