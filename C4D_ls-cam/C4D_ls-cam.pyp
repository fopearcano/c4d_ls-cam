"""C4D_ls-cam - Cinema 4D plugin.

Step 2: the "Create LS-Cam" command builds a minimal camera rig in the
active document and makes the new camera the active scene camera.

Hierarchy created::

    LS-Cam_Rig                (Null)
        LS-Cam_Camera         (Camera, active scene camera)
        LS-Cam_ForwardLight   (Light, default forward orientation)
        LS-Cam_Controller     (Null, animation/anchor controller)

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


def _make_named(obj_type, name):
    obj = c4d.BaseObject(obj_type)
    if obj is None:
        raise MemoryError("Failed to allocate BaseObject of type %d" % obj_type)
    obj.SetName(name)
    return obj


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
