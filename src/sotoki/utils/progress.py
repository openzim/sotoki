#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import datetime
from typing import Union
from collections import OrderedDict, namedtuple

from .shared import logger, GlobalMixin


class Progresser(GlobalMixin):

    PREPARATION_STEP = "prep"
    TAGS_METADATA_STEP = "tags_meta"
    QUESTIONS_METADATA_STEP = "questions_meta"
    USERS_STEP = "users"
    QUESTIONS_STEP = "questions"
    TAGS_STEP = "tags"
    LISTS_STEP = "lists"
    IMAGES_STEP = "images"

    # steps names and weights
    STEPS = OrderedDict(
        [
            (PREPARATION_STEP, 152),
            (TAGS_METADATA_STEP, 2),
            (QUESTIONS_METADATA_STEP, 470),
            (USERS_STEP, 225),
            (QUESTIONS_STEP, 3460),
            (TAGS_STEP, 10),
            (LISTS_STEP, 2),
        ]
    )

    def __init__(self, nb_questions: int):
        # adjust print periodicity based on global nb of questions for site
        self.print_every_updates = 50
        self.print_every_seconds = 60

        MConf = namedtuple("MConf", ["nb_updates", "nb_minutes"])
        milestones = {
            10000: MConf(100, 5),
            100000: MConf(1000, 10),
            1000000: MConf(5000, 15),
            10000000: MConf(1000, 30),
        }
        for milestone, conf in milestones.items():
            if nb_questions >= milestone:
                self.print_every_updates = conf.nb_updates
                self.print_every_seconds = conf.nb_minutes * 60
            else:
                break

        # keep track of current step's data
        self.current_step = self.PREPARATION_STEP
        self.current_step_index = 0
        self.current_step_total = 0
        self.current_step_progress = 0
        self.current_step_updates = 0

        # computed sum of all previous steps
        self.previous_step_weight = 0

        # compute respective weights of all steps to fix weights from constants
        self.weights = {
            key: value / sum(self.STEPS.values()) for key, value in self.STEPS.items()
        }

        self.last_print_on = datetime.datetime.now()

    def update_json(self):
        """Update JSON progress file if such a file was requested"""
        if not self.conf.stats_filename:
            return
        with open(self.conf.stats_filename, "w") as fh:
            json.dump(
                {"done": round(self.overall_progress * 100, 2), "total": 100},
                fh,
            )

    def update(
        self, nb_done: int = None, nb_total: int = None, incr: Union[int, bool] = None
    ):
        """update current step's progress

        set nb_done or nb_total to an arbitrary value
        or increment nb_done by any number"""

        # record we received an update
        self.current_step_updates += 1

        if nb_done is not None:
            self.current_step_progress = nb_done
        elif incr is not None:
            self.current_step_progress += int(incr)
        if nb_total is not None:
            self.current_step_total = nb_total

        self.update_json()

        self.print_maybe()

    def print(self):
        """log current progress state"""

        msg = (
            f"PROGRESS: {self.overall_progress * 100:.1f}% – "
            f"Step {self.current_step_index + 1}/{len(self.STEPS)}: "
            f"{self.current_step.title()} -- "
            f"{self.current_step_progress}/{self.current_step_total}"
        )

        if self.images_progress:
            msg += f" -- Images: {self.nb_img_done}"
        logger.info(msg)
        self.last_print_on = datetime.datetime.now()

    def print_maybe(self):
        if (
            self.current_step_updates % self.print_every_updates == 0
            or self.last_print_on + datetime.timedelta(seconds=self.print_every_seconds)
            < datetime.datetime.now()
        ):
            self.print()

    def start(self, step: str, nb_total: int = 0):
        """start a new step. Considers previous steps as completed.

        nb_total: set total for this step"""
        if step not in self.STEPS.keys():
            raise KeyError(f"Step `{step}` is not a valid step")

        step_index = list(self.STEPS.keys()).index(step)

        # compute done steps weight
        self.previous_step_weight = sum(
            [
                self.weights.get(s)
                for i, s in enumerate(self.STEPS.keys())
                if i < step_index
            ]
        )

        self.current_step = step
        self.current_step_index = step_index
        self.current_step_total = nb_total
        self.current_step_progress = 0
        self.current_step_updates = 0
        self.print()

    def weight_for(self, step: str) -> float:
        """weight of a step within total"""
        return self.weights.get(step)

    @property
    def step_progress(self) -> float:
        """progress of current step (0-1)"""
        try:
            return min([self.current_step_progress / self.current_step_total, 1])
        except ZeroDivisionError:
            return 1

    @property
    def nb_img_requested(self):
        return getattr(self.imager, "nb_requested", 0)

    @property
    def nb_img_done(self):
        return getattr(self.imager, "nb_done", 0)

    @property
    def images_progress(self) -> float:
        """progress of images step (0-1)"""
        if self.nb_img_requested == 0:
            return 0
        try:
            return min(
                [
                    self.nb_img_done / self.nb_img_requested,
                    1,
                ]
            )
        except ZeroDivisionError:
            return 1

    @property
    def overall_progress(self) -> float:
        """scraper progress (0-1)"""
        return self.previous_step_weight + (
            self.step_progress * self.weight_for(self.current_step)
        )
