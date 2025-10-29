import os
import sys


def env_bool(name: str, default: bool = True) -> bool:
    v = os.getenv(name, "true" if default else "false").lower()
    return v in ("1", "true", "yes", "y", "on")


def main():
    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        print(f"[ERROR] 未安装 paddleocr: {e}")
        sys.exit(1)

    img = "/root/consult/【定稿】香港人才房申请.jpg"
    if len(sys.argv) > 1:
        img = sys.argv[1]

    ocr_dir = os.getenv("PPOCR_MODEL_DIR", "/root/consult/backend/models/ppocr")
    use_gpu = env_bool("PPOCR_USE_GPU", True)
    det_dir = os.path.join(ocr_dir, "det")
    rec_dir = os.path.join(ocr_dir, "rec")
    cls_dir = os.path.join(ocr_dir, "cls")
    use_angle_cls = os.path.isdir(cls_dir) and any(os.scandir(cls_dir))

    print(f"PPOCR_MODEL_DIR={ocr_dir}")
    print(f"PPOCR_USE_GPU={use_gpu}")
    print(f"use_angle_cls={use_angle_cls}")
    print(f"image={img}")

    ocr = PaddleOCR(
        use_angle_cls=use_angle_cls,
        lang="ch",
        use_gpu=use_gpu,
        det_model_dir=det_dir,
        rec_model_dir=rec_dir,
        cls_model_dir=cls_dir if use_angle_cls else None,
        show_log=False,
    )

    try:
        result = ocr.ocr(img, cls=use_angle_cls)
    except Exception as e:
        print(f"[ERROR] OCR 调用失败: {e}")
        sys.exit(2)

    if not result:
        print("[WARN] OCR 无返回结果")
        sys.exit(0)

    lines = []
    for page in result or []:
        if not page:
            continue
        for line in page or []:
            try:
                txt = str(line[1][0])
                conf = float(line[1][1])
                lines.append((conf, txt))
            except Exception:
                continue

    if not lines:
        print("[INFO] 未识别到文本")
        sys.exit(0)

    lines.sort(reverse=True, key=lambda x: x[0])
    print("Top lines:")
    for conf, txt in lines[:10]:
        print(f"- {conf:.3f}: {txt}")

    avg_conf = sum(c for c, _ in lines) / len(lines)
    print(f"avg_conf={avg_conf:.3f}, total_lines={len(lines)}")


if __name__ == "__main__":
    main()


