"""CPU-only DocLayout-YOLO benchmark for an existing page PNG.

Use a separate Python environment. Does not contact Nextcloud or modify PDF.
"""
import argparse
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", default="/tmp/retro-doclayout")
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--conf", type=float, default=0.2)
    args = parser.parse_args()

    from huggingface_hub import hf_hub_download
    from doclayout_yolo import YOLOv10
    from PIL import Image

    path = Path(args.image).expanduser().resolve()
    if not path.is_file():
        parser.error(f"Image not found: {path}")
    dest = Path(args.out).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    weights = hf_hub_download(
        repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
        filename="doclayout_yolo_docstructbench_imgsz1024.pt",
    )
    model = YOLOv10(weights)
    start = time.perf_counter()
    results = model.predict(
        str(path), device="cpu", imgsz=args.imgsz,
        conf=args.conf, verbose=False
    )
    elapsed = time.perf_counter() - start
    result = results[0]
    detections = []
    if result.boxes is not None:
        for box in result.boxes:
            idx = int(box.cls[0].item())
            detections.append({
                "class_name": str(result.names[idx]),
                "confidence": round(float(box.conf[0].item()), 4),
                "bbox_pixels": [
                    round(float(x), 1) for x in box.xyxy[0].tolist()
                ],
            })
    detections.sort(key=lambda d: (d["bbox_pixels"][1], d["bbox_pixels"][0]))
    report = {
        "source_image": path.name,
        "model": "juliozhao/DocLayout-YOLO-DocStructBench",
        "device": "cpu",
        "seconds": round(elapsed, 2),
        "detections": detections,
        "approved": False,
    }
    report_path = dest / "layout_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    # Ultralytics returns BGR; convert to RGB for Pillow.
    annotated = Image.fromarray(result.plot()[..., ::-1])
    image_path = dest / "layout_annotated.png"
    annotated.save(image_path)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Annotated image: {image_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
