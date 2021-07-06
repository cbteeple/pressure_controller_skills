#!/usr/bin/env python

import os
import sys
import rospy
from pressure_controller_skills.build_skills import SkillBuilder


variable_ovr={}#{'grasp_pressure':24.3}
time_ovr={}


import rospkg 
rospack = rospkg.RosPack()
curr_path = rospack.get_path('pressure_controller_skills')
filepath_in = os.path.join(curr_path,'skills')

import glob

def main(file_name=None, folder=False):

    if folder:
        files_to_build = glob.glob(os.path.join(filepath_in,file_name,'*.yaml'))
        for idx,file in enumerate(files_to_build):
            file = file.strip('.yaml')
            files_to_build[idx] = os.path.relpath(file, filepath_in)

    else:
        files_to_build = [file_name]

    try:
        rospy.init_node("skill_builder_node", anonymous=True, disable_signals=True)

        node = SkillBuilder()
        for filename in files_to_build:
            print("Building: %s"%(filename))
            node.load_skill(filename)
            node.generate_skill(vars=variable_ovr, times=time_ovr)
            flat_traj = node.get_skill_flattened(main_repeat=4,flatten_points=True)

            print(flat_traj)
            #node.generate_skill()
            node.save_skill(filename)

        node.shutdown()

    except KeyboardInterrupt:
        print("Shutting Down Top-Level Node")
        node.shutdown()
        print("Shutting Down ROS")
        rospy.signal_shutdown("KeyboardInterrupt")
        raise

if __name__ == '__main__':
    if len(sys.argv) ==3:
        main(sys.argv[1],folder=True)
    elif len(sys.argv) ==2:
        main(sys.argv[1])
    else:
        print("Usage:")
        print("\tbuild_skill.py [FILENAME]\t- Build a skill from definition file")