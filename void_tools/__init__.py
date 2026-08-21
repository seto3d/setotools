bl_info = {
    "name": "Void Tools",
    "author": "seto3d",
    # Public versioning starts at 1.0.0 with the launch. The changelog's
    # 0.2-1.9 entries were private development builds that never shipped;
    # their numbers stay in the log as history, not as releases.
    "version": (1, 2, 3),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Void Tools",
    # Blender turns these two into the Documentation and Report a Bug buttons
    # on the add-on's own entry in Preferences - the place somebody looks when
    # the tab itself is not drawing and they cannot reach the Support panel.
    "doc_url": "https://seto3d.github.io/void-tools/",
    "tracker_url": "https://github.com/seto3d/void-tools/issues",
    "description": (
        "GTA V / FiveM asset authoring tools that integrate with Sollumz. "
        "Ambient Occlusion corner decals, Edge Dirt strips, Edge Wear "
        "chipped-edge strips, Smooth Edge normal-map strips, a Decal Tool that "
        "places library decals on selected faces, a Surface Painter for "
        "brushing dirt onto an asset through a non-destructive mask, and an "
        "Analysis section that grades triangles and texture memory against "
        "vanilla GTA and checks an asset before it is exported, plus "
        "Materialize, which generates height, normal and specular maps from a "
        "single diffuse image, Sign Glow, which builds an emissive halo behind "
        "3D lettering, and Trash Scatter, which litters a floor with "
        "vanilla GTA props as MLO entities."
    ),
    "category": "Object",
}

# One add-on, six tools. Each lives in its own subpackage and registers itself,
# so they stay as independent as the first three were when they shipped as
# separate add-ons - this top-level __init__ only aggregates their
# register()/unregister() calls, in panel order.
#
# What they genuinely share lives in shared/: the Sollumz integration, which
# used to be copy-pasted into each of them, the bundled-texture lookup, and the
# Color 1 vertex colour they all write.
from .shared import icons
from .shared import texture_repair
from .shared import strip_settings
from .shared import manual_offset
from .shared import viewport_grade
from .shared import groups
from . import fake_ao
from . import edge_dirt
from . import fake_damage
from . import smooth_edge
from . import decal_tool
from . import surface_painter
from . import density_checker
from . import texture_budget
from . import preflight
from . import materials
from . import sign_glow
from . import scatter
from . import updater
from . import support
from . import vertex_bake
from . import shadow_map  

# Panel order. icons first because every panel header asks it for an icon id,
# then groups - and that one is not merely tidiness: every tool panel hangs off
# one of its sections, and Blender drops a panel whose bl_parent_id is not
# registered yet. viewport_grade comes before the Analysis tools for the same
# kind of reason: both of them read scene.seto_grade, which it declares.
_modules = (icons, texture_repair, strip_settings, manual_offset, viewport_grade, groups,
            fake_damage, smooth_edge, fake_ao, decal_tool, surface_painter,
            edge_dirt, density_checker, texture_budget, preflight, materials,
            sign_glow, scatter, updater, support, vertex_bake, shadow_map)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
