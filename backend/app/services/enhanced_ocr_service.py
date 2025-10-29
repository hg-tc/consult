"""
增强OCR服务 - 使用PaddleOCR提升中文识别能力
支持中英文混合识别，提供更好的OCR效果
"""

import os
import logging
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


class EnhancedOCRService:
    """增强OCR服务 - 使用PaddleOCR"""
    
    def __init__(self):
        self.ocr_engine = None
        self.enabled = True
        self._initialize_ocr()
    
    def _initialize_ocr(self):
        """初始化OCR引擎（延迟初始化，避免启动时卡住）"""
        # 延迟初始化：不在 __init__ 时初始化，而是在首次使用时初始化
        # 这样可以避免系统启动时的导入冲突
        self.ocr_engine = None
        self._ocr_initialized = False
        self._tesseract_mode = False
        
    def _ensure_ocr_initialized(self):
        """确保 OCR 已初始化（延迟初始化）"""
        if self._ocr_initialized:
            return
        
        try:
            # 使用与 image_parser 相同的安全导入方式
            try:
                from app.services.parsers.image_parser import _load_paddle_ocr
                PaddleOCR = _load_paddle_ocr()
                
                use_gpu = os.getenv("PPOCR_USE_GPU", "true").lower() == "true"
                
                # 初始化PaddleOCR，支持中英文
                logger.info("开始初始化 PaddleOCR 实例...")
                self.ocr_engine = PaddleOCR(
                    use_angle_cls=True,  # 启用角度分类
                    lang='ch',  # 中文
                    use_gpu=use_gpu,  # 使用环境变量配置
                    show_log=False  # 关闭日志输出
                )
                
                logger.info("✅ PaddleOCR 实例初始化成功")
                self._ocr_initialized = True
                self._tesseract_mode = False
                
            except ImportError as ie:
                logger.warning(f"PaddleOCR 不可用，尝试使用 Tesseract: {ie}")
                self._initialize_tesseract_fallback()
                
        except Exception as e:
            logger.error(f"OCR 初始化失败: {e}")
            # 尝试 Tesseract 回退
            try:
                self._initialize_tesseract_fallback()
            except Exception as e2:
                logger.error(f"Tesseract 回退也失败: {e2}")
                self.enabled = False
    
    def _initialize_tesseract_fallback(self):
        """Tesseract回退方案"""
        try:
            import pytesseract
            from PIL import Image
            
            # 检查tesseract是否可用
            pytesseract.get_tesseract_version()
            
            # 设置中文语言包
            self.ocr_engine = pytesseract
            self._tesseract_mode = True
            self._ocr_initialized = True
            
            logger.info("✅ Tesseract回退方案初始化成功")
            
        except Exception as e:
            logger.error(f"Tesseract初始化也失败: {e}")
            self.enabled = False
            self._ocr_initialized = False
    
    def extract_text_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        从图片中提取文本
        
        Args:
            image_path: 图片路径
            
        Returns:
            包含文本和位置信息的字典
        """
        if not self.enabled:
            return {"text": "", "confidence": 0.0, "boxes": []}
        
        try:
            self._ensure_ocr_initialized()  # 延迟初始化
            
            if not self.ocr_engine:
                return {"text": "", "confidence": 0.0, "boxes": []}
            
            if self._tesseract_mode:
                return self._extract_with_tesseract(image_path)
            else:
                return self._extract_with_paddleocr(image_path)
                
        except Exception as e:
            logger.error(f"OCR文本提取失败: {e}")
            return {"text": "", "confidence": 0.0, "boxes": []}
    
    def _extract_with_paddleocr(self, image_path: str) -> Dict[str, Any]:
        """使用PaddleOCR提取文本"""
        try:
            # 执行OCR
            result = self.ocr_engine.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return {"text": "", "confidence": 0.0, "boxes": []}
            
            # 处理结果
            text_lines = []
            boxes = []
            confidences = []
            
            for line in result[0]:
                if line and len(line) >= 2:
                    box = line[0]  # 边界框坐标
                    text_info = line[1]  # (文本, 置信度)
                    
                    if text_info and len(text_info) >= 2:
                        text = text_info[0]
                        confidence = text_info[1]
                        
                        text_lines.append(text)
                        boxes.append(box)
                        confidences.append(confidence)
            
            # 合并文本
            full_text = '\n'.join(text_lines)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {
                "text": full_text,
                "confidence": avg_confidence,
                "boxes": boxes,
                "lines": text_lines,
                "confidences": confidences
            }
            
        except Exception as e:
            logger.error(f"PaddleOCR提取失败: {e}")
            return {"text": "", "confidence": 0.0, "boxes": []}
    
    def _extract_with_tesseract(self, image_path: str) -> Dict[str, Any]:
        """使用Tesseract提取文本"""
        try:
            from PIL import Image
            
            # 打开图片
            image = Image.open(image_path)
            
            # 配置OCR参数
            custom_config = r'--oem 3 --psm 6 -l chi_sim+eng'
            
            # 提取文本
            text = self.ocr_engine.image_to_string(image, config=custom_config)
            
            # 获取详细信息
            data = self.ocr_engine.image_to_data(image, config=custom_config, output_type=self.ocr_engine.Output.DICT)
            
            # 计算平均置信度
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {
                "text": text.strip(),
                "confidence": avg_confidence / 100.0,  # 转换为0-1范围
                "boxes": [],
                "lines": text.split('\n'),
                "confidences": [conf / 100.0 for conf in confidences]
            }
            
        except Exception as e:
            logger.error(f"Tesseract提取失败: {e}")
            return {"text": "", "confidence": 0.0, "boxes": []}
    
    def extract_text_from_pdf_page(self, pdf_path: str, page_number: int) -> Dict[str, Any]:
        """
        从PDF页面提取文本
        
        Args:
            pdf_path: PDF文件路径
            page_number: 页面编号（从0开始）
            
        Returns:
            包含文本和位置信息的字典
        """
        try:
            import fitz  # PyMuPDF
            
            # 打开PDF
            doc = fitz.open(pdf_path)
            
            if page_number >= len(doc):
                return {"text": "", "confidence": 0.0, "boxes": []}
            
            # 获取页面
            page = doc.load_page(page_number)
            
            # 首先尝试提取文本
            text = page.get_text()
            
            if text.strip():
                # 如果文本提取成功，直接返回
                return {
                    "text": text.strip(),
                    "confidence": 1.0,
                    "boxes": [],
                    "lines": text.split('\n'),
                    "confidences": [1.0] * len(text.split('\n'))
                }
            
            # 如果文本提取失败，尝试OCR
            # 将页面转换为图片
            mat = fitz.Matrix(2.0, 2.0)  # 提高分辨率
            pix = page.get_pixmap(matrix=mat)
            
            # 保存临时图片
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                pix.save(tmp_file.name)
                temp_image_path = tmp_file.name
            
            try:
                # 使用OCR提取文本
                result = self.extract_text_from_image(temp_image_path)
                return result
            finally:
                # 清理临时文件
                os.unlink(temp_image_path)
            
        except Exception as e:
            logger.error(f"PDF页面OCR失败: {e}")
            return {"text": "", "confidence": 0.0, "boxes": []}
    
    def preprocess_image(self, image_path: str) -> str:
        """
        预处理图片以提高OCR效果
        
        Args:
            image_path: 原始图片路径
            
        Returns:
            处理后图片的路径
        """
        try:
            # 读取图片
            image = cv2.imread(image_path)
            if image is None:
                return image_path
            
            # 转换为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 去噪
            denoised = cv2.medianBlur(gray, 3)
            
            # 增强对比度
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(denoised)
            
            # 二值化
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # 保存处理后的图片
            processed_path = image_path.replace('.', '_processed.')
            cv2.imwrite(processed_path, binary)
            
            return processed_path
            
        except Exception as e:
            logger.error(f"图片预处理失败: {e}")
            return image_path
    
    def is_available(self) -> bool:
        """检查 OCR 是否可用（延迟初始化，避免启动时阻塞）"""
        if not self.enabled:
            return False
        try:
            self._ensure_ocr_initialized()  # 延迟初始化
            return self.ocr_engine is not None
        except Exception:
            return False
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取OCR引擎信息"""
        return {
            "enabled": self.enabled,
            "engine_type": "Tesseract" if self._tesseract_mode else "PaddleOCR",
            "available": self.is_available()
        }
