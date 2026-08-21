# Changelog

All notable changes to Void Tools.

## 1.2.3 — the room's own light, baked in

### Added - Shadow Map Baker

The light in a room, baked into a texture and put back on a copy of the surface
as a `decal_dirt` decal. That is how GTA's own interiors have shadow at all: an
MLO gets almost none in real time, so it is painted into the asset first.

Three steps, in the order the panel puts them. **Prepare Shadow Mesh**
duplicates the selection, pushes it off the wall along its normals so the decal
cannot z-fight, and gives it its own unwrap - not the wall's, which is built for
a tiling texture and usually overlaps itself, and would draw the shadow twice.
**Bake & Process** runs it: ambient occlusion (needs no lights and reads as
contact shadow anywhere), a sun you aim by angle and altitude, or the scene
lights you placed yourself, with denoise, blur and firefly clamping so a low
sample count still comes out clean. Then **Levels** - invert, input and output
black and white, gamma - which are live and **do not re-bake**, so the
expensive half happens once and dialling the contrast in afterwards is free.
Nothing reaches disk until Save Changes to Disk.

Denoise and Soften had never actually run. The compositor pass read its result from `Render Result`, whose pixels Blender does not expose to Python - it came back empty, the read failed, and the failure was caught and printed to the console, so every map was the raw bake with the console quietly saying `expected sequence size 0`. It reads a Viewer node now. Soften's default drops from 10 to 1 to suit a blur that finally happens.

The panel says so when Cycles is switched off, since it is an add-on and the bake dies on a traceback without it - and it now says Get Extensions, where Cycles has actually lived since 4.2, rather than sending people to an Add-ons list that has no such entry. Two earlier versions of that check were wrong in opposite directions: one asked whether `CYCLES` was among the render engine's enum items, which is a dynamic enum listing only EEVEE, so it refused every bake on every machine; the other assigned the engine and compared afterwards, which never gets there because assigning an unregistered engine raises. It asks the scene for its `cycles` settings now.

Anything that degrades a bake now says so in the panel. The denoise bug above hid for a release because its failure went to `print()` and Blender does not open a console by default - the bake reported success either way. There are two message rows now: red for what stopped the run, plain for what went wrong while it still produced a usable map, and both can be dismissed. A message no longer outlives the run that wrote it: prepare and bake clear it on the way in, so a complaint from an earlier session cannot sit in the panel for the life of the .blend with nothing able to clear it.

Contributed by @cs-dev-09 ([#4](https://github.com/seto3d/void-tools/pull/4), [#6](https://github.com/seto3d/void-tools/pull/6)).

> A first build of this fix was withdrawn within the hour: it repaired the
> paths from `register()`, and `bpy.data` is restricted while Blender loads
> add-ons, so the add-on failed to register and the tab did not appear at all.
> The repair now runs from a zero-interval timer instead, once the event loop
> is up. `tests/texture_repair.py` scans every module for that shape, because
> the first version's `if not bpy.app.background` guard meant no background
> test could ever have caught it.

### Fixed — the Update button could not install anything

The releases carry a Blender **extension** package now — its manifest and
its `__init__.py` sit at the archive root, where a classic add-on zip has
a folder. The in-add-on updater only knew the old shape, so it inspected
every genuine update and refused it with *"the download did not look like
Void Tools"*. Accepting it would have been worse: `addon_install` scatters
a root-level archive loose across `scripts/addons`.

It tells the two apart now. An extension package cannot be installed over
a classic copy — Blender puts it somewhere else entirely and both would
register the same panels — so the button says so plainly and opens the
install guide, rather than leaving two Void Tools in one Blender. Moving
across is a one-time thing; after it, Blender does the updating.

### Fixed — pink textures after an update

The textures the strip tools ship with live inside the add-on, and Blender
records where an image came from as an **absolute path**. So every scene
made with them names the folder the add-on was installed in at the time —
and 1.2.2 moved that folder, from `seto_tools` to `void_tools`. An old
scene opened afterwards asked for a path that no longer existed and showed
the tell-tale pink, and restarting did not help, because the folder really
was gone.

Those paths are repaired when a file is opened now. An image is only
touched when it is **missing**, when its path is shaped like one of our
tools' `textures/` folders, and when that exact file exists inside the
add-on — so it can only ever re-point an image at something we ship, and a
missing texture belonging to anything else is left alone.

This also covers the pink you may have seen *during* an update: the folder
is deleted and written again under a running Blender, which loses the file
for a moment. That one was always fixed by restarting, and now it is
fixed without.

## 1.2.2 — a sign that lights itself, and a bake that sees the room

### Added — Sign Glow

Thanks to [Molo Modding](https://github.com/molossen), who wrote it as a
standalone add-on: the halo behind lit 3D lettering, in the **Materials**
section.

Select the letters and press Create. The tool traces their own silhouette
onto a plane square-on to the sign, blurs it at two radii — a tight core
hugging the letters and a wide bloom behind them — and puts the result on
an emissive plane just behind the lettering. That is how a sign reads at
night in game without a single real light being placed, and it costs one
quad and one texture.

Everything after Create is live: colour, the two blur sizes and their
intensities, resolution, how far behind the letters the plane sits.
**Auto Fit** sizes the plane from the halo itself, so widening the bloom
grows the plane to hold it rather than clipping it. The plane inherits
the sign's rotation, so its transform gizmo runs along the sign rather
than along the world.

**The plane fades out rather than ending on a line.** It is a bordered
grid whose outer ring of vertices carries `Color 1` alpha **0** — that
alpha is what the emissive shader blends by, so a plane that stayed at 1.0
to its border would stop at a hard rectangle even where its halo had
already faded to nothing, and read in game as a lit box of air around the
sign. **Edge Fade** sets how wide the fading band is.

**The new glow already wears the shader it will be exported with**, an
`emissive_additive_alpha.sps` pointing at the generated halo — a sign that
looks right in Blender and arrives in game as a grey quad is the thing
this tool exists to avoid. If your Sollumz does not carry that shader the
next emissive one that exists is used and the panel says which; versions
differ, and hunting through a shader table for the one word that changed
is not a thing anyone should have to do.

**Nothing is written to your drive until you ask for it.** The texture
stays packed in the .blend, which is all the viewport and the material
need. **Export for Sollumz** writes the `.dds` beside your `.blend` and
rebuilds the material around the file — the step that makes the sign
exportable, since Sollumz embeds whatever the image points at — and
**Save DDS** writes it wherever you choose. After an export, every rebuild
keeps that file equal to the halo you are looking at. Everything except
the shader works with no Sollumz installed at all.

### Added — Vertex Color Bake casts across the whole scene

Thanks to [@cs-dev-09](https://github.com/cs-dev-09) again
([#3](https://github.com/seto3d/void-tools/pull/3)):

- **Ambient Occlusion and Fake Shadow now see other objects.** They used
  to raycast against the object being baked and nothing else, so a crate
  against a wall was occluded by neither. Both now cast against the
  scene, in world space, which also means moving an object re-bakes it
  rather than keeping the shading it had somewhere else.
- **A Collection target**, with a progress bar. Point it at a collection
  and the button bakes every mesh in it — optionally including the ones
  hidden in the viewport — with nothing selected at all. Live Update
  stays on your selection whatever the target is: a slider drag walking a
  whole collection is not a live tool.
- **Two-colour gradients.** The linear gradient can fade between a top
  and a bottom colour rather than only darkening the base one, with
  Shift and Scale to place the fade where the asset needs it.
- **A Clear button**, beside Generate.

### Added — an extension repository

Asked for on the Discord, and it is the better way to install this:

    https://seto3d.github.io/void-tools/repo/index.json

Paste that once into **Preferences → Get Extensions → Repositories → Add
Remote Repository**, and Void Tools appears in Blender's own extension
list. From then on Blender does the updating — it notices new versions,
it installs them, and it shows what the add-on is allowed to reach before
you install it. There is no zip to download and no folder to find.

**Install from Disk still works exactly as before.** Both artifacts ship
on every release: `void-tools.zip` for that, and
`void_tools-<version>.zip` for the repository. They cannot be one file —
an extension carries its manifest at the archive root and Blender names
the folder itself, where a legacy add-on brings its own folder.

**This add-on's own updater stands down when Blender is doing the job.**
Installed from the repository, the Updates panel says so and offers
nothing: two updaters for one add-on can disagree, and this one could
drop a legacy copy into `scripts/addons/` beside the extension, which is
the same classes registered twice.

### Fixed — Clear leaves your alpha alone

Clear reset all four channels, alpha included. Alpha in `Color 1` is what
the decal shaders blend by, so that made every decal on the mesh fully
opaque — invisibly, from a button that says it only clears colour. It now
puts the colour back to white and reads the alpha channel back untouched.

### Fixed — the version an extension install reports

Blender removes `bl_info` from an extension's module and keeps the same
information in the manifest instead. Anything reading the attribute
directly therefore got nothing — so the Updates panel would have said
"Void Tools 0.0.0", and a bug report sent from the Support panel would
have carried that number to whoever was trying to reproduce it. Both ask
`shared/addon_version` now, which knows about both kinds of install.

## 1.2.1 — Vertex Color Bake asks before it writes

### Added — a Live Update switch on Vertex Color Bake

It writes to the mesh you have selected, and every setting used to bake
the moment it changed — so looking through the panel with an object
selected wrote to that object, and one slider drag was dozens of bakes.

**Live Update** is that decision, made visible, on by default like every
other live tool here. Turn it off and the settings are yours to read and
set; **Generate Vertex Color** then does it when you ask. With it on, a
drag now costs **one** bake, when your hand stops, and it bakes the
objects that were selected when you changed the setting rather than
whatever is selected a quarter-second later.

The panel also says plainly, under the button, that it writes `Color 1`
onto the selected mesh.

### Fixed — a bake that fails says so

The live path swallowed every exception, which made a bake that could not
run look exactly like a bake with nothing to do. The reason now lands on
the panel and in the console, and the Generate button reports it properly
instead of returning success.

## 1.2.0 — wear with no texture at all

### Added — Vertex Color Bake

Thanks to [@cs-dev-09](https://github.com/cs-dev-09) again
([#2](https://github.com/seto3d/void-tools/pull/2)): procedural wear baked
straight into `Color 1` — ambient occlusion, dirt in the concave edges,
grime on the up-facing surfaces, wear on exposed corners, noise, a
gradient and a fake directional shadow, stacked, each with its own
strength. It is the cheapest wear there is: no texture, no extra object,
no draw call.

**It is the one tool here that writes to the mesh you select**, and it
says so on its own panel. Baked vertex colour *is* mesh data — there is
nowhere else for it to go — so the rule every other tool keeps (build
something separate, never touch the source) has exactly one documented
exception, and it is one undo away. What it does **not** touch is
`Color 1`'s **alpha**: that is the channel the decal shaders blend by, and
the test suite now asserts a bake leaves every alpha exactly where it was.

Its classes arrived under another add-on's `MLOPT_*` namespace and were
renamed to this add-on's own. That is not tidying: a class name shared
with an add-on the user also has installed is registered twice and takes
the whole add-on down with it, and the test suite finds panels by their
`SETO_PT_` prefix — so under the old name the tool was invisible to every
test, including the one that drives every panel's draw.

### Changed — bug reports go to the Discord

A ticket is a conversation: somebody can ask which Blender, ask for the
`.blend`, and say *try this* in the same minute, where an issue waits for
the next time the maintainer sits down — and most people reporting a
problem with a Blender add-on do not have a GitHub account to report it
with. The Support panel now opens a ticket first, copies your versions to
the clipboard in one press, and keeps the GitHub issue form underneath for
anyone who would rather write one.

### Fixed — two small things in Trash Scatter

**Clear counted the dirt sheet as a prop** — four props and their grime
were reported as "5 scattered props", a number anyone could check and find
wrong. They are counted apart now.

**The reason entities could not be registered vanished with the status
bar.** A file with no YTYP got the same warning flashing past on every
scatter, too fast to read. It now stays on the **Selected Scatter** panel
until it is true no longer.

## 1.1.0 — dressing the floor, making the texture, choosing the colour

### Added — Trash Scatter, and the Dressing section it opens

Select the floor faces, press **Scatter**, and vanilla GTA litter lands on
them — cigarette butts, crumpled paper, crushed cans, bottles, food
wrappers, or the **Dirt & Leaves** preset's drifts of dead leaves. Not
uniformly: an **Edge Bias** slider gathers it along the walls and into the
corners, where litter really collects, and per-prop spacing keeps any two
pieces from stacking. One **Seed**, one layout — re-rolling the arrangement
is one click and reproducible.

Each piece is registered as an **MLO entity** on the floor's own
archetype, attached to the room whose bounds hold it (never to limbo:
that is GTA's outside, and the engine caps what may attach there). The
game streams the real props; the interior's own geometry, texture memory
and draw calls do not move at all. Finding the archetype needs no
selection help — the floor's ancestry is checked first, then the ytyp
panel's selection, then the file's only MLO.

**In the viewport the props are real too**, when a **Prop Library** folder
is set in the add-on preferences: a folder of .blend files whose objects
are named after archetypes (an asset library extracted from the game).
Scatter appends each prop's actual mesh and textures from there — once
per prop, every instance shares the one mesh — and any prop the library
lacks lands as its measured bounding box in wireframe instead, exporting
identically. The library is indexed once and cached; indexing a
few-hundred-blend library measures in minutes, so it never runs on its
own — only the **Rescan** button scans.

**You do not have to find a library: recent Sollumz builds one.** Its
**Sollumz Tools → Asset Library → Build Asset Library** turns extracted
`.ytyp` files into `.blend` libraries in a Shared Assets directory, and
Prop Library reads those as they are — the objects already carry their
archetype names, and where Sollumz leaves a Drawable as an empty with the
mesh parented under it, the scan takes the mesh.

**The settings are live.** A scattered floor carries its own copy of them
in a **Selected Scatter** panel — dragging Density, Edge Bias, **Prop
Scale**, Scale Jitter, Seed or switching preset rebuilds the layout in
place, debounced so a slider drag rebuilds once when the hand stops
rather than on every mouse move. A Live Update switch and an
always-available Re-Scatter button cover the rest — Re-Scatter is also
the answer after resizing or moving the floor itself, which no property
callback can see. Scatter **replaces** its previous layout on the same
floor rather than stacking, and **Clear Scatter** takes the proxies and
their entity rows away together — the active floor's, or every floor's
when the active object has none.

Two presets: **Trash** (litter — cigarette butts, paper, crushed cans,
bottles, food wrappers) and **Dirt & Leaves** (drifts of dead leaves and
the odd stone). A **Topple** slider decides how many of the standing
props — bottles, cans, cups, chip bags — lie knocked over on their side,
resting on their rolled bounding box, the way real litter does. It ships
at 1.0: litter standing to attention reads as staged (field-tested in
game), so everything topples unless the slider says otherwise.

**The floor's rim is read from its faces, not its edges.** An MLO floor
is routinely slabbed into pieces that meet exactly but are not welded,
so every side belonged to exactly one face and the seam between two
slabs was mistaken for a wall — with Edge Bias piling both the litter
and the grime along a line straight across the middle of the room
(visible in game). Sides are now matched by position, so a seam is
interior and only the real rim attracts anything.

**Clustering** gathers the litter into heaps. At 0 it spreads as
before; toward 1 the props pile up around a few seeded spots — the
spots themselves obey Edge Bias, so the heaps form by the walls and
doorways where litter really accumulates, and spacing still holds
inside a heap, so it saturates instead of stacking.

**It keeps up with the sliders.** Nearest-wall distance is answered from
a bucketed index instead of scanning every rim segment, spacing is
checked through a grid instead of against every prop already placed, and
the dirt sheet is rebuilt only when something it depends on actually
moved. On that same 20×14 m floor: a first scatter of 280 props with its
overlay takes 3.2 s, dragging Density rebuilds in 0.09 s, and a Floor
Dirt change in 0.23 s.

**The litter follows the grime.** With Floor Dirt on, the same noise
field that darkens the overlay biases where props land — trash collects
on the dirty patches and thins out over the clean stretches, so the two
read as one scene rather than two random layers. And **litter avoids
furniture**: a short upward ray from every sample drops the spots under
table tops, crates and counters, so nothing spawns inside a table leg.

**Floor Dirt** grimes the floor itself, the way vanilla actually does
it. Measured from the game's interior entity data: 176 of GTA's 377
interiors carry flat, hand-authored dirt overlay sheets
(`bkr_int01_cm3dirtfloor`, `hei_int_heist_hall_over_dirt`,
`ex_int_warem_stains`…) floated millimetres over the floor — Rockstar
does not scatter grime props. Scatter now builds that sheet
procedurally: a copy of the selected region, lifted 4 mm, wearing the
bundled dirt texture in a decal material, its blotch pattern written
into Color 1's alpha from seeded value noise with the same Edge Bias
pull the litter uses — so the grime pools along the walls exactly where
the trash does. One **Amount** slider (0 = clean, 1 = write your name
in it), one **Blotch Size**, both live on the scattered floor; the
overlay is parented to the floor, replaced per run, and removed by
Clear with everything else. The source floor is never touched. An
**Optimize Dirt** button runs Surface Painter's optimizer over the
sheet — cropped to its grime, thinned to the vertices the pattern
actually needs, pixel-identical — for when the look is final. Its
**Tolerance** sits next to it, per floor: how far the pattern may drift
in exchange for geometry. It defaults to 0.08, much looser than Surface
Painter's 0.02, because a grime sheet is noise rather than an authored
stroke — but the trade is yours to make, and the report says which
tolerance produced which count. Measured on a 20×14 m floor at the
default: **3033 faces down to 291, 70% of them quads, in 0.08 s.** The working
vertex spacing follows Blotch Size rather than a fixed number, so the
mesh is only ever as fine as the pattern on it. The
sheet's triangles are equalised before the pattern is written: the
straight fan triangulation showed the grime tracing the floor's own
edge lines in game, and even triangles are what make noise read as
blotches instead of topology — then joined back into mostly quads, so
the sheet edits like authored geometry (Sollumz re-triangulates on
export, so the game never sees the difference).

Trash Scatter opens **Dressing**, a fifth section for the tools that
populate the interior rather than build or grade the asset itself.

### Added — Edge Wear has a Strength slider

How loudly the damage reads was the one thing deciding whether a strip
could be seen in game, and it was the one thing the tab could not set. It
lived as `bumpiness` and `specularIntensityMult` in the material
properties, three clicks outside the tool that made the strip — so
"invisible in game" was diagnosed by hand, in the shader, every time.

**Strength** now drives both, from a new collapsed **Material** panel
under Edge Wear (for the next strip) and live in **Selected Strip** (for
this one). It is linear from GTA's own numbers: 1.0 is exactly what
`hn_apt_hall_blk_milo` uses, 4.0 is bumpiness 2.0 with the specular
opened to 0.5, and both stop at a ceiling rather than running away.

**New strips ship at Strength 4.0**, not at GTA's 1.0. The reference
values read too faintly on a softly lit interior wall — which is where
this tool is mostly used — and that was dialled in in the game itself
rather than guessed. 1.0 is one drag away for anything meant to sit
exactly where vanilla sits.

The
two values it is setting are printed under the slider — those are the
numbers that go in a bug report, and the ones a default gets moved to
once a value has been dialled in in the game itself.

Dragging it writes to the material and **does not rebuild the mesh**:
Strength is a shader value, and there is nothing in the geometry to
regenerate. The other three shader values stay where GTA has them —
Strength is the effect's volume, not its character.

Because a reused material is never rewritten, a new strip that adopts one
shows **that material's** Strength rather than the panel's, and says so
in the status bar. The strip also reports when its material is shared, so
it is clear that a drag changes every strip wearing it.

### Added — Material Maker, and the Materials section it lives in

Thanks to [@gecu3d](https://github.com/gecu3d): height, normal and
specular maps generated from a single diffuse image, inside Blender, with
no round trip to another program. It arrived as a finished standalone
add-on — its own numpy image pipeline, four panels and a settings page
deep enough to carry a guide of its own — and became the tab's fourth
section, **Materials**: the one tool here that *makes* a texture rather
than putting one onto geometry. Nothing in it needs Sollumz.

The algorithms are ported from Bounding Box Software's Materialize, which
is why this add-on is GPL-3.

### Added — the Color 1 colour is a choice now

Thanks to [@cs-dev-09](https://github.com/cs-dev-09)
([#1](https://github.com/seto3d/void-tools/pull/1)): every tool used to
write one fixed green into `Color 1`, and changing it meant going into
Vertex Paint by hand — which quietly destroyed the alpha channel unless
you remembered to untick **Affect Alpha**. Since the alpha is the part the
decal shaders actually blend by, the damage was invisible until you went
looking for it.

It is a preset list on the finished object now — Green, Red, White, Blue,
Yellow, or Custom with a swatch — and picking a colour **cannot** touch
the alpha.

### Changed - the add-on is called Void Tools

The N-panel tab, the add-on's name in Preferences, the documentation and every
label now say **Void Tools**.

**Only the visible name changed.** Operators are still `seto.*`, per-object data
is still `seto_fake_ao_data`, materials are still `seto_fakeao`, and panel
classes are still `SETO_PT_*`. Renaming any of those would cost every strip in
every existing .blend its settings, for a rename nobody's file needs to know
about - the same reasoning that keeps the packages called `fake_ao/` and
`fake_damage/` while the UI says Ambient Occlusion and Edge Wear.

The tab name now lives in one constant (`shared/panel_layout.TAB`) instead of
being typed into sixteen panel classes.

### Added - who this is better because of

A **Thank You** block in the add-on preferences, listing contributors, sponsors
and what the add-on is built on, with the same rule the README carries: a
sponsor is named only if their sponsorship is public, a contributor once their
PR is merged, and anyone can ask to be removed. Blender's own add-on entry also
gets Documentation and Report a Bug buttons.

## 1.0.0 — the first public release

Nine tools, one N-panel tab: six authoring tools (Ambient Occlusion, Edge
Dirt, Edge Wear, Smooth Edge, Decal Tool, Surface Painter), three
read-only Analysis tools graded against vanilla GTA (Density Check,
Texture Budget, Pre-Flight), and a Support section that reports a bug
without sending anything anywhere.

**Updating happens from inside Blender.** An **Updates** panel sits first
in the tab; when a new release exists its version appears right on the
collapsed header, and **Install Update** downloads and installs it over
the running copy — settings survive, a restart finishes the job. The
notification comes from one quiet check per Blender start, and the terms
of that check are stated everywhere and enforced by the test suite: it
asks github.com for the latest version and nothing else, it carries
nothing about you or your files, it is silent when offline, it never runs
in background Blender, and **Check for updates on startup** in the add-on
preferences turns it off entirely — the Check button still works on
demand. The download is accepted only from this repository's own
releases, the zip is inspected for this add-on's own layout before
install, and the updater package is the only code in the add-on that can
reach the network at all.

**Everything below this heading is the private development log.** Versions
0.2 through 1.9 were internal builds that never shipped outside the
machine they were written on; their numbers remain here as history. Public
versioning starts at 1.0.0 and continues upward from it.

## 1.9.0 *(internal)*

### Added — report a bug without leaving Blender

A collapsed **Support** panel at the foot of the tab. A title and the
three questions a maintainer ends up asking anyway — what you did, what
happened, what you expected — each a single plain field, because a form
that holds still is easier to fill than one that grows and shifts as you
type. **Send Report to GitHub** first shows exactly what will be handed
over, then opens GitHub's own new-issue form with all of it filled in,
plus the versions nobody remembers to include: Blender, Seto Tools, and
whether Sollumz was even found. **Clear Report** empties the form in one
undo step.

**Nothing is sent by the add-on.** The preview says so where it matters,
and what goes out is what you read and submit yourself, signed in as
yourself. There is no token, no account, and no code in the package that
can reach the network — the suite asserts that rather than trusting it. A
report too long for a URL goes to the clipboard instead of being
truncated. Screenshots are added on GitHub itself — an image cannot
travel in a link, so the panel says where to drop it instead of offering
a control that could not finish the job.

The panel also carries **Support the Project**, which opens GitHub
Sponsors — worded that way rather than "Become a Sponsor", because nobody
opens a modelling tool wanting to be asked for money and this one is free
either way. The same links live in **Edit > Preferences > Add-ons**,
which is where somebody whose tab is not drawing can still reach them.

## 1.8.0 *(internal)*

### Added — Texture Budget: what the scene costs in VRAM, and which prop is why

Triangles were only half of what an asset costs, and in FiveM rarely the
half that hurts. **Analyze Textures** colours every mesh by the texture
resolution it carries *for its physical size* — texel density, `√(pixels /
area)`, which is what an artist sees as sharpness — and totals the scene's
texture memory above it.

The target is vanilla again, and vanilla is stricter here than anyone
expects: of the 601 textures in Franklin's house **592 are 512×512 or
smaller** — 331 of them 256², 109 of them 128² — with exactly two 1024²
sheets in the entire interior, which comes to about 55 MB all told. At
1024 texels per metre its meshes grade at a median of 0.42× and a p75 of
0.90×, the same shape as the triangle budget. When something is over, the
panel names the power-of-two size that would fit rather than telling
anyone off.

Scene totals count a shared texture **once** — a sheet worn by forty props
is streamed once, and totalling it per object would report a cost nobody
pays. An untextured mesh is greyed out, not failed: a blockout has nothing
to answer for.

### Added — Pre-Flight: the export test you would otherwise run in game

**Run Pre-Flight** checks every mesh in scope for the handful of things
that pass in Blender and fail after export: no UV map, empty material
slots, unapplied scale, textures that are not DDS, zero-area faces, loose
vertices. Each finding lists the object, a button that selects it, and a
**How to fix** popup with the actual steps — a finding with no route out
is a complaint, not a report.

A mesh with **no material at all** is deliberately not reported. An
imported MLO is full of them — collision bounds, helpers, blockouts — and
flagging every one buried the findings that mattered under hundreds that
did not. An *empty slot* still is, because that is debris either way.

The findings are filed under collapsible headings — **Scale issues (11)**,
**Texture issues (6)**, **Geometry issues**, **UV issues**, **Material
issues** — with the groups that can be fixed in a click first, all closed
to begin with. Forty rows in one column is a wall nobody scrolls; the same
forty under counted headings is a report, and you open the one you came
for. Each heading carries its own **Fix** button for the rows underneath
it: what a user decides about eleven unapplied scales is not what they
decide about six textures, and one button over everything asks for both
answers at once.

Four of the six checks also get a **Fix** button that does it: delete loose
vertices, drop zero-area faces, remove material slots nothing points at,
apply a scale. Each is one undo step and reports in the status bar what it
changed, and **Fix All** clears every one of them at once — running up to
three passes, because dropping a zero-area face leaves the vertices that
were in it loose. The list is sorted with the fixable rows first, so what
can be dealt with in a click is never buried under thirty explanations.

The jump button does more than select now: it frames the object in the
viewport and, where the finding belongs to one material — a .png in the
third shader, an empty slot — makes that the active slot and turns the
Properties editor to its Material tab, whichever tab it was on. The other three deliberately have no button — an automatic
unwrap produces a layout no GTA asset would ship with, which shader a mesh
wants is what the author knows and the tool does not, and Blender cannot
write a DDS at all. A fixer that refuses says why, **on the row that refused** — before this
the button simply looked broken. Two cases are worth knowing:

*Linked duplicates.* Applying a scale writes it into the mesh, so every
object sharing that mesh would resize. Fix asks first, exactly as
Blender's own Ctrl+A does, and gives the object its own copy if you agree
— saying plainly that this ends the instancing for it. The dialog counts
how many other rows are waiting on the same answer and offers to do them
all, so six lamp posts are one question rather than six; only the copies
actually needed are made, since the last object reached is no longer
sharing anything and keeps the original mesh. **Fix All never makes that
trade for you**; it leaves those rows with their reason on them.

*Empty slots.* If every slot on the object is empty, all of them go —
nothing can be mis-assigned when there is no other material to inherit.
Otherwise the empty slots are popped highest-index first and the faces are
left alone, because `materials.pop()` already renumbers them — shifting
them again by hand left the object wearing its neighbours' textures, and
handing the job to Blender's own **Remove Unused Slots** operator quietly
did nothing at all on a real MLO. An empty slot faces still point at, on
an object
that has real materials too, is refused: which material those faces
should get is the author's answer, not the tool's. The non-DDS finding names
the **material** holding the image, not just the image, because that is the
shader you have to open.

N-gons are deliberately **not** checked: Sollumz triangulates on export,
so flagging one on every box-modelled asset would be the noise that
teaches people to ignore a checker. Non-DDS textures are, because GTA
streams mip-mapped, block-compressed DDS and a PNG has neither — it
shimmers at distance and inflates the `.ytd` it is embedded into.

Every check earns its place by being something **vanilla barely does** —
261 of Franklin's 265 render meshes come back with nothing said about them,
and the four that do trip only the mildest check — so a finding is not a
matter of taste. Non-uniform scale is graded worse
than uniform, because that is the case where normals and tangents disagree
and a normal map comes out wrong on an export that looked fine.


### Added — draw calls, in the Density Check

The object's line now reports its material count, because each material is
a draw call and in GTA those are often dearer than the triangles under
them. Vanilla is blunt about it: the median mesh in Franklin's house has
exactly **one** material. Past four, the panel says merging would help.

### Changed — one grading session, shared

Density Check and Texture Budget paint into the same object colours, so the
session that remembers what those colours were is now shared
(`shared/viewport_grade.py`). Starting one ends the other cleanly instead
of saving its verdict as "the user's own colour", and finishing either
hands back what was really there.

## 1.7.0 *(internal)*

### Added — Density Check, a triangle-budget heatmap

A third section in the tab, **Analysis**, and the first tool that builds
nothing. **Analyze Density** grades every mesh in scope — the visible view
layer or the selection — and shows the verdict as the object's viewport
colour, green through yellow to red, flipping the viewport to Object colour
so the answer is visible the moment the button is pressed. **Finish
Analysis** restores every colour and the shading mode exactly as they were.
The active object's line grades itself too: triangles, tris/m², how many
times its budget it spends, and a one-line verdict from "leave it" to
"decimate or retopo".

The budget is calibrated against **vanilla GTA V**, not against any one
class of asset. A flat per-m² threshold cannot grade a bottle and a room
shell at once, so the entitlement grows with the square root of surface
area — `1000 × √area`, one editable number. The constant is measured, not
guessed: run over **Franklin's house**, three quarters of its 261 render
meshes sit under 1× and only four — a hero tequila bottle, two controllers
and an ashtray — pass 4×. The panel says so, next to the scale, so a
colour reads as information rather than as a telling-off: 1× is what
Rockstar spends on a mesh that size, and a hero prop is *meant* to be over
it. Every doubling is one equal visual step.

The measurement is taken from the **evaluated** mesh in **world** space: a
live modifier or a scaled object grades as what Sollumz would actually
export, not as its base mesh. A mesh with triangles but no measurable
surface is flagged as the worst case rather than divided by zero.

Density Check is also the one tool that works without Sollumz installed:
counting triangles needs nothing beyond Blender.

### Fixed — Edge Dirt's Bevel Mesh did nothing

The tick was on the finished strip, it could be clicked, and nothing anywhere
read it. Edge Dirt cut its source round into the mesh with `bmesh.ops.bevel` at
creation, which works exactly once: the edge it rounded no longer exists
afterwards, so there was nothing left for the tick to act on — and the strip
had to store its corner verbatim because the indices pointing at it had stopped
meaning anything.

It is the same live **Bevel modifier** the other three tools use now. Ticking
**Bevel Mesh** rounds the source, dragging Width follows it, unticking removes
the modifier and leaves the source exactly as it was found, and the round still
reaches the YDR because Sollumz exports the evaluated object. The source mesh
is never edited, which also means an Edge Dirt strip now keeps pointing at real
source edges.

The **Bevel target** dropdown (Source / Strip / Source + Strip) is gone with
it: with both rounds live off one set of settings there is nothing left to
choose. Strips saved with a target still load — the setting is simply no longer
read.

## 1.6.1 *(internal)*

### Fixed — two tools' Bevels on one wall rounded each other's edges

Ambient Occlusion, Edge Wear and Smooth Edge all drove their source round
through Blender's own `bevel_weight_edge` attribute, which **every** Bevel
modifier limiting by Weight reads. A wall carrying an AO strip and an Edge Wear
strip therefore got two modifiers that each rounded both tools' edges, at each
other's widths, and the rounds compounded — measured on a cube, one strip takes
it from 8 vertices to 16 and two strips took it to 44.

Each tool now writes and reads its own attribute. Blender's is left alone
entirely, so a Bevel modifier you added yourself is no longer affected, and
weights left in it by older versions are cleared off our edges as each source
is next synced.

### Fixed — deleting a strip left the source rounded

The modifier came off when the last strip's Bevel was switched off, but not
when the strip itself was deleted: nothing was left to notice. The wall kept
its round and a modifier named after a tool that was no longer there. Deleting
a strip now takes its modifier and its weights with it, leaving the source as
it was found.

### Fixed — a pinned strip jumped when its Drawable was moved

Strips built from a source inside a Sollumz Drawable are parented into it. The
pinned position was remembered in world space, so moving the Drawable left that
figure stale — the strip travelled with its parent correctly, but typing into
the Offset field teleported it back to where the Drawable used to be. It is
remembered in the strip's own transform now, which parenting leaves alone.

## 1.6.0 *(internal)*

### Added — a hand-moved strip stays where it was put

Nudge a finished strip up off the floor, touch any setting, and it used to jump
back onto its source: every rebuild re-derives the strip's position from the
object it was built along, which is what keeps repeated rebuilds stable and is
also what wiped the move.

**Selected Strip** now has a **Position** section on all four strip tools —
Ambient Occlusion, Edge Wear, Smooth Edge and Edge Dirt. Move the strip where
you want it, press **Pin Position**, and every rebuild from then on puts it back
there. **Clear Offset** drops the pin and returns it to where the tool
generates it; the Offset field can be typed into directly, and moves the strip
without rebuilding its mesh.

The pin means "this far off my source", not "at these coordinates": a setting
that legitimately moves the strip — a wider shelf re-centres its origin — still
moves it, carrying the offset along. For the specific case of lifting a strip
vertically, Ambient Occlusion's **Ground Level** was already an answer and
still is.

## 1.5.1 *(internal)*

### Fixed — Edge Wear and Smooth Edge threw on their Selected Strip panel

`_draw_bevel` was called without being imported, so selecting a strip from
either tool produced a NameError and no Bevel block. Shipped in 1.5.0 because
`tests/panels.py` cannot reach these panels: a "Selected X" panel polls False
unless one of the tool's own objects is active, so its draw() was never run.

`tests/selected_panels.py` closes that gap - it builds a real strip for each
tool first, then draws its panel. These are the panels with the most in them
and the only ones anyone looks at while dragging a value.

## 1.5.0 *(internal)*

### Added — Bevel on Edge Wear and Smooth Edge

The two Geometry tools had no Bevel at all; Ambient Occlusion and Edge Dirt
did. They have the same one now, in the same shape: a **Bevel** block on the
finished strip with two ticks — **Bevel Mesh** rounds the source object's
corner with a live modifier, **Bevel Edge Wear** / **Bevel Smooth Edge** rounds
the strip's own seam — and Width, Segments and Profile Shape underneath.

Both off by default, both live: drag the width and whichever is ticked follows.
Unticking Bevel Mesh removes the modifier and leaves the source exactly as it
was found. A strip built from Ground Level says so instead, since there is no
selected edge to round on either mesh.

The definitions are imported from Ambient Occlusion rather than written out
again, so the three tools cannot drift into rounding things three different
ways, and `source_bevel.py` now serves all of them — a tool differs only by
which per-object group its strips live in and what its modifier is called.

## 1.4.0 *(internal)*

### Changed — one layout for the whole tab

Six tools grew their panels separately and ended up saying the same things six
different ways: three spellings of the child-panel boilerplate, five copies of
the "Selected X" header, Create buttons at three sizes, and — on the tools that
had not been split up — a dozen settings run together in one unlabelled column.

They now share one vocabulary (`shared/panel_layout.py`):

- **Related rows sit under a heading.** Every finished object's panel is now
  Shape / Fade / Bevel — and, where the tool has them, Texture Placement,
  Corner Alpha, Border Alpha — instead of one column you had to read to
  navigate.
- **The Create button is the same button everywhere**, and taller than a
  normal row. Child panels are drawn after their parent, so it stays at the top
  of the tool's block however much is expanded below it.
- **Sub-panels collapse, order and hide themselves the same way.** The order is
  declared rather than left to whatever registration happened to run first, and
  the "Selected X" panel is always last and always open.

**Fixed on the way through:** Surface Painter's five sub-panels drew regardless
of Sollumz. A child panel is a panel in its own right — Blender draws it
whether or not its parent drew anything — so on a machine without Sollumz they
came up fully populated underneath a parent that had just said the tool could
not run. The shared base polls for Sollumz, so this cannot come back one tool
at a time.

### Fixed — Edge Dirt's panel listed its textures folder on every redraw

`os.listdir` per redraw, which is per mouse move over the panel. Bundled-texture
scans are now cached against the folder's modification time, so dropping a file
in is still picked up with nothing to press.

### Changed — Create no longer opens the redo panel

The "Adjust Last Operation" box in the bottom-left corner is gone from every
Create button. It duplicated the panel you had just used, and it disappears the
moment you click anything else — while the same settings live on the finished
strip, in **Selected Strip**, where they rebuild it live and stay there.

### Changed — generated objects are named after the tool

`fake_ao_003` and `fake_dmg_003` named tools that no longer exist anywhere in
the UI. New strips are **`ambient_occlusion_003`** and **`edge_wear_003`**, and
their collections match. Existing files keep the collection they already have
rather than growing a second one beside it, and numbering continues past
old-named strips instead of restarting at 001 on top of them.

### Added — Alpha Bottom and Alpha Top on Edge Wear and Smooth Edge

They were Ambient Occlusion's only. Both Geometry tools have them now, through
the section that owns their shared settings, and on finished strips in
**Selected Strip**. Alpha Center/Outer fade a strip *across*; these fade it
*along* the run, so an edge can let go before it reaches the floor. 1.0 at both
ends — the default — leaves the strip exactly as it was.

Bottom and top are the building's, read out of the source's world matrix, so a
wall whose object happens to be rotated still fades toward the real floor.

### Added — Edge Dirt

A sixth tool, at the bottom of the **Surface** section. It is Ambient Occlusion
with a different texture on it: the same strip, the same Width, alphas, Bevel
and Ground Level, the same live rebuild on the finished strip — but it takes
its image from `void_tools/edge_dirt/textures/` and puts it on a
`seto_edgedirt` material of its own.

**The folder is the setting.** Drop a dirt texture in and every strip the tool
builds picks it up in `DiffuseSampler`, as sRGB and not embedded; the panel
names the file it found, and says so plainly when the folder is empty. A file
called `edge_dirt.*` wins if you want to pin one while keeping others around.

A strip built **before** the texture was dropped in leaves an untextured
material behind, and reuse would hand that same empty material to every strip
after it — the tool looking broken however many times the texture was added.
So reuse now fills a DiffuseSampler that is empty. One that has an image in it
is still never touched.

The two tools keep their own settings and their own materials, so a dirt strip
and an AO strip can sit on the same wall without either one moving or
retexturing the other. What they share is the code: the geometry and the
rebuild live in `fake_ao/` and are imported, not copied, so a fix to one corner
case is a fix in both.

### Changed — Ambient Occlusion's Bevel is live, and rounds both meshes

It used to be set before Create and then cut into the source mesh with
`bmesh.ops.bevel`. That worked exactly once: the edge it rounded no longer
existed afterwards, so the width could never be changed and the round could
never be taken back.

**The Bevel block has moved off the create panel and onto the finished strip**,
where one set of controls drives the strip's own seam *and* the source's corner,
live. Drag Width and both follow. Switch it off and the round comes off both,
leaving the source exactly as it was found. There is no Target to pick any more
— rounding one mesh and not the other was never what anyone wanted.

The source's round is a **Bevel modifier** (`Seto AO Bevel`) limited by edge
weight, with the weight set on the strip's own edges and nowhere else. The mesh
itself is not edited. Sollumz exports the evaluated object, so the round is
baked into the YDR exactly as if it had been applied by hand — checked against a
real evaluated mesh, not assumed.

Two things fall out of the mesh no longer being cut. A strip can go on pointing
at its corner by **vertex index**, so the frozen-geometry fallback that a
destructive bevel forced is down to Ground Level strips alone. And **one
modifier serves every strip on an object** at each strip's own width: weight
limiting scales the modifier's width per edge, so the modifier carries the
widest strip's width and the rest are weighted down to their share. Segments and
Profile Shape have no per-edge equivalent and are genuinely shared.

Edge Dirt is unchanged — it still cuts its bevel in, and keeps the Target
choice.

### Added — Ambient Occlusion fades along the run, not just across it

**Alpha Bottom** and **Alpha Top**, next to the two alphas that were already
there. Those fade the strip *across* the shelf, corner out onto the wall; these
fade it *along* the run, so a corner does not have to arrive at the floor or
the ceiling at full strength. 1.0 at both ends — the default — leaves the strip
exactly as it was, and anything lower scales what the across-fade produced,
ramping back to full at the other end.

Bottom and top are the **building's**, read out of the source's world matrix,
so a wall whose object happens to be rotated still fades toward the real floor.

Each vertex is placed by the selected-edge end it came from rather than by
where it itself ended up, which is the part that is easy to get wrong: a
wall-to-floor edge is all one height, but its strip climbs the wall, so
measuring the vertices would fade the top of the *shelf* and call it the top of
the run. Measured properly, a run with no height has no bottom or top to fade
between and is left alone.

The ramp is linear, because that is what the geometry can carry — a run built
from one selected edge has two vertices along its length. Subdivide the source
edge for a tighter falloff, the same as for everything else in this tool.

### Added — Ambient Occlusion along a ground line, with no edge to select

From a tester, with a screenshot of a curved desk sunk into the floor: *"can I
create a decal for an object that extends into the ground?"* There was no edge
there to select — the line you can see is where the mesh crosses the floor, not
geometry.

**Build From: Ground Level** takes a world height and builds along the contour
at that height. A copy of the mesh is cut there and everything below is
discarded, which is what makes the strip run **upward only**: cutting the wall
in place would leave an edge with a face either side and a strip spread equally
both ways, half of it buried. **The object itself is never touched.**

It needs no selection and no Edit Mode — pick the object and press Create.
Bevel is not available in this mode: it rounds off selected edges, and there
are none.

### Fixed — Surface Painter ignored a folder of loose images

A tester pointed **Custom Library** at a folder of PNGs and got *"No textures
yet"*. Categories were subfolders and nothing else, so a flat folder — the
obvious thing to try — read as an empty library. Loose images now form their
own category, exactly as they always have in the Decal Tool, and the message
when a folder really does come back empty now says which file types are read.

### Changed — the Decal Tool gets Surface Painter's texture browser

The same list of names with the pick previewed underneath, in place of a
dropdown. A dropdown can only show a thumbnail for the row the pointer happens
to be over, and choosing a decal is choosing a picture. The texture enum is
still there under the preview, so nothing that scripted against it breaks.

## 1.3.1 *(internal)*

### Fixed — Sollumz Development was reported as not installed

From a tester running it: every tool claimed Sollumz was unavailable on a
machine that plainly had it working.

Two things were wrong, and both are now gone.

**Detection only ever looked at add-ons whose name began with "sollumz".** It
now tries **every enabled add-on** and lets an import decide — the name only
chooses what to try first, so a fork, a rename or a build nobody anticipated is
found rather than declared missing. The answer is cached, so this costs nothing
per redraw.

**A missing `dependencies` module was treated as fatal.** That module is
Sollumz's own, and a fork is free to move or drop it. What is checked now is
what these tools actually need — that Sollumz's shader module imports. Its
dependency check still counts, but only when it exists *and* answers no.

### Added — you can point Seto Tools at Sollumz by hand

Also the tester's suggestion, for the case where detection still fails.
**Preferences → Add-ons → Seto Tools → Sollumz Module** takes either the module
name as Blender knows it (`Sollumz`, `Sollumz-main`,
`bl_ext.user_default.sollumz`) or the folder Sollumz is installed in. Leave it
empty and nothing changes.

The preferences now show what was detected, and the "Sollumz not available"
warning in every panel has a button that opens them.

## 1.3.0 *(internal)*

### Changed — a redrawn icon set

Line-art icons, one per tool and one per section, cropped out of the frames
they were drawn in — a rounded box around every icon costs about a sixth of a
32 px tile and reads as a button next to Blender's own frameless icons.

They ship at 55% of the source brightness. A custom icon is never tinted by the
theme, and this art is pure white line with no darker pixel anywhere in it, so
above roughly 60% there is nothing for the eye to catch on a light theme.

### Changed — Fake AO and Fake Damage are now Ambient Occlusion and Edge Wear

From a tester: *"in an abstract sense everyone knows we are doing fake things,
it's a videogame — the interiors themselves are fake, but we don't call MLOs
Fake Interiors."* Hard to argue with. **Fake AO → Ambient Occlusion**,
**Fake Damage → Edge Wear**.

Labels, tooltips and messages only. Operators are still `seto.create_fake_ao`
and `seto.create_fake_damage`, materials are still `seto_fakeao` and
`seto_fakedamage`, and every strip in an existing .blend keeps its settings.

### Changed — the strip settings are the Geometry section's, not each tool's

Also from a tester: the same seven rows — Width, Surface Offset, Merge
Distance, the two alphas, Invert Fade, Flip Direction — were listed under Edge
Wear and then listed again, identically, under Smooth Edge. They build the
*same* strip; only the texture on it differs.

The **Geometry** section now draws them once, above both tools. Edge Wear keeps
its UV Scale and UV Offset, Smooth Edge is left with nothing but its Create
button, and **Material** moves up with the rest.

The values are shared, which is the point: set Width to 4 cm and both tools use
it. A **finished** strip is unaffected — every created object still carries its
own copy and rebuilds from that, so a change to the section never reaches back
into what you already made.

Ambient Occlusion is deliberately not part of this. It lives in the Surface
section and its Width means something else — the flat shelf the AO fades
across, 0.25 m against 0.04 m here — so sharing would have the two overwriting
each other.

## 1.2.1 *(internal)*

### Changed — the tab has its own icons

All seven panel headers — both sections and all five tools — now draw a PNG
that ships with the add-on, in `void_tools/icons/`, loaded through the same
preview mechanism the decal and dirt thumbnails use. Blender's built-in set has
nothing for "chipped corner" or "dirt brushed onto a wall", and two tools were
sharing an icon because of it.

They are 32×32, which is the size Blender draws an icon at, and mid-grey with
one warm accent rather than near-white: a custom icon is **not** tinted by the
theme, so a near-white one disappears on a light theme. A missing or unreadable
file costs that one icon — the header falls back to the built-in it used
before.

### Fixed — dropdowns you could open onto nothing

With no library set, **Category** and **Texture** in the Decal Tool and Surface
Painter still opened as dropdowns, onto a single `<no categories>` placeholder.
Picking it did nothing, which made the tool look broken rather than unset. Both
are greyed out until there is something behind them. The placeholder text stays
— it says what to do about it — and **Refresh** stays live, since it is the way
out of that state.

## 1.2.0 *(internal)*

### Removed — the lighting module is gone

An unfinished God Ray tool that was never registered, so Blender never loaded
it. It has been excluded from the zip by hand since it was written; it is now
simply deleted, along with the `.gitignore` entry and the sync-script step that
kept working around it.

### Changed — The tab is two sections instead of five headers

Five tools side by side gave no hint of which one to reach for, so the
**Seto Tools** tab now opens on two sections and the tools nest inside them:

```
Geometry            builds new mesh along the selected edges
  Fake Damage
  Smooth Edge
Surface             puts texture on a surface that is already there
  Fake AO
  Decal Tool
  Surface Painter
```

**Fake AO moved in with the surface tools.** It builds a strip the way the two
Geometry tools do, but what it is *for* is shading a surface, which is how it
gets reached for.

Each tool also gets its own header icon — Fake Damage and Smooth Edge shared
one before, which made the two hardest tools to tell apart look identical in a
collapsed tab.

Nothing about any tool changed, only where it sits. The sections own no
settings; they are headers.

**Material** is now **Reuse** / **Create** in all four tools, instead of
*Reuse if Exists* / *Always Create New*. The long labels were wrapping in a
tab this narrow; the tooltips still spell out what each one does.

### Added — Fake AO rounds the corner off as well as decalling it

A razor-sharp corner reads as sharp no matter how good the AO on it is, so the
manual step before running the tool was always the same one: bevel the edge.
Fake AO now does it, in a **Bevel** block using Blender's own bevel settings
under Blender's own names — **Width**, **Segments**, **Profile Shape**.

It is **on by default**, at **Width 0.0833 m, 4 segments, profile 0.5**, and the
default **Target** is **Source + Strip**: the source edge is rounded, and the
strip is built to follow that round with the same Width and Segments. Both
meshes come out the same shape, which is the only way the decal sits *on* the
rounded corner rather than flat across it. The other two targets are still
there — **Strip Only** rounds the strip and leaves the source sharp (the round
hides the sharp corner under it), **Source Only** rounds the source and runs a
flat strip along each side of it.

Because a rounded corner takes a bite out of the shelf the AO fades across, the
default **Width** goes from 0.1 m to **0.25 m** — the old default would have
left 1.7 cm of flat to fade over. The panel warns when Bevel Width is no longer
below Width.

Three things this had to get right, all of them checked by
`tests/fake_ao_bevel.py`:

- The strip's round is generated by beveling its own seam with the same
  settings, not by approximating the source's — so the two are the same shape
  by construction, and the strip sits exactly Surface Offset outside the
  source.
- The source bevel happens **once**, at creation. A live rebuild only
  re-applies the strip's, otherwise every slider drag would chamfer the
  chamfer.
- The corner a **Source + Strip** strip was built from no longer exists once
  the bevel has run, so vertex indices cannot describe it. Those strips store
  the corner itself and rebuild from that. **Source Only** strips keep using
  indices, plus a record of *which* faces were used, so a rebuild cannot
  quietly adopt the chamfer face creation deliberately left bare.

Strips made before this release store neither, and keep behaving exactly as
they did.

### Fixed — a beveled corner came out as a band of the wrong material

The chamfer showed up as a coloured stripe running the full length of the
corner. Beveling the same edge by hand looked perfect, which is the clue:
`bmesh.ops.bevel` defaults its `material` argument to **0**, where Blender's
own Bevel defaults Material Index to **-1**, "same as the adjacent face". So
every face the bevel created was dragged onto material slot 0 — on a wall whose
brick lives in another slot, an entire corner's worth of the wrong material.

It was never a UV problem. Blender's own interpolation lays the chamfer's UVs
out as a blend between the two rims, which can only ever land inside the span
the walls already occupied — checked now against a wall mapped into an atlas
island with something else parked next to it.

### Changed — Fake AO: Merge Distance is worked out, Surface Offset has a ceiling

**Merge Distance is gone from the panel.** It was a slider with one correct
answer, and both of its bounds came from the other two settings: large enough
to close the seam where two wings meet — `Surface Offset × √2` at a right
angle, more on a shallower corner — and far enough below Width not to collapse
the strip. It is now `Surface Offset × 4`, floored and capped at a quarter of
Width. Existing strips keep the value they stored; it is simply no longer read.

**Surface Offset is capped at 0.05 m** rather than merely suggesting it. It is
a z-fighting nudge; past a few centimetres the strip is not on the wall any
more.

## 1.1.1 *(internal)*

### Fixed — Sollumz was not detected when installed from the repository

Every tool reported **"Sollumz not available"** on machines that plainly had it.
The detection required the add-on's module name to end in exactly `sollumz`,
which is true for an extension and for a folder called `Sollumz` — and false
for the most ordinary way there is to install it. GitHub names its archive
after the branch or tag, so downloading Sollumz from its repository installs as
`Sollumz-main`, `Sollumz-master` or `Sollumz-2.9.0`, and none of those matched.

The name test is now a loose *candidate* filter — anything starting with
`sollumz` — and the decision is made by importing a module only Sollumz has.
Guessing which separators are legitimate is what caused this in the first
place; verifying is what settles it, and it also means an unrelated add-on
called `sollumz_extras` is rejected for being the wrong thing rather than for
being spelled unexpectedly. Extension names are split at the `bl_ext.<repo>.`
prefix rather than the last dot, so a version number in a folder name no longer
turns `Sollumz-2.9.0` into `0`.

When nothing is found at all, the message now says the add-on must also be
*enabled* — `preferences.addons` only lists enabled ones, so installed-but-
unticked was reported as "not installed", which sends people to reinstall
something they already have.

### Fixed — Surface Painter did not say when Sollumz was missing

The other four tools each showed a "Sollumz not available" box; Surface Painter
was the one that never got the paste, so it drew its whole UI and looked like
the tool that worked without Sollumz — until Start Paint, which needs a
`decal.sps` material that only Sollumz can build. Failing in the panel, with
the reason, beats failing at the button.

That block now lives once in `shared/ui_common.py` and all five tools use it,
along with the label-wrapping helper that had been copy-pasted five times.

### Changed

- **"No textures found" now says what to do.** With nothing bundled, an empty
  library is the normal first run, not a fault, so the panel points at Library
  Folder instead of showing an error icon.

### Added

- `tests/panels.py` drives **every** Seto panel's `draw()` against a validating
  stub layout, with Sollumz both available and missing — 261 checks. Blender
  only calls `draw()` from the UI thread, so every other test here can pass
  while a panel explodes on first redraw; that had happened three times before
  this existed, and each time a user found it rather than the suite.

## 1.1.0 *(internal)*

### Added — Surface Painter

Brush dirt, grime and graffiti straight onto a surface, without the surface
ever being modified. **Start Paint** spawns a separate *paint mesh* over it — a
copy of the surface, packed with extra vertices, floated a few millimetres off
it, wearing a `decal.sps` material — and painting happens on that. Delete it and
the dirt is gone and the wall is exactly as it was. Same trick GTA uses for
grime.

`decal.sps` reads `Color 1`'s alpha as its blend factor, which is Sollumz's own
node wiring, so painting alpha is painting visibility: the brush works in
`ADD_ALPHA` / `ERASE_ALPHA` and the mesh carries only what Sollumz exports —
`Color 1`, `UVMap 0`, and nothing else in either list.

- **Layers.** One per texture, per wall. Picking a different texture and
  pressing Start Paint again adds a layer over the first rather than
  retexturing what you already painted.
- **Its own UVs.** The paint mesh is given one planar projection across the
  whole surface instead of inheriting the wall's unwrap. A wall's layout is
  built for its tiling texture, so it is usually several islands stacked in
  0–1 — a wall with one loop cut is two of them — and inheriting that drew the
  decal once per island. A projection cannot overlap itself.
- **Place On Surface.** Drags the texture with the mouse, and the point you
  grabbed stays under the pointer at any Width, Height or Rotation. It keeps
  tracking past the edge of the surface, by falling back to the projection
  plane, so a decal can be pushed into a corner or half off an edge. The wheel
  resizes around the pointer, `X`/`Y` lock an axis.
- **Lossless placement.** Opacity, Width, Height, Offset and Rotation all
  recompute from a pristine copy of the UVs and strokes, so dragging a slider
  back where it was gives back exactly what you had.
- **Preview Texture.** The whole texture shown semi-transparent over the
  surface, Substance-projection style, as an object-level override on a copy —
  the material that exports is never touched.
- **Optimize**, which never touches the texture: unpainted faces are cropped
  away so the layer ends up the size of the decal rather than the wall, the
  staircase left around the patch is welded down, and inside it the vertices a
  stroke does not need are dissolved. Then the origin moves to the middle of
  what is left. Measured: **1024 triangles down to 91**, UVs bit-identical.
- **Texture library** with categories, an in-panel browser and disk-backed
  thumbnails, so browsing loads nothing into your file. No textures are
  bundled — the category folders ship empty, each with a README saying what
  goes there. Dirt sheets are large enough to have been most of the download,
  and anyone doing this work already has a library: point **Custom Library**
  at it.

Baking was built, worked, and was removed. A baked texture is flattened from a
tiling one and can never be sharper than what it sampled, which on a wall is a
lot worse — so the optimisation removes geometry instead, and the pixels are
untouched.

### Changed — the N-panel

- **The tab is grouped by what a tool works on.** The three that build a strip
  along selected edges come first — Fake AO, Fake Damage, **Smooth Edge** —
  then the two that put texture on a surface: Decal Tool and Surface Painter.
  Smooth Edge used to sit below the Decal Tool, splitting the strip tools in
  half, and the ordering had a hole in it.
- **Surface Painter's section is split into child panels** the way the Decal
  Tool's is. It has the most controls of the five, and as one column it was
  long enough that Start Paint scrolled off the bottom while you were choosing
  a texture. What is left in the main section is the workflow — layers,
  texture, paint — with **Brush**, **Placement**, **Normal Map**, **Paint
  Mesh** and **Library Folder** below it. Placement and Normal Map only appear
  once a layer exists.
- **Explanations moved out of the panel and into tooltips**, where Blender
  meant them to live. Several three-line paragraphs of `label()` were spending
  permanent vertical space on things you read once.
- **Buttons are Title Case**, matching the other four tools. Surface Painter
  was the only one shouting `START PAINT`.

### Verified

`tests/surface_painter.py`, headless against Sollumz on Blender 5.2.0 LTS. The
two checks worth keeping: that the paint mesh's UVs are one **affine** function
of position — an island or a repeat breaks that fit and nothing else does — and
that a drag leaves the texture point you grabbed under the pointer at every
Width, Height and Rotation, which catches a wrong sign, a missing divide by the
size and a missing rotation as three separate failures.

## 1.0.0

### One add-on instead of three

Fake AO, Fake Damage and the new Decal Tool now ship as a single **Seto Tools**
add-on (`void_tools/`) rather than three that had to be installed separately.
They already shared the Seto Tools N-panel tab; now they share a process and,
more usefully, one copy of the Sollumz integration.

The three copies were byte-identical apart from their docstrings and one material
builder each, so merging them changed no behaviour. The builders are simply named
apart now, each with its own material name and reuse rule so no tool can adopt —
and then retexture — another's material:

| Builder | Tool | Shader |
| --- | --- | --- |
| `find_or_create_fake_ao_material` | Fake AO | `decal.sps` |
| `find_or_create_damage_material` | Fake Damage | `decal_normal_only.sps` |
| `find_or_create_smooth_edge_material` | Smooth Edge | `decal_normal_only.sps` |
| `find_or_create_decal_material` | Decal Tool | `decal.sps` |

> **Upgrading:** disable and remove `seto_fake_ao`, `seto_fake_dmg` and
> `seto_decal_tool` before installing this. They register the same operators and
> panels, so having both loaded conflicts.

### Added — Decal Tool

Select faces, pick a decal from an external library, press one button. Per
selected surface it builds a plane aligned to that surface, offset along its
normal, with a `decal.sps` material carrying the chosen texture and its origin at
its own centre. The source mesh is only ever read.

- **Library folder** is an add-on preference, so it is picked once and survives
  new files and restarts. Categories are its subfolders. Scanned into a cache
  rather than on every redraw; **Refresh Library** rescans.
- **Texture thumbnails** in the panel — only the texture being looked at is
  loaded, once per session.
- **Merge Coplanar** — touching faces in the same plane count as one surface, so
  a wall split into N quads takes one decal, not N.
- **Randomization** — rotation, scale, texture and position, evaluated per
  surface.
- **Border ring** — the decal is a 4×4 grid (16 vertices, 9 quads) whose outer
  ring starts at alpha 0, so it dissolves into the surface instead of ending on a
  hard rectangular outline. **Edge Fade** sets its width.
- **Per-corner and per-side alpha** — four **Corner Alpha** values on the inner
  rectangle give any linear gradient across the decal; four **Border Alpha**
  values raise individual sides of the ring, for instance to keep the edge that
  meets a floor hard. Where two sides meet, the ring corner takes the lower of
  the two, so a faded side stays faded into its corners.
- **Live editing** — size, edge fade, surface offset, rotation, position on the
  surface and every alpha update as you drag. Sliding a decal past an edge
  **walks it onto the neighbouring face** instead of leaving it hanging in space;
  it can cross several faces in one drag and dragging back retraces the path.
- **No orphans on failure** — a texture that fails to load never leaves a decal
  behind. Materials are resolved before any geometry exists, so the common
  failure never creates an object at all.

### Added — Smooth Edge

Fake Damage's structure applied to a different job: a normal-map strip along a
hard edge so it reads as rounded in game, without adding a bevel. Two things it
does that Fake Damage did not:

- **Shade smooth**, automatically, on the generated strip only.
- **Its texture is bundled** in `smooth_edge/textures/` and wired into
  `BumpSampler` and `DiffuseSampler` as Non-Color, not embedded.

### Added — across the tools

- **Bundled textures.** Fake AO, Fake Damage and Smooth Edge each carry their
  texture in the tool's own `textures/` folder and wire it in automatically. Fake
  AO uses `decal.sps`, which has only `DiffuseSampler` and wants a colour
  texture, so its image goes in as **sRGB**; the other two are normal maps in
  both slots as **Non-Color**. An empty folder is not an error — the strip is
  still built and the tool reports that the slot was left for you.
- **Shade smooth** on everything generated, applied through the data API so it
  survives a live rebuild.
- **One vertex colour.** Every tool writes the same `Color 1`: RGB `#00B200`,
  alpha 1.0 at the centre fading to 0.0 at the outer edge. Defined once in
  `shared/vertex_color.py`.
- **Sorted output.** Inside a Sollumz Drawable, generated geometry lands in the
  Drawable's own collection, beside the rest of the asset — parenting alone left
  it greyed out in the outliner and out of reach of anything working on that
  collection. Outside one, each tool files into its own collection, created on
  first use: `fake_ao`, `fake_dmg`, `smooth_edge`, and `decals` with one child
  per library category.
- **Upright UVs.** The strip tools rotate their island 90° so it stands vertical
  in the 0..1 square. A real rotation, not an axis swap — swapping would mirror
  the island and flip the direction a normal map points in.

### Changed

- **Fake Damage shader values** now match GTA's own damage strips
  (`hn_apt_hall_blk_milo`): `bumpiness` 0.50, `specularIntensityMult` 0.125,
  `specularFalloffMult` 100, `specularFresnel` 0.97.

  `specularIntensityMult` was `0.00`, which is what made strips read as nearly
  invisible in game. `decal_normal_only` carries no colour of its own — it only
  perturbs the surface normal — so what makes a crease readable is the light's
  response to that normal, and most of that response is specular. Turning it off
  removed the effect however strong the normal map was.

  A **reused** material is never rewritten, so an existing `seto_fakedamage`
  keeps its old values — delete it, or use *Always Create New*, to pick these up.
  Smooth Edge keeps its own separate values.
- **Fake Damage UV placement.** New **UV Scale** and **UV Offset** settings place
  the fitted island on the part of the texture that holds the crease. Both are
  live-editable per strip.
- **"Damage Width" is now just "Width"** in Fake Damage and Smooth Edge.
- **Collections lost their `seto` prefix**: `fake_ao`, `fake_dmg`, `decals`.
  Generated strips are filed there instead of next to the source object.

### Fixed

- **Fake AO adopted other tools' materials.** Its reuse matched any `decal.sps`
  material, so it could pick up — and then use — one of the Decal Tool's
  per-texture materials. It now has its own name (`seto_fakeao`) and only
  recognises that.
- **Decal placement applied the offsets twice**, so a 0.2 m slide moved 0.4 m.
- **Surface tangents used the wrong matrix.** A normal must go through the
  inverse-transpose normal matrix; a tangent is an ordinary direction and must go
  through the plain linear part. Under non-uniform scale the two disagree.

### Removed

- The `seto_fake_ao/`, `seto_fake_dmg/` and `seto_decal_tool/` folders, and their
  separate zips, superseded by `void_tools/`.

### Verified

Headless against **Sollumz 2.8.3 on Blender 5.0.1** and **Sollumz 2.9.0 on
Blender 5.2.0 LTS** — surface alignment under rotated and non-uniformly scaled
sources, Sollumz attributes and shader parameters, material reuse and separation,
bundled textures, collection placement, failure cleanup, and a clean YDR export.
