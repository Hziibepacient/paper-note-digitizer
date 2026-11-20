---
name: paper-note-digitizer
description: Digitize photos of handwritten paper notes, cards, and small paper keepsakes into transparent PNGs with their original silhouettes, folds, and a short paper-edge shadow. Use for extracting one paper item or processing a reviewed batch. Use the source artwork and keep the original photography separate.
---

# Paper Note Digitizer

Create an sRGB transparent PNG from each photographed paper item. Keep the original handwriting, artwork, paper color, folds, and curved silhouette. The original-edge treatment adds a thin, muted edge at the lower right and a short contact shadow. Match the photograph's actual perimeter. Use the original paper pixels for the face and keep the narrow shadow outside it.

1. Inventory the requested files. Inspect a contact sheet for mixed collections and identify which files show separate paper items, repeat views, reverse sides, or related enclosures. Keep source filenames in the local batch mapping. Preserve the original files and use a separate output directory.
2. Trace each paper boundary on the EXIF-oriented photo. Follow physical bends and folds. Use extra points wherever the contour changes direction. Check the trace over the photo at the corners and where the paper touches fingers, a similarly colored surface, or text. Review any proposed automatic outline. The tool also accepts an existing transparent PNG with a clean, unshaded outline.
3. Run `scripts/digitize_note.py` with Python 3 and Pillow (`python -m pip install Pillow` if needed). Pass the full photo and its outline, or pass the clean transparent PNG without `--outline`.

   ```text
   python scripts/digitize_note.py photo.jpg note.png --outline outline.json
   python scripts/digitize_note.py photo.jpg note.png --outline outline.json --rotate 90
   python scripts/digitize_note.py cutout.png note.png
   ```

   Outline JSON is an array of `[x, y]` pixel coordinates in perimeter order, measured on the full-size EXIF-oriented photo from its top-left. The tool closes the polygon. If you trace on a resized image, scale both axes back to full pixels. `--rotate` is the additional clockwise quarter-turn after tracing and before lighting, useful when the handwriting is sideways. The tool emits one PNG and refuses to replace it without `--overwrite`.
4. Review the exports as a contact sheet at a normal display size and inspect trouble spots at full size. Check that each note is upright, fingers and background are gone, strokes that reach the edge remain visible, and the lower-right shadow sits close to the edge. Use a light neutral and a darker surface to reveal fringing or edge clipping. For a batch, reconcile the exported file count against the selected sources and record incomplete or ambiguous items.

The PNG is an asset for a gallery, archive, or scrapbook. It includes the paper appearance and its short shadow. Keep personal photos, annotations, and finished assets local unless the user explicitly asks to share them.
