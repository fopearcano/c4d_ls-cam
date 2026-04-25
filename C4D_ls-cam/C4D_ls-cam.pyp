"""C4D_ls-cam - Cinema 4D plugin.

Step 4: in addition to building the rig and User Data, this module now
exposes a set of pure helper functions that turn ``beta = v/c`` into
artistic factors for FOV, exposure / light intensity, colour tint,
aperture, and depth-of-field.  Nothing is yet wired into the camera -
the helpers are dependency-free and safely callable at any time.

Hierarchy created::

    LS-Cam_Rig                (Null)
        LS-Cam_Camera         (Camera, active scene camera)
        LS-Cam_ForwardLight   (Light, default forward orientation)
        LS-Cam_Controller     (Null with LS-Cam User Data parameters)

LS-Cam_Controller User Data:

    Enable LS-Cam Effect    bool, default True
    Beta v/c                float slider, 0.0 .. 0.999, default 0.0
    Aberration Strength     float slider, 0.0 .. 2.0,   default 1.0
    Doppler Strength        float slider, 0.0 .. 2.0,   default 1.0
    Searchlight Strength    float slider, 0.0 .. 5.0,   default 1.0
    Exposure Compensation   float slider, -5.0 .. 5.0,  default 0.0
    DOF Compensation        float slider, 0.0 .. 2.0,   default 1.0
    Aperture Compensation   float slider, 0.0 .. 2.0,   default 1.0

No camera math, no Octane integration yet.

Target: Cinema 4D 2023.2 (Python API).
Reference: https://developers.maxon.net/docs/py/2023_2/manuals/index.html
Reference: https://developers.maxon.net/docs/py/2023_2/misc/pluginstructure.html

Place this folder inside Cinema 4D's `plugins/` directory:
    <C4D install or prefs>/plugins/C4D_ls-cam/C4D_ls-cam.pyp
"""

import math

import c4d

# Placeholder Plugin ID. MUST be replaced with an official ID obtained from
# the Maxon Plugin Cafe (https://plugincafe.maxon.net/) before public release.
# Using an unregistered ID risks collisions with other plugins.
PLUGIN_ID = 1000001

PLUGIN_NAME = "Create LS-Cam"
PLUGIN_HELP = "Create the LS-Cam rig (Rig / Camera / ForwardLight / Controller)."

# Object names - kept as constants so later steps can reference the rig
# reliably without depending on hard-coded string literals scattered around.
NAME_RIG = "LS-Cam_Rig"
NAME_CAMERA = "LS-Cam_Camera"
NAME_LIGHT = "LS-Cam_ForwardLight"
NAME_CONTROLLER = "LS-Cam_Controller"

# User Data parameter keys. The string value is also the visible label in
# Cinema 4D, so future code can locate a UD entry by iterating
# ``controller.GetUserDataContainer()`` and matching ``DESC_NAME``.
UD_ENABLE = "Enable LS-Cam Effect"
UD_BETA = "Beta v/c"
UD_ABERRATION = "Aberration Strength"
UD_DOPPLER = "Doppler Strength"
UD_SEARCHLIGHT = "Searchlight Strength"
UD_EXPOSURE = "Exposure Compensation"
UD_DOF = "DOF Compensation"
UD_APERTURE = "Aperture Compensation"


# ---------------------------------------------------------------------------
# Physically inspired relativistic helpers
# ---------------------------------------------------------------------------
# These functions approximate the QUALITATIVE behaviour of relativistic
# optical effects (Lorentz factor, aberration, Doppler shift, beaming) for
# an artistic camera.  They are NOT a full special/general relativistic
# renderer - they return scalar/colour factors that downstream code can
# multiply into existing camera parameters.  Inputs are guarded against
# the divide-by-zero singularity at beta = 1, and outputs are clamped to
# safe artistic ranges so a runaway parameter cannot blow up the scene.

# Hard limits on beta.  A true 1.0 makes gamma diverge, so we clamp just
# below it; users can still expose 0.999 in the UI.
BETA_MIN = 0.0
BETA_MAX = 0.999


def clamp(value, min_value, max_value):
    """Return *value* limited to the inclusive ``[min_value, max_value]`` range."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def beta_to_gamma(beta):
    """Lorentz factor: ``gamma = 1 / sqrt(1 - beta**2)``.

    Beta is clamped to ``[BETA_MIN, BETA_MAX]`` first so the square root
    never sees a zero or negative argument.
    """
    b = clamp(beta, BETA_MIN, BETA_MAX)
    return 1.0 / math.sqrt(1.0 - b * b)


def _forward_doppler(beta):
    """Forward Doppler factor ``D = sqrt((1+beta)/(1-beta))`` (D >= 1)."""
    b = clamp(beta, BETA_MIN, BETA_MAX)
    return math.sqrt((1.0 + b) / (1.0 - b))


def beta_to_fov_factor(beta, aberration_strength):
    """Forward field-of-view multiplier (relativistic aberration).

    Classical aberration narrows the forward FOV by
    ``sqrt((1 - beta) / (1 + beta))``.  ``aberration_strength`` of 0
    disables the effect, 1 reproduces the classical value, and >1
    exaggerates it artistically (the base factor is raised to that
    power).  Clamped to ``[0.05, 1.0]`` so the FOV never collapses to a
    pinhole or grows above the rest-frame value.
    """
    b = clamp(beta, BETA_MIN, BETA_MAX)
    s = clamp(aberration_strength, 0.0, 4.0)
    base = math.sqrt((1.0 - b) / (1.0 + b))
    return clamp(base ** s, 0.05, 1.0)


def beta_to_light_intensity(beta, searchlight_strength):
    """Forward intensity multiplier (relativistic 'searchlight' beaming).

    A bolometric beaming exponent in flat space is 4; we expose it as
    ``searchlight_strength`` so artists can dial it back for stable
    exposure.  Output is clamped to a generous but finite range to
    protect tone-mapping downstream.
    """
    s = clamp(searchlight_strength, 0.0, 5.0)
    factor = _forward_doppler(beta) ** s
    return clamp(factor, 0.0, 1.0e6)


def beta_to_doppler_color(beta, doppler_strength):
    """Forward colour-tint ``(r, g, b)`` multiplier from Doppler blueshift.

    At ``beta = 0`` the tint is neutral white.  As beta grows, the
    forward Doppler factor pushes the visible spectrum toward the blue,
    so red falls off and blue lifts slightly.  ``doppler_strength``
    scales the aggressiveness of the tint; components are clamped to
    safe display ranges.
    """
    s = clamp(doppler_strength, 0.0, 2.0)
    D = _forward_doppler(beta)
    shift = s * (D - 1.0) / D            # in [0, s)
    r = clamp(1.0 - shift, 0.0, 1.0)
    g = clamp(1.0 - shift * 0.5, 0.0, 1.0)
    b = clamp(1.0 + shift * 0.3, 1.0, 2.0)
    return (r, g, b)


def beta_to_aperture_factor(beta, aperture_strength):
    """f-number compensation multiplier.

    As beaming grows, the effective scene gets brighter; the natural
    photographic response is to close the aperture (raise f-number).
    The curve is purely artistic (linear in ``beta**2``) and clamped to
    ``[0.1, 8.0]`` to keep the camera usable.
    """
    b = clamp(beta, BETA_MIN, BETA_MAX)
    s = clamp(aperture_strength, 0.0, 2.0)
    return clamp(1.0 + s * b * b, 0.1, 8.0)


def beta_to_dof_factor(beta, dof_strength):
    """Depth-of-field range multiplier.

    A purely artistic ``beta**2`` curve so DOF stretches as the rig
    accelerates; downstream code can multiply this into the focus
    distance or DOF range.  Clamped to ``[0.1, 8.0]``.
    """
    b = clamp(beta, BETA_MIN, BETA_MAX)
    s = clamp(dof_strength, 0.0, 2.0)
    return clamp(1.0 + s * b * b, 0.1, 8.0)


def _debug_dump_helpers():
    """Print a sanity table of helper outputs at canonical beta values."""
    print("LS-Cam helper sanity check (strengths = 1.0):")
    for b in (0.0, 0.5, 0.9, 0.999):
        gamma = beta_to_gamma(b)
        fov = beta_to_fov_factor(b, 1.0)
        intensity = beta_to_light_intensity(b, 1.0)
        rgb = beta_to_doppler_color(b, 1.0)
        ap = beta_to_aperture_factor(b, 1.0)
        dof = beta_to_dof_factor(b, 1.0)
        print(
            "  beta=%.3f  gamma=%.3f  fov=%.4f  I=%.3f"
            "  rgb=(%.3f, %.3f, %.3f)  ap=%.3f  dof=%.3f"
            % (b, gamma, fov, intensity, rgb[0], rgb[1], rgb[2], ap, dof)
        )


# ---------------------------------------------------------------------------
# Object / User Data helpers
# ---------------------------------------------------------------------------


def _make_named(obj_type, name):
    obj = c4d.BaseObject(obj_type)
    if obj is None:
        raise MemoryError("Failed to allocate BaseObject of type %d" % obj_type)
    obj.SetName(name)
    return obj


def _add_bool_userdata(obj, name, default):
    """Add a checkbox User Data entry; returns its DescID."""
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_BOOL)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_DEFAULT] = bool(default)
    bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_ON
    desc_id = obj.AddUserData(bc)
    obj[desc_id] = bool(default)
    return desc_id


def _add_real_slider_userdata(obj, name, default, vmin, vmax, step):
    """Add a REAL slider User Data entry; returns its DescID."""
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_REAL)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_DEFAULT] = float(default)
    bc[c4d.DESC_MIN] = float(vmin)
    bc[c4d.DESC_MAX] = float(vmax)
    bc[c4d.DESC_MINSLIDER] = float(vmin)
    bc[c4d.DESC_MAXSLIDER] = float(vmax)
    bc[c4d.DESC_STEP] = float(step)
    bc[c4d.DESC_UNIT] = c4d.DESC_UNIT_FLOAT
    bc[c4d.DESC_CUSTOMGUI] = c4d.CUSTOMGUI_REALSLIDER
    bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_ON
    desc_id = obj.AddUserData(bc)
    obj[desc_id] = float(default)
    return desc_id


def _setup_controller_userdata(controller):
    """Populate LS-Cam_Controller with all LS-Cam parameters.

    Returns a ``{label: DescID}`` dict so the caller can immediately
    address the new entries; later steps can rebuild the same mapping
    from the controller via :func:`get_userdata_ids`.
    """
    ids = {}
    ids[UD_ENABLE] = _add_bool_userdata(
        controller, UD_ENABLE, default=True)
    ids[UD_BETA] = _add_real_slider_userdata(
        controller, UD_BETA, default=0.0, vmin=0.0, vmax=0.999, step=0.001)
    ids[UD_ABERRATION] = _add_real_slider_userdata(
        controller, UD_ABERRATION, default=1.0, vmin=0.0, vmax=2.0, step=0.01)
    ids[UD_DOPPLER] = _add_real_slider_userdata(
        controller, UD_DOPPLER, default=1.0, vmin=0.0, vmax=2.0, step=0.01)
    ids[UD_SEARCHLIGHT] = _add_real_slider_userdata(
        controller, UD_SEARCHLIGHT, default=1.0, vmin=0.0, vmax=5.0, step=0.01)
    ids[UD_EXPOSURE] = _add_real_slider_userdata(
        controller, UD_EXPOSURE, default=0.0, vmin=-5.0, vmax=5.0, step=0.01)
    ids[UD_DOF] = _add_real_slider_userdata(
        controller, UD_DOF, default=1.0, vmin=0.0, vmax=2.0, step=0.01)
    ids[UD_APERTURE] = _add_real_slider_userdata(
        controller, UD_APERTURE, default=1.0, vmin=0.0, vmax=2.0, step=0.01)
    return ids


def find_rig(doc):
    """Return the top-level LS-Cam_Rig object in *doc* or None."""
    if doc is None:
        return None
    obj = doc.GetFirstObject()
    while obj is not None:
        if obj.GetName() == NAME_RIG:
            return obj
        obj = obj.GetNext()
    return None


def find_rig_child(rig, name):
    """Return the immediate child of *rig* with *name*, or None."""
    if rig is None:
        return None
    child = rig.GetDown()
    while child is not None:
        if child.GetName() == name:
            return child
        child = child.GetNext()
    return None


def get_userdata_ids(controller):
    """Map ``DESC_NAME`` to its DescID for every User Data entry on *controller*.

    Lets later steps recover the IDs without having stored them at creation
    time; the labels in :data:`UD_*` constants are the lookup keys.
    """
    ids = {}
    if controller is None:
        return ids
    for desc_id, bc in controller.GetUserDataContainer():
        ids[bc[c4d.DESC_NAME]] = desc_id
    return ids


class CreateLSCamCommand(c4d.plugins.CommandData):
    """CommandData plugin invoked from the Cinema 4D Extensions menu."""

    def Execute(self, doc):
        if doc is None:
            return False

        rig = _make_named(c4d.Onull, NAME_RIG)
        camera = _make_named(c4d.Ocamera, NAME_CAMERA)
        light = _make_named(c4d.Olight, NAME_LIGHT)
        controller = _make_named(c4d.Onull, NAME_CONTROLLER)

        # Camera at world origin, default orientation (looking down -Z).
        camera.SetAbsPos(c4d.Vector(0.0, 0.0, 0.0))
        camera.SetAbsRot(c4d.Vector(0.0, 0.0, 0.0))

        # Spot-style light gives the rig an obvious forward cone along -Z;
        # it inherits the camera-forward axis when parented to the rig.
        light[c4d.LIGHT_TYPE] = c4d.LIGHT_TYPE_SPOT

        # Add User Data BEFORE inserting the controller so a single
        # UNDOTYPE_NEW captures the object and all of its parameters.
        _setup_controller_userdata(controller)

        doc.StartUndo()
        try:
            # Insert the parent first so children land inside the rig branch.
            doc.InsertObject(rig)
            doc.AddUndo(c4d.UNDOTYPE_NEW, rig)

            for child in (camera, light, controller):
                child.InsertUnder(rig)
                doc.AddUndo(c4d.UNDOTYPE_NEW, child)

            # Promote the new camera to the active scene camera so the
            # viewport switches to it immediately.
            base_draw = doc.GetActiveBaseDraw()
            if base_draw is not None:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, base_draw)
                base_draw.SetSceneCamera(camera)

            doc.SetActiveObject(rig, c4d.SELECTION_NEW)
        finally:
            doc.EndUndo()

        c4d.EventAdd()
        print("C4D_ls-cam loaded and command executed")
        _debug_dump_helpers()
        return True


def register():
    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        help=PLUGIN_HELP,
        dat=CreateLSCamCommand(),
        icon=None,
    )


if __name__ == "__main__":
    register()
