# cnc-emulator
An addon to simulate a CNC inside blender. The idea is to read .gcode and either lay out the toolpath as a polyline or move an empty to points along the path using a modal. Combined with dynamic paint you can simulate milling etc straight in Blender.  

# Mandatory picture
Below is the toolpath for milling one side of a wooden button for a dress. There are still some intermittent issues with the XZ and ZY plane arc angles. Will be resolved shortly

![CNC-Emulator running in Blender 2.82](https://raw.githubusercontent.com/Ulrhol/cnc-emulator/master/img/blender_toolpath.png)

# Credits

The gcode parser is forked from Peter Rogers (https://github.com/parogers/gsim) and adapted for 3 axis coordinates and support of multiple planes. 
