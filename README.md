# AssetUpdater

AssetUpdater is a ComfyUI custom node package for processing large image asset libraries one file at a time. It is designed for texture, icon, and game-art update workflows where each source PNG needs to keep its folder structure, prompt context, alpha mask, and dimensions through an image-edit pipeline.

The included demo workflow can be used with image editing models such as Qwen Image Edit, Flux Kontext or other ComfyUI compatable image edit models.

## What It Does

- Recursively scans a source folder for PNG files.
- Reads `prompt.txt` from each image folder.
- Falls back to `DefaultPrompt.txt` in the source root when a folder prompt is missing.
- Loads one image at a time to keep memory and VRAM use predictable.
- Converts PNG alpha into a ComfyUI mask output.
- Preserves the original relative path as metadata.
- Restores the original width and height before saving.
- Saves edited images under `ComfyUI/output/AssetUpdater/<original relative path>.png`.

## Nodes

### AssetUpdater Auto Batch Loader

Use this for most batch work. It scans the selected source root and returns the next image each time the workflow is queued.

Inputs:

- `source_root`: absolute path to the asset library root.
- `folder_mode`: `full` processes every PNG; `single_per_folder` processes the first PNG in each folder.
- `start_image_number`: zero-based image index where processing should begin.
- `reset_batch`: resets the internal cursor back to `start_image_number`.

Outputs include the serialized asset record, prompt text, relative path, total image count, current image number, and whether more images remain.

### AssetUpdater Folder Loader

Use this when you want manual index control instead of automatic queued progression.

Inputs:

- `source_root`
- `mode`: `full` or `test_one_per_folder`
- `index`
- `start_index`
- `max_files`

### AssetUpdater Image Load

Takes an `asset` from one of the loader nodes and outputs:

- `image`
- `mask`
- `prompt`
- `relative_path`
- `width`
- `height`
- `source_path`

### AssetUpdater Save Output

Takes the edited image plus the original metadata and saves a PNG that mirrors the original folder structure.

## Prompt Files

AssetUpdater looks for prompt text in this order:

1. `prompt.txt` in the same folder as the source PNG.
2. `DefaultPrompt.txt` in the selected source root.
3. Empty prompt text if neither file exists.

This keeps per-folder prompt writing simple while still allowing a root-level default.

## Prompt Writer App

The `prompt-writer-app` folder contains a browser-only helper for generating `prompt.txt` files.

Open `prompt-writer-app/index.html` in current Chrome or Edge, choose the asset root folder, then review the discovered leaf folders. The app lists only folders with no subfolders, shows their zero-based image index range, and lets you edit the prompt label before writing `prompt.txt`.

The template box supports `[folderName]`. When prompt files are generated, `[folderName]` is replaced with the edited label for that row. Existing `prompt.txt` files are skipped so hand-written prompts are not overwritten.

## Demo Workflow

`asset_updater_clean_auto.json` is the cleaned automatic batch workflow. In ComfyUI:

1. Install this folder under `ComfyUI/custom_nodes/AssetUpdater`.
2. Restart ComfyUI.
3. Load `asset_updater_clean_auto.json`.
4. Set `source_root` on `AssetUpdater Auto Batch Loader`.
5. Set `reset_batch` to true for the first run.
6. Queue the workflow for the number of images you want to process.

The loader advances by one image for each queued execution.


