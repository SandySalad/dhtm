#  Copyright (c) 2022 Autonomous Non-Profit Organization "Artificial Intelligence Research
#  Institute" (AIRI); Moscow Institute of Physics and Technology (National Research University).
#  All rights reserved.
#
#  Licensed under the AGPLv3 license. See LICENSE in the project root for license information.

import numpy as np
from PIL import Image, ImageDraw

EPS = 1e-12


class ReachAndGrasp2D:
    def __init__(self,
                 goal_position,
                 grip_position,
                 grip_radius=0.07,
                 goal_radius=0.05,
                 max_grip_speed=0.1,
                 max_grip_acceleration=0.02,
                 max_grab_speed=0.01,
                 max_grab_acceleration=0.01,
                 action_cost=-0.01,
                 goal_reward=1,
                 grabbed_reward=0.1,
                 dense_reward=0.1,
                 time_constant=1,
                 camera_resolution: tuple[int, int] = (128, 128)):
        self.camera_resolution = camera_resolution
        self.action_cost = action_cost
        self.goal_reward = goal_reward
        self.grabbed_reward = grabbed_reward
        self.dense_reward = dense_reward
        self.max_grip_acceleration = max_grip_acceleration
        self.max_grip_speed = max_grip_speed
        self.max_grab_acceleration = max_grab_acceleration
        self.max_grab_speed = max_grab_speed
        self.time_constant = time_constant
        self.init_grip_position = grip_position
        self.max_grip_radius = grip_radius
        self.init_goal_position = goal_position
        self.goal_radius = goal_radius

        # state variables
        self.goal_position = np.array(self.init_goal_position)
        self.grip_position = np.array(self.init_grip_position)
        self.grip_radius = self.max_grip_radius
        self.distance_to_goal = np.linalg.norm(self.goal_position - self.grip_position)
        self.target_distance_to_goal = None
        self.can_grab = self.check_gripper()
        self.goal_grabbed = False
        self.grip_radius_speed = np.zeros(1)
        self.grip_speed = np.zeros(2)

        self.target_grip_position = None
        self.target_grip_radius = None
        self.previous_position = np.copy(self.grip_position)

    def act(self, action):
        self.target_grip_position = np.array(action[:2])
        self.target_grip_radius = action[2] * self.max_grip_radius

    def obs(self):
        return self.reward(), self.render_rgb()

    def reset(self):
        self.goal_position = np.array(self.init_goal_position)
        self.grip_position = np.array(self.init_grip_position)
        self.grip_radius = self.max_grip_radius
        self.distance_to_goal = np.linalg.norm(self.goal_position - self.grip_position)
        self.target_distance_to_goal = None
        self.can_grab = self.check_gripper()
        self.goal_grabbed = False
        self.grip_radius_speed = np.zeros(1)
        self.grip_speed = np.zeros(2)

        self.target_grip_position = None
        self.target_grip_radius = None

    def reward(self):
        reward = self.dense_reward/(1 + self.distance_to_goal)
        reward -= self.get_action_cost()
        if self.can_grab:
            reward += self.grabbed_reward
        if self.goal_grabbed:
            reward += self.goal_reward
        return reward

    def get_action_cost(self):
        distance = np.linalg.norm(self.previous_position - self.grip_position)
        self.previous_position = np.copy(self.grip_position)
        return self.action_cost * distance/np.sqrt(2)

    def check_gripper(self):
        if ((self.distance_to_goal < (self.grip_radius - self.goal_radius)) and
                (self.target_distance_to_goal < (self.target_grip_radius - self.goal_radius))):
            return True
        else:
            return False

    def simulation_step(self):
        if (self.target_grip_position is None) or (self.target_grip_radius is None):
            return

        self.grip_position, self.grip_speed = self.dynamics(
            self.grip_position,
            self.grip_speed,
            self.max_grip_acceleration,
            self.target_grip_position,
            self.max_grip_speed
        )

        self.grip_position = np.clip(self.grip_position, 0, 1)

        # check possibility to grab
        self.distance_to_goal = np.linalg.norm(self.goal_position
                                               - self.grip_position)
        self.target_distance_to_goal = np.linalg.norm(self.goal_position
                                                      - self.target_grip_position)

        self.can_grab = self.check_gripper()

        self.grip_radius, self.grip_radius_speed = self.dynamics(
            self.grip_radius,
            self.grip_radius_speed,
            self.max_grab_acceleration,
            self.target_grip_radius,
            self.max_grab_speed
        )

        self.grip_radius = min(self.max_grip_radius, self.grip_radius)
        if self.grip_radius == self.max_grip_radius:
            self.grip_speed = 0

        if self.can_grab:
            self.grip_radius = max(self.goal_radius, self.grip_radius)
            if self.grip_radius == self.goal_radius:
                self.grip_speed = 0
                self.goal_grabbed = True
            else:
                self.goal_grabbed = False
        else:
            self.grip_radius = max(0.0, self.grip_radius)
            if self.grip_radius == 0:
                self.grip_speed = 0
            self.goal_grabbed = False

    def dynamics(self, x, dx, ddx, x_target, max_dx):
        speed_delta = x_target - x
        norm_ddx = np.linalg.norm(speed_delta)
        dx += self.time_constant * ddx * speed_delta / (norm_ddx + EPS)

        norm_speed = np.linalg.norm(dx)
        if norm_speed > max_dx:
            dx = max_dx * dx / norm_speed

        x += self.time_constant * dx
        return x, dx

    def render_rgb(self, show_goal=False, camera_resolution=None):
        if camera_resolution is None:
            camera_resolution = self.camera_resolution

        image = Image.new('RGB', camera_resolution, (0, 0, 0))
        draw = ImageDraw.Draw(image)
        scale_factor = max(camera_resolution)

        goal_bbox = np.concatenate(
            [self.goal_position - self.goal_radius,
             self.goal_position + self.goal_radius
             ]).flatten()

        grip_bbox = np.concatenate(
            [self.grip_position - self.grip_radius,
             self.grip_position + self.grip_radius
             ]).flatten()
        if show_goal and (self.target_grip_position is not None):
            target_bbox = np.concatenate(
                [self.target_grip_position - self.target_grip_radius,
                 self.target_grip_position + self.target_grip_radius
                 ]).flatten()
            draw.ellipse(list(target_bbox * scale_factor),
                         outline=(50, 255, 0, 30),
                         width=max(1, int(0.02 * scale_factor))
                         )

        draw.ellipse(list(goal_bbox * scale_factor),
                     outline=(0, 0, 0),
                     fill=(0, 255, 255),
                     width=0)
        draw.ellipse(list(grip_bbox * scale_factor),
                     outline=(0, 0, 255),
                     width=max(1, int(0.02 * scale_factor)))

        return image


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    env = ReachAndGrasp2D(
        goal_position=(0.7, 0.7),
        grip_position=(0.1, 0.1),
    )
    env.act((0.5, 0.5, 0.05))
    plt.imshow(env.render_rgb(True))
    plt.show()
    env.simulation_step()
    plt.imshow(env.render_rgb(True))
    plt.show()
