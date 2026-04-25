"""C4D_ls-cam - Cinema 4D plugin skeleton.

Step 1 skeleton: registers a single CommandData entry ("Create LS-Cam")
that prints a confirmation message to the Cinema 4D console when invoked.

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
PLUGIN_HELP = "Create LS-Cam (skeleton stub - no camera logic yet)."


class CreateLSCamCommand(c4d.plugins.CommandData):
    """CommandData plugin invoked from the Cinema 4D Extensions menu."""

    def Execute(self, doc):
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
