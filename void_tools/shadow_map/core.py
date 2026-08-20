import bpy
import bmesh
import math
import os
import tempfile
import time

import numpy as np
from mathutils import Vector
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
    PointerProperty,
)

from ..shared import panel_layout as pl
from ..shared import icons


# ---------------------------------------------------------------------------
#   File I/O Helpers
# ---------------------------------------------------------------------------

def _resolve_writable_dir(settings):
    """Return an existing, writable directory for shadow map output.

    Tries each candidate in priority order and verifies write access by
    creating a temporary probe file.  This prevents silent failures on
    permission-restricted paths (e.g. ``C:\\Program Files``).

    Fallback order:
        1. User-configured ``output_path`` property.
        2. Directory of the saved ``.blend`` file.
        3. User home directory.
        4. System temporary directory.
    """
    candidates = []

    user_dir = bpy.path.abspath(settings.output_path)
    if user_dir and user_dir.strip():
        candidates.append(user_dir)

    if bpy.data.filepath:
        candidates.append(os.path.dirname(bpy.data.filepath))

    candidates.append(os.path.expanduser("~"))
    candidates.append(tempfile.gettempdir())

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".__shadowmap_write_test__")
            with open(probe, 'w') as f:
                f.write("test")
            os.remove(probe)
            return candidate
        except (OSError, PermissionError):
            continue

    return os.path.expanduser("~")


def ensure_disk_shadowmap(settings, res):
    """Guarantee that a valid ``shadowmap.png`` exists on disk.

    If the file is missing or appears corrupt (< 100 bytes), a blank PNG
    at the requested *res*olution is written via Blender's image API.
    Returns the absolute filepath.
    """
    out_dir = _resolve_writable_dir(settings)
    filepath = os.path.join(out_dir, "shadowmap.png")

    need_init = (
        not os.path.exists(filepath)
        or _file_size_safe(filepath) < 100
    )

    if need_init:
        try:
            dummy = bpy.data.images.new(
                "__init_shadowmap__", width=res, height=res, alpha=False,
            )
            dummy.colorspace_settings.name = 'sRGB'
            dummy.filepath_raw = filepath
            dummy.file_format = 'PNG'
            dummy.save()
            bpy.data.images.remove(dummy)
        except Exception as e:
            print(f"[ShadowMap] Failed to initialise PNG on disk: {e}")

    return filepath


def _file_size_safe(path):
    """Return the file size in bytes, or ``0`` on any OS error."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def load_shadowmap_image(filepath, res):
    """Load or create the working ``shadowmap`` image data-block.

    If *filepath* exists on disk the image is loaded from it; otherwise a
    blank image is created in-memory and saved so that all downstream
    operations (bake, save, levels) always have a valid backing file.

    The image is tagged sRGB so that bakes, compositor previews, and the
    saved PNG all interpret pixel data consistently.
    """
    img_name = "shadowmap"
    if img_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[img_name], do_unlink=True)

    if os.path.exists(filepath):
        img = bpy.data.images.load(filepath, check_existing=False)
        img.name = img_name
    else:
        img = bpy.data.images.new(img_name, width=res, height=res, alpha=False)
        img.filepath_raw = filepath
        img.file_format = 'PNG'
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            img.save()
        except Exception as e:
            print(f"[ShadowMap] Failed to save initial blank image: {e}")

    img.colorspace_settings.name = 'sRGB'
    if img.size[0] != res or img.size[1] != res:
        img.scale(res, res)
    return img


# ---------------------------------------------------------------------------
#   Post-Bake Levels / Invert (Live Preview)
# ---------------------------------------------------------------------------

def update_levels(self, context):
    """Recalculate invert and levels adjustments on the live preview.

    Reads the pristine bake from ``ShadowMap_RAW``, applies the current
    invert / levels settings, and writes the result into the ``shadowmap``
    data-block.  Disk saving is intentionally deferred to the explicit
    *Save Changes* operator to avoid UI stutter on every slider tick.
    """
    if getattr(bpy.types.Scene, "_shadowmap_baking", False):
        return

    img_raw = bpy.data.images.get("ShadowMap_RAW")
    img = bpy.data.images.get("shadowmap")
    if not img_raw or not img:
        return

    settings = context.scene.seto_shadow_map
    width, height = img_raw.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    img_raw.pixels.foreach_get(pixels)

    alphas = pixels[3::4].copy()

    if settings.invert:
        pixels[0::4] = 1.0 - pixels[0::4]

    if not getattr(settings, "use_levels_adjustment", False):
        pixels[0::4] = np.clip(pixels[0::4], 0.0, 1.0)
    else:
        in_black = settings.levels_input_black / 255.0
        in_white = settings.levels_input_white / 255.0
        gamma = settings.levels_gamma
        out_black = settings.levels_output_black / 255.0
        out_white = settings.levels_output_white / 255.0

        if in_white <= in_black:
            in_white = in_black + 0.001

        pixels[0::4] = (pixels[0::4] - in_black) / (in_white - in_black)
        pixels[0::4] = np.clip(pixels[0::4], 0.0, 1.0)
        pixels[0::4] = np.power(pixels[0::4], 1.0 / gamma)
        pixels[0::4] = pixels[0::4] * (out_white - out_black) + out_black
        pixels[0::4] = np.clip(pixels[0::4], 0.0, 1.0)

    # Broadcast red channel to green and blue; restore original alpha.
    pixels[1::4] = pixels[0::4]
    pixels[2::4] = pixels[0::4]
    pixels[3::4] = alphas

    if img.size[0] != width or img.size[1] != height:
        img.scale(width, height)

    img.pixels.foreach_set(pixels)
    img.update()


# ---------------------------------------------------------------------------
#   Operators
# ---------------------------------------------------------------------------

class SETO_OT_save_shadow_levels(bpy.types.Operator):
    """Persist the current invert / levels adjustments to disk."""

    bl_idname = "seto.save_shadow_levels"
    bl_label = "Save Changes to Disk"
    bl_description = (
        "Save the current Invert and Levels adjustments to the "
        "shadowmap.png file on disk"
    )

    @classmethod
    def poll(cls, context):
        return bpy.data.images.get("shadowmap") is not None

    def execute(self, context):
        img = bpy.data.images.get("shadowmap")
        if img and img.filepath:
            try:
                img.file_format = 'PNG'
                img.save()
                self.report({'INFO'}, f"Saved changes to {img.filepath}")
            except Exception as e:
                self.report({'ERROR'}, f"Could not save: {e}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#   Property Group
# ---------------------------------------------------------------------------

class SETO_PG_shadow_map(bpy.types.PropertyGroup):
    """Stores all user-facing settings for the Shadow Map Baker panel."""

    bake_mode: EnumProperty(
        name="Bake Mode",
        items=[
            ('AO', "Ambient Occlusion (Recommended)",
             "Bake soft corner shadows (ignores lights)"),
            ('SUN', "Shadow: Auto Sun (Angle/Altitude)",
             "Bake directional cast shadows from an auto-generated sun"),
            ('CUSTOM', "Shadow: Custom Scene Lights",
             "Bake cast shadows using existing Point / Spot lights in the scene"),
        ],
        default='AO',
    )
    resolution: EnumProperty(
        name="Resolution",
        items=[
            ('512', "512", ""),
            ('1024', "1024 (Recommended)", ""),
            ('2048', "2048", ""),
            ('4096', "4096 (Slow)", ""),
        ],
        default='512',
    )
    bake_half_res: BoolProperty(
        name="Bake at Half Res (Fast)",
        description=(
            "Bake at half resolution then upscale. "
            "Ideal for soft shadows and significantly reduces bake time"
        ),
        default=True,
    )
    keep_uvs: BoolProperty(
        name="Keep Existing UVs",
        description=(
            "Bake into the UV layout the mesh already has, instead of running "
            "Smart UV Project. Vanilla GTA shadow maps are packed by hand into "
            "a few large islands, which is what keeps them sharp - Smart UV "
            "Project scatters a room into hundreds of small ones and spends "
            "most of the texture on the gaps between them"
        ),
        default=False,
    )
    offset_distance: FloatProperty(
        name="Surface Offset",
        description="Push the shadow mesh along normals to prevent Z-fighting",
        default=0.003, min=-1.0, max=1.0, precision=3, step=0.1,
    )
    shadow_angle: FloatProperty(
        name="Light Angle", default=45.0, min=0.0, max=360.0,
    )
    shadow_altitude: FloatProperty(
        name="Light Altitude", default=45.0, min=0.0, max=90.0,
    )
    invert: BoolProperty(
        name="Invert Shadow",
        description="Invert the baked shadow values (live preview)",
        default=True,
        update=update_levels,
    )

    # Levels adjustment
    use_levels_adjustment: BoolProperty(
        name="Enable Post-Bake Levels",
        description="Apply non-destructive contrast and gamma adjustments after baking",
        default=False,
        update=update_levels,
    )
    levels_input_black: IntProperty(
        name="Input Black", default=0, min=0, max=255, update=update_levels,
    )
    levels_input_white: IntProperty(
        name="Input White", default=255, min=0, max=255, update=update_levels,
    )
    levels_gamma: FloatProperty(
        name="Gamma", default=1.0, min=0.01, max=9.99, update=update_levels,
    )
    levels_output_black: IntProperty(
        name="Output Black", default=0, min=0, max=255, update=update_levels,
    )
    levels_output_white: IntProperty(
        name="Output White", default=255, min=0, max=255, update=update_levels,
    )

    # Sampling
    samples: EnumProperty(
        name="Samples",
        items=[
            ('64', "64 (Fast / Grainy)", ""),
            ('128', "128", ""),
            ('256', "256 (Recommended)", ""),
            ('512', "512 (Clean)", ""),
            ('1024', "1024 (Maximum)", ""),
            ('2048', "2048 (Ultra / Slow)", ""),
        ],
        default='2048',
    )
    use_denoise: BoolProperty(
        name="Denoise",
        description="Smart noise removal (may appear smudged)",
        default=True,
    )
    post_blur: IntProperty(
        name="Soften (Blur) px",
        description="Gaussian blur radius applied after baking",
        default=1, min=0, max=50,
    )
    use_clamp: BoolProperty(
        name="Clamp Fireflies",
        description="Cap sample brightness to reduce bright speckle noise",
        default=True,
    )
    clamp_value: FloatProperty(
        name="Clamp Value",
        description="Lower values are smoother but may lose bright detail",
        default=2.0, min=0.0, max=20.0,
    )
    ao_distance: FloatProperty(
        name="AO Distance",
        description="Maximum ray travel distance for AO; shorter is less noisy",
        default=1.0, min=0.0, max=100.0,
    )
    output_path: StringProperty(
        name="Output Dir",
        subtype='DIR_PATH',
        description="Output folder for the shadow map. Use // to save next to the .blend file",
        default="//",
    )
    last_error: StringProperty(default="", options={'HIDDEN'})


# ---------------------------------------------------------------------------
#   UI Panel
# ---------------------------------------------------------------------------

class SETO_PT_shadow_map_panel(bpy.types.Panel):
    bl_idname = "SETO_PT_shadow_map_panel"
    bl_label = "Shadow Map Baker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = "SETO_PT_surface_group"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 101

    def draw_header(self, context):
        icons.draw_header(self.layout, "vertex_bake", 'SHADING_RENDERED')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_shadow_map

        # Mesh preparation
        col = layout.column(align=True)
        col.prop(settings, "offset_distance")
        col.prop(settings, "keep_uvs")
        col.separator()

        row = col.row()
        row.scale_y = 1.2
        row.operator("seto.prepare_shadow_mesh", icon='DUPLICATE')

        layout.separator()

        # Bake settings
        col = layout.column(align=True)
        col.prop(settings, "bake_mode")
        col.separator()

        if settings.bake_mode == 'SUN':
            col.prop(settings, "shadow_angle")
            col.prop(settings, "shadow_altitude")
            col.separator()

        if settings.bake_mode == 'AO':
            col.prop(settings, "ao_distance")
            col.separator()

        col.prop(settings, "resolution")
        col.prop(settings, "bake_half_res")
        col.prop(settings, "samples")
        col.prop(settings, "use_denoise")
        col.prop(settings, "post_blur")
        col.separator()
        col.prop(settings, "use_clamp")
        sub = col.row(align=True)
        sub.active = settings.use_clamp
        sub.prop(settings, "clamp_value")
        col.separator()
        col.prop(settings, "output_path")
        col.separator()

        # Post-bake adjustments
        col.prop(settings, "invert")
        box = col.box()
        row = box.row()
        row.prop(
            settings, "use_levels_adjustment",
            text="Levels Adjustment", icon='IMAGE_RGB_ALPHA',
        )

        if settings.use_levels_adjustment:
            row = box.row()
            col1 = row.column()
            col1.prop(settings, "levels_input_black")
            col1.prop(settings, "levels_output_black")

            col2 = row.column()
            col2.prop(settings, "levels_input_white")
            col2.prop(settings, "levels_output_white")

            box.prop(settings, "levels_gamma")

        box.separator()
        box.operator("seto.save_shadow_levels", icon='FILE_TICK')

        col.separator()
        row = col.row()
        row.scale_y = 1.2
        row.operator("seto.bake_shadow_map", icon='TEXTURE')

        # Persistent error display
        if settings.last_error:
            warn = layout.box()
            warn.alert = True
            warn.label(text=settings.last_error, icon='ERROR')


# ---------------------------------------------------------------------------
#   Prepare Shadow Mesh
# ---------------------------------------------------------------------------

class SETO_OT_prepare_shadow_mesh(bpy.types.Operator):
    """Duplicate selected meshes, offset normals, UV-unwrap, and assign a bake material."""

    bl_idname = "seto.prepare_shadow_mesh"
    bl_label = "Prepare Shadow Mesh"
    bl_description = (
        "Duplicate selected meshes, push normals by offset distance, "
        "clear vertex data, run Smart UV Project, and assign a bake material"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
        )

    def execute(self, context):
        settings = context.scene.seto_shadow_map

        try:
            if context.active_object and context.active_object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            # Deselect non-mesh objects
            for obj in context.selected_objects:
                if obj.type != 'MESH':
                    obj.select_set(False)

            if not context.selected_objects:
                settings.last_error = "No mesh objects selected."
                return {'CANCELLED'}

            context.view_layer.objects.active = context.selected_objects[0]

            # Duplicate and merge into a single shadow mesh
            bpy.ops.object.duplicate()
            clones = [o for o in context.selected_objects if o.type == 'MESH']

            if len(clones) > 1:
                context.view_layer.objects.active = clones[0]
                bpy.ops.object.join()

            shadow_obj = context.active_object
            shadow_obj.name = "ShadowMap_Mesh"

            # Strip existing materials and vertex colour layers
            shadow_obj.data.materials.clear()
            if hasattr(shadow_obj.data, "color_attributes"):
                while shadow_obj.data.color_attributes:
                    shadow_obj.data.color_attributes.remove(
                        shadow_obj.data.color_attributes[0],
                    )
            if hasattr(shadow_obj.data, "vertex_colors"):
                while shadow_obj.data.vertex_colors:
                    shadow_obj.data.vertex_colors.remove(
                        shadow_obj.data.vertex_colors[0],
                    )

            # Offset vertices along normals to prevent Z-fighting
            bm = bmesh.new()
            bm.from_mesh(shadow_obj.data)
            bm.normal_update()
            for v in bm.verts:
                v.co += v.normal * settings.offset_distance
            bm.to_mesh(shadow_obj.data)
            bm.free()

            # Generate UVs via Smart UV Project - unless the mesh already
            # carries a layout worth keeping. A hand-packed lightmap layout is
            # the difference between vanilla's crisp shadow maps and a blurred
            # one: Smart UV Project scatters a room into hundreds of islands,
            # and at any resolution most of the texture goes on their margins.
            if not settings.keep_uvs:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(
                    angle_limit=1.15192,
                    margin_method='SCALED',
                    island_margin=0.02,
                )
                bpy.ops.object.mode_set(mode='OBJECT')
            elif not shadow_obj.data.uv_layers:
                settings.last_error = (
                    "Keep Existing UVs is on, but this mesh has no UV map. "
                    "Unwrap it first, or turn the option off."
                )
                return {'CANCELLED'}

            # Rename UV layer for Sollumz compatibility
            if shadow_obj.data.uv_layers:
                shadow_obj.data.uv_layers.active.name = "UVMap 0"

            # Build a minimal bake material: Texture → Diffuse → Output
            mat = bpy.data.materials.new(name="ShadowMap_Mat")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes.clear()

            out_node = nodes.new('ShaderNodeOutputMaterial')
            diffuse_node = nodes.new('ShaderNodeBsdfDiffuse')
            tex_node = nodes.new('ShaderNodeTexImage')

            out_node.location = (200, 0)
            diffuse_node.location = (0, 0)
            tex_node.location = (-250, 0)

            links.new(diffuse_node.outputs[0], out_node.inputs[0])

            # Resolve bake resolution and load (or create) the shadow map image
            res = int(settings.resolution)
            if settings.bake_half_res:
                res = max(64, res // 2)
            filepath = ensure_disk_shadowmap(settings, res)
            img = load_shadowmap_image(filepath, res)

            tex_node.image = img
            nodes.active = tex_node
            shadow_obj.data.materials.append(mat)

            settings.last_error = ""
            self.report({'INFO'}, "Shadow mesh prepared")
            return {'FINISHED'}

        except Exception as e:
            settings.last_error = f"{type(e).__name__}: {e}"
            self.report({'ERROR'}, "Failed to prepare mesh")
            return {'CANCELLED'}


# ---------------------------------------------------------------------------
#   Compositor Post-Processing (Denoise / Blur)
# ---------------------------------------------------------------------------

def _compositor_post_process(img, context, use_denoise, blur_radius):
    """Run the baked image through Blender's compositor for denoising and blur.

    Creates a temporary scene with a minimal compositor node tree, renders
    through it, and returns the processed pixel buffer.  Returns ``None``
    if no post-processing is required.
    """
    if not use_denoise and blur_radius <= 0:
        return None

    width, height = img.size

    # Temporary scene with Workbench engine (fastest possible render)
    temp_scene = bpy.data.scenes.new(name="TempDenoiseScene")
    temp_scene.render.engine = 'BLENDER_WORKBENCH'
    temp_scene.render.resolution_x = width
    temp_scene.render.resolution_y = height
    temp_scene.render.resolution_percentage = 100
    temp_scene.use_nodes = True

    # A camera is required for render to succeed
    cam_data = bpy.data.cameras.new("TempCam")
    cam_obj = bpy.data.objects.new("TempCam", cam_data)
    temp_scene.collection.objects.link(cam_obj)
    temp_scene.camera = cam_obj

    # Build compositor node chain: Image → [Denoise] → [Blur] → Composite
    tree = temp_scene.node_tree
    tree.nodes.clear()

    img_node = tree.nodes.new('CompositorNodeImage')
    img_node.image = img
    last_node = img_node

    if use_denoise:
        denoise_node = tree.nodes.new('CompositorNodeDenoise')
        denoise_node.use_hdr = True
        tree.links.new(last_node.outputs[0], denoise_node.inputs[0])
        last_node = denoise_node

    if blur_radius > 0:
        blur_node = tree.nodes.new('CompositorNodeBlur')
        blur_node.filter_type = 'GAUSS'
        blur_node.size_x = blur_radius
        blur_node.size_y = blur_radius
        tree.links.new(last_node.outputs[0], blur_node.inputs[0])
        last_node = blur_node

    comp_node = tree.nodes.new('CompositorNodeComposite')
    viewer_node = tree.nodes.new('CompositorNodeViewer')
    tree.links.new(last_node.outputs[0], comp_node.inputs[0])
    tree.links.new(last_node.outputs[0], viewer_node.inputs[0])

    orig_scene = context.window.scene
    context.window.scene = temp_scene

    pixels = None
    try:
        bpy.ops.render.render(write_still=False)
        result_img = bpy.data.images.get('Viewer Node')
        if result_img and len(result_img.pixels) > 0:
            pixels = np.empty(width * height * 4, dtype=np.float32)
            result_img.pixels.foreach_get(pixels)
        else:
            print("[ShadowMap] Viewer Node image not found or empty.")
    finally:
        context.window.scene = orig_scene
        bpy.data.objects.remove(cam_obj)
        bpy.data.cameras.remove(cam_data)
        bpy.data.scenes.remove(temp_scene)

    return pixels


# ---------------------------------------------------------------------------
#   Bake Helper
# ---------------------------------------------------------------------------

def _patch_missing_file_images(mat):
    """Temporarily switch missing-file image nodes to GENERATED.

    Cycles refuses to bake when any ``TEX_IMAGE`` node references a file
    that no longer exists on disk.  This function marks those images as
    ``GENERATED`` for the duration of the bake and returns a list of
    ``(image, original_source)`` pairs so the caller can restore them.
    """
    patched = []
    if not mat or not mat.use_nodes:
        return patched
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            img_data = node.image
            if img_data.source == 'FILE' and img_data.filepath:
                if not os.path.exists(bpy.path.abspath(img_data.filepath)):
                    patched.append((img_data, img_data.source))
                    img_data.source = 'GENERATED'
    return patched


# ---------------------------------------------------------------------------
#   Bake & Process Operator
# ---------------------------------------------------------------------------

class SETO_OT_bake_shadow_map(bpy.types.Operator):
    """Bake shadows via Cycles, apply post-processing, and save the result."""

    bl_idname = "seto.bake_shadow_map"
    bl_label = "Bake & Process Texture"
    bl_description = (
        "Bake a shadow pass using Cycles, apply denoise / blur, "
        "and save the result as a PNG"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.active_object.name.startswith("ShadowMap")
        )

    def execute(self, context):
        settings = context.scene.seto_shadow_map
        obj = context.active_object

        # --- Validate material setup ---
        if not obj.data.materials:
            settings.last_error = "No material found on the active object."
            return {'CANCELLED'}

        mat = obj.data.materials[0]
        if (
            not mat.use_nodes
            or not mat.node_tree.nodes.active
            or mat.node_tree.nodes.active.type != 'TEX_IMAGE'
        ):
            settings.last_error = "Active node in material must be an Image Texture."
            return {'CANCELLED'}

        if not mat.node_tree.nodes.active.image:
            settings.last_error = "Image Texture node has no image assigned."
            return {'CANCELLED'}

        # --- Resolve bake resolution and refresh the target image ---
        res = int(settings.resolution)
        if settings.bake_half_res:
            res = max(64, res // 2)

        filepath = ensure_disk_shadowmap(settings, res)
        img = load_shadowmap_image(filepath, res)
        mat.node_tree.nodes.active.image = img

        # Temporarily fix any image nodes referencing deleted files
        patched_images = _patch_missing_file_images(mat)

        scene = context.scene
        orig_engine = scene.render.engine

        sun_obj = None
        sun_data = None
        orig_ao_distance = None
        created_world = False

        # --- Mode-specific scene setup ---
        if settings.bake_mode == 'AO':
            if scene.world is None:
                scene.world = bpy.data.worlds.new("World")
                created_world = True
            orig_ao_distance = scene.world.light_settings.distance
            scene.world.light_settings.distance = settings.ao_distance

        if settings.bake_mode == 'SUN':
            yaw = math.radians(settings.shadow_angle)
            pitch = math.radians(settings.shadow_altitude)
            direction = Vector((
                math.cos(yaw) * math.cos(pitch),
                math.sin(yaw) * math.cos(pitch),
                -math.sin(pitch),
            )).normalized()

            sun_data = bpy.data.lights.new(name="TempShadowSun", type='SUN')
            sun_data.energy = 2.0
            sun_obj = bpy.data.objects.new(name="TempShadowSun", object_data=sun_data)
            context.collection.objects.link(sun_obj)
            sun_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

        try:
            # Blender baking requires Cycles. Attempt to switch to it, then
            # verify — Blender silently ignores invalid engine names rather
            # than raising an exception.
            scene.render.engine = 'CYCLES'
            if scene.render.engine != 'CYCLES':
                settings.last_error = (
                    "Cycles is disabled - baking needs it. "
                    "Edit > Preferences > Get Extensions, search 'Cycles Render Engine', install/tick it."
                )
                self.report({'ERROR'}, settings.last_error)
                return {'CANCELLED'}

            # CUSTOM mode uses the scene's existing render settings as-is;
            # AO and SUN modes override them with the addon's own values.
            if settings.bake_mode != 'CUSTOM':
                scene.cycles.samples = int(settings.samples)
                if settings.use_clamp:
                    scene.cycles.sample_clamp_direct = settings.clamp_value
                    scene.cycles.sample_clamp_indirect = settings.clamp_value

                scene.render.bake.use_pass_direct = True
                scene.render.bake.use_pass_indirect = True
                scene.render.bake.use_pass_color = False

            # Force a viewport redraw so the user sees that Blender is working
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            # Flush dependency graph before baking
            mat.update_tag()
            obj.update_tag()
            context.view_layer.update()

            # --- Bake ---
            bake_type = 'AO' if settings.bake_mode == 'AO' else 'DIFFUSE'
            bake_start = time.time()
            bpy.ops.object.bake(
                type=bake_type, margin=16, margin_type='ADJACENT_FACES',
            )

            # --- Post-process (denoise / blur) ---
            if settings.use_denoise or settings.post_blur > 0:
                try:
                    processed = _compositor_post_process(
                        img, context, settings.use_denoise, settings.post_blur,
                    )
                    if processed is not None:
                        img.pixels.foreach_set(processed)
                        img.update()
                except Exception as e:
                    print(f"[ShadowMap] Post-process failed: {e}")

            bake_elapsed = time.time() - bake_start

            # Upscale to target resolution if baked at half res
            target_res = int(settings.resolution)
            if img.size[0] != target_res or img.size[1] != target_res:
                img.scale(target_res, target_res)

            # --- Cache the raw (un-inverted) bake for live levels adjustment ---
            width, height = img.size
            pixels = np.empty(width * height * 4, dtype=np.float32)
            img.pixels.foreach_get(pixels)

            raw_img = bpy.data.images.get("ShadowMap_RAW")
            if raw_img and (raw_img.size[0] != width or raw_img.size[1] != height):
                bpy.data.images.remove(raw_img)
                raw_img = None
            if not raw_img:
                raw_img = bpy.data.images.new(
                    "ShadowMap_RAW", width=width, height=height, alpha=True,
                )
            raw_img.pixels.foreach_set(pixels)

            # --- Assign output filepath ---
            out_dir = _resolve_writable_dir(settings)
            filepath = os.path.join(out_dir, "shadowmap.png")
            img.filepath = filepath
            img.source = 'FILE'

            # Reset levels properties without triggering intermediate updates
            setattr(bpy.types.Scene, "_shadowmap_baking", True)
            try:
                settings.invert = True
                settings.use_levels_adjustment = False
                settings.levels_input_black = 0
                settings.levels_input_white = 255
                settings.levels_gamma = 1.0
                settings.levels_output_black = 0
                settings.levels_output_white = 255
            finally:
                setattr(bpy.types.Scene, "_shadowmap_baking", False)

            # Apply initial invert / levels to the preview image
            update_levels(settings, context)

            # Persist the bake to disk
            if img.filepath:
                try:
                    img.file_format = 'PNG'
                    img.save()
                except Exception:
                    pass

            # Update any open Image Editor to show the baked result
            if hasattr(context, "screen") and context.screen:
                for area in context.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        for space in area.spaces:
                            if space.type == 'IMAGE_EDITOR':
                                space.image = img

            # --- Assign Sollumz decal_dirt material if available ---
            sollumz_warning = self._assign_sollumz_material(context, obj, img)

            settings.last_error = sollumz_warning or ""
            self.report(
                {'INFO'},
                f"Saved shadowmap to {filepath}  |  {bake_elapsed:.1f}s bake",
            )

        except Exception as e:
            settings.last_error = f"Bake failed: {e}"
            self.report({'ERROR'}, settings.last_error)
            return {'CANCELLED'}

        finally:
            # Restore patched image sources
            for img_data, orig_source in patched_images:
                img_data.source = orig_source
            # Remove temporary sun light
            if sun_obj:
                bpy.data.objects.remove(sun_obj)
            if sun_data:
                bpy.data.lights.remove(sun_data)
            # Restore AO distance / remove temporary world
            if orig_ao_distance is not None:
                scene.world.light_settings.distance = orig_ao_distance
            if created_world:
                bpy.data.worlds.remove(scene.world)
            scene.render.engine = orig_engine

        return {'FINISHED'}

    # ----- Sollumz integration (best-effort) -----

    @staticmethod
    def _assign_sollumz_material(context, obj, img):
        """Try to replace the bake material with Sollumz ``decal_dirt.sps``.

        Returns a warning string on failure, or ``None`` on success.
        """
        try:
            from ..shared import sollumz_integration as szi
            if not szi.is_sollumz_available():
                return None

            shader_materials = szi._import("ydr.shader_materials")
            new_mat = shader_materials.create_shader("decal_dirt.sps")
            new_mat.name = "ShadowMap_DecalDirt"

            # Locate the DiffuseSampler node; create a fallback if absent
            target_node = None
            for node in new_mat.node_tree.nodes:
                if node.name == "DiffuseSampler":
                    target_node = node
                    break
            if target_node is None:
                target_node = new_mat.node_tree.nodes.new('ShaderNodeTexImage')

            target_node.image = img
            new_mat.node_tree.nodes.active = target_node

            if obj.data.materials:
                obj.data.materials[0] = new_mat
            else:
                obj.data.materials.append(new_mat)

            # Add vertex colour attribute required by the shader
            context.view_layer.objects.active = obj
            bpy.ops.geometry.color_attribute_add(
                name="Color 1",
                domain='CORNER',
                data_type='BYTE_COLOR',
                color=(0, 0, 0, 0.6),
            )
        except Exception as e:
            warning = f"Bake saved, but Sollumz Decal Dirt assignment failed: {e}"
            print(f"[ShadowMap] {warning}")
            return warning

        return None


# ---------------------------------------------------------------------------
#   Registration
# ---------------------------------------------------------------------------

classes = (
    SETO_PG_shadow_map,
    SETO_OT_save_shadow_levels,
    SETO_PT_shadow_map_panel,
    SETO_OT_prepare_shadow_mesh,
    SETO_OT_bake_shadow_map,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_shadow_map = PointerProperty(type=SETO_PG_shadow_map)


def unregister():
    if hasattr(bpy.types.Scene, 'seto_shadow_map'):
        del bpy.types.Scene.seto_shadow_map
    if hasattr(bpy.types.Scene, '_shadowmap_baking'):
        del bpy.types.Scene._shadowmap_baking
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
