"""Shadow Map Baker - that it can tell whether Cycles is there.

Cycles is the only engine that bakes and it can be switched off, so the panel
says so rather than letting the bake die on a traceback. Two ways of asking
have already shipped and neither worked, which is why this file exists.

* **Its enum items.** ``engine`` is a *dynamic* enum whose RNA definition
  lists only ``BLENDER_EEVEE``, enabled or not, asked of the type or of a live
  scene - so the test reported Cycles missing on every machine and refused
  every bake, including on a Blender with Cycles plainly selected in the
  dropdown. Wrong in the worst direction: it blames the user for a setting
  that is already correct.
* **Assign, then compare.** The premise was that Blender ignores an
  unregistered engine name and leaves the old value in place. It does not - it
  raises ``TypeError`` out of RNA, so the comparison after it never runs and
  the panel shows the traceback instead of the sentence written for it.

Both premises are pinned here as well as the behaviour, so that the day either
one changes the test says the old code was unlucky rather than quietly
blessing it.
"""
import sys

import addon_utils
import bpy

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


import void_tools  # noqa: E402
if getattr(bpy.types, "SETO_PT_shadow_map_panel", None) is None:
    void_tools.register()

from void_tools.shadow_map import core  # noqa: E402

scene = bpy.context.scene

print("=== the enum really is the trap it looked like ===")
check("no CYCLES among the engine property's items, whatever the state",
      'CYCLES' not in [
          item.identifier for item
          in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
      ],
      "if this ever passes, the enum check was merely unlucky, not wrong")
check("and asking a live scene rather than the type makes no difference",
      'CYCLES' not in [
          item.identifier for item
          in scene.render.bl_rna.properties["engine"].enum_items
      ])

print("=== with Cycles enabled, a bake is allowed to start ===")
check("Cycles is enabled on the Blender running this",
      addon_utils.check("cycles")[1],
      "the rest of this file assumes it - enable Cycles and run again")
check("so the check lets it through", core._cycles_available(scene))

print("=== with Cycles off, it is refused - and assigning would have thrown ===")
orig_engine = scene.render.engine
addon_utils.disable("cycles", default_set=False)
check("the check refuses", not core._cycles_available(scene))

raised = None
try:
    scene.render.engine = 'CYCLES'
except TypeError as e:
    raised = e
check("assigning an unregistered engine raises rather than being ignored",
      raised is not None,
      "assign-then-compare only works if this is silently ignored - it is not")
check("and the scene is left on the engine it had",
      scene.render.engine == orig_engine, scene.render.engine)

addon_utils.enable("cycles", default_set=False)
check("switching it back on is enough - no restart, no re-registration",
      core._cycles_available(scene))

print("=== the message tells the user where it actually lives ===")
src = core.SETO_OT_bake_shadow_map.execute.__doc__ or ""
import inspect  # noqa: E402
body = inspect.getsource(core.SETO_OT_bake_shadow_map.execute)
check("it points at Get Extensions, not the Add-ons list",
      "Get Extensions" in body and "> Add-ons, search Cycles" not in body,
      "Cycles is not in the Add-ons list in 4.2+; sending users there is a "
      "dead end they reported")

print("=== a message from the last run cannot become a tombstone ===")
settings = scene.seto_shadow_map
settings.last_error = "left over from some earlier run"
settings.last_warning = "and this too"
check("the dismiss operator is registered",
      getattr(bpy.types, "SETO_OT_clear_shadow_message", None) is not None)
bpy.ops.seto.clear_shadow_message()
check("and it clears both messages",
      settings.last_error == "" and settings.last_warning == "",
      (settings.last_error, settings.last_warning))

settings.last_error = "stale"
try:
    bpy.ops.seto.prepare_shadow_mesh()
except RuntimeError:
    pass                      # nothing selected here; entry still clears
check("starting a prepare clears what the previous run said",
      settings.last_error == "" or "selected" in settings.last_error.lower(),
      settings.last_error)

print("=== a degraded bake warns rather than printing to a closed console ===")
body = inspect.getsource(core.SETO_OT_bake_shadow_map.execute)
check("a post-process that returns nothing is warned about, not ignored",
      "warnings.append" in body and "raw bake" in body)
check("and the warning survives the end of the bake",
      "settings.last_warning = " in body,
      "the old code overwrote the field with the Sollumz result, so anything "
      "written earlier in the run was erased before the panel saw it")
check("a warning is not reported as an error - the map is still usable",
      "self.report({'ERROR'}, settings.last_warning)" not in body)

print()
failed = [r for r in RESULTS if not r[0]]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    for _ok, name, detail in failed:
        print(f"FAILED: {name}  -- {detail}")
    sys.exit(1)
