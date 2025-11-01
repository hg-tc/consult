# debug_import_v2.py
import logging, time, psutil
# 手工点名 llama-index 的 logger
for log_name in ['llama_index', 'llama_index.core', 'llama_index.core.indices']:
    logging.getLogger(log_name).setLevel(logging.DEBUG)

print("import start | 内存", psutil.Process().memory_info().rss >> 20, "MB")
t0 = time.time()
from llama_index.core.indices.vector_store import VectorStoreIndex
print("import 完成，耗时 %.1f s" % (time.time() - t0))