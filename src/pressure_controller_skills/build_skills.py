#!/usr/bin/env python

import os
import sys
import yaml
import rospy
import numpy as np
import copy


import rospkg 
rospack = rospkg.RosPack()



def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z


class SkillBuilder:
    def __init__(self, context=None, skill_package='pressure_controller_skills', skill_folder="skills"):
        curr_path = rospack.get_path(skill_package)
        #curr_path=os.path.dirname(os.path.abspath(__file__))
        filepath_in = os.path.join(curr_path,skill_folder)
        filepath_out = os.path.join(curr_path,'.'+skill_folder)
        self.filepath_in = filepath_in
        self.filepath_out = filepath_out
        self.controller_context = context
        self.reset_skill()
        

    # Reset skill attributes
    def reset_skill(self):
        self.skill_config = None
        self.skill_definition = None
        self.skill_compiled = None
        self.skill_flattened = None


    # Load the skill definition intoa python dictionary
    def load_skill(self,filename):
        self.reset_skill()

        config_file = os.path.join(self.filepath_in,filename+'.yaml')

        if os.path.isfile(config_file):
            with open(config_file,'r') as f:
                self.skill_config = yaml.safe_load(f)
        else:
            self.skill_config = None
            print(config_file)
            print("Skill config file cannot be found")

        return self.skill_config


    def set_skill_config(self, skill_config):
        self.reset_skill()
        self.skill_config = skill_config


    def get_skill_config(self):
        return self.skill_config


    # Compile the skill from the definition
    def generate_skill(self, vars=None, times=None):
        variables = self.skill_config.get('variables', None)
        postures = self.skill_config.get('postures', None)
        skill = self.skill_config.get('skill', None)
        skill_settings = skill.get('settings', {})
        skill_times = skill_settings.get('default_times', None)
        context_curr = self.skill_config.get('context', None)

        if (variables is None) or (postures is None) or (skill is None):
            raise ValueError("Skill definition is invalid")
            return

        if not self._validate_context(context_curr):
            raise ValueError("Skill is not valid in context %s"%(context_curr))
            return


        # Assimilate variables into defaults:
        if isinstance(vars,dict):
            variables = merge_two_dicts(variables,vars)

        # Compile postures based on equations
        postures_compiled = {}
        for key in postures:
            if not isinstance(postures[key], list):
                print('Posture definition "%s" is not a list'%(key))
                continue

            postures_compiled[key] = []
            for equation in postures[key]:
                postures_compiled[key].append(
                    self._substitute_variables(equation,variables)
                )
                

        self.postures_compiled = postures_compiled

        self._validate_postures(skill,postures_compiled)

        # Assimilate skill timings
        if isinstance(times,dict):
            skill_times = merge_two_dicts(skill_times,times)


        self.skill_timed = self._set_skill_times(skill,skill_times)
        del skill_settings['default_times']
        self.skill_definition = {'skill':self.skill_timed,
                                   'context':context_curr,
                                   'settings':skill_settings,
                                   'postures':postures_compiled}


        return self.skill_definition


    # Get compiled skill definition
    def get_skill_definition(self):
        return self.skill_definition


    # Set the compiled skill definition
    def set_skill_definition(self, skill_definition):
        self.skill_definition = skill_definition


    # Get compiled skill definition
    def get_skill_compiled(self, sorotraj_format=False):
        self._compile_skill()

        if sorotraj_format:
            return self.to_sototraj(self.skill_compiled)

        else:
            return self.skill_compiled


    # Get compiled skill definition
    def get_skill_flattened(self, main_repeat=None, flatten_points=False):
        self._flatten_skill(main_repeat)

        if flatten_points:
            return self._flatten_points(self.skill_flattened)

        else:
            return self.skill_flattened



    # Save the skill in a yaml file for use later 
    def save_skill(self, filename):
        if self.skill_definition is not None:
            self._save_skill(filename,self.skill_definition)

        if self.skill_compiled is not None:
            self._save_skill(filename, self.skill_compiled, 'comp')

        if self.skill_flattened is not None:
            self._save_skill(filename, self.skill_flattened, 'flat')


    # Save the skill in a yaml file for use later 
    def _save_skill(self, filename, skill, suffix=''):
        outfile = os.path.join(self.filepath_out,filename+'.skill'+suffix)
        outdir = os.path.dirname(outfile)
        if not os.path.exists(outdir):
            try:
                os.makedirs(outdir)
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        with open(outfile, 'w+') as f:
            f.write('# This file was automatically generated by the pressure_controller_skills package\n# (https://github.com/cbteeple/pressure_controller_skills)\n# DO NOT EDIT THIS FILE DIRECTLY UNLESS YOU KNOW WHAT YOU ARE DOING!\n\n')
            yaml.dump(skill, f, default_flow_style=None)


    # Convert a skill to sorotraj format
    def to_sototraj(self, compiled_skill):
        out = {}
        out['settings'] = compiled_skill['settings']
        out['settings']['traj_type'] = 'direct'
        out['config'] = {}
        skill = compiled_skill['skill']

        setpoints = {}
        for key in skill:
            setpoints[key] = []
            for idx,point in enumerate(skill[key]):
                time = point['time']
                pres = point['pressure']
                setpoints[key].append([time] + pres)

        out['config']['setpoints'] = setpoints

        return out


    # Compile skill from times
    def _set_skill_times(self,skill,times):
        skill_timed = {}
        for key in skill:
            if key == 'settings':
                continue
            
            if not isinstance(skill[key], list):
                print('Skill subcomponent "%s" is not a list'%(key))
                continue

            if len(skill[key])<1:
                print('Skill subcomponent "%s" is empty'%(key))
                continue
            
            def_last_time = skill[key][-1]['time']
            time_goal=times.get(key, 1.0)

            skill_timed[key] = []

            for row in skill[key]:
                new_row=copy.deepcopy(row)
                new_row['pressure'] = new_row.pop('posture')
                new_row['time'] = row['time']*time_goal/def_last_time
                skill_timed[key].append(new_row)

        return skill_timed


    # Compile the skill into sorotraj-compatible format
    def _compile_skill(self):
        if self.skill_definition is None:
            raise ValueError('You must build a skill before compiling it')

        skill=self.skill_definition['skill']
        postures=self.skill_definition['postures']
        settings=self.skill_definition['settings']

        self._validate_postures(skill, postures, posture_key='pressure')

        skill_compiled = copy.deepcopy(skill)

        for traj_key in skill:
            traj = skill[traj_key]

            for idx,point in enumerate(traj):
                skill_compiled[traj_key][idx]['pressure'] = postures[point['pressure']]

        self.skill_compiled={}
        self.skill_compiled['settings'] = settings
        self.skill_compiled['skill'] = skill_compiled

        return self.skill_compiled


    # Flatten the skill
    def _flatten_skill(self, main_repeat=None):
        if self.skill_definition is None:
            raise ValueError('You must build a skill before compiling it')

        if self.skill_compiled is None:
            self._compile_skill()


        skill = self.skill_compiled['skill']
        settings = self.skill_compiled['settings']

        if main_repeat is None:
            main_repeat = settings['main_repeat']

        prefix = skill.get('prefix', None)
        main   = skill.get('main', None)
        suffix = skill.get('suffix', None)

        skill_flat = []
        last_time = 0

        if prefix is not None:
            if len(prefix)>0:
                skill_flat.extend(self._adjust_points(prefix))


        if main is not None:
            if len(main)>0:
                for idx in range(main_repeat):
                    if len(skill_flat)>0:
                        last_time = skill_flat[-1]['time']
                    skill_flat.extend(self._adjust_points(main, last_time))


        if suffix is not None:
            if len(suffix)>0:
                last_time = skill_flat[-1]['time']
                skill_flat.extend(self._adjust_points(suffix, last_time))


        self.skill_flattened = skill_flat
        return self.skill_flattened



    def _adjust_points(self, trajectory, starting_time=0.0):
        new_traj = copy.deepcopy(trajectory)
        for idx,point in enumerate(new_traj):
            new_traj[idx]['time'] = point['time']+starting_time

        return new_traj


    def _flatten_points(self, flattened_skill):
        flat_skill = []
        for point in flattened_skill:
            new_point = copy.deepcopy(point['pressure'])
            new_point.insert(0,point['time'])
            flat_skill.append(new_point)

        return flat_skill
            

    # Check if the current skill is valid in the current controller context
    def _validate_context(self, context):
        if self.controller_context is None:
            return True
        elif self.controller_context in context:
            return True
        else:
            return False


    # Validate that all postures in a skill are defined
    def _validate_postures(self, skill, postures, posture_key='posture'):
        posture_list = list(postures.keys())

        for traj_key in skill:
            if traj_key == 'settings':
                continue

            for point in skill[traj_key]:
                posture_curr = point[posture_key]
                if posture_curr not in posture_list:
                    raise ValueError('Posture "%s" not defined in skill definition'%(posture_curr))


    # Substitute variable values into equations and evaluate them
    def _substitute_variables(self, equation, variables):
        for var_key in variables:
            equation = equation.replace(var_key,str(variables[var_key]))
        
        return eval(equation)
        

    def shutdown(self):
        pass
           


        

