# Python G-Code simulator
#
# Copyright (C) 2011 Peter Rogers
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with self program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

from __future__ import absolute_import, division, print_function

import sys
import math
try:
    import numpy
except ImportError:
    print("ERROR - Cannot import NumPy module. Please visit http://www.numpy.org/\n")
    raise
    
# Get mathutils in from Blender and skip intermediate location handling
from mathutils import Vector

###########
# Globals #
###########

OPERATIONS = {
    "*" : lambda a, b : a*b,
    "/" : lambda a, b : a/float(b),
    "+" : lambda a, b : a+b,
    "-" : lambda a, b : a-b,
}

# The rapid speed rate in mm/s
RAPID_SPEED_MM = 25.0

#############
# Functions #
#############

def parse_program(path):
    fd = open(path, "r")

    prog = Program()
    while 1:
        line = fd.readline()
        if (not line): 
            break
        line = line.strip()

        try:
            i = line.index("(")
        except ValueError:
            comment = ""
        else:
            comment = line[i:]
            line = line[:i].strip()

        args = line.split()

        statement = Statement()
        statement.command = line.strip() + " " + comment
        statement.lineNumber = len(prog.statements)
        if (line.startswith("#")):
            # Assignment statement
            if (len(args) != 3):
                print("bad line: %s" % repr(line))
                prog.invalidLines.append(line)
                continue

            name = args[0]
            op = args[1]
            exp = args[2]

            if (op != "="):
                print("bad line: %s" % repr(line))
                continue

            statement.code = op
            statement.args = (name, exp)

        elif (not line):
            pass

        else:
            code = args[0]
            args = args[1:]
            if (code.startswith("G") or code.startswith("M")):
                # Format as a two digit number to make things standard (M2 -> M02)
                letter = code[0]
                try:
                    num = int(code[1:])
                except ValueError:
                    prog.invalidLines.append(line)
                    continue
                code = "%s%02d" % (letter, num)

            statement.code = code
            statement.args = args

            # Parse the arguments for self statement. Each parameter has a letter associated
            # with it, and there may or may not be a space between it and the value.
            n = 0
            while n < len(args):
                # Grab the next parameter
                arg = args[n]
                n += 1
                if (len(arg) == 1):
                    # The parameter and value are split up (eg "X" and "123.4")
                    key = arg
                    if (n < len(args)):
                        value = args[n]
                    else:
                        value = ""
                    n += 1
                else:
                    # The parameter and value come as a single token (eg "X123.4")
                    key = arg[0]
                    value = arg[1:]
                statement.params[key] = value

        statement.comment = comment
        prog.statements.append(statement)

    fd.close()
    return prog

def distance_from_point_to_line(pt, p1, p2):
    return abs( (p2[0]-p1[0])*(p1[1]-pt[1]) - (p1[0]-pt[0])*(p2[1]-p1[1]) ) / numpy.linalg.norm(p2-p1)

# Attempt to reduce the given path geometry to something more simple
def reduce_paths(paths, tolerance):
    lst = []
    running = []
    for path in paths:
        if (isinstance(path, Line)):
            if (running):
                # Check if self line segment can extend our running approximation
                start = running[0].start
                end = path.end
                # Make sure each segment falls within tolerance
                for p in running:
                    dist = distance_from_point_to_line(p.end, start, end)
                    if (dist > tolerance):
                        line = Line(start, running[-1].end, running[0].feedRate)
                        lst.append(line)
                        running = [path]
                        break
            else:
                running.append(path)
        else:
            if (running):
                line = Line(running[0].start, running[-1].end, running[0].feedRate)
                lst.append(line)
                running = []
            lst.append(path)
    return lst


###########
# Classes #
###########

class Program(object):
    statements = None
    invalidLines = None

    def __init__(self):
        self.statements = []
        self.invalidLines = []

    def start(self):
        return State(self)

class Statement(object):
    code = None
    args = None
    comment = None
    command = None
    params = None
    lineNumber = 0

    def __init__(self):
        self.code = ""
        self.params = {}

# A path plotting out by the cutting head
class Path(object):
    # Whether the spindle is on/off when tracing self path
    spindleOn = False
    # The statement that generated self path
    statement = None
    # The command that generated self path
    command = ""
    # The length of the path in machine units
    length = 0
    # The rate which we move along the path, in machine units
    feedRate = 1
    # When self path is traversed in the job timeline
    startTime = 0
    duration = 0

# A path between two points
class Line(Path):
    start = None
    end = None
    # Whether self represents a rapid movement command (G00), or 
    # a linear interpolation (G01)
    rapid = False

    def __init__(self, start, end, feedRate):
        self.start = start.copy()
        self.end = end.copy()
        self.feedRate = feedRate
        self.length = numpy.linalg.norm(self.end-self.start)
        self.duration = self.length/float(self.feedRate)

    def __repr__(self):
        template = '{0.__class__.__name__}({0.start}, {0.end}, {0.feedRate})'
        return template.format(self)

# An arc segment
class Arc(Path):
    clockwise = True
    center = None
    start = None
    end = None
    radius = 0
    diff = 0

    def __init__(self, start, end, center, feedRate, clockwise=True):
        self.start = start.copy()
        self.end = end.copy()
        self.center = center.copy()
        self.feedRate = feedRate
        self.clockwise = clockwise

        u = self.start - self.center
        v = self.end - self.center

        self.radius = numpy.linalg.norm(u)

        self.angle1 = math.atan2(u[1], u[0])
        self.angle2 = math.atan2(v[1], v[0])

        if (self.angle1 < 0): self.angle1 += 2*math.pi
        if (self.angle2 < 0): self.angle2 += 2*math.pi

        diff = abs(self.angle1-self.angle2)
        if (diff > math.pi): 
            diff = 2*math.pi - diff
        self.diff = diff
        self.length = self.radius * diff
        self.duration = self.length/float(self.feedRate)

    def __repr__(self):
        template = ('{0.__class__.__name__}({0.start}, {0.end}, {0.center}, '
                    '{0.feedRate}, {0.clockwise})')
        return template.format(self)

class ToolChange(Path):
    length = 0
    duration = 0
    def __repr__(self):
        return self.__class__.__name__ + '()'

class Dwell(Path):
    duration = 0
    def __repr__(self):
        return self.__class__.__name__ + '()'

class State(object):
    variables = None
    lineno = 0
    debug = False
    finished = False
    program = None
    # In units per second
    feedRate = 1
    time = 0
    minPos = None
    maxPos = None
    pos = None
    scale = 1000 # Blender standard is m which needs to be mm to match CNC format (not counting inches)
    spindleOn = True
    # The paths cut by the laser
    paths = None
    # The units are mm by default
    units = "mm"
    rapidSpeed = RAPID_SPEED_MM
    # The list of not-implemented codes in self program
    unknownCodes = None

    def __init__(self, program):
        self.variables = {}
        self.program = program
        self.paths = []
        # Note it is important to pass floats to make self a float array (otherwise it uses ints)
        self.pos = Vector([0.0, 0.0, 0.0])
        self.unknownCodes = []

    # Returns the length of the job
    def get_run_length(self):
        total = 0
        for path in self.paths:
            total += path.duration
        return total

    def eval_expression(self, exp):
        if (exp.startswith("[")):
            # Calculated value
            exp = exp[1:-1]

        if (not exp): 
            return 0

        for op in ("*", "/", "+", "-"):
            try:
                i = exp.index(op)
            except ValueError:
                pass
            else:
                (left, right) = (exp[:i], exp[i+1:])
                left = self.eval_expression(left)
                right = self.eval_expression(right)
                func = OPERATIONS[op]
                return func(left, right)

        if (exp.startswith("#")):
            return self.variables[exp]

        return float(exp)

    def eval_coords(self, args):
        lst = {}
        for arg in args:
            lst[arg[0]] = self.eval_expression(arg[1:])
        return lst

    def eval_params(self, params):
        lst = {}
        for key in params:
            lst[key] = self.eval_expression(params[key])
        return lst

    def handle_statement(self, st):
        if (st.code == ""):
            # Noop
            pass

        elif (st.code == "%"):
            pass

        elif (st.code == "="):
            # Variable assignment
            (name, exp) = st.args
            self.variables[name] = self.eval_expression(exp)

        elif (st.code == "G01" or st.code == "G00"):
            # Linear interpolation / rapid positioning
            params = self.eval_params(st.params)
            try:
                # The feed rate is supplied per minute
                self.feedRate = params["F"]/60.0
            except KeyError:
                pass

            if (self.pos is None):
                # Use self move to define the starting position
                self.pos = Vector([params["X"]/self.scale, 
                                   params["Y"]/self.scale, 
                                   params["Z"]/self.scale])
                return

            if ("X" in params or "Y" in params or "Z" in params):
                newpos = self.pos.copy()
                try:
                    newpos.x = params["X"]/self.scale
                except KeyError:
                    pass
                try:
                    newpos.y = params["Y"]/self.scale
                except KeyError:
                    pass
                try:
                    newpos.z = params["Z"]/self.scale
                except KeyError:
                    pass

                if (self.spindleOn):
                    # The spindle is on, move at the feed rate
                    feedRate = self.feedRate
                else:
                    # Otherwise move at the jog rate
                    feedRate = self.rapidSpeed

                # Create a line connecting our position to the target position
                line = Line(self.pos, newpos, feedRate)
                line.startTime = self.time
                line.spindleOn = self.spindleOn
                line.rapid = (st.code == "G00")
                line.statement = st
                self.paths.append(line)
                # Advance the timeline
                self.time += line.duration
                # Jump to the end position
                self.pos = newpos.copy()

        elif (st.code == "G02" or st.code == "G03"):
            # Circle interpolation, clockwise or couter-clockwise
            params = self.eval_params(st.params)

            try:
                # The feed rate is supplied per minute
                self.feedRate = params["F"]/60.0
            except KeyError:
                pass

            end = self.pos.copy()
            if "X" in params: end.x = params["X"]/self.scale
            if "Y" in params: end.y = params["Y"]/self.scale
            if "Z" in params: end.z = params["Z"]/self.scale

            if (self.spindleOn):
                center = Vector([self.pos.x + params["I"]/self.scale, self.pos.y + params["J"]/self.scale, self.pos.z])

                arc = Arc(self.pos, end, center, self.feedRate, clockwise=(st.code=="G02"))
                arc.startTime = self.time
                arc.spindleOn = self.spindleOn
                arc.statement = st
                self.paths.append(arc)
                # Advance the timeline
                self.time += arc.duration

            self.pos = end.copy()

        elif (st.code == "M02"):
            # End of program
            self.finished = True

        elif (st.code == "M03"):
            self.spindleOn = True

        elif (st.code == "M05"):
            self.spindleOn = False

        elif (st.code == "G96"):
            # Constant surface speed
            pass

        elif (st.code == "G20"):
            # Programming in inches
            self.units = "in"
            self.rapidSpeed = RAPID_SPEED_MM/25.4

        elif (st.code == "G90"):
            print("G90: absolute distance mode")

        elif (st.code == "G17"):
            # Define the XY plane
            pass

        elif (st.code.startswith("F")):
            # Feed rate definition
            rate = self.eval_expression(st.code[1:])
            self.feedRate = float(rate)

        elif (st.code == "M06"):
            # Tool change operation
            change = ToolChange()
            change.duration = 3
            change.startTime = self.time
            change.statement = st
            self.paths.append(change)
            self.time += change.duration

        elif (st.code.startswith("T")):
            # Tool selection operation
            pass

        elif (st.code == "G04"):
            # Dwell operation
            params = self.eval_params(st.params)
            dwell = Dwell()
            dwell.startTime = self.time
            dwell.statement = st
            dwell.duration = params.get("P", 0)
            self.paths.append(dwell)
            self.time += dwell.duration

        else:
            print("Unknown code: %s" % st.code)
            if (not st.code in self.unknownCodes):
                self.unknownCodes.append(st.code)

    def step(self):
        # Execute the current statement
        st = self.program.statements[self.lineno]
        self.handle_statement(st)

        # Increment to the next statement
        self.lineno += 1
        # Check if the program is finished
        if (self.lineno >= len(self.program.statements)):
            self.finished = True

        if (self.pos is None):
            return

        # Update the minimum pos
        if (self.minPos is None):
            self.minPos = self.pos.copy()
        else:
            self.minPos[0] = min(self.pos[0], self.minPos[0])
            self.minPos[1] = min(self.pos[1], self.minPos[1])
        # Update the max position too
        if (self.maxPos is None):
            self.maxPos = self.pos.copy()
        else:
            self.maxPos[0] = max(self.pos[0], self.maxPos[0])
            self.maxPos[1] = max(self.pos[1], self.maxPos[1])


def dump_parse():
    """Command line function to print G-code from a file."""
    import re
    import os
    import sys
    from pprint import pprint

    if len(sys.argv) != 2:
        print('Please give path to G-code file.')
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print('File does not exist.')
        sys.exit(1)

    prog = parse_program(path)
    state = prog.start()

    while not state.finished:
        state.step()

    pprint(state.paths)


if __name__ == '__main__':
    dump_parse()
