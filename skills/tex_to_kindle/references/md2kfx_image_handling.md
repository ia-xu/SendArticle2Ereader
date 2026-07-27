# md2kfx.py Image Handling — Full Trace

## Architecture

```
MarkdownToKFX(markdown_file, output_file)
  │
  ├─ self.md_file      = Path(markdown_file).absolute()   ← anchor for image lookup
  ├─ self.temp_dir     = tempfile.mkdtemp()                ← C:\Temp\xxx
  └─ self.images_dir   = temp_dir / "images"              ← images land here for EPUB
```

## Image Processing Flow (in `markdown_to_html`)

For each `![alt](url)` in the Markdown:

### 1. Remote images (`http://` / `https://`)
- Downloaded via `download_image()` → `temp_dir/images/<hash>.jpg`
- MD reference updated to `images/<hash>.jpg`

### 2. Local `images/xxx` paths (our paper case)
```python
img_name = img_url[len('images/'):]               # "mainfig.jpg"
src_path = self.md_file.parent / 'images' / img_name  # md's sibling images/
if src_path.exists():
    converted_name = self.convert_image_for_kindle(src_path, self.images_dir)
    # Copies src → temp_dir/images/<converted_name>
else:
    print(f"  [Warning] Image not found: {src_path}")
    # MD reference left AS-IS — image never reaches EPUB/KFX
```

### 3. Other relative paths
- Same logic, resolved against `self.md_file.parent`

## The Silent Skip Problem

When `src_path` doesn't exist:
- A `[Warning]` is printed to stdout (easily missed in MCP server logs)
- The `![](images/xxx.jpg)` reference remains unchanged in the Markdown
- `temp_dir/images/` stays empty (no image files to embed)
- Python markdown converts `![alt](images/xxx.jpg)` → `<img alt="alt" src="images/xxx.jpg"/>`
- `create_epub()` iterates `temp_dir/images/` — finds nothing — no images in EPUB
- EPUB → KFX via Calibre: KFX has `<img>` tags but no resource files
- Kindle renders placeholder icons for missing resources

## Diagnostic Recipe (Kindle shows placeholders)

### Step 1: Check EPUB content
```python
import zipfile, re
with zipfile.ZipFile('paper.epub', 'r') as z:
    content = z.read('EPUB/content.xhtml').decode('utf-8')
    imgs = re.findall(r'<img[^>]*>', content)
    img_files = [f for f in z.namelist() if f.startswith('EPUB/images/')]
    print(f"<img> tags: {len(imgs)}, actual image files: {len(img_files)}")
```
If `<img>` count > image file count → images were never embedded.

### Step 2: Check KFX resources
```bash
calibre-debug -r "KFX Input" -- paper.kfx --unpack unpacked.zip
```
Then compare resource count vs expected. If zero JPEG resources → pipeline never had images.

### Step 3: Verify source image directory
Check that `self.md_file.parent / "images" / img_name` exists at conversion time.
For MCP conversions, `self.md_file.parent` is `UPLOAD_FOLDER` (not the original
paper output directory).

## MCP Server Path Mismatch (P27)

The MCP server (`mcp_server.py`) copies images to `UPLOAD_FOLDER/{file_id}_images/`
but `MarkdownToKFX` looks in `UPLOAD_FOLDER/images/`. The `_images` suffix on the
directory name causes the path mismatch.

Fixed in v3.7: `mcp_server.py` line 284 changed from `f"{file_id}_images"` to `"images"`.

### Step 4: Unpack KFX and verify resource references match
```python
with zipfile.ZipFile('kfx_unpacked.zip', 'r') as z:
    ion = z.read('book.ion').decode('utf-8', errors='replace')
    refs = set(re.findall(r'resource/rsrc[A-Za-z0-9]+', ion))
    files = set(f.split('/')[1].replace('..jpg','') for f in z.namelist() if f.startswith('resource/'))
    print(f"Missing: {files - refs}")
```
