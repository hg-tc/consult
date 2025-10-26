"""
OCR服务
处理扫描版PDF和图片中的文字识别
"""

import os
import logging
import tempfile
from typing import List, Optional, Tuple
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class OCRService:
    """OCR文字识别服务"""
    
    def __init__(self):
        self.tesseract_config = '--oem 3 --psm 6 -l chi_sim+eng'
        self.available = self._check_tesseract_availability()
        
        if self.available:
            logger.info("OCR服务初始化成功")
        else:
            logger.warning("OCR服务不可用，将跳过OCR处理")
    
    def _check_tesseract_availability(self) -> bool:
        """检查tesseract是否可用"""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.error(f"Tesseract不可用: {e}")
            return False
    
    async def extract_text_from_image(self, image_path: str) -> str:
        """
        从图片中提取文字
        
        Args:
            image_path: 图片路径
            
        Returns:
            str: 提取的文字
        """
        if not self.available:
            return ""
        
        try:
            import pytesseract
            from PIL import Image
            
            # 图像预处理
            processed_image = self._preprocess_image(image_path)
            
            # OCR识别
            text = pytesseract.image_to_string(
                processed_image, 
                config=self.tesseract_config
            )
            
            # 后处理清洗
            cleaned_text = self._clean_ocr_text(text)
            
            logger.info(f"OCR提取完成: {image_path}, 文字长度: {len(cleaned_text)}")
            return cleaned_text
            
        except Exception as e:
            logger.error(f"图片OCR失败 {image_path}: {e}")
            return ""
    
    async def process_scanned_pdf(self, pdf_path: str) -> str:
        """
        处理扫描版PDF
        
        Args:
            pdf_path: PDF路径
            
        Returns:
            str: 提取的文字
        """
        if not self.available:
            return ""
        
        try:
            from pdf2image import convert_from_path
            
            logger.info(f"开始处理扫描版PDF: {pdf_path}")
            
            # PDF转图片
            pages = convert_from_path(pdf_path, dpi=300)
            
            all_text = []
            for i, page in enumerate(pages):
                logger.info(f"处理第 {i+1} 页")
                
                # 保存临时图片
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    page.save(tmp_file.name, 'PNG')
                    
                    # OCR识别
                    page_text = await self.extract_text_from_image(tmp_file.name)
                    
                    if page_text.strip():
                        all_text.append(f"第{i+1}页:\n{page_text}")
                    
                    # 清理临时文件
                    os.unlink(tmp_file.name)
            
            result = '\n\n'.join(all_text)
            logger.info(f"扫描版PDF处理完成: {pdf_path}, 总页数: {len(pages)}")
            return result
            
        except Exception as e:
            logger.error(f"扫描版PDF处理失败 {pdf_path}: {e}")
            return ""
    
    def _preprocess_image(self, image_path: str):
        """图像预处理"""
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import cv2
            import numpy as np
            
            # 读取图片
            image = Image.open(image_path)
            
            # 转换为灰度图
            if image.mode != 'L':
                image = image.convert('L')
            
            # 转换为numpy数组进行OpenCV处理
            img_array = np.array(image)
            
            # 去噪
            img_array = cv2.medianBlur(img_array, 3)
            
            # 增强对比度
            img_array = cv2.equalizeHist(img_array)
            
            # 二值化
            _, img_array = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # 转换回PIL Image
            processed_image = Image.fromarray(img_array)
            
            return processed_image
            
        except Exception as e:
            logger.warning(f"图像预处理失败，使用原图: {e}")
            return Image.open(image_path)
    
    def _clean_ocr_text(self, text: str) -> str:
        """OCR文字后处理清洗"""
        if not text:
            return ""
        
        # 移除多余的空白字符
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:  # 只保留非空行
                cleaned_lines.append(line)
        
        # 重新组合
        cleaned_text = '\n'.join(cleaned_lines)
        
        # 移除常见的OCR错误
        replacements = {
            '|': 'I',  # 常见的OCR错误
            '0': 'O',  # 在某些字体中容易混淆
        }
        
        for old, new in replacements.items():
            cleaned_text = cleaned_text.replace(old, new)
        
        return cleaned_text
    
    async def batch_process_images(self, image_paths: List[str]) -> List[str]:
        """
        批量处理图片
        
        Args:
            image_paths: 图片路径列表
            
        Returns:
            List[str]: 每张图片的提取文字
        """
        results = []
        
        for image_path in image_paths:
            text = await self.extract_text_from_image(image_path)
            results.append(text)
        
        return results
    
    def is_available(self) -> bool:
        """检查OCR服务是否可用"""
        return self.available
    
    def get_supported_languages(self) -> List[str]:
        """获取支持的语言"""
        if not self.available:
            return []
        
        try:
            import pytesseract
            languages = pytesseract.get_languages()
            return languages
        except Exception as e:
            logger.error(f"获取支持语言失败: {e}")
            return []
    
    async def extract_text_with_confidence(self, image_path: str) -> Tuple[str, float]:
        """
        提取文字并返回置信度
        
        Args:
            image_path: 图片路径
            
        Returns:
            Tuple[str, float]: (提取的文字, 平均置信度)
        """
        if not self.available:
            return "", 0.0
        
        try:
            import pytesseract
            from PIL import Image
            
            processed_image = self._preprocess_image(image_path)
            
            # 获取详细OCR数据
            data = pytesseract.image_to_data(
                processed_image, 
                config=self.tesseract_config,
                output_type=pytesseract.Output.DICT
            )
            
            # 提取文字
            text_parts = []
            confidences = []
            
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 0:  # 置信度大于0
                    text_parts.append(data['text'][i])
                    confidences.append(int(data['conf'][i]))
            
            text = ' '.join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return text, avg_confidence
            
        except Exception as e:
            logger.error(f"带置信度的OCR失败 {image_path}: {e}")
            return "", 0.0
