# AssetUpdater Implementation Notes

## Purpose

AssetUpdater is a ComfyUI custom node package for one-at-a-time asset update workflows. It handles PNG discovery, prompt lookup, image and alpha-mask loading, metadata handoff, and mirrored output saving so the main ComfyUI workflow can focus on the image edit model.

## Folder

Recommended install location:

- `ComfyUI/custom_nodes/AssetUpdater`

## Registered Nodes

Current public node names:

- `AssetUpdater Auto Batch Loader`
- `AssetUpdater Folder Loader`
- `AssetUpdater Image Load`
- `AssetUpdater Save Output`

Legacy compatibility aliases are also registered for existing workflows:

- `AssetMan Auto Batch Loader`
- `AssetMan Folder Loader`
- `AssetMan Image Load`
- `AssetMan Save Output`

## Processing Model

AssetUpdater scans PNG files recursively in sorted folder and filename order. Prompt text is resolved from `prompt.txt` in each image folder, then from root-level `DefaultPrompt.txt` as a fallback.

The auto batch loader returns one asset per queued execution and advances its internal cursor. This keeps large texture libraries from being loaded into memory all at once.

## Prompt Writer

`prompt-writer-app/index.html` is a browser helper for creating folder-level `prompt.txt` files before running the ComfyUI workflow. It scans only leaf folders, displays each folder's image index range, and writes prompts from a template without overwriting existing prompt files.

## Output

The save node writes edited PNG files to:

- `ComfyUI/output/AssetUpdater/<original relative path>.png`

The original width and height are restored before save, and batch outputs keep the source folder structure intact.
