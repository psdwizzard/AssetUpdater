import hashlib
import json
import os
import time
from pathlib import Path

import folder_paths
import node_helpers
import numpy as np
import torch
from PIL import Image, ImageOps


# Keep this legacy socket type stable so older saved workflow links keep resolving.
ASSET_TYPE = "ASSETMAN_ASSET"
OUTPUT_SUBFOLDER = "AssetUpdater"
PROMPT_FILENAME = "prompt.txt"
DEFAULT_PROMPT_FILENAME = "DefaultPrompt.txt"


def _normalize_path(path_text: str) -> Path:
    normalized = os.path.expandvars(os.path.expanduser(path_text.strip()))
    return Path(normalized).resolve()


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip()


def _build_asset_entry(source_root: Path, image_path: Path, prompt_text: str) -> str:
    relative_path = image_path.relative_to(source_root).as_posix()
    payload = {
        "source_root": source_root.as_posix(),
        "image_path": image_path.as_posix(),
        "relative_path": relative_path,
        "prompt": prompt_text,
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_asset_entry(asset_entry: str) -> dict:
    payload = json.loads(asset_entry)
    required_keys = {"source_root", "image_path", "relative_path", "prompt"}
    missing = required_keys.difference(payload)
    if missing:
        raise ValueError(f"Asset entry missing keys: {sorted(missing)}")
    return payload


def _pil_to_image_tensor(image: Image.Image) -> torch.Tensor:
    image_np = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(image_np)[None, ...]


def _pil_to_mask_tensor(image: Image.Image) -> torch.Tensor:
    if "A" in image.getbands():
        alpha = np.asarray(image.getchannel("A")).astype(np.float32) / 255.0
        return (1.0 - torch.from_numpy(alpha)).unsqueeze(0)
    return torch.zeros((1, 64, 64), dtype=torch.float32)


def _resize_image_tensor(images: torch.Tensor, width: int, height: int) -> list[Image.Image]:
    resized_images = []
    for image in images:
        image_np = np.clip(image.cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        pil_image = Image.fromarray(image_np)
        if pil_image.size != (width, height):
            pil_image = pil_image.resize((width, height), Image.Resampling.LANCZOS)
        resized_images.append(pil_image)
    return resized_images


def _collect_asset_entries(source_root: Path, mode: str) -> list[str]:
    default_prompt_path = source_root / DEFAULT_PROMPT_FILENAME
    default_prompt = _read_text_file(default_prompt_path) if default_prompt_path.exists() else ""

    assets = []
    for current_root, dirnames, filenames in os.walk(source_root):
        dirnames.sort()
        current_path = Path(current_root)
        prompt_path = current_path / PROMPT_FILENAME
        prompt_text = _read_text_file(prompt_path) if prompt_path.exists() else default_prompt

        image_paths = sorted(
            current_path / name
            for name in filenames
            if name.lower().endswith(".png")
        )

        if mode == "test_one_per_folder" and image_paths:
            image_paths = image_paths[:1]

        for image_path in image_paths:
            assets.append(_build_asset_entry(source_root, image_path, prompt_text))

    return assets


class AssetUpdaterFolderLoader:
    _asset_cache = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_root": ("STRING", {"default": "", "multiline": False}),
                "mode": (["test_one_per_folder", "full"],),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999999, "step": 1}),
                "start_index": ("INT", {"default": 0, "min": 0, "max": 9999999, "step": 1}),
                "max_files": ("INT", {"default": 100, "min": 0, "max": 9999999, "step": 1}),
            }
        }

    RETURN_TYPES = (ASSET_TYPE, "STRING", "STRING", "INT", "INT", "INT", "BOOLEAN")
    RETURN_NAMES = (
        "asset",
        "prompt",
        "relative_path",
        "asset_count",
        "selected_count",
        "selected_index",
        "has_more",
    )
    FUNCTION = "scan"
    CATEGORY = "AssetUpdater"

    @classmethod
    def IS_CHANGED(cls, source_root, mode, index=0, start_index=0, max_files=100):
        try:
            root = _normalize_path(source_root)
        except Exception:
            return hashlib.sha256(
                f"{source_root}|{mode}|{index}|{start_index}|{max_files}".encode("utf-8")
            ).hexdigest()

        digest = hashlib.sha256(
            f"{root.as_posix()}|{mode}|{index}|{start_index}|{max_files}".encode("utf-8")
        )
        if not root.exists():
            return digest.hexdigest()

        for current_root, _, files in os.walk(root):
            digest.update(current_root.encode("utf-8"))
            for name in sorted(files):
                if name.lower().endswith(".png") or name in {PROMPT_FILENAME, DEFAULT_PROMPT_FILENAME}:
                    file_path = Path(current_root) / name
                    try:
                        stat = file_path.stat()
                    except OSError:
                        continue
                    digest.update(name.encode("utf-8"))
                    digest.update(str(stat.st_mtime_ns).encode("utf-8"))
                    digest.update(str(stat.st_size).encode("utf-8"))
        return digest.hexdigest()

    def _get_assets(self, source_root: Path, mode: str, cache_key: str) -> list[str]:
        cache_key_full = f"{cache_key}|{mode}"
        if cache_key_full not in self._asset_cache:
            self._asset_cache[cache_key_full] = _collect_asset_entries(source_root, mode)
        return self._asset_cache[cache_key_full]

    def scan(self, source_root, mode, index, start_index, max_files):
        root = _normalize_path(source_root)
        if not root.exists():
            raise FileNotFoundError(f"Source root does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Source root is not a directory: {root}")

        cache_key = self.IS_CHANGED(source_root, mode, index, start_index, max_files)
        assets = self._get_assets(root, mode, cache_key)
        asset_count = len(assets)

        if asset_count == 0:
            raise ValueError(f"No PNG files found under: {root}")

        selected_assets = assets[start_index:]
        if max_files > 0:
            selected_assets = selected_assets[:max_files]

        selected_count = len(selected_assets)
        if selected_count == 0:
            raise ValueError(
                f"No assets selected from start_index={start_index} max_files={max_files} under: {root}"
            )
        if index >= selected_count:
            raise IndexError(
                f"Requested index {index} is outside the selected range of {selected_count} assets"
            )

        selected_asset = selected_assets[index]
        payload = _parse_asset_entry(selected_asset)
        has_more = index < (selected_count - 1)

        return (
            selected_asset,
            payload["prompt"],
            payload["relative_path"],
            asset_count,
            selected_count,
            index,
            has_more,
        )


class AssetUpdaterAutoBatchLoader:
    _asset_cache = {}
    _run_state = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_root": ("STRING", {"default": "", "multiline": False}),
                "folder_mode": (["full", "single_per_folder"],),
                "start_image_number": ("INT", {"default": 0, "min": 0, "max": 9999999, "step": 1}),
                "reset_batch": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = (ASSET_TYPE, "STRING", "STRING", "INT", "INT", "INT", "BOOLEAN")
    RETURN_NAMES = (
        "asset",
        "prompt",
        "relative_path",
        "total_images_found",
        "images_in_this_run",
        "current_image_number",
        "has_more",
    )
    FUNCTION = "next_asset"
    CATEGORY = "AssetUpdater"

    @classmethod
    def IS_CHANGED(cls, source_root, folder_mode, start_image_number=0, reset_batch=False):
        # Force execution on each queued run so the node can advance its internal cursor.
        return f"{source_root}|{folder_mode}|{start_image_number}|{reset_batch}|{time.time_ns()}"

    def _get_assets(self, source_root: Path, folder_mode: str) -> list[str]:
        normalized_mode = "test_one_per_folder" if folder_mode == "single_per_folder" else "full"
        cache_key = f"{source_root.as_posix()}|{normalized_mode}"
        if cache_key not in self._asset_cache:
            self._asset_cache[cache_key] = _collect_asset_entries(source_root, normalized_mode)
        return self._asset_cache[cache_key]

    def _state_key(self, source_root: Path, folder_mode: str) -> str:
        return f"{source_root.as_posix()}|{folder_mode}"

    def next_asset(self, source_root, folder_mode, start_image_number, reset_batch):
        root = _normalize_path(source_root)
        if not root.exists():
            raise FileNotFoundError(f"Source root does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Source root is not a directory: {root}")

        assets = self._get_assets(root, folder_mode)
        total_images_found = len(assets)
        if total_images_found == 0:
            raise ValueError(f"No PNG files found under: {root}")

        if start_image_number >= total_images_found:
            raise ValueError(
                f"start_image_number={start_image_number} is outside the available range of {total_images_found} images under: {root}"
            )

        state_key = self._state_key(root, folder_mode)
        if reset_batch or state_key not in self._run_state:
            self._run_state[state_key] = start_image_number

        current_image_number = self._run_state[state_key]
        if current_image_number < start_image_number:
            current_image_number = start_image_number
            self._run_state[state_key] = current_image_number

        if current_image_number >= total_images_found:
            raise IndexError(
                f"All images have been processed starting from start_image_number={start_image_number}. "
                "Set reset_batch to true to restart from that image number."
            )

        selected_asset = assets[current_image_number]
        payload = _parse_asset_entry(selected_asset)
        has_more = current_image_number < (total_images_found - 1)
        self._run_state[state_key] = current_image_number + 1

        return (
            selected_asset,
            payload["prompt"],
            payload["relative_path"],
            total_images_found,
            1,
            current_image_number,
            has_more,
        )


class AssetUpdaterImageLoad:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"asset": (ASSET_TYPE,)}}

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("image", "mask", "prompt", "relative_path", "width", "height", "source_path")
    FUNCTION = "load"
    CATEGORY = "AssetUpdater"

    def load(self, asset):
        payload = _parse_asset_entry(asset)
        image_path = Path(payload["image_path"])
        if not image_path.exists():
            raise FileNotFoundError(f"Image file does not exist: {image_path}")

        pil_image = node_helpers.pillow(Image.open, str(image_path))
        pil_image = node_helpers.pillow(ImageOps.exif_transpose, pil_image)
        rgba_image = pil_image.convert("RGBA")
        rgb_image = rgba_image.convert("RGB")

        width, height = rgb_image.size
        image_tensor = _pil_to_image_tensor(rgb_image)
        mask_tensor = _pil_to_mask_tensor(rgba_image)

        return (
            image_tensor,
            mask_tensor,
            payload["prompt"],
            payload["relative_path"],
            width,
            height,
            payload["image_path"],
        )


class AssetUpdaterSaveOutput:
    def __init__(self):
        self.output_dir = Path(folder_paths.get_output_directory())

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "relative_path": ("STRING", {"forceInput": True}),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "overwrite": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "AssetUpdater"

    def save(self, images, relative_path, width, height, overwrite):
        relative = Path(relative_path)
        target_path = (self.output_dir / OUTPUT_SUBFOLDER / relative).with_suffix(".png")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        resized_images = _resize_image_tensor(images, width, height)

        for index, pil_image in enumerate(resized_images):
            current_target = target_path
            if len(resized_images) > 1:
                current_target = current_target.with_name(
                    f"{current_target.stem}_{index:03d}{current_target.suffix}"
                )

            if not overwrite and current_target.exists():
                suffix = 1
                while True:
                    candidate = current_target.with_name(
                        f"{current_target.stem}_{suffix:03d}{current_target.suffix}"
                    )
                    if not candidate.exists():
                        current_target = candidate
                        break
                    suffix += 1

            pil_image.save(current_target, format="PNG")
            saved_paths.append(current_target.as_posix())

        saved_path_text = "\n".join(saved_paths)
        return {
            "ui": {"text": saved_paths},
            "result": (saved_path_text,),
        }


AssetManFolderLoader = AssetUpdaterFolderLoader
AssetManAutoBatchLoader = AssetUpdaterAutoBatchLoader
AssetManImageLoad = AssetUpdaterImageLoad
AssetManSaveOutput = AssetUpdaterSaveOutput


NODE_CLASS_MAPPINGS = {
    "AssetUpdater Auto Batch Loader": AssetUpdaterAutoBatchLoader,
    "AssetUpdater Folder Loader": AssetUpdaterFolderLoader,
    "AssetUpdater Image Load": AssetUpdaterImageLoad,
    "AssetUpdater Save Output": AssetUpdaterSaveOutput,
    "AssetMan Auto Batch Loader": AssetUpdaterAutoBatchLoader,
    "AssetMan Folder Loader": AssetUpdaterFolderLoader,
    "AssetMan Image Load": AssetUpdaterImageLoad,
    "AssetMan Save Output": AssetUpdaterSaveOutput,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "AssetUpdater Auto Batch Loader": "AssetUpdater Auto Batch Loader",
    "AssetUpdater Folder Loader": "AssetUpdater Folder Loader",
    "AssetUpdater Image Load": "AssetUpdater Image Load",
    "AssetUpdater Save Output": "AssetUpdater Save Output",
    "AssetMan Auto Batch Loader": "AssetUpdater Auto Batch Loader",
    "AssetMan Folder Loader": "AssetUpdater Folder Loader",
    "AssetMan Image Load": "AssetUpdater Image Load",
    "AssetMan Save Output": "AssetUpdater Save Output",
}
