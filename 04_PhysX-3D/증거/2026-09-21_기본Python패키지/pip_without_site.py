"""Run the designated pip without executing installed .pth/sitecustomize files."""
import runpy
import sys

sys.path.insert(0, '/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/lib/python3.10/site-packages')
runpy.run_module('pip', run_name='__main__')
