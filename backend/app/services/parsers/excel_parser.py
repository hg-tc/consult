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
    """将 DataFrame 转换为 Markdown 表格格式"""
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


def _structured_rows_from_dataframe(df, max_rows_per_chunk: int = 50) -> List[str]:
    """
    将 DataFrame 转换为结构化行格式，每行包含完整的表头上下文
    这样即使分块，每行数据都带有表头信息
    
    返回格式示例：
    ```
    表头1: 值1 | 表头2: 值2 | 表头3: 值3
    表头1: 值1 | 表头2: 值2 | 表头3: 值3
    ```
    
    或者当列数较少时，使用更自然的格式：
    ```
    第1行数据：{表头1: 值1, 表头2: 值2, 表头3: 值3}
    第2行数据：{表头1: 值1, 表头2: 值2, 表头3: 值3}
    ```
    """
    df = df.fillna("")
    headers = [str(col) for col in df.columns]
    rows_text = []
    
    # 如果列数较少（<=5），使用 JSON 样式的对象格式，更容易理解
    if len(headers) <= 5:
        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            row_dict = {header: str(row[header]) for header in headers if str(row[header]).strip()}
            row_text = f"第{idx}行数据：{row_dict}"
            rows_text.append(row_text)
    else:
        # 列数较多时，使用紧凑格式
        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            pairs = [f"{header}: {str(row[header])}" for header in headers if str(row[header]).strip()]
            row_text = f"第{idx}行数据：" + " | ".join(pairs)
            rows_text.append(row_text)
    
    return rows_text


def _chunk_dataframe_with_headers(df, chunk_size: int = 50) -> List[Dict[str, Any]]:
    """
    将 DataFrame 分块，每个块都包含表头信息
    
    返回：List[Dict] 每个字典包含：
    - headers: 表头列表
    - rows: 该块的行数据（结构化格式）
    - start_row: 起始行号
    - end_row: 结束行号
    """
    df = df.fillna("")
    headers = [str(col) for col in df.columns]
    chunks = []
    
    total_rows = len(df)
    for start in range(0, total_rows, chunk_size):
        end = min(start + chunk_size, total_rows)
        chunk_df = df.iloc[start:end]
        
        # 生成该块的结构化行格式
        rows = []
        for idx, (_, row) in enumerate(chunk_df.iterrows(), start=start + 1):
            if len(headers) <= 5:
                row_dict = {header: str(row[header]) for header in headers if str(row[header]).strip()}
                rows.append(f"第{idx}行：{row_dict}")
            else:
                pairs = [f"{header}: {str(row[header])}" for header in headers if str(row[header]).strip()]
                rows.append(f"第{idx}行：" + " | ".join(pairs))
        
        chunks.append({
            "headers": headers,
            "rows": rows,
            "start_row": start + 1,
            "end_row": end,
            "total_rows": total_rows
        })
    
    return chunks


def _is_likely_header(text: str) -> float:
    """
    判断文本更像表头的概率（0-1）
    
    表头特征：
    1. 较短（通常 2-20 字符）
    2. 包含常见表头关键词
    3. 抽象、概括性用词
    4. 不含或含较少数字
    5. 不含具体日期格式（除非是"日期"这样的关键词）
    """
    if not text or not str(text).strip():
        return 0.0
    
    text = str(text).strip()
    text_lower = text.lower()
    
    score = 0.0
    
    # 1. 长度特征（表头通常较短）
    length = len(text)
    if 2 <= length <= 20:
        score += 0.3
    elif length > 50:  # 太长更可能是数据
        score -= 0.2
    
    # 2. 常见表头关键词（中文）
    header_keywords_cn = [
        '名称', '姓名', '名字', '标题', '类型', '类别', '分类',
        '日期', '时间', '年份', '月份', '季度',
        '数量', '总数', '合计', '总计', '金额', '价格', '费用', '成本',
        '状态', '等级', '级别', '阶段',
        '部门', '单位', '公司', '机构',
        '编号', '代码', 'ID', '标识',
        '备注', '说明', '描述', '详情',
        '序号', '排名', '排序',
        '地区', '城市', '省份', '国家',
        '产品', '商品', '项目', '任务'
    ]
    
    # 常见表头关键词（英文）
    header_keywords_en = [
        'name', 'id', 'code', 'type', 'category', 'status',
        'date', 'time', 'year', 'month', 'quarter',
        'count', 'total', 'amount', 'price', 'cost', 'fee',
        'level', 'rank', 'order', 'index',
        'department', 'company', 'organization',
        'note', 'remark', 'description', 'detail',
        'region', 'city', 'province', 'country',
        'product', 'item', 'task', 'project'
    ]
    
    # 检查是否包含表头关键词
    has_header_keyword = any(kw in text for kw in header_keywords_cn) or \
                        any(kw in text_lower for kw in header_keywords_en)
    if has_header_keyword:
        score += 0.4
    
    # 3. 数字特征（表头较少包含纯数字或长数字）
    import re
    numbers = re.findall(r'\d+', text)
    if not numbers:
        score += 0.1  # 没有数字更像表头
    elif len(numbers) > 3:  # 太多数字更像数据
        score -= 0.3
    elif any(len(n) > 4 for n in numbers):  # 长数字更像数据
        score -= 0.2
    
    # 4. 日期格式检测（包含日期格式更像数据）
    date_patterns = [
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',  # 2024-01-01
        r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',  # 01/01/2024
        r'\d{4}年\d{1,2}月\d{1,2}日',    # 2024年1月1日
    ]
    has_date_format = any(re.search(pattern, text) for pattern in date_patterns)
    if has_date_format and '日期' not in text and 'date' not in text_lower:
        score -= 0.3  # 有日期格式但不是"日期"关键词，更像数据
    
    # 5. 抽象性判断（包含抽象词汇更像表头）
    abstract_words = ['的', '和', '或', '与', '及', '等', '各', '所有', '全部']
    if any(word in text for word in abstract_words) and length < 15:
        score += 0.1
    
    # 限制在 0-1 范围
    return max(0.0, min(1.0, score))


def _analyze_candidate_headers(values: List[str]) -> Dict[str, Any]:
    """
    分析一组值，判断它们更像表头还是数据的特征
    """
    if not values:
        return {'header_score': 0.0, 'unique_ratio': 0.0, 'non_empty_ratio': 0.0}
    
    non_empty = [str(v).strip() for v in values if str(v).strip()]
    if len(non_empty) == 0:
        return {'header_score': 0.0, 'unique_ratio': 0.0, 'non_empty_ratio': 0.0}
    
    unique_count = len(set(non_empty))
    unique_ratio = unique_count / len(values) if len(values) > 0 else 0
    
    # 计算语义特征：每个值更像表头的平均分数
    header_scores = [_is_likely_header(v) for v in non_empty]
    avg_header_score = sum(header_scores) / len(header_scores) if header_scores else 0.0
    
    # 表头通常唯一值比例高（每个列名不同）
    # 但如果所有值都唯一，可能是数据而不是表头（除非有明确的表头特征）
    header_likelihood = avg_header_score
    
    # 如果语义得分高且唯一值比例也高，更像表头
    if avg_header_score > 0.5 and unique_ratio > 0.8:
        header_likelihood += 0.2
    
    return {
        'header_score': header_likelihood,
        'unique_ratio': unique_ratio,
        'non_empty_ratio': len(non_empty) / len(values) if len(values) > 0 else 0,
        'avg_text_length': sum(len(str(v)) for v in non_empty) / len(non_empty) if non_empty else 0
    }


def _detect_table_orientation(df) -> Dict[str, Any]:
    """
    检测表格方向（表头是行还是列）
    使用语义特征 + 结构特征综合判断
    
    返回:
    {
        'orientation': 'row' 或 'column',
        'headers': 表头列表,
        'df': 调整后的 DataFrame（转置后如果orientation是row）
    }
    """
    if df.empty or len(df) == 0 or len(df.columns) == 0:
        # 空表格，默认列表头
        return {
            'orientation': 'column',
            'headers': [str(col) for col in df.columns],
            'df': df.copy(),
            'original_df': df
        }
    
    first_row_values = df.iloc[0].tolist() if len(df) > 0 else []
    first_col_values = df.iloc[:, 0].tolist() if len(df.columns) > 0 else []
    
    # 使用语义分析判断
    row_stats = _analyze_candidate_headers(first_row_values)
    col_stats = _analyze_candidate_headers(first_col_values)
    
    # 结构特征
    is_wide_table = len(df.columns) > len(df) * 2  # 列数远大于行数
    is_tall_table = len(df) > len(df.columns) * 2  # 行数远大于列数
    
    # 综合判断
    # 1. 如果第一行的语义得分明显高于第一列，更像是列表头
    # 2. 如果第一列的语义得分明显高于第一行，更像是行表头
    # 3. 考虑表格形状（宽表格更可能是行表头）
    
    row_header_score = row_stats['header_score']
    col_header_score = col_stats['header_score']
    
    # 判断阈值
    orientation = 'column'  # 默认列表头
    headers = [str(col) for col in df.columns]
    df_transposed = df.copy()
    detected_headers = headers
    
    # 如果列的语义得分明显更高，且表格很宽，可能是行表头
    score_diff = col_header_score - row_header_score
    
    if is_wide_table and score_diff > 0.15:
        # 宽表格且第一列更像表头
        orientation = 'row'
        headers = [str(v) for v in first_col_values]
        # 转置处理
        try:
            df_transposed = df.set_index(df.columns[0]).T.reset_index()
            df_transposed.columns = ['列名'] + [str(h) for h in headers[1:] if str(h).strip()]
            detected_headers = [str(df.columns[0])] + [str(h) for h in headers[1:] if str(h).strip()]
        except Exception as e:
            logger.warning(f"表格转置失败，使用原始格式: {e}")
            df_transposed = df.copy()
            orientation = 'column'
            detected_headers = [str(col) for col in df.columns]
    elif score_diff < -0.15 or row_header_score > 0.5:
        # 第一行更像表头，或者语义得分明显更高
        orientation = 'column'
        headers = [str(col) for col in df.columns]
        df_transposed = df.copy()
        detected_headers = headers
    
    logger.info(f"表格方向检测：orientation={orientation}, 第一行表头得分={row_header_score:.2f}, "
               f"第一列表头得分={col_header_score:.2f}, 表格形状={len(df)}行×{len(df.columns)}列")
    
    return {
        'orientation': orientation,
        'headers': detected_headers,
        'df': df_transposed,
        'original_df': df
    }


def _structured_rows_from_dataframe(df, headers: List[str], orientation: str = 'column') -> List[str]:
    """
    将 DataFrame 转换为结构化行格式，每行包含完整的表头上下文
    
    支持两种表格方向：
    - column: 列表头（第一行是表头）
    - row: 行表头（第一列是表头，已转置处理）
    """
    df = df.fillna("")
    rows_text = []
    
    # 如果列数较少（<=5），使用 JSON 样式的对象格式，更容易理解
    if len(headers) <= 5:
        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            # 为每行构建字典，包含所有表头
            row_dict = {}
            for header in headers:
                if header in row.index:
                    value = str(row[header]).strip()
                    if value:
                        row_dict[header] = value
            row_text = f"第{idx}行数据：{row_dict}"
            rows_text.append(row_text)
    else:
        # 列数较多时，使用紧凑格式
        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            pairs = []
            for header in headers:
                if header in row.index:
                    value = str(row[header]).strip()
                    if value:
                        pairs.append(f"{header}: {value}")
            row_text = f"第{idx}行数据：" + " | ".join(pairs)
            rows_text.append(row_text)
    
    return rows_text


def _chunk_dataframe_with_headers(df, headers: List[str], chunk_size: int = 50) -> List[Dict[str, Any]]:
    """
    将 DataFrame 分块，每个块都包含表头信息
    """
    df = df.fillna("")
    chunks = []
    
    total_rows = len(df)
    for start in range(0, total_rows, chunk_size):
        end = min(start + chunk_size, total_rows)
        chunk_df = df.iloc[start:end]
        
        # 生成该块的结构化行格式
        rows = []
        for idx, (_, row) in enumerate(chunk_df.iterrows(), start=start + 1):
            if len(headers) <= 5:
                row_dict = {header: str(row[header]) for header in headers if header in row.index and str(row[header]).strip()}
                rows.append(f"第{idx}行：{row_dict}")
            else:
                pairs = [f"{header}: {str(row[header])}" for header in headers if header in row.index and str(row[header]).strip()]
                rows.append(f"第{idx}行：" + " | ".join(pairs))
        
        chunks.append({
            "headers": headers,
            "rows": rows,
            "start_row": start + 1,
            "end_row": end,
            "total_rows": total_rows
        })
    
    return chunks


def parse_excel_to_documents(file_path: str, source_metadata: Dict[str, Any] | None = None) -> List["Document"]:
    """将 Excel 解析为 LlamaIndex Document 列表。

    自动检测表格方向：
    - 列表头（第一行是表头）：常规表格
    - 行表头（第一列是表头）：转置表格
    
    每个 Sheet 输出：
    - Markdown 表格（主要结构化内容）
    - 结构化行格式（带表头上下文，确保AI理解数据含义）
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
        
        # 检测表格方向（列表头 vs 行表头）
        detection = _detect_table_orientation(df)
        df_processed = detection['df']
        headers = detection['headers']
        orientation = detection['orientation']
        
        n_rows = int(df_processed.shape[0])
        n_cols = int(df_processed.shape[1])
        
        # 记录表格方向信息
        orientation_note = "（列表头，第一行为表头）" if orientation == 'column' else "（行表头，第一列为表头，已转置处理）"
        
        # 策略选择：
        # 1. 小表格（<100行）：生成完整表格 + 结构化行格式（双重保证）
        # 2. 大表格（>=100行）：分块，每个块包含表头 + 结构化行格式
        
        if n_rows < 100:
            # 小表格：完整格式 + 结构化格式
            content_parts: List[str] = []
            
            # 1. 完整的 Markdown 表格（用于整体查看）
            try:
                md_table = _markdown_table_from_dataframe(df_processed)
                content_parts.append(f"## Sheet: {sheet_name} {orientation_note}\n\n### 完整表格（{n_rows}行 × {n_cols}列）\n\n{md_table}")
            except Exception as e:
                logger.warning(f"表格转 Markdown 失败: {e}")
            
            # 2. 结构化行格式（每个数据行都带有表头上下文）
            structured_rows = _structured_rows_from_dataframe(df_processed, headers, orientation)
            content_parts.append(f"### 结构化数据（带表头上下文）\n\n**表头：** {', '.join(headers[:10])}")
            if len(headers) > 10:
                content_parts[-1] += f" ... 等共 {len(headers)} 列"
            content_parts.append("\n\n" + "\n".join(structured_rows))
            
            content_text = "\n\n".join(content_parts)
            metadata = {
                **base_meta,
                "sheet": sheet_name,
                "orientation": orientation,  # 记录表格方向
                "n_rows": n_rows,
                "n_cols": n_cols,
                "headers": headers,  # 保存表头信息
                "format": "complete_table_with_structured_rows"
            }
            documents.append(Document(text=content_text, metadata=metadata))
            
        else:
            # 大表格：分块处理，每个块都包含表头信息
            chunks = _chunk_dataframe_with_headers(df_processed, headers, chunk_size=50)
            
            # 首先添加一个总览文档
            overview_text = f"## Sheet: {sheet_name} {orientation_note}\n\n"
            overview_text += f"总行数：{n_rows}，总列数：{n_cols}\n\n"
            overview_text += f"**表头列表：** {', '.join(headers[:10])}"
            if len(headers) > 10:
                overview_text += f" ... 等共 {len(headers)} 列"
            overview_text += f"\n\n该表格已分为 {len(chunks)} 个数据块，每个数据块包含完整的表头上下文。"
            
            overview_meta = {
                **base_meta,
                "sheet": sheet_name,
                "orientation": orientation,  # 记录表格方向
                "n_rows": n_rows,
                "n_cols": n_cols,
                "n_chunks": len(chunks),
                "headers": headers,  # 保存表头信息
                "format": "table_overview"
            }
            documents.append(Document(text=overview_text, metadata=overview_meta))
            
            # 为每个块创建独立文档，包含表头信息
            for chunk_idx, chunk in enumerate(chunks, start=1):
                chunk_text = f"## Sheet: {sheet_name} - 数据块 {chunk_idx}/{len(chunks)} {orientation_note}\n\n"
                chunk_text += f"**表头：** {', '.join(chunk['headers'][:10])}"
                if len(chunk['headers']) > 10:
                    chunk_text += f" ... 等共 {len(chunk['headers'])} 列\n\n"
                else:
                    chunk_text += "\n\n"
                chunk_text += f"**数据范围：** 第 {chunk['start_row']} 行到第 {chunk['end_row']} 行（共 {chunk['total_rows']} 行）\n\n"
                chunk_text += "**数据内容：**\n\n"
                chunk_text += "\n".join(chunk['rows'])
                
                chunk_meta = {
                    **base_meta,
                    "sheet": sheet_name,
                    "orientation": orientation,  # 记录表格方向
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "start_row": chunk['start_row'],
                    "end_row": chunk['end_row'],
                    "n_rows_in_chunk": len(chunk['rows']),
                    "headers": chunk['headers'],  # 在元数据中也保存表头
                    "format": "chunked_with_headers"
                }
                documents.append(Document(text=chunk_text, metadata=chunk_meta))

    return documents


