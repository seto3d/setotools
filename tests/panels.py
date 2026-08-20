"""Every Void Tools panel, drawn - including the state a new user starts in.

Blender only calls draw() from the UI thread, so a headless test never draws a
panel by running the add-on normally: all the logic can pass while the panel
explodes on first redraw. This drives every registered panel's draw() by hand
against a stub layout that validates what it is asked to do.

The stub has to validate three separate things, because each has shipped a bug
here before:

  1. an attribute the real UILayout does not have (`row.prop_enabled = True`)
  2. a keyword or enum value this Blender rejects - `template_list(type='GRID')`
     was valid in 4.x and removed in 5.x
  3. a property or operator name that does not exist

A stub that quietly swallows **kwargs sees none of those.

Both Sollumz states are covered. The unavailable one is not hypothetical: a
tester installed Sollumz from the GitHub repository, where the folder is called
"Sollumz-main", and every tool told them it was not installed.
"""
import bpy, sys, os

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import void_tools
from void_tools.shared import sollumz_integration as szi
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    void_tools.register()


def _check_layout_call(fn_name, kwargs):
    fn = bpy.types.UILayout.bl_rna.functions.get(fn_name)
    if fn is None:
        check("UILayout has " + fn_name, False)
        return
    params = {p.identifier: p for p in fn.parameters}
    for key, value in kwargs.items():
        param = params.get(key)
        check(f"{fn_name}() accepts '{key}'", param is not None, sorted(params))
        if param is not None and param.type == 'ENUM':
            allowed = [i.identifier for i in param.enum_items]
            check(f"{fn_name}({key}={value!r}) is valid", value in allowed, allowed)


_UILAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())


class StubLayout:
    def __setattr__(self, name, value):
        check(f"UILayout really has '{name}'", name in _UILAYOUT_PROPS,
              sorted(_UILAYOUT_PROPS))
        object.__setattr__(self, name, value)

    scale_y = scale_x = 1.0
    enabled = alert = False
    active = True

    def _sub(self, *a, **k): return self
    row = column = box = grid_flow = split = column_flow = _sub

    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def menu(self, *a, **k): return None

    def template_icon(self, **k):
        _check_layout_call("template_icon", k)

    def template_list(self, listtype, list_id, data, prop, active_data,
                      active_prop, **k):
        check(f"template_list collection: {prop}", prop in data.bl_rna.properties)
        check(f"template_list index: {active_prop}",
              active_prop in active_data.bl_rna.properties)
        check(f"UIList registered: {listtype}",
              listtype == "" or hasattr(bpy.types, listtype))
        _check_layout_call("template_list", k)

    def template_icon_view(self, data, name, **k):
        check(f"icon_view prop: {type(data).__name__}.{name}",
              name in data.bl_rna.properties)
        _check_layout_call("template_icon_view", k)

    def template_ID(self, data, name, **k):
        check(f"template_ID target: {type(data).__name__}.{name}",
              name in data.bl_rna.properties)
        return self

    def operator(self, idname, **k):
        module, _, op = idname.partition(".")
        exists = hasattr(getattr(bpy.ops, module, object()), op)
        check("operator exists: " + idname, exists)
        rna = getattr(getattr(bpy.ops, module), op).get_rna_type() if exists else None
        keys = list(rna.properties.keys()) if rna else []
        return type("OpProps", (), {"__setattr__": lambda s, key, value: check(
            f"op prop {idname}.{key}", key in keys, keys)})()

    def prop(self, data, name, **k):
        check(f"prop exists: {type(data).__name__}.{name}",
              name in data.bl_rna.properties, list(data.bl_rna.properties.keys()))
        return self


def panel_layout_tab():
    """The tab name, read from the add-on rather than typed here again."""
    from void_tools.shared import panel_layout
    return panel_layout.TAB


def seto_panels():
    """Every panel this add-on registers, in tab order."""
    found = []
    for name in dir(bpy.types):
        if not name.startswith("SETO_PT_"):
            continue
        cls = getattr(bpy.types, name)
        if getattr(cls, "bl_category", None) == panel_layout_tab():
            found.append(cls)
    return sorted(found, key=lambda c: (getattr(c, "bl_order", 0), c.__name__))


def draw_panel(cls, label):
    """Drive draw()/draw_header() without instantiating the Panel.

    A Panel subclass cannot be constructed (bpy_struct.__new__ refuses), so the
    methods are bound onto a plain object carrying a `layout`.
    """
    shim = type("Shim", (), {})()
    shim.layout = StubLayout()
    for attr in dir(cls):
        if attr.startswith("_draw") or attr in ("draw", "draw_header"):
            fn = getattr(cls, attr)
            if callable(fn):
                setattr(shim, attr, fn.__get__(shim))
    for entry in ("draw_header", "draw"):
        fn = getattr(shim, entry, None)
        if fn is None:
            continue
        try:
            fn(bpy.context)
            check(f"{cls.__name__}.{entry} [{label}]", True)
        except Exception as e:
            import traceback; traceback.print_exc()
            check(f"{cls.__name__}.{entry} [{label}]", False, e)


panels = seto_panels()
# The tab is four sections and nothing else at the top level; every tool
# hangs off one of them. A tool whose parent failed to register is not merely
# misplaced - Blender drops it, and the tab silently loses a tool.
check("the tab's top level is Updates, the five sections, then Support",
      [c.bl_idname for c in panels if not getattr(c, "bl_parent_id", "")]
      == ["SETO_PT_updates_panel", "SETO_PT_geometry_group",
          "SETO_PT_surface_group", "SETO_PT_analysis_group",
          "SETO_PT_materials_group", "SETO_PT_dressing_group",
          "SETO_PT_support_panel"],
      [c.__name__ for c in panels if not getattr(c, "bl_parent_id", "")])

for parent, expected in (
        ("SETO_PT_geometry_group",
         ["SETO_PT_fake_damage_panel", "SETO_PT_smooth_edge_panel"]),
        ("SETO_PT_surface_group",
         ["SETO_PT_fake_ao_panel", "SETO_PT_decal_tool_panel",
          "SETO_PT_surface_painter_panel", "SETO_PT_edge_dirt_panel",
          "SETO_PT_vertex_bake_panel", "SETO_PT_shadow_map_panel"]),
        ("SETO_PT_analysis_group",
         ["SETO_PT_density_checker_panel", "SETO_PT_texture_budget_panel",
          "SETO_PT_preflight_panel"]),
        ("SETO_PT_materials_group",
         ["SETO_PT_material_maker_panel", "SETO_PT_sign_glow_panel"]),
        ("SETO_PT_dressing_group", ["SETO_PT_scatter_panel"])):
    got = [c.bl_idname for c in panels
           if getattr(c, "bl_parent_id", "") == parent]
    check(f"{parent} holds its tools, in order", got == expected, got)

print("=== the tab's layout contract ===")
# One vocabulary across six tools - see shared/panel_layout.py. These are the
# three rules that were each broken by at least one tool before it existed.
from void_tools.shared import panel_layout

for cls in panels:
    parent = getattr(cls, "bl_parent_id", "")
    if not parent or parent in ("SETO_PT_geometry_group",
                                "SETO_PT_surface_group",
                                "SETO_PT_analysis_group",
                                "SETO_PT_materials_group",
                                "SETO_PT_dressing_group"):
        continue          # sections and tools, not the settings children
    name = cls.__name__
    selected = cls.bl_label.startswith("Selected")
    if selected:
        # The finished object's panel is always last and always open: it only
        # appears because one of the tool's objects is selected, and selecting
        # it is the act of asking to edit it.
        check(f"{name} sits last", getattr(cls, "bl_order", 0) == panel_layout.SELECTED,
              getattr(cls, "bl_order", 0))
        check(f"{name} is not collapsed",
              'DEFAULT_CLOSED' not in getattr(cls, "bl_options", set()),
              getattr(cls, "bl_options", set()))
    elif getattr(cls, "needs_sollumz", True) is False:
        # A tool that genuinely runs without Sollumz says so on its base
        # (panel_layout.PlainChildPanel) and is not asked to hide itself.
        # Materialize is the one: turning a diffuse image into a normal map is
        # numpy, and the machine with no working Sollumz is exactly the one
        # that might still want it.
        check(f"{name} declares its order", "bl_order" in cls.__dict__, sorted(cls.__dict__))
    else:
        # A child panel is drawn whether or not its parent drew anything, so
        # each one has to answer for Sollumz itself.
        check(f"{name} hides itself without Sollumz",
              cls.poll.__func__.__qualname__.split(".")[0]
              in ("ToolChildPanel", "_LayerChildPanel"),
              cls.poll.__func__.__qualname__)
        check(f"{name} declares its order", "bl_order" in cls.__dict__, sorted(cls.__dict__))

print("=== every panel draws, with Sollumz available ===")
bpy.ops.mesh.primitive_cube_add(size=2)
for cls in panels:
    draw_panel(cls, "sollumz ok")

print("=== the Shadow Map Baker with a message to show ===")
# The message rows only exist when a run left one behind, so the pass above
# drew neither. That is the shape of bug this file was written for: a panel
# that is green on every logic test and explodes the first time something
# goes wrong and it has to say so.
shadow = bpy.context.scene.seto_shadow_map
try:
    for label, error, warning in (
            ("error only", "Cycles is disabled - baking needs it.", ""),
            ("warning only", "", "Denoise / Soften did not run."),
            ("both", "something stopped it", "and something degraded it")):
        shadow.last_error = error
        shadow.last_warning = warning
        for cls in panels:
            if "shadow_map" in cls.bl_idname:
                draw_panel(cls, label)
finally:
    shadow.last_error = ""
    shadow.last_warning = ""

print("=== Ambient Occlusion's Bevel block, in every state ===")
# The pass above only saw the default (on, Source + Strip). Each target draws
# its own warnings, and switching the block off greys out a different branch.
fake_ao = bpy.context.scene.seto_fake_ao
try:
    for target in ('STRIP', 'SOURCE', 'BOTH'):
        fake_ao.bevel_target = target
        for cls in panels:
            if "fake_ao" in cls.bl_idname:
                draw_panel(cls, f"bevel {target}")
    # Bevel Width at or above Width - the "raise Width" warning.
    fake_ao.bevel_width = fake_ao.width
    for cls in panels:
        if "fake_ao" in cls.bl_idname:
            draw_panel(cls, "bevel too wide")
    fake_ao.bevel_enabled = False
    for cls in panels:
        if "fake_ao" in cls.bl_idname:
            draw_panel(cls, "bevel off")
finally:
    fake_ao.property_unset("bevel_enabled")
    fake_ao.property_unset("bevel_target")
    fake_ao.property_unset("bevel_width")

print("=== the Analysis tools, mid-run ===")
# The pass above drew them idle. Showing a result changes each panel's shape
# entirely - Finish Analysis, the scene totals, the verdict lines, the
# findings list - and none of that was drawn by anything above.
grade = bpy.context.scene.seto_grade
preflight = bpy.context.scene.seto_preflight
for tool, match in (('DENSITY', "density"), ('TEXTURE', "texture_budget")):
    try:
        grade.owner = tool
        for cls in panels:
            if match in cls.bl_idname:
                draw_panel(cls, f"{match} active")
    finally:
        grade.property_unset("owner")

try:
    preflight.has_run = True
    for cls in panels:
        if "preflight" in cls.bl_idname:
            draw_panel(cls, "preflight all clear")
    finding = preflight.findings.add()
    finding.object_name = bpy.context.active_object.name
    finding.check = "Scale"
    finding.severity = "BROKEN"
    finding.message = "Non-uniform scale not applied"
    for cls in panels:
        if "preflight" in cls.bl_idname:
            draw_panel(cls, "preflight with findings")
    # Collapsed as well as open: a heading that is closed takes the other
    # branch through the drawing, and that branch has never been drawn by
    # anything else here.
    preflight.expanded = [False] * len(preflight.expanded)
    for cls in panels:
        if "preflight" in cls.bl_idname:
            draw_panel(cls, "preflight collapsed")
    preflight.property_unset("expanded")
finally:
    preflight.findings.clear()
    preflight.property_unset("has_run")

# Pre-Flight's How to fix popup is an Operator draw(), which Blender calls
# from the UI thread exactly like a panel's - so it has the same way of
# passing every logic test and exploding on first click. Driven here for
# every check that exists, not only the one a finding happened to carry.
# The bug report's preview dialog is an Operator draw() too, called from
# the UI thread exactly like a panel's - and it is the last thing a user
# sees before their report leaves for GitHub, so it exploding there would
# be the worst possible moment.
report_cls = getattr(bpy.types, "SETO_OT_support_report", None)
check("the report operator is registered", report_cls is not None)
if report_cls is not None:
    support = bpy.context.scene.seto_support
    for label, filled in (("empty", False), ("filled in", True)):
        if filled:
            support.title = "Something is wrong"
            support.steps_0 = "opened the file"
            support.result_0 = "it went grey"
        shim = type("Shim", (), {})()
        shim.layout = StubLayout()
        try:
            report_cls.draw.__get__(shim)(bpy.context)
            check(f"the report preview draws [{label}]", True)
        except Exception as e:
            import traceback; traceback.print_exc()
            check(f"the report preview draws [{label}]", False, e)
    from void_tools.support import properties as support_properties
    support_properties.clear(support)
    support.property_unset("title")

from void_tools.preflight import checks as preflight_checks
fix_cls = getattr(bpy.types, "SETO_OT_preflight_fix", None)
check("the How to fix operator is registered", fix_cls is not None)
if fix_cls is not None:
    for name, _fn in preflight_checks.CHECKS:
        shim = type("Shim", (), {})()
        shim.layout = StubLayout()
        shim.check = name
        shim.object_name = "some_object"
        try:
            fix_cls.draw.__get__(shim)(bpy.context)
            check(f"How to fix draws for {name}", True)
        except Exception as e:
            import traceback; traceback.print_exc()
            check(f"How to fix draws for {name}", False, e)

print("=== every panel draws when Sollumz is missing ===")
# The tester's state. Every tool must say so rather than drawing buttons that
# cannot work - Surface Painter used to draw its whole UI and only fail at
# Start Paint.
real_status = szi.get_status_message
szi.get_status_message = lambda: (False, "No enabled Sollumz add-on found.")
try:
    for cls in panels:
        draw_panel(cls, "no sollumz")

    from void_tools.shared import ui_common
    for tool in ("fake_ao", "edge_dirt", "fake_damage", "smooth_edge",
                 "decal_tool", "surface_painter"):
        module = __import__(f"void_tools.{tool}.ui", fromlist=["ui"])
        check(f"{tool} uses the shared warning, not its own copy",
              "ui_common" in dir(module) and not hasattr(module, "_wrap"))

    drawn = []

    class Sink(StubLayout):
        def label(self, text="", icon=''):
            drawn.append(text)

    check("the warning stops the panel", ui_common.draw_sollumz_warning(Sink()))
    check("and it names Sollumz", any("Sollumz" in line for line in drawn), drawn)
finally:
    szi.get_status_message = real_status

print("=== the add-on preferences draw too ===")
# Not a Panel, so nothing above reaches it - and it is where someone whose
# Sollumz was not detected has to go, which makes it the worst place for a
# traceback. Driven in both Sollumz states, because it reports that status.
# Taken from the module, not from bpy.types: like a PropertyGroup, an
# AddonPreferences subclass never appears there in Blender 5.x even when it is
# registered, so `getattr(bpy.types, ...)` is not the test for it.
from void_tools.decal_tool import preferences as decal_preferences
prefs_cls = getattr(decal_preferences, "SETO_AP_decal_tool", None)
check("the add-on preferences class exists", prefs_cls is not None)
if prefs_cls is not None:
    for label, status in (("sollumz ok", None),
                          ("no sollumz",
                           lambda: (False, "No enabled Sollumz add-on found."))):
        real_status = szi.get_status_message
        if status is not None:
            szi.get_status_message = status
        try:
            # The shim stands in for the preferences instance, so it has to
            # answer for its properties too - draw() reads them, and the stub
            # layout validates every name against bl_rna. Anything it is asked
            # for goes to the real preferences.
            from void_tools.shared import addon_prefs
            real_prefs = addon_prefs.get()
            if real_prefs is None:
                check("preferences are available to draw", False,
                      "void_tools is not enabled in this Blender")
                break

            class PrefsShim:
                def __init__(self):
                    object.__setattr__(self, "layout", StubLayout())

                def __getattr__(self, name):
                    return getattr(real_prefs, name)

            shim = PrefsShim()
            try:
                prefs_cls.draw.__get__(shim)(bpy.context)
                check(f"SETO_AP_decal_tool.draw [{label}]", True)
            except Exception as error:
                import traceback; traceback.print_exc()
                check(f"SETO_AP_decal_tool.draw [{label}]", False, error)
        finally:
            szi.get_status_message = real_status

failed = [r for r in RESULTS if not r[0]]
print("\n" + "="*60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("="*60)
sys.exit(1 if failed else 0)
