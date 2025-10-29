"""
Excel 解析器（离线）
使用 pandas + openpyxl 将多 Sheet 转为结构化 Markdown 文本，
并输出 LlamaIndex Document 列表以供向量化索引。
"""

from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


def _try_import_pandas():
    try:
        import pandas as pd  # type: ignore
        return pd
    except Exception as e:
        raise ImportError("需要安装 pandas 才能解析 Excel 文件") from e


def _markdown_table_from_dataframe(df) -> str:
    # 限制过宽表格，避免超长文本
    max_cols = 64
    if df.shape[1] > max_cols:
        df = df.iloc[:, :max_cols]

    # 将 NaN 填充为空字符串，保证可序列化
    df = df.fillna("")

    headers = [str(col) for col in df.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in df.iterrows():
        vals = [str(v) for v in row.tolist()]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def parse_excel_to_documents(file_path: str, source_metadata: Dict[str, Any] | None = None) -> List["Document"]:
    """将 Excel 解析为 LlamaIndex Document 列表。

    每个 Sheet 输出：
    - Markdown 表格（主要结构化内容）
    - 可选：KV 段落（当列数较少时）
    """
    pd = _try_import_pandas()

    # 惰性导入 Document，兼容不同版本的 LlamaIndex
    try:
        from llama_index.core import Document  # type: ignore
    except Exception:
        from llama_index import Document  # type: ignore

    xlsx_path = Path(file_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {file_path}")

    try:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
    except Exception as e:
        logger.error(f"读取 Excel 失败: {e}")
        raise

    documents: List[Document] = []
    base_meta: Dict[str, Any] = {
        "type": "excel",
        "source_file": str(xlsx_path),
        **(source_metadata or {}),
    }

    for sheet_name in xls.sheet_names:
        try:
            df = xls.parse(sheet_name=sheet_name, dtype=str)
        except Exception as e:
            logger.warning(f"解析 Sheet 失败，跳过: {sheet_name}, {e}")
            continue

        if df.empty:
            logger.info(f"Sheet 为空，跳过: {sheet_name}")
            continue

        # 前向填充处理合并单元格常见空洞
        df = df.ffill().fillna("")

        content_parts: List[str] = []
        # 表格转 Markdown
        try:
            md_table = _markdown_table_from_dataframe(df)
            content_parts.append(f"# Sheet: {sheet_name}\n\n{md_table}")
        except Exception as e:
            logger.warning(f"表格转 Markdown 失败，退化为 CSV: {e}")
            try:
                csv_text = df.to_csv(index=False)
                content_parts.append(f"# Sheet: {sheet_name}\n\n```
{csv_text}
```")
            except Exception as e2:
                logger.error(f"表格转 CSV 仍失败，跳过该 sheet: {e2}")
                continue

        content_text = "\n\n".join(content_parts)
        metadata = {
            **base_meta,
            "sheet": sheet_name,
            "n_rows": int(df.shape[0]),
            "n_cols": int(df.shape[1]),
        }
        documents.append(Document(text=content_text, metadata=metadata))

    return documents


