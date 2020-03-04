bl_info = {
  "name": "CNC Emulator for Blender 2.8",
  "author": "Ulrik Holmen",
  "version": (1, 0),
  "blender": (2, 80, 0),
  "location": "",
  "description": "Emulate basic CNC functionality inside Blender. Load G-code and let an object carry out the instructions. Built on PyCNC",
  "warning": "",
  "wiki_url": "",
  "category": "Scene"
}

# This script defines functions to be used directly in drivers expressions to
# extend the builtin set of python functions.
# This can be executed on manually or set to 'Register' to
# initialize thefunctions on file load.

import os
import bpy
import sys
import math
import numpy
from mathutils import Vector
from bpy.utils.toolsystem import ToolDef
from bpy.props import IntProperty, FloatProperty, FloatVectorProperty, StringProperty, BoolProperty
from bpy.types import WorkSpaceTool
from bpy_extras.io_utils import ImportHelper

# Load local modules
print("Path: {}".format(os.path.realpath(__file__)))
sys.path.append(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
for dir in sys.path:
    print("{}".format(dir))
import gcode

# Virtual CNC
class VirtualCNC():
    location = Vector([0,0,0])
    lines = 0
    debug = False
    currentline = 0
    program = None
    state = None
    curve = None
    resolution = 10
    message = "Initialized"
    statement = "No codes yet"
    polyline = None
    finished = False

    def __init__(self):
        self.filename = None

    def load_program(self):
        self.debug = bpy.context.scene.CNCDebug
        if self.filename:
            self.program = gcode.parse_program(self.filename)
            self.run_program()
        else:
            self.message = "No filename"

    def run_program(self):
        if self.program:
            self.state = self.program.start()
            self.state.scale = 1
            self.message = "Loaded {} statements".format(len(self.program.statements))
                        
    def create_polyline(self):
        if not self.polyline:
            curve = bpy.data.curves.new('MyCurve', type='CURVE')
            curve.dimensions = '3D'
            curve.resolution_u = 2
            polyline = curve.splines.new('POLY')
            self.polyline = polyline
            CNCCurve = bpy.data.objects.new('CNCCurve', curve)
            scn =  bpy.context.scene
            self.curve = CNCCurve
            bpy.context.scene.collection.objects.link(CNCCurve)

    def delete_polyline(self):
        if self.polyline:
            bpy.ops.object.select_all(action='DESELECT')
            if 'CNCCurve' in bpy.data.objects:
                bpy.data.objects['CNCCurve'].select_set(True)
            bpy.ops.object.delete()
            self.polyline = None

    def draw_all(self):
        scn = bpy.context.scene
        if self.finished:
            return
        while self.currentline != self.lines:
            self.draw_path()
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()

    def get_intermediates(self, path):
        if (isinstance(path, gcode.Line)):
            nb_points = numpy.floor(path.length * (self.resolution * self.state.scale) / path.feedRate)
            # If we have 8 intermediate points, we have 8+1=9 spaces
            # between p1 and p2
            x_spacing = (path.end.x - path.start.x) / (nb_points + 1)
            y_spacing = (path.end.y - path.start.y) / (nb_points + 1)
            z_spacing = (path.end.z - path.start.z) / (nb_points + 1)

            return [Vector([path.start.x + i * x_spacing, 
                            path.start.y + i * y_spacing, 
                            path.start.z + i * z_spacing])
                for i in range(1, int(nb_points)+1)]

        elif (isinstance(path, gcode.Arc)):
            angle1 = path.angle1
            angle2 = path.angle2

            if (abs(angle2-angle1) >= math.pi):
                if (angle1 < math.pi):
                    angle2 -= 2*math.pi
                else:
                    angle2 += 2*math.pi

            if (path.clockwise):
                (angle1, angle2) = (angle2, angle1)

            nb_points = numpy.floor(path.length * (self.resolution * self.state.scale) / path.feedRate)
            if nb_points == 0:
                nb_points = 2
            arc = abs((angle2 - angle1)) / nb_points
            if arc == float(0): return []
            points = []
            for p in range(1, int(nb_points)):
                if self.debug and path.clockwise: print("Clockwise Angle: {}, plane {}".format(angle1 + (arc * p), path.plane))
                if self.debug and not path.clockwise: print("Angle: {}, plane {}".format(angle1 + (arc * p), path.plane))
                if path.plane == "XY" and path.clockwise:
                    px = path.center.x + (path.radius * math.sin(angle2 - (arc * p)))
                    py = path.center.y + (path.radius * math.cos(angle2 - (arc * p)))
                    pz = path.center.z
                elif path.plane == "XY":
                    px = path.center.x + (path.radius * math.cos(angle1 + (arc * p)))
                    py = path.center.y + (path.radius * math.sin(angle1 + (arc * p)))
                    pz = path.center.z
                elif path.plane == "ZX" and path.clockwise:
                    px = path.center.x + (path.radius * math.cos(angle1 + (arc * p)))
                    py = path.center.y
                    pz = path.center.z + (path.radius * math.sin(angle1 + (arc * p)))
                elif path.plane == "ZX":
                    px = path.center.x + (path.radius * math.sin(angle1 + (arc * p)))
                    py = path.center.y
                    pz = path.center.z + (path.radius * math.cos(angle1 + (arc * p)))
                elif path.plane == "YZ" and path.clockwise:
                    px = path.center.x
                    py = path.center.y + (path.radius * math.sin(angle2 - (arc * p)))
                    pz = path.center.z + (path.radius * math.cos(angle2 - (arc * p)))
                elif path.plane == "YZ":
                    px = path.center.x
                    py = path.center.y + (path.radius * math.cos(angle1 + (arc * p)))
                    pz = path.center.z + (path.radius * math.sin(angle1 + (arc * p)))
                else:
                    print("Unknown plane {}".format(self.plane))
                points.append(Vector([px,py,pz]))
            return points

    def draw_path(self):
        if not self.polyline:
            self.create_polyline()
        self.state.step()
        if self.state.finished:
            self.finished
            self.message = "Completed, you have to reset"
            return

        try:
            if self.debug: print("{}".format(self.program.statements[self.currentline]))
            self.statement = "{} {}".format(self.program.statements[self.currentline].code, " ".join(self.program.statements[self.currentline].args))
        except:
            self.message = "{}".format(self.program.statements[self.currentline].command)

        try: 
            path = self.state.paths[self.currentline]
            self.message = "Drawing path {}".format(self.currentline)
            if self.debug: print(path)
        except:
            self.currentline += 1
            return
        if self.finished:
            self.message = "Completed, you have to reset"
            return
        if isinstance(path, gcode.Line) and path.rapid: 
            if self.debug: print("Rapidline from {},{},{} to {},{},{}".format(path.start.x, path.start.y, path.start.z, path.end.x, path.end.y, path.end.z))
        if (isinstance(path, gcode.Line)):
            self.polyline.points.add(1)
            self.polyline.points[-1].co = path.start.to_4d()
            self.location = path.start
            for point in self.get_intermediates(path):
                nextpoint = Vector([point.x,point.y,point.z]).to_4d()
                if nextpoint == path.start or nextpoint == path.end:
                    next
                if self.debug: print("Line to {},{},{}".format(nextpoint.x,nextpoint.y,nextpoint.z))
                self.polyline.points.add(1)
                self.polyline.points[-1].co = nextpoint
                self.location = nextpoint
            self.polyline.points.add(1)
            self.polyline.points[-1].co = path.end.to_4d()
            self.location = path.end

        elif (isinstance(path, gcode.Arc)):
            # self.polyline.points.add(1)
            # self.polyline.points[-1].co = path.start.to_4d()
            self.location = path.start
            for point in self.get_intermediates(path):
                nextpoint = Vector([point.x,point.y,point.z]).to_4d()
                if nextpoint == path.start or nextpoint == path.end:
                    next
                if self.debug: print("Arc line to {},{},{}".format(nextpoint.x,nextpoint.y,nextpoint.z))
                self.polyline.points.add(1)
                self.polyline.points[-1].co = nextpoint
                self.location = nextpoint
            if self.location != path.start:
                self.polyline.points.add(1)
                self.polyline.points[-1].co = path.end.to_4d()
                self.location = path.end

        else:        
            print("This class of path is not implemented")
        self.currentline += 1
        if self.currentline == self.lines:
            self.finished = True

    def reset(self):
        self.delete_polyline()
        self.currentline = 0
        self.finished = False

# CNC Operator
class CNCOperator_OT_Modal(bpy.types.Operator):
    """Operator which runs its self from a timer"""
    bl_idname = "cnctool.mod"
    bl_label = "CNC Operator Up Modal"

    _timer = None
    end = None

    dir_enum = [ 'up', 'down', 'fwd', 'bwd', 'left', 'right', 'stop' ]
    dir: bpy.props.StringProperty(default='stop')
    
    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            # change theme color, silly!
            ao = bpy.context.scene.objects[context.scene.CNCObject]
            vcnc = bpy.types.Scene.VirtualCNC
            speed = context.scene.CNCSpeed
            if self.dir == 'up':
                if ao.location.z < self.end:
                    ao.location.z += speed
                    self.report({'INFO'}, "Dir %s, Current Z: %s" % (self.dir, ao.location.z))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'down': 
                if ao.location.z > self.end:
                    ao.location.z -= speed
                    self.report({'INFO'}, "Dir %s, Current Z: %s" % (self.dir, ao.location.z))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'left': 
                if ao.location.y < self.end:
                    ao.location.y += speed
                    self.report({'INFO'}, "Dir %s, Current Y: %s" % (self.dir, ao.location.y))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'right': 
                if ao.location.y > self.end:
                    ao.location.y -= speed
                    self.report({'INFO'}, "Dir %s, Current Y: %s" % (self.dir, ao.location.y))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'fwd': 
                if ao.location.x < self.end:
                    ao.location.x += speed
                    self.report({'INFO'}, "Dir %s, Current X: %s" % (self.dir, ao.location.x))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'bwd': 
                if ao.location.x > self.end:
                    ao.location.x -= speed
                    self.report({'INFO'}, "Dir %s, Current X: %s" % (self.dir, ao.location.x))
                else:
                    self.cancel(context)
                    return {'CANCELLED'}
            elif self.dir == 'play':
                vcnc.draw_path()
                self.report({'INFO'}, "Line %s, statement: %s" % (vcnc.currentline, vcnc.statement))
            else:
                self.cancel(context)
                return {'CANCELLED'}
            
        return {'PASS_THROUGH'}

    def execute(self, context):
        ao = bpy.context.scene.objects[context.scene.CNCObject]
        vcnc = bpy.types.Scene.VirtualCNC
        if self.dir != "stop":
            if self.dir == 'up':
                self.end = ao.location.z + bpy.context.scene.ZStep
                self.report({'INFO'}, "Dir: %s, Goal Z: %s" % (self.dir, self.end) )
            elif self.dir == 'down':
                self.end = ao.location.z - bpy.context.scene.ZStep
                self.report({'INFO'}, "Dir: %s, Goal Z: %s" % (self.dir, self.end) )
            elif self.dir == 'left':
                self.end = ao.location.y + bpy.context.scene.XYStep
                self.report({'INFO'}, "Dir: %s, Goal Y: %s" % (self.dir, self.end) )
            elif self.dir == 'right':
                self.end = ao.location.y - bpy.context.scene.XYStep
                self.report({'INFO'}, "Dir: %s, Goal Y: %s" % (self.dir, self.end) )
            elif self.dir == 'fwd':
                self.end = ao.location.x + bpy.context.scene.XYStep
                self.report({'INFO'}, "Dir: %s, Goal X: %s" % (self.dir, self.end) )
            elif self.dir == 'bwd':
                self.end = ao.location.x - bpy.context.scene.XYStep
                self.report({'INFO'}, "Dir: %s, Goal X: %s" % (self.dir, self.end) )
            elif self.dir == 'next':
                vcnc.draw_path() 
                return {'CANCELLED'}
            elif self.dir == 'reset':
                vcnc.reset()
                return {'CANCELLED'}
            elif self.dir == 'play':
                self.report({'INFO'}, "Line %s, statement: %s" % (vcnc.currentline, vcnc.statement))
            elif self.dir == 'stop':
                self.report({'INFO'}, "Stopping")
                self.cancel(context)
                return {'CANCELLED'}
            else:
                return {'CANCELLED'}
        else: 
            self.cancel(context)
            return {'CANCELLED'}
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self.dir = 'stop'
        self.report({'INFO'}, "Dir: %s" % self.dir)
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

# File browser
class OT_TestOpenFilebrowser(bpy.types.Operator, ImportHelper): 
    bl_idname = "cnctool.open_filebrowser" 
    bl_label = "Open the file browser (yay)" 

    filter_glob: StringProperty( default='*.nc;*.gcode;*.ngc', options={'HIDDEN'} ) 

    def execute(self, context):
        """Do something with the selected file(s).""" 
        filename, extension = os.path.splitext(self.filepath) 
        print('Selected file:', self.filepath) 
        print('File name:', filename) 
        print('File extension:', extension)
        cnc = bpy.types.Scene.VirtualCNC
        cnc.filename=self.filepath
        cnc.load_program()
                  
        return {'FINISHED'}
    

# CNC Add Panel
class CNCEMU_PT_Panel(bpy.types.Panel):
    bl_label = "CNC Emulator"# title

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CNC Emulator"#name of the tab

    @classmethod
    def poll(cls, context):
        return (context.object is not None)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        flow = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=False)
        layout = flow.column()

        obj = bpy.context.object

        #default label and operator
        row = layout.row()
        row.label(text="CNC Emulator", icon='PREFERENCES')

        # layout.separator() #Get some space

        box = layout.box()#put something in a box
        box.label(text="Manual CNC Operation")
        row = box.row()
        box.operator("cnctool.mod", icon="TRIA_UP", text='').dir = 'fwd'
        row = box.row()
        split = box.split(factor=0.5)
        split.operator("cnctool.mod", icon="TRIA_LEFT", text='').dir = 'left' 
        split.operator("cnctool.mod", icon="TRIA_RIGHT", text="").dir = 'right' 
        row = box.row()
        box.operator("cnctool.mod", icon="TRIA_DOWN", text='').dir = 'bwd'
        row = box.row()
        box.operator("cnctool.mod", text="Up").dir = 'up'
        box.operator("cnctool.mod", text="Down").dir = 'down' 
        row = box.row()
        box.operator("cnctool.mod", text="Next").dir = 'next' 
        box.operator("cnctool.mod", text="Reset").dir = 'reset' 
        row = box.row()
        box.operator("cnctool.mod", icon="PLAY", text="").dir = 'play' 
        row = box.row()
        box.operator("cnctool.mod", icon="PAUSE", text="").dir = 'stop' 

        row = box.row()
        layout.separator() #Get some space
        scene = context.scene
        box.prop_search(scene, "CNCObject", scene, "objects")   
        layout.separator() #Get some space
        row = box.row()
        row.prop(scene, "XYStep")
        row = box.row()
        row.prop(scene, "ZStep")
        row = box.row()
        row.prop(scene, "CNCSpeed")
        row = box.row()
        layout.separator() #Get some space
        row.label(text="Object: %s" % scene.CNCObject)
        row = box.row()
        vcnc = bpy.types.Scene.VirtualCNC
        row.label(text="X Location: %s" % vcnc.location.x)
        row = box.row()
        row.label(text="Y Location: %s" % vcnc.location.y)
        row = box.row()
        row.label(text="Z Location: %s" % vcnc.location.z)
        row = box.row()
        layout.separator() #Get some space
        row = box.row()
        box.operator("cnctool.open_filebrowser", icon="FILE", text="Load file")
        row = box.row()
        row.label(text="Loaded: %s paths" % vcnc.lines)
        row = box.row()
        row.prop(scene, "CNCDebug")
        row = box.row()
        box.label(text="%s" % vcnc.message)
        row = box.row()
        box.label(text="%s" % vcnc.statement)
        row = box.row()

classlist = [ CNCEMU_PT_Panel, 
              CNCOperator_OT_Modal,
              OT_TestOpenFilebrowser
            ]

def register():
    for cls in classlist:
        bpy.utils.register_class(cls)
    bpy.types.Scene.VirtualCNC = VirtualCNC()
    bpy.types.Scene.CNCObject = bpy.props.StringProperty()
    bpy.types.Scene.XYStep = bpy.props.FloatProperty(name = "XY Step", default=0.1, min=0.0001, max=10)
    bpy.types.Scene.ZStep = bpy.props.FloatProperty(name = "Z Step", default=0.1, min=0.0001, max=10)
    bpy.types.Scene.CNCSpeed = bpy.props.FloatProperty(name = "CNC Speed", default=0.1, min=0.0001, max=10)
    bpy.types.Scene.CNCDebug = bpy.props.BoolProperty(name = "debug", default=False)

    
def unregister():
    for cls in classlist:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
