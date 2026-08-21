"""Build the add-on package, and the repository index beside it.

    python scripts/build_extension.py --blender "D:/Blender52/blender.exe"

Two things come out of `dist/`:

  * `void-tools.zip` - the add-on, and the only file that goes on a release;
  * `index.json` - the repository listing.

**The listing is only published with `--publish`.** `docs/repo/index.json` is
served from GitHub Pages and is what every installed copy reads to decide which
version to fetch, so a build that writes it every time is a build that can
advertise a release nobody made: a test build of an unreleased version,
committed with the code, gave everyone who checked for updates a 404. Pass the
flag when the version is actually going out, and not before.

Add that listing's URL once under **Preferences -> Get Extensions ->
Repositories** and Blender does the updating from then on, which is what a user
asked for on the Discord.

**One archive, both ways of installing.** It is a Blender *extension*: the
manifest sits at the archive root and Blender names the directory itself, from
the manifest's `id`. Since 4.2 - which is this add-on's minimum - the same
archive installs through **Install from Disk** as well, so the legacy add-on zip
that used to ship beside it is gone. Verified, not assumed: `tests/extension.py`
installs this file through the operator that button uses and enables it.

**Why the manifest is generated rather than tracked.** It repeats the version,
the name and the description that `bl_info` already carries, and a manifest
sitting in the source tree is a second place for them to be wrong. Here it is
written from `bl_info` at build time, so the package cannot ship claiming a
version the add-on does not.
"""

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "void_tools")
DIST = os.path.join(ROOT, "dist")
DOCS_REPO = os.path.join(ROOT, "docs", "repo")

# Nothing here is source. `__pycache__` is this machine's Python version and is
# regenerated on first import. `.md` covers the per-package READMEs: they are the
# old documentation, kept in the repository where GitHub renders them, but nobody
# has ever read a Markdown file inside an installed add-on and they were 60 KB of
# it. The `.txt` files in the texture folders deliberately stay - those folders
# are opened by hand to swap a texture, the note explains what belongs there, and
# an empty folder cannot survive a zip.
SKIP_DIRECTORIES = {"__pycache__", ".git"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".blend1", ".orig", ".rej", ".md")
SKIP_NAMES = {"desktop.ini", "Thumbs.db", ".DS_Store"}

# The extension id. Blender installs the package as `bl_ext.<repo>.<id>`, and
# every module here reaches its own preferences through `__package__` rather
# than a hardcoded name, so the rename costs nothing at runtime.
EXTENSION_ID = "void_tools"

# One asset per release, named the way people expect to find it - the same
# shape Sollumz's own release page has. The version is inside the manifest,
# not in the filename: a release page that offers two files makes somebody
# choose, and there is nothing here to choose between.
ARCHIVE_NAME = "void-tools.zip"

# Where the built archive actually lives once released. `server-generate` writes
# a relative URL, which would mean serving the zip from GitHub Pages as well;
# pointing at the release asset instead keeps binaries out of the repository and
# keeps one download count.
RELEASE_ASSET = ("https://github.com/seto3d/void-tools/releases/download/"
                 "v{version}/{filename}")

MANIFEST = """\
schema_version = "1.0.0"

id = "{id}"
version = "{version}"
name = "Void Tools"
tagline = "GTA V / FiveM asset authoring tools, built on Sollumz"
maintainer = "Seto <https://github.com/seto3d>"
type = "add-on"

website = "https://seto3d.github.io/void-tools/"
tags = {tags}

blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 Sertan (seto3d)"]

# The one thing this add-on reaches the network for, declared where Blender can
# show it before anybody installs: the updater asks github.com whether there is
# a newer release, once per start, and downloads one only when asked. Nothing
# else in the package may open a socket - tests/updater.py pins that by
# scanning every module.
[permissions]
network = "Ask github.com for a newer release, and fetch it when you ask"

[build]
paths_exclude_pattern = [
{excludes}
]
"""

TAGS = ["Material", "Mesh", "Object"]


def bl_info():
    """`bl_info` out of the add-on, read rather than imported - `bpy` is absent."""
    with open(os.path.join(SOURCE, "__init__.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(target, "id", "") == "bl_info" for target in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("no bl_info in void_tools/__init__.py")


def stage(directory):
    """Copy the add-on into `directory` with the manifest at its root."""
    for folder, subfolders, files in os.walk(SOURCE):
        subfolders[:] = sorted(d for d in subfolders if d not in SKIP_DIRECTORIES)
        target = os.path.join(directory, os.path.relpath(folder, SOURCE))
        os.makedirs(target, exist_ok=True)
        for name in sorted(files):
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES):
                continue
            shutil.copy2(os.path.join(folder, name), os.path.join(target, name))


def write_manifest(directory, version):
    excludes = "\n".join(f'    "**/{pattern}",'
                         for pattern in ("__pycache__/", "*.pyc"))
    text = MANIFEST.format(id=EXTENSION_ID, version=version,
                           tags=json.dumps(TAGS), excludes=excludes)
    path = os.path.join(directory, "blender_manifest.toml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def verify(archive_path):
    """The manifest is at the root, and no entry carries a Windows separator."""
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    problems = []
    if "blender_manifest.toml" not in names:
        problems.append("blender_manifest.toml is not at the archive root")
    backslashes = [name for name in names if "\\" in name]
    if backslashes:
        problems.append(f"{len(backslashes)} entry name(s) with a backslash")
    return names, problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", required=True,
                        help="Path to a Blender 4.2+ executable")
    parser.add_argument("--publish", action="store_true",
                        help="Also write docs/repo/index.json - the listing "
                             "Blender reads. Only for a version being released")
    args = parser.parse_args()

    version = ".".join(str(part) for part in bl_info()["version"])
    # Emptied first: server-generate lists whatever it finds, so a package left
    # over from the last build puts a second version in the index - and one
    # pointing at a release that never carried it.
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)
    filename = ARCHIVE_NAME
    output = os.path.join(DIST, filename)

    with tempfile.TemporaryDirectory() as staging:
        stage(staging)
        write_manifest(staging, version)
        build = subprocess.run(
            [args.blender, "--command", "extension", "build",
             "--source-dir", staging, "--output-filepath", output],
            capture_output=True, text=True)
    if not os.path.exists(output):
        print(build.stdout)
        print(build.stderr, file=sys.stderr)
        return 1

    names, problems = verify(output)
    if problems:
        for problem in problems:
            print("FAILED:", problem)
        return 1

    # The listing. server-generate scans a directory of packages, so it is run
    # over dist/ and its relative archive_url is then pointed at the release.
    generate = subprocess.run(
        [args.blender, "--command", "extension", "server-generate",
         "--repo-dir", DIST],
        capture_output=True, text=True)
    index_path = os.path.join(DIST, "index.json")
    if not os.path.exists(index_path):
        print(generate.stdout)
        print(generate.stderr, file=sys.stderr)
        return 1

    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    for entry in index.get("data", []):
        # The name from the entry's own relative URL, not the one just built:
        # if this ever lists more than one version, each has to point at its
        # own file under its own tag.
        entry_file = os.path.basename(entry.get("archive_url", filename))
        entry["archive_url"] = RELEASE_ASSET.format(
            version=entry.get("version", version), filename=entry_file)
    # Gated on --publish, and the guard belongs here rather than in the
    # caller's discipline: this wrote the listing on every build once, with
    # the message below still reporting that it had not, and a test build of
    # an unreleased version went out with the code and 404'd everyone who
    # checked for an update.
    published = os.path.join(DOCS_REPO, "index.json")
    if args.publish:
        os.makedirs(DOCS_REPO, exist_ok=True)
        with open(published, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2)
            handle.write("\n")

    print(f"{os.path.relpath(output, ROOT)}: {len(names)} files, {version}")
    print(f"  {os.path.getsize(output) / 1024:.0f} KB")
    print(f"{os.path.relpath(published, ROOT)}: "
          f"{len(index.get('data', []))} listing(s)"
          + ("" if args.publish else "  (not published - pass --publish)"))
    for entry in index.get("data", []):
        print(f"  {entry.get('id')} {entry.get('version')} -> {entry['archive_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
