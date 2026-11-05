"""生成《拓》教学用阳刻板：先打印 50×50 mm 单字试片，再考虑整板。

文字竖排、右起；《劝学》两列分别为五字和四字，共九字。
PNG 与 STL 使用同一份加工后的轮廓；字内孔洞保留，浮雕与底板布尔并集。
笔画加粗为加工目标，可能合并密集字的间隙，必须查看预览和切片。
用法：python make_stele.py [--preview] [--font 字体路径] [--sample-only]
"""

import argparse
import json
import math
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon

OUT_DIR = Path(__file__).parent / "stl"
PREVIEW_DIR = Path(__file__).parent / "preview"
PLATE_W = 120.0
PLATE_H = 200.0
PLATE_T = 4.0
RELIEF_H = 1.2
MARGIN = 10.0
PX_PER_MM = 8.0
MIN_STROKE_MM = 1.5
OVERLAP_MM = 0.05
FONT_CANDIDATES = [
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/STKAITI.TTF",
    "C:/Windows/Fonts/simsun.ttc",
]
BOARD_RIGHT = "青取之於藍"
BOARD_LEFT = "而青於藍"
BOARD_ALT = "拓之唯印之傳"  # 自拟展台文案，不标为古籍引文。


def load_font(size, font_path=None):
    paths = [font_path] if font_path else FONT_CANDIDATES
    for p in paths:
        if p and Path(p).is_file():
            return ImageFont.truetype(str(p), size)
    raise RuntimeError("找不到中文字体，请通过 --font 指定支持繁体字的字体")


def fit_font(text, plate_w, plate_h, font_path=None, max_px=400):
    """按每个字实际墨迹边界计算列高，留出加粗所需余量。"""
    if not text:
        raise ValueError("文字不能为空")
    pad = MIN_STROKE_MM
    usable_w = (plate_w - 2 * (MARGIN + pad)) * PX_PER_MM
    usable_h = (plate_h - 2 * (MARGIN + pad)) * PX_PER_MM
    for px in range(max_px, 15, -2):
        font = load_font(px, font_path)
        boxes = [font.getbbox(ch) for ch in text]
        widths = [b[2] - b[0] for b in boxes]
        heights = [b[3] - b[1] for b in boxes]
        gap = px * 0.18
        col_w = max(widths)
        col_h = sum(heights) + gap * (len(text) - 1)
        if col_w <= usable_w and col_h <= usable_h:
            return px, font, col_w, col_h, gap, heights
    raise ValueError("板面过小，文字无法在留边范围内排下")


def render_column(text, font, canvas_wh, gap, heights):
    """图像坐标原点在左上角；生成竖排文字 mask。"""
    w, h = canvas_wh
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    y = (h - sum(heights) - gap * (len(text) - 1)) / 2
    for ch, char_h in zip(text, heights):
        bb = d.textbbox((0, 0), ch, font=font)
        char_w = bb[2] - bb[0]
        d.text(((w - char_w) / 2 - bb[0], y - bb[1]), ch, font=font, fill=255)
        y += char_h + gap
    return img


def thicken_to_min_stroke(mask, min_stroke_px):
    """用骨架上直径至少达到目标的圆盘补粗，再开运算清理细尖。

    参数单位是像素。返回骨架局部宽度的第10百分位(mm)，这是诊断值，
    不是所有尖角的严格最小宽度；密集笔画可能相连，需人工审预览。
    """
    from scipy import ndimage
    from skimage import morphology

    if min_stroke_px <= 0:
        raise ValueError("目标笔画宽度必须为正")
    m = np.asarray(mask) > 127
    if not m.any():
        raise ValueError("文字 mask 为空")
    radius = max(1, math.ceil(min_stroke_px / 2))
    disk = morphology.disk(radius)
    skeleton = morphology.skeletonize(m)
    cur = m | morphology.binary_dilation(skeleton, disk)
    cur = morphology.binary_opening(cur, disk)
    distance = ndimage.distance_transform_edt(cur)
    spine = morphology.skeletonize(cur)
    widths = 2 * distance[spine] / PX_PER_MM
    diagnostic = float(np.percentile(widths, 10)) if widths.size else 0.0
    return Image.fromarray((cur * 255).astype(np.uint8)), diagnostic


def mask_to_polygons(mask, min_area_px=4):
    """提取带内孔的 Shapely Polygon；不把内孔作为独立实心笔画。"""
    import cv2

    m = (np.asarray(mask) > 127).astype(np.uint8)
    contours, hierarchy = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    polys = []
    for i, c in enumerate(contours):
        if hierarchy[i][3] != -1 or len(c) < 3:
            continue
        holes = []
        child = hierarchy[i][2]
        while child != -1:
            if len(contours[child]) >= 3:
                holes.append(contours[child].reshape(-1, 2))
            child = hierarchy[child][0]
        poly = Polygon(c.reshape(-1, 2), holes)
        if not poly.is_valid:
            poly = poly.buffer(0)
        parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
        polys.extend(p for p in parts if not p.is_empty and p.area >= min_area_px)
    return polys


def to_mm_polygon(poly, plate_w, plate_h):
    """像素左上原点 -> 毫米板心原点；翻 Y，让俯视 STL 字向与 PNG 一致。"""
    from shapely.affinity import affine_transform
    return affine_transform(poly, [1 / PX_PER_MM, 0, 0, -1 / PX_PER_MM,
                                   -plate_w / 2, plate_h / 2])


def prepare_plate(text, plate_w, plate_h, font_path=None):
    px, font, _, _, gap, heights = fit_font(text, plate_w, plate_h, font_path)
    canvas = (round(plate_w * PX_PER_MM), round(plate_h * PX_PER_MM))
    mask = render_column(text, font, canvas, gap, heights)
    mask, stroke = thicken_to_min_stroke(mask, MIN_STROKE_MM * PX_PER_MM)
    polys = mask_to_polygons(mask)
    if not polys:
        raise RuntimeError(f"未能从 {text!r} 提取到笔画轮廓")
    mm_polys = [to_mm_polygon(p, plate_w, plate_h) for p in polys]
    for p in mm_polys:
        x0, y0, x1, y1 = p.bounds
        if x0 <= -plate_w / 2 or x1 >= plate_w / 2 or y0 <= -plate_h / 2 or y1 >= plate_h / 2:
            raise ValueError("字形越过底板边界")
    return mm_polys, px, stroke


def build_solid(polys, plate_w, plate_h, plate_t, relief_h):
    """浮雕与底板略微重叠后并集，输出可切片的单个封闭实体。"""
    import trimesh

    if min(plate_w, plate_h, plate_t, relief_h) <= 0 or plate_t <= OVERLAP_MM:
        raise ValueError("板面、板厚和浮雕高度必须为正且板厚大于并集重叠量")
    base = trimesh.creation.box(extents=[plate_w, plate_h, plate_t])
    base.apply_translation([0, 0, plate_t / 2])
    meshes = [base]
    for poly in polys:
        raised = trimesh.creation.extrude_polygon(poly, relief_h + OVERLAP_MM, engine="earcut")
        raised.apply_translation([0, 0, plate_t - OVERLAP_MM])
        meshes.append(raised)
    body = trimesh.boolean.union(meshes, engine="manifold", check_volume=True)
    body.remove_unreferenced_vertices()
    if not body.is_watertight or not body.is_volume or body.body_count != 1:
        raise RuntimeError("STL 未通过单一封闭实体检查")
    expected = plate_w * plate_h * plate_t + sum(p.area for p in polys) * relief_h
    if not math.isclose(body.volume, expected, rel_tol=1e-5, abs_tol=0.01):
        raise RuntimeError("布尔并集体积不符，可能有浮雕重叠或丢失")
    return body


def build_plate(text, plate_w, plate_h, plate_t, relief_h, out_path, font_path=None):
    polys, px, stroke = prepare_plate(text, plate_w, plate_h, font_path)
    body = build_solid(polys, plate_w, plate_h, plate_t, relief_h)
    body.export(out_path)
    return body, polys, px, stroke


def draw_preview(polys, plate_w, plate_h):
    """按最终轮廓绘图；白底黑字，内孔保持白色。"""
    img = Image.new("RGB", (round(plate_w * PX_PER_MM), round(plate_h * PX_PER_MM)), "white")
    d = ImageDraw.Draw(img)

    def points(ring):
        return [((x + plate_w / 2) * PX_PER_MM,
                 (plate_h / 2 - y) * PX_PER_MM) for x, y in ring.coords]

    # 大轮廓先画，使孔内嵌套的独立笔画最后补回。
    for p in sorted(polys, key=lambda p: p.area, reverse=True):
        d.polygon(points(p.exterior), fill="black")
        for hole in p.interiors:
            d.polygon(points(hole), fill="white")
    return img


def preview_pair(out_png, tiles):
    gap = round(14 * PX_PER_MM)
    out = Image.new("RGB", (tiles[0].width + gap + tiles[1].width,
                            max(tile.height for tile in tiles)), "white")
    out.paste(tiles[0], (0, 0))  # 下句在左。
    out.paste(tiles[1], (tiles[0].width + gap, 0))
    out.save(out_png)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true", help="只生成 PNG，不生成 STL")
    ap.add_argument("--font", help="支持繁体中文的字体文件")
    ap.add_argument("--sample-only", action="store_true", help="仅生成 50×50 mm 首测板")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    PREVIEW_DIR.mkdir(exist_ok=True)
    jobs = [("stele_sample_qing", "青", 50.0, 50.0)]
    if not args.sample_only:
        jobs.extend([
            ("stele_right_qing", BOARD_RIGHT, PLATE_W, PLATE_H),
            ("stele_left_er", BOARD_LEFT, PLATE_W, PLATE_H),
            ("stele_alt_tuozhi", BOARD_ALT, PLATE_W, PLATE_H),
        ])
    manifest = []
    tiles = {}
    for name, text, w, h in jobs:
        polys, px, stroke = prepare_plate(text, w, h, args.font)
        image = draw_preview(polys, w, h)
        image.save(PREVIEW_DIR / f"{name}.png")
        tiles[name] = image
        row = dict(name=name, text=text, size_mm=[w, h, PLATE_T + RELIEF_H],
                   font_size_px=px, stroke_target_mm=MIN_STROKE_MM,
                   skeleton_width_p10_mm=round(stroke, 3),
                   counter_count=sum(len(p.interiors) for p in polys),
                   preview=f"preview/{name}.png")
        if not args.preview:
            body = build_solid(polys, w, h, PLATE_T, RELIEF_H)
            body.export(OUT_DIR / f"{name}.stl")
            row.update(stl=f"stl/{name}.stl", watertight=bool(body.is_watertight),
                       solid_count=int(body.body_count), volume_cm3=round(body.volume / 1000, 3))
        manifest.append(row)
        print(json.dumps(row, ensure_ascii=False))
    if not args.sample_only:
        preview_pair(PREVIEW_DIR / "stele_pair.png",
                     [tiles["stele_left_er"], tiles["stele_right_qing"]])
    # 分开保存，避免只出预览时覆盖已验证 STL 的清单。
    manifest_name = "preview_manifest.json" if args.preview else "manifest.json"
    (PREVIEW_DIR if args.preview else OUT_DIR).joinpath(manifest_name).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
