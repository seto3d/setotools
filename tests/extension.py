"""The extension package, and the repository listing that serves it.

Since 4.2 Blender can take a repository URL and do the updating itself, which
is what a user asked for. That means a second artifact per release with a
different shape - manifest at the archive root, Blender naming the directory -
and a JSON listing on GitHub Pages pointing at it.

Four things here would each break it silently:

* **the version in two places.** `bl_info` and the manifest both carry it, and
  a listing that advertises a version the add-on does not report is an update
  that arrives and changes nothing;
* **the archive's shape.** A manifest one folder down is not an extension, and
  a backslash in an entry name is the macOS/Linux install failure this project
  already met once with `Compress-Archive`;
* **the package name.** Blender installs this as `bl_ext.<repo>.void_tools`,
  so anything that found its own preferences by a hardcoded "void_tools" would
  quietly lose them - it is enabled here under the real extension name and the
  tab is checked for;
* **two updaters.** With Blender doing the updating, this add-on's own updater
  must stand down - otherwise it can drop a legacy copy into `scripts/addons/`
  beside the extension, and the same classes registered twice is a crash this
  project has already written down.

Run `python scripts/build_extension.py --blender <exe>` first; without the
build this reports what is missing and stops.
"""
import ast
import json
import os
import shutil
import sys
import zipfile

import addon_utils
import bpy

REPO = r"D:\SetoClaude\setotools"
sys.path.append(REPO)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


def finish():
    failed = [r for r in RESULTS if not r[0]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        for _ok, name, detail in failed:
            print(f"FAILED: {name}  -- {detail}")
        sys.exit(1)
    sys.exit(0)


sys.path.insert(0, os.path.join(REPO, "scripts"))
import build_extension  # noqa: E402


def _release_order(version):
    """`"1.2.10"` sorts after `"1.2.9"`, which it does not as a string."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


VERSION = ".".join(str(part) for part in build_extension.bl_info()["version"])
ARCHIVE = os.path.join(REPO, "dist", build_extension.ARCHIVE_NAME)
INDEX = os.path.join(REPO, "docs", "repo", "index.json")

print("=== the package exists and is shaped like an extension ===")
check(f"{os.path.basename(ARCHIVE)} is built", os.path.exists(ARCHIVE), ARCHIVE)
if not os.path.exists(ARCHIVE):
    finish()

with zipfile.ZipFile(ARCHIVE) as archive:
    names = archive.namelist()
    manifest_text = archive.read("blender_manifest.toml").decode("utf-8")
check("the manifest is at the archive root, where Blender looks",
      "blender_manifest.toml" in names)
check("and the add-on's own code came with it",
      "__init__.py" in names and any(n.startswith("shared/") for n in names))
check("no entry name carries a Windows separator",
      not [n for n in names if "\\" in n],
      [n for n in names if "\\" in n][:3])
check("the manifest states the version bl_info states - one release, one number",
      f'version = "{VERSION}"' in manifest_text)
check("it declares the network permission the updater needs, and says what for",
      "[permissions]" in manifest_text and "network =" in manifest_text)
check("and it is GPL-3, like the repository",
      "GPL-3.0-or-later" in manifest_text)

print("=== the listing points at the release, not at Pages ===")
check("docs/repo/index.json is written", os.path.exists(INDEX), INDEX)
if os.path.exists(INDEX):
    with open(INDEX, encoding="utf-8") as handle:
        index = json.load(handle)
    entries = index.get("data", [])
    check("it lists exactly this add-on", len(entries) == 1, len(entries))
    if entries:
        entry = entries[0]
        check("under the id Blender will install it as",
              entry.get("id") == build_extension.EXTENSION_ID, entry.get("id"))
        # The listing may lag the working tree and that is correct: it
        # names the version people can actually download, and an
        # unreleased one has no tag behind it yet. Ahead is the failure -
        # a listing naming a release that does not exist hands a 404 to
        # everyone whose Blender checks for an update.
        listed = entry.get("version", "")
        check("at a version that has been released - the listing may lag "
              "the build, never lead it",
              _release_order(listed) <= _release_order(VERSION),
              f"listed {listed}, built {VERSION}")
        url = entry.get("archive_url", "")
        check("under the tag that carries it - the listing's own version "
              "and the tag in its URL cannot disagree",
              f"/download/v{listed}/" in url, url)
        check("and the archive it points at is the release asset, absolute - "
              "a relative URL would mean serving binaries from the docs site",
              url.startswith("https://github.com/seto3d/void-tools/releases/download/")
              and url.endswith(build_extension.ARCHIVE_NAME), url)


print("=== the build does not publish the listing on its own ===")
# The flag used to be advice rather than a guard: the write ran on every
# build while the message still said it had not, so a test build of an
# unreleased version was committed with the code and everyone who checked
# for an update got a 404. Read from the source rather than by running the
# build, which needs a second Blender and a minute.
BUILD_SOURCE = os.path.join(REPO, "scripts", "build_extension.py")
with open(BUILD_SOURCE, encoding="utf-8") as handle:
    build_tree = ast.parse(handle.read())


def _writes_listing(node):
    """Does `node` contain the `open(published, "w")` that writes it?"""
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call)
                and getattr(sub.func, "id", "") == "open"
                and sub.args and getattr(sub.args[0], "id", "") == "published"):
            return True
    return False


writes = [n for n in ast.walk(build_tree) if _writes_listing(n)
          and isinstance(n, (ast.With, ast.Expr))]
guarded = [n for n in ast.walk(build_tree)
           if isinstance(n, ast.If)
           and isinstance(n.test, ast.Attribute) and n.test.attr == "publish"
           and _writes_listing(n)]
check("docs/repo/index.json is written only under `if args.publish` - a "
      "build that writes it every time advertises a release nobody made",
      len(guarded) == 1, f"{len(guarded)} guarded write(s)")
check("and nothing writes it outside that guard",
      bool(guarded) and all(
          any(w in ast.walk(g) for g in guarded) for w in writes),
      f"{len(writes)} write statement(s)")
print("=== it installs, and answers to its extension name ===")
# The legacy copy has to go first: both register the same SETO_* classes, and
# two of them in one Blender is the crash this project has written down.
LEGACY = "void_tools"
legacy_was_enabled = any(module.__name__ == LEGACY
                         for module in addon_utils.modules()
                         if addon_utils.check(module.__name__)[1])
if legacy_was_enabled:
    addon_utils.disable(LEGACY, default_set=False)

extensions_root = bpy.utils.user_resource('EXTENSIONS', path="user_default",
                                          create=True)
installed = os.path.join(extensions_root, build_extension.EXTENSION_ID)
package = f"bl_ext.user_default.{build_extension.EXTENSION_ID}"
if os.path.exists(installed):
    shutil.rmtree(installed)
with zipfile.ZipFile(ARCHIVE) as archive:
    archive.extractall(installed)

try:
    addon_utils.enable(package, default_set=False, persistent=False)
    enabled = addon_utils.check(package)[1]
    check("Blender enables it under bl_ext.user_default.void_tools", enabled)

    panel = getattr(bpy.types, "SETO_PT_geometry_group", None)
    check("and the tab comes up - the sections are registered", panel is not None)
    check("with the tools under them",
          getattr(bpy.types, "SETO_PT_sign_glow_panel", None) is not None
          and getattr(bpy.types, "SETO_PT_vertex_bake_panel", None) is not None)
    check("its scene settings are there under this add-on's prefix",
          hasattr(bpy.context.scene, "seto_sign_glow")
          and hasattr(bpy.context.scene, "seto_vertex_bake"))

    extension_module = sys.modules.get(package)
    prefs_module = sys.modules.get(f"{package}.shared.addon_prefs")
    check("preferences are looked up under the extension's own package name, "
          "not a hardcoded one",
          prefs_module is not None
          and prefs_module.ADDON_PACKAGE == package,
          None if prefs_module is None else prefs_module.ADDON_PACKAGE)
    # Not asserted here: an entry in `preferences.addons`. Blender adds one
    # when it enables an add-on normally, and this run deliberately enables
    # with default_set=False so it does not write itself into the owner's
    # actual preferences. What matters is the name the lookup uses, checked
    # above.

    updater = sys.modules.get(f"{package}.updater.logic")
    check("the updater knows Blender is the one updating it",
          updater is not None and updater.installed_as_extension(),
          None if updater is None else updater.__package__)
    check("and it still reports the version it is - the panel shows it",
          updater is not None and updater.current_str() == VERSION,
          None if updater is None else updater.current_str())
finally:
    if addon_utils.check(package)[1]:
        addon_utils.disable(package, default_set=False)
    shutil.rmtree(installed, ignore_errors=True)
    if legacy_was_enabled:
        addon_utils.enable(LEGACY, default_set=False, persistent=False)

check("the legacy add-on is back where the run found it",
      not legacy_was_enabled or addon_utils.check(LEGACY)[1])

finish()
