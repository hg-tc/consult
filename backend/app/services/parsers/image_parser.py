"""
图片解析器（离线 OCR，优先 GPU）
使用 PaddleOCR/PP-Structure 从图片中提取文本与表格（转 Markdown），
输出 LlamaIndex Document 列表。
"""

from __future__ import annotations

from typing import List, Dict, Any, Tuple
from pathlib import Path
import time
import os
import logging
import threading

logger = logging.getLogger(__name__)

# 全局缓存：避免重复导入 PaddleOCR 类（导入本身很耗时且可能有并发问题）
_paddle_ocr_class = None
_paddle_ocr_lock = threading.Lock()
_paddle_ocr_import_failed = False  # 标记导入是否失败，避免重复尝试


def _load_paddle_ocr():
    """
    安全导入 PaddleOCR（线程安全的单例模式，带超时保护）：
    - 使用全局缓存避免重复导入
    - 使用线程锁确保并发安全
    - 在禁用 GPU 时，提前关闭 CUDA 探测
    - 限制大并发线程，避免 MKL/OMP 带来的导入卡顿
    - 注意：如果导入卡住，调用者应该捕获异常并使用回退方案
    """
    global _paddle_ocr_class, _paddle_ocr_import_failed
    
    # 如果之前导入失败，直接抛出异常
    if _paddle_ocr_import_failed:
        raise ImportError("PaddleOCR 导入已失败，无法使用。请设置 DISABLE_PADDLEOCR=true 或使用 Tesseract")
    
    # 快速检查（无锁）
    if _paddle_ocr_class is not None:
        logger.debug("使用缓存的 PaddleOCR 类")
        return _paddle_ocr_class
    
    # 检查是否完全禁用
    disable_paddle = os.getenv("DISABLE_PADDLEOCR", "false").lower() == "true"
    if disable_paddle:
        raise ImportError("PaddleOCR 已被禁用（DISABLE_PADDLEOCR=true），请使用 Tesseract")
    
    # 需要导入时，使用锁确保线程安全
    with _paddle_ocr_lock:
        # 双重检查
        if _paddle_ocr_class is not None:
            logger.debug("PaddleOCR 类已被其他线程导入，使用缓存")
            return _paddle_ocr_class
        
        try:
            use_gpu_env = os.getenv("PPOCR_USE_GPU", "true").lower()
            use_gpu = use_gpu_env == "true"

            # 关键：在导入前强制设置所有可能影响 paddle 初始化的环境变量
            # 这些变量必须在导入 paddleocr 之前设置，否则无效
            logger.info("设置导入环境变量...")
            
            # CUDA 相关：如果不用 GPU，完全禁用 CUDA 探测
            if not use_gpu:
                # 重要：不要设置为空字符串，会导致解析错误
                # 删除 CUDA_VISIBLE_DEVICES 让 paddle 自动使用 CPU，或设置为 -1
                if "CUDA_VISIBLE_DEVICES" in os.environ:
                    del os.environ["CUDA_VISIBLE_DEVICES"]
                # 设置 Paddle 内部标志强制使用 CPU
                os.environ["FLAGS_use_cuda"] = "0"
                os.environ["FLAGS_cudnn_deterministic"] = "0"
                # 删除 GPU 相关环境变量
                if "FLAGS_selected_gpus" in os.environ:
                    del os.environ["FLAGS_selected_gpus"]
                logger.info("已清除 GPU 相关环境变量，强制使用 CPU")
            else:
                # 即使使用 GPU，也限制 CUDA 初始化行为
                os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")

            # 线程限制：防止 MKL/OMP 在导入时创建过多线程导致卡住
            os.environ["OMP_NUM_THREADS"] = "1"
            os.environ["MKL_NUM_THREADS"] = "1"
            os.environ["NUMEXPR_NUM_THREADS"] = "1"
            os.environ["OPENBLAS_NUM_THREADS"] = "1"
            
            # Paddle 内部线程控制
            os.environ.setdefault("FLAGS_cudnn_batchnorm_spatial_persistent", "0")
            os.environ.setdefault("FLAGS_conv_workspace_size_limit", "400")

            # 预检测 OpenCV，若非 headless 版本可能引入 GUI 依赖导致卡住
            try:
                import cv2  # noqa: F401
                logger.debug("cv2 导入成功")
            except Exception as cv_err:
                logger.warning("cv2 导入失败，可能导致 paddleocr 导入异常或卡顿: %s", cv_err)

            t0 = time.time()
            logger.info(f"准备 import paddleocr (use_gpu={use_gpu})...")
            logger.info(f"环境变量检查:")
            logger.info(f"  - CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', 'unset')}")
            logger.info(f"  - OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS', 'unset')}")
            logger.info(f"  - MKL_NUM_THREADS={os.environ.get('MKL_NUM_THREADS', 'unset')}")
            
            # 关键：这里是真正耗时的地方，可能卡住
            # 在导入前再次确保环境变量设置（paddle 可能在导入时读取）
            if not use_gpu:
                # 确保 CUDA_VISIBLE_DEVICES 不存在或设置为一个无效值（但不要是空字符串）
                # Paddle 在 CPU 模式下不需要这个变量
                if "CUDA_VISIBLE_DEVICES" in os.environ:
                    # 如果是空字符串，删除它
                    if os.environ["CUDA_VISIBLE_DEVICES"] == "":
                        del os.environ["CUDA_VISIBLE_DEVICES"]
                        logger.info("已删除空的 CUDA_VISIBLE_DEVICES 以避免解析错误")
            
            # 关键导入：这里可能会卡住，特别是在异步环境中
            # 如果卡住，通常是因为 paddle 在导入时尝试初始化 CUDA/GPU
            logger.info("开始执行 'from paddleocr import PaddleOCR'...")
            logger.info("⚠️  注意：如果这里卡住，请设置 DISABLE_PADDLEOCR=true 来完全禁用 PaddleOCR")
            logger.info("⚠️  系统会自动回退到 Tesseract OCR")
            
            # 直接导入（如果卡住超过一段时间，调用者应该捕获并回退）
            # 注意：我们无法在这里设置超时（Python 的 import 无法中断）
            # 但如果卡住，调用者会超时，然后使用 Tesseract 回退
            from paddleocr import PaddleOCR  # type: ignore
            
            import_time = time.time() - t0
            logger.info(f"✅ paddleocr 导入成功，耗时 {import_time:.2f}s")
            
            # 缓存类对象
            _paddle_ocr_class = PaddleOCR
            return PaddleOCR
            
        except Exception as e:
            logger.error(f"❌ paddleocr 导入失败: {e}")
            _paddle_ocr_import_failed = True  # 标记导入失败
            raise ImportError("需要安装 paddleocr 并提供离线模型目录(PPOCR_MODEL_DIR)") from e


def _init_ocr() -> "PaddleOCR":
    """初始化 OCR 引擎"""
    # 检查是否完全禁用 PaddleOCR（使用环境变量控制）
    disable_paddle = os.getenv("DISABLE_PADDLEOCR", "false").lower() == "true"
    if disable_paddle:
        raise ImportError("PaddleOCR 已被禁用（DISABLE_PADDLEOCR=true），请使用 Tesseract")
    
    PaddleOCR = _load_paddle_ocr()
    logger.info(f"load paddle 成功")

    use_gpu = os.getenv("PPOCR_USE_GPU", "true").lower() == "true"
    model_dir = os.getenv("PPOCR_MODEL_DIR", "").strip()
    if not model_dir or not Path(model_dir).exists():
        raise RuntimeError("PPOCR_MODEL_DIR 未设置或不存在，无法进行离线 OCR")

    det_dir = Path(model_dir) / "det"
    rec_dir = Path(model_dir) / "rec"
    cls_dir = Path(model_dir) / "cls"

    use_angle = cls_dir.exists() and any(cls_dir.iterdir())

    # 仅中英文常用配置；当无 cls 模型时自动关闭方向分类
    logger.info(
        f"[OCR] 初始化: gpu={use_gpu}, det={det_dir.exists()}, rec={rec_dir.exists()}, cls={use_angle}, model_dir={model_dir}"
    )
    t0 = time.time()
    kwargs = dict(
        use_angle_cls=use_angle,
        lang="ch",
        use_gpu=use_gpu,
        det_model_dir=str(det_dir),
        rec_model_dir=str(rec_dir),
        show_log=False,
    )
    if use_angle:
        kwargs["cls_model_dir"] = str(cls_dir)

    ocr = PaddleOCR(**kwargs)
    logger.info(f"[OCR] 初始化完成: took={time.time()-t0:.3f}s")
    return ocr


def _recognize_text(ocr, image_path: str) -> Tuple[str, float]:
    """调用 PaddleOCR 进行识别，兼容 None/空结果/异常结构。"""
    t0 = time.time()
    try:
        logger.info(f"[OCR] 推理")
        result = ocr.ocr(image_path, cls=True)
        logger.info(f"[OCR] 推理得到result")
    except Exception as e:
        logger.error(f"[OCR] 调用失败: {e}")
        return "", 0.0
    finally:
        logger.info(f"[OCR] 推理完成: took={time.time()-t0:.3f}s, image={image_path}")

    if not result:
        # 兼容 None 或空列表
        logger.warning("[OCR] 返回为空")
        return "", 0.0

    texts: List[str] = []
    confs: List[float] = []
    try:
        for page in result or []:
            if not page:
                continue
            for line in page or []:
                try:
                    txt = line[1][0]
                    conf = float(line[1][1])
                except Exception:
                    # 结构异常，跳过该行
                    continue
                texts.append(str(txt))
                confs.append(conf)
    except TypeError:
        # 防御性：当 result 结构异常时
        logger.warning("[OCR] 返回结构异常，跳过解析")
        return "", 0.0

    full_text = "\n".join(texts)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    logger.info(
        f"[OCR] 解析统计: lines={len(texts)}, avg_conf={avg_conf:.3f}, sample={(texts[0][:50]+'...') if texts else ''}"
    )
    return full_text, avg_conf


def _preprocess_image_for_ocr(image):
    """
    图像预处理以提升 OCR 效果
    - 转换为灰度图
    - 增强对比度
    - 降噪处理
    """
    from PIL import Image, ImageEnhance, ImageFilter
    
    # 转换为灰度图（Tesseract 在灰度图上效果更好）
    if image.mode != 'L':
        image = image.convert('L')
    
    # 增强对比度
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)  # 增强 1.5 倍
    
    # 轻度降噪（避免过度处理导致文字模糊）
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    return image


def _extract_with_tesseract(image_path: str) -> Tuple[str, float]:
    """
    使用 Tesseract OCR 提取文本（主要 OCR 方案，更可靠）
    
    优势：
    - 稳定可靠，不会卡住
    - 中文识别效果好（清晰文档 85-90% 准确率）
    - 依赖简单，易于部署
    
    适用场景：
    - 清晰的印刷文档
    - 扫描件（质量较好）
    - 截图（文字清晰）
    
    不适用场景：
    - 严重模糊、低分辨率图片
    - 复杂表格布局
    - 手写文字
    """
    try:
        import pytesseract
        from PIL import Image
        
        img = Image.open(image_path)
        
        # 图像预处理以提升识别效果
        try:
            img = _preprocess_image_for_ocr(img)
            logger.debug("[OCR] 图像预处理完成")
        except Exception as e:
            logger.debug(f"[OCR] 图像预处理跳过: {e}")
        
        # 配置：中文+英文，自动页面分割模式
        # --oem 3: 使用 LSTM OCR 引擎（最准确）
        # --psm 6: 假设单一统一的文本块
        config = '--oem 3 --psm 6 -l chi_sim+eng'
        
        # 提取文本
        text = pytesseract.image_to_string(img, config=config)
        
        # 获取置信度信息
        try:
            data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_conf = sum(confidences) / len(confidences) / 100.0 if confidences else 0.75
        except Exception:
            avg_conf = 0.75  # 默认置信度
        
        logger.info(f"[OCR] Tesseract 提取完成: lines={len(text.splitlines())}, chars={len(text)}, avg_conf={avg_conf:.3f}")
        return text.strip(), avg_conf
        
    except Exception as e:
        logger.error(f"[OCR] Tesseract 提取失败: {e}")
        return "", 0.0


def parse_image_to_documents(file_path: str, source_metadata: Dict[str, Any] | None = None) -> List["Document"]:
    """
    将图片解析为 LlamaIndex Document 列表（OCR 文本 + 元数据）。
    
    主要使用 Tesseract OCR（稳定可靠），PaddleOCR 作为可选增强（如果可用且未禁用）。
    """
    # 惰性导入 Document
    try:
        from llama_index.core import Document  # type: ignore
    except Exception:
        from llama_index import Document  # type: ignore

    img_path = Path(file_path)
    if not img_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {file_path}")

    logger.info(f"[OCR] 图像解析开始: {img_path}")
    
    text = ""
    avg_conf = 0.0
    ocr_engine_used = "tesseract"  # 默认使用 Tesseract
    
    # 优先使用 Tesseract（稳定可靠）
    try:
        text, avg_conf = _extract_with_tesseract(str(img_path))
        if text.strip():
            logger.info(f"[OCR] Tesseract 解析成功: {img_path}, has_text={bool(text.strip())}")
        else:
            logger.warning(f"[OCR] Tesseract 未识别到文本，尝试可选方案...")
    except Exception as tesseract_err:
        logger.error(f"[OCR] Tesseract 失败: {tesseract_err}")
        text = ""
    
    # 可选：如果 Tesseract 失败或结果很差，且 PaddleOCR 可用，尝试使用 PaddleOCR
    use_paddle_ocr = os.getenv("USE_PADDLEOCR_AS_BACKUP", "false").lower() == "true"
    disable_paddle = os.getenv("DISABLE_PADDLEOCR", "true").lower() == "true"  # 默认禁用
    
    if (not text.strip() or avg_conf < 0.3) and not disable_paddle and use_paddle_ocr:
        logger.info(f"[OCR] 尝试使用 PaddleOCR 作为增强方案...")
        try:
            ocr = _init_ocr()
            logger.info(f"[OCR] PaddleOCR init成功")
            paddle_text, paddle_conf = _recognize_text(ocr, str(img_path))
            if paddle_text.strip() and (paddle_conf > avg_conf or not text.strip()):
                text = paddle_text
                avg_conf = paddle_conf
                ocr_engine_used = "paddleocr"
                logger.info(f"[OCR] PaddleOCR 增强成功: avg_conf={avg_conf:.3f}")
        except (ImportError, RuntimeError, Exception) as e:
            logger.debug(f"[OCR] PaddleOCR 不可用（这是正常的）: {e}")
    
    if not text.strip():
        text = "(OCR 未识别到有效文本)"
        ocr_engine_used = "none"

    metadata = {
        "type": "image",
        "source_file": str(img_path),
        "ocr_model": ocr_engine_used,
        "avg_conf": avg_conf,
        **(source_metadata or {}),
    }

    if not text.strip():
        text = "(OCR 未识别到有效文本)"

    return [Document(text=text, metadata=metadata)]


