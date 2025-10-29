"""
PDF 增强处理器
优先使用 marker-pdf 将 PDF 转换为 Markdown，否则使用其他方案
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def process_pdf_to_markdown(file_path: str) -> Dict[str, Any]:
    """
    将 PDF 转换为 Markdown 格式
    
    优先使用 marker-pdf（AI 驱动，效果最好），失败则回退其他方案
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF文件不存在: {file_path}")
    
    markdown_content = ""
    metadata = {
        "file_size": os.path.getsize(file_path),
        "file_path": file_path
    }
    
    # 方案1: 优先使用 marker-pdf
    try:
        from marker.convert import convert_single_pdf
        logger.info(f"使用 marker-pdf 处理: {file_path}")
        
        # marker 会自动转换为 Markdown
        result = convert_single_pdf(file_path)
        if isinstance(result, str):
            markdown_content = result
        elif isinstance(result, dict) and "markdown" in result:
            markdown_content = result["markdown"]
        else:
            markdown_content = str(result)
        
        metadata["conversion_method"] = "marker-pdf"
        logger.info(f"✅ marker-pdf 转换成功")
        
    except ImportError:
        logger.warning("marker-pdf 未安装，尝试其他方案")
        markdown_content = None
    except Exception as e:
        logger.warning(f"marker-pdf 转换失败: {e}，尝试其他方案")
        markdown_content = None
    
    # 方案2: 回退到 pymupdf4llm
    if not markdown_content:
        try:
            from pymupdf4llm import markdownify
            import fitz  # PyMuPDF
            
            logger.info(f"使用 pymupdf4llm 处理: {file_path}")
            doc = fitz.open(file_path)
            markdown_content = markdownify(doc)
            doc.close()
            
            metadata["conversion_method"] = "pymupdf4llm"
            logger.info(f"✅ pymupdf4llm 转换成功")
            
        except ImportError:
            logger.warning("pymupdf4llm 未安装，尝试基础方案")
            markdown_content = None
        except Exception as e:
            logger.warning(f"pymupdf4llm 转换失败: {e}，尝试基础方案")
            markdown_content = None
    
    # 方案3: 基础方案 - PyMuPDF 提取文本 + 表格提取 + OCR（如果需要）
    if not markdown_content:
        try:
            import fitz
            from app.services.ocr_service import OCRService
            
            logger.info(f"使用基础方案处理: {file_path}")
            doc = fitz.open(file_path)
            
            markdown_parts = []
            ocr_service = OCRService()
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # 提取文本
                text = page.get_text()
                
                # 检查是否为扫描版（文本很少）
                is_scanned = len(text.strip()) < 100
                
                if is_scanned:
                    # 扫描版：使用 OCR
                    logger.info(f"检测到扫描版PDF，第 {page_num + 1} 页使用 OCR")
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        pix.save(tmp.name)
                        ocr_text = ocr_service.extract_text_from_image(tmp.name)
                        if isinstance(ocr_text, dict):
                            ocr_text = ocr_text.get("text", "")
                        text = str(ocr_text).strip()
                        os.unlink(tmp.name)
                
                # 尝试提取表格（使用简单模式）
                # 注意：这里不依赖 camelot/tabula，仅做文本格式的表格识别
                
                if text.strip():
                    markdown_parts.append(f"## 第 {page_num + 1} 页\n\n{text.strip()}\n")
            
            doc.close()
            markdown_content = "\n\n".join(markdown_parts)
            metadata["conversion_method"] = "pymupdf_basic"
            logger.info(f"✅ 基础方案转换成功")
            
        except Exception as e:
            logger.error(f"PDF 处理失败: {e}")
            raise
    
    return {
        "file_type": "pdf",
        "content": markdown_content,
        "metadata": {
            **metadata,
            "page_count": metadata.get("page_count", 0)
        }
    }

