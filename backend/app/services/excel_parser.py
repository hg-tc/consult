"""
Excel 结构化解析器
将 Excel 转换为结构化 JSON 与 Markdown 表格，保留表头/层次/合并单元格等信息
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
import logging

import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)


def _detect_header_rows(ws: Worksheet, max_header_rows: int = 5) -> int:
    """粗略检测表头占用的行数（1-5 行）。
    策略：
    - 前几行文本占比更高，且非空单元格较集中
    - 出现明显数值列则认为数据区开始
    """
    header_rows = 1
    for i in range(1, min(ws.max_row, max_header_rows) + 1):
        row_values = [cell.value for cell in ws[i]]
        non_empty = [v for v in row_values if v is not None and str(v).strip() != ""]
        if not non_empty:
            continue
        num_like = sum(isinstance(v, (int, float)) for v in non_empty)
        text_like = len(non_empty) - num_like
        # 若文本明显多于数字，可能仍在表头
        if text_like >= num_like:
            header_rows = i
        else:
            break
    return max(1, header_rows)


def _merged_header(ws: Worksheet, header_rows: int) -> List[List[str]]:
    """构建多级表头，展开合并单元格并向下填充。"""
    grid: List[List[str]] = []
    for r in range(1, header_rows + 1):
        row_vals: List[str] = []
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(row=r, column=c)
            val = str(cell.value).strip() if cell.value is not None else ""
            row_vals.append(val)
        grid.append(row_vals)

    # 向右填充空表头（继承左侧值），向下填充（继承上一层）
    for r in range(len(grid)):
        last = ""
        for c in range(len(grid[r])):
            if grid[r][c] == "":
                grid[r][c] = last
            last = grid[r][c]

    for r in range(1, len(grid)):
        for c in range(len(grid[r])):
            if grid[r][c] == "":
                grid[r][c] = grid[r - 1][c]

    return grid


def _headers_to_single_row(headers_grid: List[List[str]]) -> List[str]:
    """将多级表头压平成单行列名，以 ' / ' 连接。"""
    levels = len(headers_grid)
    cols = len(headers_grid[0]) if headers_grid else 0
    single: List[str] = []
    for c in range(cols):
        parts = []
        for r in range(levels):
            val = headers_grid[r][c].strip()
            if val:
                parts.append(val)
        single.append(" / ".join(parts) if parts else f"col_{c+1}")
    return single


def _infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            mapping[col] = "datetime"
        elif pd.api.types.is_integer_dtype(df[col]):
            mapping[col] = "integer"
        elif pd.api.types.is_float_dtype(df[col]):
            mapping[col] = "float"
        elif pd.api.types.is_bool_dtype(df[col]):
            mapping[col] = "bool"
        else:
            mapping[col] = "text"
    return mapping


def _df_to_markdown(df: pd.DataFrame, max_rows: int = 2000) -> str:
    preview = df.head(max_rows)
    return preview.to_markdown(index=False)


def parse_excel_to_markdown(file_path: str) -> Dict[str, Any]:
    """解析 Excel，输出结构化信息与 Markdown 文本。

    Returns:
        {
          'file_type': 'excel',
          'sheets': [ {sheet_name, headers_levels, headers_flat, types, rows, markdown} ],
          'content': '拼接后的markdown',
          'metadata': {...}
        }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    wb = load_workbook(file_path, read_only=True, data_only=True)
    result_sheets: List[Dict[str, Any]] = []
    md_parts: List[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row == 0 or ws.max_column == 0:
            continue

        header_rows = _detect_header_rows(ws)
        header_grid = _merged_header(ws, header_rows)
        headers_flat = _headers_to_single_row(header_grid)

        # 读取数据区
        data: List[List[Any]] = []
        for r in range(header_rows + 1, ws.max_row + 1):
            row_vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            if any(v is not None and str(v).strip() != "" for v in row_vals):
                data.append(row_vals)

        df = pd.DataFrame(data, columns=headers_flat if headers_flat else None)
        types = _infer_column_types(df) if not df.empty else {}
        md = _df_to_markdown(df) if not df.empty else ""

        # 每个工作表生成独立段落
        section_md = f"### 工作表: {sheet_name}\n\n{md}\n"
        md_parts.append(section_md)

        result_sheets.append({
            "sheet_name": sheet_name,
            "headers_levels": header_grid,
            "headers_flat": headers_flat,
            "data_types": types,
            "row_count": int(df.shape[0]) if not df.empty else 0,
            "markdown": md,
        })

    wb.close()

    final_md = "\n\n".join(md_parts)

    return {
        "file_type": "excel",
        "sheets": result_sheets,
        "content": final_md,
        "metadata": {
            "sheet_count": len(result_sheets),
            "file_size": os.path.getsize(file_path)
        }
    }


