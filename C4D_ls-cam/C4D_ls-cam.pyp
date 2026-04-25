"""C4D_ls-cam - Cinema 4D plugin.

Step 3: the "Create LS-Cam" command builds the rig and populates
LS-Cam_Controller with User Data parameters that future steps will
read for the relativistic camera effect (no live evaluation yet).

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
