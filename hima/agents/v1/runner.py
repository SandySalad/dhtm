#  Copyright (c) 2022 Autonomous Non-Profit Organization "Artificial Intelligence Research
#  Institute" (AIRI); Moscow Institute of Physics and Technology (National Research University).
#  All rights reserved.
#
#  Licensed under the AGPLv3 license. See LICENSE in the project root for license information.

import pygame
from PIL import Image
import numpy as np

from hima.agents.v1.agent import ExploreAgent
from animalai.envs.environment import AnimalAIEnvironment
from animalai.envs.actions import AAIActions
from hima.modules.v1 import V1


def np2pygame(data: np.ndarray, zoom=2):
    img = Image.fromarray(data).convert('RGB')
    s1, s2 = img.size
    img = img.resize((s1 * zoom, s2 * zoom), Image.NEAREST)
    return pygame.image.fromstring(img.tobytes(), img.size, img.mode).convert()


class AAIPygameRunner:
    def __init__(
            self, seed: int, env_filename: str, configuration_filename: str, resolution: int, v1_config: dict,
            zoom: int, bin_size: int
    ):
        self.env = AnimalAIEnvironment(
            file_name=env_filename,
            arenas_configurations=configuration_filename,
            seed=seed,
            play=False,
            useCamera=True,
            useRayCasts=False,
            resolution=resolution
        )
        self.behavior = list(self.env.behavior_specs.keys())[0]  # by default should be AnimalAI?team=0
        self.actions = AAIActions().allActions
        print("Environment loaded")

        self.v1 = V1((resolution, resolution), v1_config['complex_config'], *v1_config['simple_configs'])
        self.sdr_data = np.zeros(self.v1.output_sdr_size)
        self.sdr_size = int(np.sqrt(self.sdr_data.size)) + 1

        self.key_actions = (
            pygame.K_s, #stop
            pygame.K_a, #left
            pygame.K_d, #right
            pygame.K_w, #forward
            pygame.K_q, #leftforward
            pygame.K_e, #rightforward
            pygame.K_x, #backward
            pygame.K_c, #rightbackward
            pygame.K_z #leftbackward
        )
        self.gray = (150, 150, 150)
        width = resolution * zoom + self.sdr_size * bin_size
        height = max(zoom * resolution, self.sdr_size * bin_size)
        self.window_size = (width, height)
        self.zoom = zoom
        self.bin_size = bin_size
        self.resolution = resolution

    def get_obs(self):
        dec, term = self.env.get_steps(self.behavior)
        if len(term) > 0:
            obs = self.env.get_obs_dict(term.obs)
            is_first = True
        else:
            obs = self.env.get_obs_dict(dec.obs)
            is_first = False
        img = obs['camera'] * 255
        img = img.astype(np.uint8)
        return img, is_first

    def update_screen(self, image: np.ndarray):
        v1_data, _ = self.v1.compute(image)
        self.sdr_data[v1_data[0]] += 1

        start_x, start_y = self.resolution * self.zoom, 0
        max_v = self.sdr_data.max()
        self.screen.fill(self.gray)
        for i, r in enumerate(self.sdr_data):
            cur_x = start_x + self.bin_size * (i % self.sdr_size)
            cur_y = start_y + self.bin_size * (i // self.sdr_size)
            pygame.draw.rect(
                self.screen, (255, 255, 255),
                pygame.Rect(cur_x, cur_y, self.bin_size, self.bin_size * (1 - r / max_v)), 2
            )
            pygame.draw.rect(
                self.screen, (0, 0, 0),
                pygame.Rect(cur_x, cur_y + self.bin_size * (1 - r/max_v), self.bin_size, self.bin_size * r/max_v)
            )
        self.screen.blit(np2pygame(image, self.zoom), (0, 0))

        text = pygame.font.Font(None, 36).render(
            str(np.round(len(v1_data[0])/len(self.sdr_data), 3)),
            True, (180, 0, 0)
        )
        self.screen.blit(text, (5, 5))
        pygame.display.update()

    def run(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode(self.window_size)
        running = True
        firststep = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    for a, k in enumerate(self.key_actions):
                        if event.key == k:
                            if firststep:
                                self.env.step()
                                firststep = False
                            self.env.set_actions(self.behavior, self.actions[a].action_tuple)
                            self.env.step()
                            raw_image, firststep = self.get_obs()
                            self.update_screen(raw_image)
        pygame.quit()
        self.env.close()


class ExplorationAAIRunner:
    def __init__(self, config):

        self.env = AnimalAIEnvironment(**config['environment'])
        self.behavior = list(self.env.behavior_specs.keys())[0]
        self.actions = AAIActions().allActions
        self.steps = config['steps']
        self.agent = ExploreAgent(**config['agent'])

    def run(self):
        firststep = True
        for i in range(self.steps):
            if firststep:
                self.env.step()
                firststep = False
                dec, term = self.env.get_steps(self.behavior)

            pos = self.env.get_obs_dict(dec.obs)["position"]
            vel = self.env.get_obs_dict(dec.obs)["velocity"]
            cam = self.env.get_obs_dict(dec.obs)["camera"]
            action = self.agent.act(pos, vel, cam)

            self.env.set_actions(self.behavior, self.actions[action].action_tuple)
            self.env.step()
            dec, term = self.env.get_steps(self.behavior)
            if len(term) > 0:  # Episode is over
                firststep = True
        self.env.close()
