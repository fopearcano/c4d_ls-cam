"""C4D_ls-cam - Cinema 4D plugin.

Step 7: a safe ``detect_octane()`` helper is added and called once per
click of the menu command.  It only reports presence ("Octane
detected" / "Octane not detected; using standard C4D camera mode") -
no Octane tag is created and no Octane parameters are written yet.
Standard C4D output is unchanged.

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
    finally:
        if doc is not None:
            doc.EndUndo()

    print(
        "LS-Cam apply: enabled=%s beta=%.4f gamma=%.4f"
        " | fov*=%.3f I=%.3f rgb=(%.3f,%.3f,%.3f) ap*=%.3f dof*=%.3f exp=%+.2f"
        % (enabled, beta, gamma, fov_factor, intensity,
           rgb[0], rgb[1], rgb[2], aperture_f, dof_f, exposure)
    )
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

# Well-known Octane plugin IDs.  These have been stable across recent
# Octane Render Cinema 4D releases; mismatched builds simply fall
# through to the next probe.
OCTANE_VIDEOPOST_ID = 1029525     # Octane Render video post
OCTANE_CAMERA_TAG_ID = 1029524    # Octane Camera Tag


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
