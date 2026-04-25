"""C4D_ls-cam - Cinema 4D plugin.

A small CommandData plugin that builds a relativistic ("LS-Cam")
rig in the active document and drives a standard C4D camera + a
spot light from a single ``beta = v/c`` slider, with optional
Octane bridging.  See README.md for a full description, installation
notes, and the v2 roadmap.

Verbose console output is gated behind the :data:`LSCAM_DEBUG`
module-level flag; flip it to True to see the helper sanity table,
the per-click factor breakdown, and per-parameter skip reasons.

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
UD_DIRECTION_MODE = "Direction Mode"
UD_CUSTOM_VECTOR = "Custom Direction Vector"
UD_TARGET_LINK = "Target Object Link"

# Cycle values for the Direction Mode dropdown.  Stored as the integer
# values of the UD CYCLE entries; resolve_direction() switches on these.
# Camera Forward is the default and matches the rig's prior visual
# behaviour, so existing scenes look the same.
DIR_MODE_CAMERA_FORWARD = 0
DIR_MODE_CUSTOM_VECTOR = 1
DIR_MODE_TARGET_OBJECT = 2

# Rest-frame (beta = 0) reference values applied to the camera and light.
# Every per-click apply pass re-derives the live values from these bases
# multiplied by the helper factors, so the parameters never drift across
# repeated invocations or animated User Data.
BASE_FOV_RAD = math.radians(54.0)            # ~ 36 mm focal length, 36 mm sensor
BASE_FOV_VERTICAL_RAD = math.radians(32.0)
BASE_FNUMBER = 8.0
BASE_TARGETDISTANCE = 200.0                  # cm; C4D's default scene unit
BASE_LIGHT_BRIGHTNESS = 1.0

# Python Tag name. The tag is hosted on LS-Cam_Controller and re-runs
# the camera/light derivation on every expression pass.
PYTHON_TAG_NAME = "LS-Cam Auto Update"

# Source code installed into the Python Tag.  Kept fully self-contained
# (no import of this plugin) so saved scenes work even if the plugin
# is uninstalled or deactivated.  Touches only the camera and forward
# light siblings - never writes back to the controller - so the tag
# cannot trigger an evaluation loop on itself.
PYTHON_TAG_SOURCE = '''"""LS-Cam auto-update Python Tag (embedded by C4D_ls-cam plugin).

Reads User Data on the host (LS-Cam_Controller) every expression pass
and rewrites the standard Cinema 4D parameters of the sibling camera
and forward light.  This is a trimmed copy of the math that lives in
C4D_ls-cam.pyp; keep them in sync.
"""

import math
import c4d


NAME_CAMERA = "LS-Cam_Camera"
NAME_LIGHT = "LS-Cam_ForwardLight"

UD_ENABLE = "Enable LS-Cam Effect"
UD_BETA = "Beta v/c"
UD_ABERRATION = "Aberration Strength"
UD_DOPPLER = "Doppler Strength"
UD_SEARCHLIGHT = "Searchlight Strength"
UD_EXPOSURE = "Exposure Compensation"
UD_DOF = "DOF Compensation"
UD_APERTURE = "Aperture Compensation"
UD_DIRECTION_MODE = "Direction Mode"
UD_CUSTOM_VECTOR = "Custom Direction Vector"
UD_TARGET_LINK = "Target Object Link"

DIR_MODE_CAMERA_FORWARD = 0
DIR_MODE_CUSTOM_VECTOR = 1
DIR_MODE_TARGET_OBJECT = 2

BETA_MIN = 0.0
BETA_MAX = 0.999
BASE_FOV_RAD = math.radians(54.0)
BASE_FOV_VERTICAL_RAD = math.radians(32.0)
BASE_FNUMBER = 8.0
BASE_TARGETDISTANCE = 200.0
BASE_LIGHT_BRIGHTNESS = 1.0


def _clamp(v, a, b):
    return a if v < a else b if v > b else v


def _D(beta):
    b = _clamp(beta, BETA_MIN, BETA_MAX)
    return math.sqrt((1.0 + b) / (1.0 - b))


def _gamma(beta):
    b = _clamp(beta, BETA_MIN, BETA_MAX)
    return 1.0 / math.sqrt(1.0 - b * b)


def _fov_factor(beta, s):
    b = _clamp(beta, BETA_MIN, BETA_MAX)
    s = _clamp(s, 0.0, 4.0)
    return _clamp(math.sqrt((1.0 - b) / (1.0 + b)) ** s, 0.05, 1.0)


def _intensity(beta, s):
    return _clamp(_D(beta) ** _clamp(s, 0.0, 5.0), 0.0, 1.0e6)


def _doppler_color(beta, s):
    s = _clamp(s, 0.0, 2.0)
    D = _D(beta)
    sh = s * (D - 1.0) / D
    return (_clamp(1.0 - sh, 0.0, 1.0),
            _clamp(1.0 - sh * 0.5, 0.0, 1.0),
            _clamp(1.0 + sh * 0.3, 1.0, 2.0))


def _aperture_factor(beta, s):
    b = _clamp(beta, BETA_MIN, BETA_MAX)
    s = _clamp(s, 0.0, 2.0)
    return _clamp(1.0 + s * b * b, 0.1, 8.0)


def _dof_factor(beta, s):
    b = _clamp(beta, BETA_MIN, BETA_MAX)
    s = _clamp(s, 0.0, 2.0)
    return _clamp(1.0 + s * b * b, 0.1, 8.0)


def _safe_set(o, attr_name, value):
    if o is None:
        return
    pid = getattr(c4d, attr_name, None)
    if pid is None:
        return
    try:
        o[pid] = value
    except Exception:
        pass


def _sibling(parent, name):
    if parent is None:
        return None
    c = parent.GetDown()
    while c is not None:
        if c.GetName() == name:
            return c
        c = c.GetNext()
    return None


def _read_ud(ctrl, label, default):
    if ctrl is None:
        return default
    for did, bc in ctrl.GetUserDataContainer():
        if bc[c4d.DESC_NAME] == label:
            try:
                v = ctrl[did]
            except Exception:
                return default
            return default if v is None else v
    return default


def main():
    controller = op.GetObject()
    if controller is None:
        return
    rig = controller.GetUp()
    if rig is None:
        return
    camera = _sibling(rig, NAME_CAMERA)
    light = _sibling(rig, NAME_LIGHT)

    enabled = bool(_read_ud(controller, UD_ENABLE, True))
    beta = float(_read_ud(controller, UD_BETA, 0.0))
    if not enabled:
        beta = 0.0

    fov_f = _fov_factor(beta, float(_read_ud(controller, UD_ABERRATION, 1.0)))
    rgb = _doppler_color(beta, float(_read_ud(controller, UD_DOPPLER, 1.0)))
    intensity = _intensity(beta, float(_read_ud(controller, UD_SEARCHLIGHT, 1.0)))
    aper_f = _aperture_factor(beta, float(_read_ud(controller, UD_APERTURE, 1.0)))
    dof_f = _dof_factor(beta, float(_read_ud(controller, UD_DOF, 1.0)))
    expmult = 2.0 ** _clamp(float(_read_ud(controller, UD_EXPOSURE, 0.0)),
                            -10.0, 10.0)

    if camera is not None:
        _safe_set(camera, "CAMERAOBJECT_FOV", BASE_FOV_RAD * fov_f)
        _safe_set(camera, "CAMERAOBJECT_FOV_VERTICAL",
                  BASE_FOV_VERTICAL_RAD * fov_f)
        _safe_set(camera, "CAMERAOBJECT_FNUMBER_VALUE", BASE_FNUMBER * aper_f)
        _safe_set(camera, "CAMERAOBJECT_TARGETDISTANCE",
                  BASE_TARGETDISTANCE * dof_f)
        _safe_set(camera, "CAMERAOBJECT_DOF", True)

    if light is not None:
        _safe_set(light, "LIGHT_COLOR", c4d.Vector(rgb[0], rgb[1], rgb[2]))
        _safe_set(light, "LIGHT_BRIGHTNESS",
                  BASE_LIGHT_BRIGHTNESS * intensity * expmult)
        _orient_light(light, _resolve_direction(controller, camera))


def _resolve_direction(controller, camera):
    mode = int(_read_ud(controller, UD_DIRECTION_MODE,
                        DIR_MODE_CAMERA_FORWARD))
    if mode == DIR_MODE_CUSTOM_VECTOR:
        v = _read_ud(controller, UD_CUSTOM_VECTOR, None)
        if v is None or v.GetLength() < 1.0e-9:
            return None
        return v.GetNormalized()
    if mode == DIR_MODE_TARGET_OBJECT and camera is not None:
        target = _read_ud(controller, UD_TARGET_LINK, None)
        if target is not None:
            try:
                d = target.GetMg().off - camera.GetMg().off
            except Exception:
                d = None
            if d is not None and d.GetLength() > 1.0e-9:
                return d.GetNormalized()
    if camera is not None:
        try:
            f = -camera.GetMg().v3
        except Exception:
            f = None
        if f is not None and f.GetLength() > 1.0e-9:
            return f.GetNormalized()
    return None


def _orient_light(light, direction):
    if light is None or direction is None:
        return
    if direction.GetLength() < 1.0e-9:
        return
    fwd = direction.GetNormalized()
    up = c4d.Vector(0.0, 1.0, 0.0)
    if abs(fwd.y) > 0.99:
        up = c4d.Vector(0.0, 0.0, 1.0)
    z = -fwd
    x = up.Cross(z)
    if x.GetLength() < 1.0e-9:
        x = c4d.Vector(1.0, 0.0, 0.0)
    x = x.GetNormalized()
    y = z.Cross(x).GetNormalized()
    m = light.GetMg()
    m.v1 = x
    m.v2 = y
    m.v3 = z
    light.SetMg(m)
'''


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


def _add_cycle_userdata(obj, name, options, default):
    """Add a CYCLE (dropdown) User Data entry; returns its DescID.

    *options* is an iterable of ``(int_value, label)`` pairs.
    """
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_LONG)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_CUSTOMGUI] = c4d.CUSTOMGUI_CYCLE
    cycle = c4d.BaseContainer()
    for value, label in options:
        cycle[int(value)] = str(label)
    bc[c4d.DESC_CYCLE] = cycle
    bc[c4d.DESC_DEFAULT] = int(default)
    bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_ON
    desc_id = obj.AddUserData(bc)
    obj[desc_id] = int(default)
    return desc_id


def _add_vector_userdata(obj, name, default):
    """Add a 3-component VECTOR User Data entry; returns its DescID."""
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_VECTOR)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_DEFAULT] = default
    bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_ON
    desc_id = obj.AddUserData(bc)
    obj[desc_id] = default
    return desc_id


def _add_link_userdata(obj, name):
    """Add a BaseList2D link (object picker) User Data entry; returns its DescID."""
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_BASELISTLINK)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_OFF
    return obj.AddUserData(bc)


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
    ids[UD_DIRECTION_MODE] = _add_cycle_userdata(
        controller, UD_DIRECTION_MODE,
        options=((DIR_MODE_CAMERA_FORWARD, "Camera Forward"),
                 (DIR_MODE_CUSTOM_VECTOR, "Custom Vector"),
                 (DIR_MODE_TARGET_OBJECT, "Target Object")),
        default=DIR_MODE_CAMERA_FORWARD)
    ids[UD_CUSTOM_VECTOR] = _add_vector_userdata(
        controller, UD_CUSTOM_VECTOR, default=c4d.Vector(0.0, 0.0, -1.0))
    ids[UD_TARGET_LINK] = _add_link_userdata(controller, UD_TARGET_LINK)
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


# ---------------------------------------------------------------------------
# Direction modes (Camera Forward / Custom Vector / Target Object)
# ---------------------------------------------------------------------------


def resolve_direction(camera, controller):
    """Return the world-space direction selected by the controller's UD.

    * Camera Forward - camera's local -Z transformed to world.
    * Custom Vector  - the user vector (treated as world space).
    * Target Object  - normalized vector from camera origin to the
      linked object's origin.

    Returns a normalized :class:`c4d.Vector`, or ``None`` when no
    valid direction can be derived (so the caller can leave the
    light's orientation untouched and preserve the prior look).
    """
    if controller is None:
        return None
    ids = get_userdata_ids(controller)
    mode = int(_read_ud(controller, ids,
                        UD_DIRECTION_MODE, DIR_MODE_CAMERA_FORWARD))

    if mode == DIR_MODE_CUSTOM_VECTOR:
        v = _read_ud(controller, ids, UD_CUSTOM_VECTOR, None)
        if v is None or v.GetLength() < 1.0e-9:
            return None
        return v.GetNormalized()

    if mode == DIR_MODE_TARGET_OBJECT and camera is not None:
        target = _read_ud(controller, ids, UD_TARGET_LINK, None)
        if target is not None:
            try:
                delta = target.GetMg().off - camera.GetMg().off
            except Exception:
                delta = None
            if delta is not None and delta.GetLength() > 1.0e-9:
                return delta.GetNormalized()
        # Linked target missing or coincident; fall through to camera-forward.

    if camera is not None:
        try:
            forward_world = -camera.GetMg().v3
        except Exception:
            forward_world = None
        if forward_world is not None and forward_world.GetLength() > 1.0e-9:
            return forward_world.GetNormalized()
    return None


def orient_light_along(light, direction):
    """Rotate *light* so its local -Z axis points along world *direction*.

    Translation is preserved by reusing the current world matrix's
    ``off`` field; only the rotation columns are rewritten.  An
    almost-vertical *direction* falls back to a different up vector to
    avoid a degenerate cross product.  No-op for ``None`` /
    zero-length input.
    """
    if light is None or direction is None:
        return
    if direction.GetLength() < 1.0e-9:
        return
    fwd = direction.GetNormalized()
    up = c4d.Vector(0.0, 1.0, 0.0)
    if abs(fwd.y) > 0.99:
        up = c4d.Vector(0.0, 0.0, 1.0)
    z_axis = -fwd                              # local +Z = -direction
    x_axis = up.Cross(z_axis)
    if x_axis.GetLength() < 1.0e-9:
        x_axis = c4d.Vector(1.0, 0.0, 0.0)
    x_axis = x_axis.GetNormalized()
    y_axis = z_axis.Cross(x_axis).GetNormalized()
    m = light.GetMg()
    m.v1 = x_axis
    m.v2 = y_axis
    m.v3 = z_axis
    light.SetMg(m)


# ---------------------------------------------------------------------------
# Apply LS-Cam User Data to the standard C4D camera + forward light
# ---------------------------------------------------------------------------


def _safe_set(obj, attr_name, value):
    """Assign ``obj[c4d.<attr_name>] = value`` if the constant exists.

    The Python API exposes camera/light parameters as module-level
    constants whose presence varies across C4D versions.  Looking them
    up via :func:`getattr` and wrapping the assignment in try/except
    keeps the apply pass crash-free on parameters this build of C4D
    does not know about.
    """
    if obj is None:
        return False
    pid = getattr(c4d, attr_name, None)
    if pid is None:
        return False
    try:
        obj[pid] = value
        return True
    except Exception as ex:
        if LSCAM_DEBUG:
            print("LS-Cam: skipped %s (%s)" % (attr_name, ex))
        return False


def _read_ud(controller, ids, label, default):
    """Return controller[ids[label]] or *default* if the entry is missing."""
    desc_id = ids.get(label)
    if desc_id is None:
        return default
    try:
        value = controller[desc_id]
    except Exception:
        return default
    return default if value is None else value


def apply_lscam_effect(doc, camera, light, controller):
    """Drive *camera* and *light* from *controller*'s User Data.

    Reads the LS-Cam parameters, computes the helper factors, then
    writes them into standard Cinema 4D camera / light parameters
    inside an undo-able block.  Skips silently on missing parameter
    IDs so a partial mapping never crashes the command.
    """
    if controller is None:
        return None

    ids = get_userdata_ids(controller)
    enabled = bool(_read_ud(controller, ids, UD_ENABLE, True))
    beta = float(_read_ud(controller, ids, UD_BETA, 0.0))
    aberration = float(_read_ud(controller, ids, UD_ABERRATION, 1.0))
    doppler = float(_read_ud(controller, ids, UD_DOPPLER, 1.0))
    searchlight = float(_read_ud(controller, ids, UD_SEARCHLIGHT, 1.0))
    exposure = float(_read_ud(controller, ids, UD_EXPOSURE, 0.0))
    dof_strength = float(_read_ud(controller, ids, UD_DOF, 1.0))
    aperture_strength = float(_read_ud(controller, ids, UD_APERTURE, 1.0))

    # When the master toggle is off, pin beta to 0 so every helper
    # collapses to its identity factor and the rig returns to rest.
    if not enabled:
        beta = 0.0

    fov_factor = beta_to_fov_factor(beta, aberration)
    intensity = beta_to_light_intensity(beta, searchlight)
    rgb = beta_to_doppler_color(beta, doppler)
    aperture_f = beta_to_aperture_factor(beta, aperture_strength)
    dof_f = beta_to_dof_factor(beta, dof_strength)
    gamma = beta_to_gamma(beta)
    exposure_mult = 2.0 ** clamp(exposure, -10.0, 10.0)

    if doc is not None:
        doc.StartUndo()
    try:
        if camera is not None:
            if doc is not None:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, camera)
            _safe_set(camera, "CAMERAOBJECT_FOV", BASE_FOV_RAD * fov_factor)
            _safe_set(camera, "CAMERAOBJECT_FOV_VERTICAL",
                      BASE_FOV_VERTICAL_RAD * fov_factor)
            _safe_set(camera, "CAMERAOBJECT_FNUMBER_VALUE",
                      BASE_FNUMBER * aperture_f)
            _safe_set(camera, "CAMERAOBJECT_TARGETDISTANCE",
                      BASE_TARGETDISTANCE * dof_f)
            # Enable Standard-renderer DOF so the f-number actually shows.
            _safe_set(camera, "CAMERAOBJECT_DOF", True)

        if light is not None:
            if doc is not None:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, light)
            _safe_set(light, "LIGHT_COLOR",
                      c4d.Vector(rgb[0], rgb[1], rgb[2]))
            _safe_set(light, "LIGHT_BRIGHTNESS",
                      BASE_LIGHT_BRIGHTNESS * intensity * exposure_mult)
            # Re-aim the light along the controller's selected direction.
            # ``None`` from resolve_direction means "no valid direction";
            # we leave the existing orientation alone in that case so an
            # unconfigured rig keeps its prior look.
            direction = resolve_direction(camera, controller)
            if direction is not None:
                orient_light_along(light, direction)
    finally:
        if doc is not None:
            doc.EndUndo()

    if LSCAM_DEBUG:
        print(
            "LS-Cam apply: enabled=%s beta=%.4f gamma=%.4f"
            " | fov*=%.3f I=%.3f rgb=(%.3f,%.3f,%.3f)"
            " ap*=%.3f dof*=%.3f exp=%+.2f"
            % (enabled, beta, gamma, fov_factor, intensity,
               rgb[0], rgb[1], rgb[2], aperture_f, dof_f, exposure)
        )
    else:
        suffix = "" if enabled else " (effect disabled)"
        print("LS-Cam: beta=%.3f gamma=%.3f%s" % (beta, gamma, suffix))
    return {
        "beta": beta, "gamma": gamma,
        "fov_factor": fov_factor, "intensity": intensity,
        "rgb": rgb, "aperture_factor": aperture_f,
        "dof_factor": dof_f, "exposure": exposure,
    }


def _find_python_tag(obj, tag_name):
    """Return a Python Tag named *tag_name* on *obj*, or None."""
    if obj is None:
        return None
    tag = obj.GetFirstTag()
    while tag is not None:
        if tag.CheckType(c4d.Tpython) and tag.GetName() == tag_name:
            return tag
        tag = tag.GetNext()
    return None


def _ensure_python_tag(controller, doc):
    """Install (or refresh) the LS-Cam auto-update Python Tag.

    Idempotent: if the tag already exists its source is rewritten only
    when it differs from the embedded version.  Adds undo entries
    against *doc* when one is supplied.
    """
    if controller is None:
        return None
    tag = _find_python_tag(controller, PYTHON_TAG_NAME)
    created = False
    if tag is None:
        tag = c4d.BaseTag(c4d.Tpython)
        if tag is None:
            return None
        tag.SetName(PYTHON_TAG_NAME)
        controller.InsertTag(tag)
        if doc is not None:
            doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
        created = True

    code_id = getattr(c4d, "TPYTHON_CODE", None)
    if code_id is not None:
        try:
            current = tag[code_id]
        except Exception:
            current = None
        if current != PYTHON_TAG_SOURCE:
            if doc is not None and not created:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
            tag[code_id] = PYTHON_TAG_SOURCE
    return tag


def _build_new_rig(doc):
    """Create the LS-Cam rig in *doc* and return ``(rig, cam, light, ctrl)``."""
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
        doc.InsertObject(rig)
        doc.AddUndo(c4d.UNDOTYPE_NEW, rig)

        for child in (camera, light, controller):
            child.InsertUnder(rig)
            doc.AddUndo(c4d.UNDOTYPE_NEW, child)

        # Attach the live-update Python Tag once the controller is
        # parented under doc, so its undo entry is captured here.
        _ensure_python_tag(controller, doc)

        # Promote the new camera to the active scene camera so the
        # viewport switches to it immediately.
        base_draw = doc.GetActiveBaseDraw()
        if base_draw is not None:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, base_draw)
            base_draw.SetSceneCamera(camera)

        doc.SetActiveObject(rig, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()

    return rig, camera, light, controller


# ---------------------------------------------------------------------------
# Octane Render presence detection (read-only)
# ---------------------------------------------------------------------------
# Best-effort presence check: tries the c4doctane module first (shipped
# with newer Octane builds), then falls back to looking up known plugin
# IDs.  Each probe is wrapped in try/except so a missing plugin or an
# unfamiliar Octane build never raises.  This step only *detects*; it
# never installs Octane tags or writes Octane parameters.

# Octane plugin IDs are isolated here so they are easy to audit.
# These values have been stable across recent Octane Render Cinema 4D
# releases, but they are NOT defined by Maxon - they belong to OTOY's
# Octane plugin.  VERIFY against the installed Octane build before
# shipping; if either ID changes in a future Octane release, update
# the constant and the detection / tag-installation paths will pick
# the new value up automatically.
OCTANE_VIDEOPOST_ID = 1029525     # Octane Render video post
OCTANE_CAMERA_TAG_ID = 1029524    # Octane Camera Tag (REQUIRES VERIFICATION)

# -----------------------------------------------------------------------------
# Octane Camera Tag PARAMETER IDs.
# -----------------------------------------------------------------------------
# These identify individual fields *inside* the Octane Camera Tag.  They are
# part of OTOY's Octane schema, NOT Maxon's, and OTOY does not publish a
# stable mapping.  Each constant defaults to ``None`` (disabled).  To enable
# a mapping, replace ``None`` with the verified DescID for your installed
# Octane build (inspect an existing Octane Camera Tag via the Cinema 4D
# Python console or attribute manager to confirm).  ``safe_set_octane_param``
# silently skips any ID that is ``None`` or that the tag does not understand,
# so leaving them unset is the safe default.
OCTANE_CAM_APERTURE = None        # f-number / aperture size
OCTANE_CAM_FOCAL_DEPTH = None     # focus distance (cm)
OCTANE_CAM_AUTO_FOCUS = None      # autofocus toggle (bool)
OCTANE_CAM_EXPOSURE = None        # exposure (EV stops or linear, build-dependent)

# Module-level debug switch.  Flip to True while wiring up Octane parameter
# IDs to see one console line per skipped / failed write.  Defaults False so
# normal end-user runs stay quiet.
LSCAM_DEBUG = False


def detect_octane():
    """Return True if Octane Render appears to be installed in this C4D.

    Order of probes:
      1. ``import c4doctane`` - the Python module bundled with current
         Octane builds.
      2. ``c4d.plugins.FindPlugin`` for the Octane video-post renderer.
      3. ``c4d.plugins.FindPlugin`` for the Octane Camera Tag.

    Any probe raising is treated as "absent" and the next probe runs.
    """
    try:
        import c4doctane  # noqa: F401  (presence check only)
        return True
    except Exception:
        pass

    try:
        if c4d.plugins.FindPlugin(OCTANE_VIDEOPOST_ID,
                                  c4d.PLUGINTYPE_VIDEOPOST) is not None:
            return True
    except Exception:
        pass

    try:
        if c4d.plugins.FindPlugin(OCTANE_CAMERA_TAG_ID,
                                  c4d.PLUGINTYPE_TAG) is not None:
            return True
    except Exception:
        pass

    return False


def _find_tag_by_plugin_id(obj, plugin_id):
    """Return the first tag on *obj* whose plugin id matches, or None."""
    if obj is None:
        return None
    tag = obj.GetFirstTag()
    while tag is not None:
        try:
            if tag.GetType() == plugin_id:
                return tag
        except Exception:
            pass
        tag = tag.GetNext()
    return None


def ensure_octane_camera_tag(camera, doc):
    """Attach an Octane Camera Tag to *camera* if Octane is installed.

    Idempotent: returns the existing tag if one is already present.
    Returns None when Octane is not installed, the tag plugin cannot
    be located, or allocation fails - callers should treat that as
    "skip silently" since the user-facing presence message has
    already been emitted by :func:`detect_octane`.

    No Octane parameters are touched here.
    """
    if camera is None:
        return None

    try:
        plug = c4d.plugins.FindPlugin(OCTANE_CAMERA_TAG_ID,
                                      c4d.PLUGINTYPE_TAG)
    except Exception:
        plug = None
    if plug is None:
        return None

    existing = _find_tag_by_plugin_id(camera, OCTANE_CAMERA_TAG_ID)
    if existing is not None:
        return existing

    try:
        tag = c4d.BaseTag(OCTANE_CAMERA_TAG_ID)
    except Exception:
        tag = None
    if tag is None:
        return None

    if doc is not None:
        doc.StartUndo()
    try:
        camera.InsertTag(tag)
        if doc is not None:
            doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
    finally:
        if doc is not None:
            doc.EndUndo()
    return tag


# ---------------------------------------------------------------------------
# Octane parameter bridge (safe, never assumes a DescID is present)
# ---------------------------------------------------------------------------


def safe_set_octane_param(tag, param_id, value):
    """Write *value* to ``tag[param_id]`` if and only if it is safe to do so.

    Returns True on a successful write, False otherwise.  The bridge
    treats every failure mode as "skip silently":

      * ``tag is None``                       - no Octane tag installed
      * ``param_id is None``                  - constant not yet verified
      * the parameter does not exist on the tag (read returns ``None``
        or raises)
      * the assignment itself raises

    When :data:`LSCAM_DEBUG` is True a single console line is emitted
    per skipped attempt so the developer can identify which Octane ID
    needs to be confirmed for the installed build.
    """
    if tag is None:
        if LSCAM_DEBUG:
            print("LS-Cam Octane: skip (no tag)")
        return False
    if param_id is None:
        if LSCAM_DEBUG:
            print("LS-Cam Octane: skip (param id not configured)")
        return False

    # Touch-read to confirm the description actually contains this ID
    # in this Octane build.  c4d returns None for unknown keys.
    try:
        if tag[param_id] is None:
            if LSCAM_DEBUG:
                print("LS-Cam Octane: param %s not present on tag" % (param_id,))
            return False
    except Exception as ex:
        if LSCAM_DEBUG:
            print("LS-Cam Octane: param %s read failed (%s)" % (param_id, ex))
        return False

    try:
        tag[param_id] = value
        return True
    except Exception as ex:
        if LSCAM_DEBUG:
            print("LS-Cam Octane: param %s write failed (%s)"
                  % (param_id, ex))
        return False


def apply_octane_bridge(doc, oct_tag, controller):
    """Push artistic LS-Cam values into the Octane Camera Tag.

    Reads the controller User Data, computes the same factors used for
    the standard C4D camera, and writes them through
    :func:`safe_set_octane_param`.  Any ID still set to ``None`` in the
    OCTANE_CAM_* constants is skipped silently, so the bridge is a
    safe no-op until the developer fills the IDs in.
    """
    if oct_tag is None or controller is None:
        return

    ids = get_userdata_ids(controller)
    enabled = bool(_read_ud(controller, ids, UD_ENABLE, True))
    beta = float(_read_ud(controller, ids, UD_BETA, 0.0))
    if not enabled:
        beta = 0.0

    aperture_strength = float(_read_ud(controller, ids, UD_APERTURE, 1.0))
    dof_strength = float(_read_ud(controller, ids, UD_DOF, 1.0))
    searchlight_strength = float(_read_ud(controller, ids, UD_SEARCHLIGHT, 1.0))
    exposure = float(_read_ud(controller, ids, UD_EXPOSURE, 0.0))

    aperture_f = beta_to_aperture_factor(beta, aperture_strength)
    dof_f = beta_to_dof_factor(beta, dof_strength)
    intensity = beta_to_light_intensity(beta, searchlight_strength)

    # Fold the relativistic beaming intensity into the exposure
    # (in stops) so the Octane imager compensates the same way as the
    # forward light's brightness in the standard pipeline.
    exposure_total = clamp(exposure + math.log2(max(intensity, 1.0e-6)),
                           -10.0, 10.0)

    if doc is not None:
        doc.StartUndo()
        try:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, oct_tag)
            safe_set_octane_param(oct_tag, OCTANE_CAM_APERTURE,
                                  BASE_FNUMBER * aperture_f)
            safe_set_octane_param(oct_tag, OCTANE_CAM_FOCAL_DEPTH,
                                  BASE_TARGETDISTANCE * dof_f)
            safe_set_octane_param(oct_tag, OCTANE_CAM_EXPOSURE,
                                  exposure_total)
        finally:
            doc.EndUndo()
    else:
        safe_set_octane_param(oct_tag, OCTANE_CAM_APERTURE,
                              BASE_FNUMBER * aperture_f)
        safe_set_octane_param(oct_tag, OCTANE_CAM_FOCAL_DEPTH,
                              BASE_TARGETDISTANCE * dof_f)
        safe_set_octane_param(oct_tag, OCTANE_CAM_EXPOSURE, exposure_total)


class CreateLSCamCommand(c4d.plugins.CommandData):
    """CommandData plugin invoked from the Cinema 4D Extensions menu.

    Create-or-update: if the rig is already present its camera and
    light are re-driven from the controller's User Data; otherwise the
    rig is built first and then driven from its defaults.
    """

    def Execute(self, doc):
        if doc is None:
            return False

        rig = find_rig(doc)
        if rig is None:
            rig, camera, light, controller = _build_new_rig(doc)
            print("C4D_ls-cam loaded and command executed (rig created)")
            if LSCAM_DEBUG:
                _debug_dump_helpers()
        else:
            camera = find_rig_child(rig, NAME_CAMERA)
            light = find_rig_child(rig, NAME_LIGHT)
            controller = find_rig_child(rig, NAME_CONTROLLER)
            # Older rigs may predate the auto-update tag, or its source
            # may be out of date.  Re-install / refresh it here.
            doc.StartUndo()
            try:
                _ensure_python_tag(controller, doc)
            finally:
                doc.EndUndo()
            print("C4D_ls-cam loaded and command executed (rig updated)")

        apply_lscam_effect(doc, camera, light, controller)

        if detect_octane():
            print("Octane detected")
            tag = ensure_octane_camera_tag(camera, doc)
            if tag is not None:
                print("LS-Cam: Octane Camera Tag ready on %s" % NAME_CAMERA)
                apply_octane_bridge(doc, tag, controller)
        else:
            print("Octane not detected; using standard C4D camera mode")

        c4d.EventAdd()
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
