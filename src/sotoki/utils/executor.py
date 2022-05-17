#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
import queue
import threading
from typing import Callable

from .shared import logger

_shutdown = False
# Lock that ensures that new workers are not created while the interpreter is
# shutting down. Must be held while mutating _threads_queues and _shutdown.
_global_shutdown_lock = threading.Lock()
thread_deadline_sec = 60


def excepthook(args):
    logger.error(f"UNHANDLED Exception in {args.thread.name}: {args.exc_type}")
    logger.exception(args.exc_value)


threading.excepthook = excepthook


class SotokiExecutor(queue.Queue):
    """Custom FIFO queue based Executor that's less generic than ThreadPoolExec one

    Providing more flexibility for the use cases we're interested about:
    - halt immediately (sort of) upon exception (if requested)
    - able to join() then restart later to accomodate successive steps

    See: https://github.com/python/cpython/blob/3.8/Lib/concurrent/futures/thread.py
    """

    def __init__(self, queue_size: int = 10, nb_workers: int = 1, prefix: str = "T-"):
        super().__init__(queue_size)
        self.prefix = prefix
        self._shutdown_lock = threading.Lock()
        self.nb_workers = nb_workers
        self.exceptions = []

    @property
    def exception(self):
        """Exception raises in any thread, if any"""
        try:
            return self.exceptions[0:1].pop()
        except IndexError:
            return None

    @property
    def alive(self):
        """whether it should continue running"""
        return not self._shutdown

    def submit(self, task: Callable, **kwargs):
        """Submit a callable and its kwargs for execution in one of the workers"""
        with self._shutdown_lock, _global_shutdown_lock:
            if not self.alive:
                raise RuntimeError("cannot submit task to dead executor")
            if _shutdown:
                raise RuntimeError("cannot submit task after " "interpreter shutdown")

        while True:
            try:
                self.put((task, kwargs), block=True, timeout=3.0)
            except queue.Full:
                if self.no_more:
                    break
            else:
                break

    def start(self):
        """Enable executor, starting requested amount of workers

        Workers are started always, not provisioned dynamicaly"""
        self.drain()
        self.release_halt()
        self._workers = set()
        self._shutdown = False
        self.exceptions[:] = []

        for n in range(self.nb_workers):
            t = threading.Thread(target=self.worker, name=f"{self.prefix}{n}")
            t.daemon = True
            t.start()
            self._workers.add(t)

    def worker(self):
        while self.alive or self.no_more:
            try:
                func, kwargs = self.get(block=True, timeout=2.0)
            except queue.Empty:
                if self.no_more:
                    break
                continue
            except TypeError:
                # received None from the queue. most likely shuting down
                return

            raises = kwargs.pop("raises") if "raises" in kwargs.keys() else False
            callback = kwargs.pop("callback") if "callback" in kwargs.keys() else None
            dont_release = kwargs.pop("dont_release", False)

            try:
                func(**kwargs)
            except Exception as exc:
                logger.error(f"Error processing {func} with {kwargs=}")
                logger.exception(exc)
                if raises:
                    self.exceptions.append(exc)
                    self.shutdown()
            finally:
                # user will manually release the queue for this task.
                # most likely in a libzim-written callback
                if not dont_release:
                    self.task_done()
                if callback:
                    callback.__call__()

    def drain(self):
        """Empty the queue without processing the tasks (tasks will be lost)"""
        while True:
            try:
                self.get_nowait()
            except queue.Empty:
                break

    def join(self):
        """Await completion of workers, requesting them to stop taking new task"""
        logger.debug(f"joining all threads for {self.prefix}")
        self.no_more = True
        for num, t in enumerate(self._workers):
            deadline = datetime.datetime.now() + datetime.timedelta(
                seconds=thread_deadline_sec
            )
            logger.debug(f"Giving {self.prefix}{num} {thread_deadline_sec}s to join")
            e = threading.Event()
            while t.is_alive() and datetime.datetime.now() < deadline:
                t.join(1)
                e.wait(timeout=2)
            if t.is_alive():
                logger.debug(f"Thread {self.prefix}{num} is not joining. Skipping…")
            else:
                logger.debug(f"Thread {self.prefix}{num} joined")
        logger.debug(f"all threads joined for {self.prefix}")

    def release_halt(self):
        """release the `no_more` flag preventing workers from taking up tasks"""
        self.no_more = False

    def shutdown(self, wait=True):
        """stop the executor, either somewhat immediately or awaiting completion"""
        logger.debug(f"shutting down executor {self.prefix} with {wait=}")
        with self._shutdown_lock:
            self._shutdown = True

            # Drain all work items from the queue
            if not wait:
                self.drain()
        if wait:
            self.join()
