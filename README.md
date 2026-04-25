# C4D_ls-cam

A Cinema 4D plugin that fakes a relativistic ("LS-Cam") perception layer on
top of a standard C4D camera. The command builds a small rig and drives a
standard camera + a forward spot light from a single `beta = v/c` slider on
an animator-friendly controller, with an optional Octane Render bridge.

> Physically inspired, not physically exact - see *Caveats* below.

## Compatibility

Tested with **Cinema 4D 2023.2** (Python API).

References:
- https://developers.maxon.net/docs/py/2023_2/manuals/index.html
- https://developers.maxon.net/docs/py/2023_2/misc/pluginstructure.html

## Installation

Copy the `C4D_ls-cam/` folder into Cinema 4D's `plugins/` directory:

```
<C4D install or prefs>/plugins/
└── C4D_ls-cam/
    ├── C4D_ls-cam.pyp
    └── res/
        ├── c4d_symbols.h
        └── strings_us/
            └── c4d_strings.str
```

Restart Cinema 4D. The command appears under **Extensions → Create LS-Cam**.

## Replacing the placeholder Plugin ID

The plugin ships with `PLUGIN_ID = 1000001` as a placeholder. Before public
distribution, replace it with an official ID obtained from
[Maxon Plugin Café](https://plugincafe.maxon.net/). Edit the constant near
the top of `C4D_ls-cam/C4D_ls-cam.pyp`:

```python
PLUGIN_ID = 1000001  # ← replace with your registered ID
```

A registered ID prevents collisions with other community plugins. The
`OCTANE_*` constants belong to OTOY's Octane plugin (not Maxon) and need
verification against the installed Octane build before they will produce
any effect.

## Creating an LS-Cam

1. Open or create a scene.
2. Run **Extensions → Create LS-Cam**. The first invocation:
   - Creates `LS-Cam_Rig` (null) at the world origin.
   - Adds three children under the rig:
     - `LS-Cam_Camera` (camera, set as the active scene camera).
     - `LS-Cam_ForwardLight` (spot light pointing along -Z).
     - `LS-Cam_Controller` (null with the LS-Cam parameters as User Data).
   - Attaches a self-contained Python Tag named `LS-Cam Auto Update` to
     the controller so live edits and timeline scrubbing re-drive the
     camera and light every expression pass.
3. Subsequent invocations are *create-or-update*: an existing rig is
   re-driven from the current User Data and the auto-update tag is
   refreshed if needed.

### `LS-Cam_Controller` User Data

| Parameter                | Type        | Range / Default                                |
| ------------------------ | ----------- | ---------------------------------------------- |
| Enable LS-Cam Effect     | bool        | True                                           |
| Beta v/c                 | slider      | 0.0 – 0.999, default 0.0                       |
| Aberration Strength      | slider      | 0.0 – 2.0, default 1.0                         |
| Doppler Strength         | slider      | 0.0 – 2.0, default 1.0                         |
| Searchlight Strength     | slider      | 0.0 – 5.0, default 1.0                         |
| Exposure Compensation    | slider      | -5.0 – 5.0, default 0.0                        |
| DOF Compensation         | slider      | 0.0 – 2.0, default 1.0                         |
| Aperture Compensation    | slider      | 0.0 – 2.0, default 1.0                         |
| Direction Mode           | dropdown    | Camera Forward / Custom Vector / Target Object |
| Custom Direction Vector  | vector      | (0, 0, -1)                                     |
| Target Object Link       | object link | none                                           |

`Camera Forward` is the default direction mode and reproduces the
out-of-the-box visual behaviour.

## What `Beta v/c` means

`beta = v / c` is the dimensionless ratio of the rig's velocity to the
speed of light. It is the master input for every relativistic factor:

- `gamma = 1 / sqrt(1 - beta^2)` is the Lorentz factor.
- Forward aberration narrows the FOV by `sqrt((1 - beta) / (1 + beta))`,
  raised to the aberration strength.
- The forward Doppler factor `D = sqrt((1 + beta) / (1 - beta))` drives
  the visible blueshift, scales relativistic beaming intensity, and folds
  into the Octane imager exposure.
- DOF and aperture are nudged by `1 + strength * beta**2` so the rig
  retains usable photographic behaviour even at very high beta.

Beta is clamped to `[0.0, 0.999]` before any `sqrt` to avoid the
singularity at `beta = 1`. Every output factor is clamped to a safe
artistic range so a runaway slider cannot destroy the scene.

## Caveats: physically inspired, not physically exact

This plugin **does not** ray-trace special-relativistic light cones. It
derives a few scalar / colour factors from `beta` and multiplies them
into existing camera and light parameters. The result is a fast,
art-directable approximation that captures the *qualitative* feel of
relativistic optics (FOV narrowing, blueshift, forward beaming, exposure
response), but it is not a substitute for a true relativistic renderer.
A genuine implementation would need per-pixel four-velocity transforms
and spectral integration, which is out of scope for this plugin.

## Octane support

When Octane Render is installed, the menu command:

- Detects Octane via `import c4doctane`, then via
  `c4d.plugins.FindPlugin` against the isolated `OCTANE_VIDEOPOST_ID` and
  `OCTANE_CAMERA_TAG_ID` constants.
- Idempotently attaches an Octane Camera Tag to `LS-Cam_Camera` if one is
  missing.
- Pushes aperture, focus distance, and combined exposure / beaming into
  the tag through `safe_set_octane_param`, which validates the DescID
  before writing.

### Limitations

- The Octane Camera Tag *parameter* IDs (`OCTANE_CAM_APERTURE`,
  `OCTANE_CAM_FOCAL_DEPTH`, `OCTANE_CAM_AUTO_FOCUS`,
  `OCTANE_CAM_EXPOSURE`) default to `None` (disabled). They belong to
  OTOY's schema and are not published as a stable mapping; fill them in
  for your Octane build by inspecting an existing Octane Camera Tag.
  Until they are filled in the bridge is a clean no-op.
- Octane imager parameters (gamma, response curve, white balance) are
  not yet driven – only the camera tag.
- The Python Tag updates the standard C4D camera/light every expression
  pass; the Octane bridge currently runs only when the menu command is
  re-invoked.

## Debugging

Set `LSCAM_DEBUG = True` near the top of `C4D_ls-cam/C4D_ls-cam.pyp` to
get verbose console output:

- A sanity table of helper outputs at `beta = 0.0, 0.5, 0.9, 0.999` when
  the rig is created.
- A per-click factor breakdown (FOV factor, intensity, RGB tint,
  aperture factor, DOF factor, exposure).
- One line per skipped Octane / camera / light parameter explaining why.

Default mode prints only the per-click `beta`/`gamma` summary plus the
operational status (rig created/updated, Octane detected/not detected,
Octane Camera Tag ready).

## Troubleshooting

- **Command does not appear in the Extensions menu.** Check the plugin
  folder is at `<C4D prefs>/plugins/C4D_ls-cam/C4D_ls-cam.pyp`. Open the
  Cinema 4D Console and look for plugin load errors.
- **`PLUGIN_ID` collision.** Replace `PLUGIN_ID = 1000001` with your
  registered Plugin Café ID.
- **Rig builds but Octane parameters do nothing.** The
  `OCTANE_CAM_*` constants are `None` by default. Fill them in for your
  Octane build, then set `LSCAM_DEBUG = True` to see which IDs are being
  skipped.
- **Camera looks normal at high beta.** The *Enable LS-Cam Effect*
  toggle may be off, or the strength sliders may be at zero. Check the
  controller.
- **Light does not re-aim when changing Direction Mode.** Make sure the
  controller has the auto-update Python Tag (`LS-Cam Auto Update`).
  Re-running the command refreshes it.
- **Editing User Data does nothing live.** The Python Tag runs in the
  expression pass; trigger an evaluation by scrubbing the timeline. If
  the tag is missing, run *Create LS-Cam* again to install it.
- **Saved scene works without the plugin.** That is by design – the
  Python Tag's source is bundled into the scene.

## Roadmap (v2)

- **True shader / node spectral shift.** Replace the scalar light tint
  with a per-pixel relativistic shading pass driven by a node-graph
  spectral-shift shader.
- **Octane imager support.** Drive white balance, gamma, response curve,
  and dynamic exposure on the Octane imager alongside the camera tag.
- **Redshift Render integration.** A parallel bridge for Redshift's
  camera / imager parameters.
- **Starfield streak mode.** Stretch small bright sources along the
  motion vector for the classic "warp" feel.
- **Viewport overlay (HUD).** Real-time on-screen readout of `beta`,
  `gamma`, and the resolved direction-mode vector.

## License

Add your preferred license here before distributing.
