"""Launcher button that patches a USA 1.1 disc from a downloaded .apalundra file.

The download is a zip. placement.json inside it is the document --placement-in
reads. This module extracts that member. The randomizer is not taught to open
the zip. The Linux binary and its two tools ship in patcher/linux and are
extracted to a temporary directory, which is the process working directory.
The tools are ./tools/dumpsxiso and ./tools/mkpsxiso from that directory.
"""

from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
import zipfile
from importlib.resources import files
from pathlib import Path

_LINUX_FILES = (
    "alundra-randomizer",
    "tools/dumpsxiso",
    "tools/mkpsxiso",
)
_WINDOWS_FILES = (
    "alundra-randomizer.exe",
    "tools/dumpsxiso.exe",
    "tools/mkpsxiso.exe",
)
_PLATFORM_LAYOUT = {
    "linux": ("linux", _LINUX_FILES),
    "win32": ("win32", _WINDOWS_FILES),
}
_PLATFORM_NAME = {
    "linux": "Linux",
    "win32": "Windows",
    "darwin": "macOS",
}
_OUTPUT_MARK = "Randomized game outputted to "
_PATCH_TYPES = (("Alundra patch", (".apalundra",)),)
_DISC_TYPES = (("Alundra disc", (".bin",)),)


class PatchError(Exception):
    """The button cannot start the randomizer, or the randomizer did not produce a disc."""


def launch_patch(*args: str) -> None:
    """Patch a USA 1.1 disc.

    With no path, ask for the .apalundra file, then ask for the disc. Open
    Patch does not offer this suffix. The placement file already carries the
    settings, so this does not ask for a preset.
    """
    from worlds.LauncherComponents import launch

    launch(_patch_from_button, name="Alundra Patch", args=args)


def _patch_from_button(*args: str) -> None:
    from Utils import messagebox, open_filename

    patch_path = args[0] if args and args[0] else ""
    if not patch_path:
        chosen = open_filename("Select Alundra patch", _PATCH_TYPES)
        if not chosen:
            return
        patch_path = chosen
    disc = open_filename("Select Alundra USA 1.1 disc", _DISC_TYPES)
    if not disc:
        return
    try:
        image = _patch(Path(patch_path), Path(disc))
    except PatchError as error:
        messagebox("Alundra patch failed", str(error), error=True)
        return
    cue = image.with_suffix(".cue")
    messagebox("Alundra patched", f"Patched BIN/CUE written to:\n{image}\n{cue}")


def _patch(patch_path: Path, disc_path: Path) -> Path:
    """Extract the shipped patcher and placement.json, then run the randomizer."""
    patch_path = patch_path.expanduser().absolute()
    disc_path = disc_path.expanduser().absolute()
    if not disc_path.is_file():
        raise PatchError(f"Disc image was not found: {disc_path}")
    placement = _read_placement(patch_path)
    layout = _platform_layout(sys.platform)
    members = layout[1]
    with tempfile.TemporaryDirectory(prefix="alundra-patch-") as temporary:
        work = Path(temporary)
        _extract_patcher(layout, work)
        placement_path = work / "placement.json"
        placement_path.write_bytes(placement)
        output_dir = _output_directory(disc_path, patch_path, work)
        image = _run_randomizer(work, members[0], placement_path, disc_path, output_dir)
    if not image.is_file() or not image.with_suffix(".cue").is_file():
        raise PatchError(f"The randomizer finished without writing the BIN/CUE at {image}.")
    if _same_file(image, disc_path):
        raise PatchError("The patched image replaced the input disc.")
    return image


def _platform_layout(platform: str) -> tuple[str, tuple[str, ...]]:
    """Return the resource directory and the three files for this platform."""
    found = _PLATFORM_LAYOUT.get(platform)
    if found is None or not _layout_is_packaged(*found):
        raise PatchError(_missing_patcher(platform))
    return found


def _missing_patcher(platform: str) -> str:
    name = _PLATFORM_NAME.get(platform, platform)
    return f"The {name} patcher is not in this package."


def _layout_is_packaged(directory: str, members: tuple[str, ...]) -> bool:
    root = files(__package__).joinpath("patcher", directory)
    for member in members:
        resource = root.joinpath(*member.split("/"))
        try:
            present = resource.is_file()
        except OSError:
            return False
        if not present:
            return False
    return True


def _extract_patcher(layout: tuple[str, tuple[str, ...]], work: Path) -> None:
    directory, members = layout
    root = files(__package__).joinpath("patcher", directory)
    for member in members:
        target = work.joinpath(*member.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(root.joinpath(*member.split("/")).read_bytes())
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _read_placement(patch_path: Path) -> bytes:
    if not patch_path.is_file():
        raise PatchError(f"Patch file was not found: {patch_path}")
    if not zipfile.is_zipfile(patch_path):
        raise PatchError("The .apalundra file is not a zip, so placement.json cannot be read.")
    with zipfile.ZipFile(patch_path) as archive:
        try:
            return archive.read("placement.json")
        except KeyError as error:
            raise PatchError("The .apalundra file has no placement.json.") from error


def _output_directory(disc: Path, patch: Path, work: Path) -> Path:
    """A directory next to the disc, outside the temporary working directory."""
    stem = patch.stem or "Alundra"
    directory = disc.parent / stem
    if _conflicts(directory, disc, work):
        directory = disc.parent / f"{stem} patched"
    if _conflicts(directory, disc, work):
        raise PatchError("No output directory next to the disc is free of the input image.")
    if directory.exists() and not directory.is_dir():
        raise PatchError(f"{directory} is a file, so the patched disc cannot be written there.")
    if not directory.parent.is_dir():
        raise PatchError(f"Cannot create {directory} beside the disc.")
    return directory


def _conflicts(directory: Path, disc: Path, work: Path) -> bool:
    if _same_file(directory, disc) or _same_file(directory, work):
        return True
    return _is_inside(directory, work) or _is_inside(work, directory)


def _same_file(left: Path, right: Path) -> bool:
    if left.absolute() == right.absolute():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.absolute().relative_to(parent.absolute())
    except ValueError:
        return False
    return True


def _run_randomizer(work: Path, executable: str, placement: Path, disc: Path, output_dir: Path) -> Path:
    """Run with work as the working directory so ./tools resolves there.

    --input is required: the temporary directory does not contain the disc.
    --outputrom is a directory, so the image is named from the hash sentence
    and is not the input file. --placement-in reads the options from the JSON.
    """
    if _same_file(output_dir, work) or _is_inside(output_dir, work):
        raise PatchError("The output directory is the temporary directory.")
    completed = subprocess.run(
        [
            str(work / executable),
            f"--placement-in={placement}",
            f"--input={disc}",
            f"--outputrom={output_dir}",
            "--nopause",
        ],
        cwd=work,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    output = _process_output(completed)
    if completed.returncode != 0:
        raise PatchError(output or f"The randomizer exited with status {completed.returncode}.")
    image = _patched_image(completed.stdout, work)
    if image is None:
        raise PatchError(output or "The randomizer exited 0 without reporting the patched image.")
    if not image.is_absolute():
        image = work / image
    if _same_file(image, disc):
        raise PatchError("The patched image would replace the input disc.\n" + output)
    if _is_inside(image, work):
        raise PatchError("The patched image was written in the temporary directory.\n" + output)
    return image


def _process_output(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [part.rstrip() for part in (completed.stdout, completed.stderr) if part and part.strip()]
    text = "\n".join(parts)
    limit = 12000
    if len(text) <= limit:
        return text
    return text[-limit:]


def _patched_image(stdout: str, work: Path) -> Path | None:
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_OUTPUT_MARK):
            continue
        value = stripped[len(_OUTPUT_MARK):].strip()
        if value.endswith("."):
            value = value[:-1].strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = work / path
        return path
    return None
