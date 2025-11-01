import os, time, logging, psutil
# 强制把 llama-index 的日志打到控制台
logging.basicConfig(level=logging.DEBUG, force=True)

print("import start | 内存", psutil.Process().memory_info().rss >> 20, "MB")
t0 = time.time()
from llama_index.core.indices.vector_store import VectorStoreIndex
print("import 完成，耗时 %.1f s" % (time.time() - t0))