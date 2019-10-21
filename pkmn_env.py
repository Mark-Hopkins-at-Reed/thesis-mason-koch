import time
import threading
import os
import subprocess
import pexpect

class Env():
    def __init__(self):
        self.done = True
    def seed(self, num):
        dummy = True
    def render(self):
        raise NotImplementedError()
    def reset(self):
        # Create a Pokemon battle.
        self.t = threading.Thread(target = self.pokemon_wrapper)
        self.t.start()
        self.done = False
        # Wait a bit for the game to initialise.
        time.sleep(2)
        # The Pokemon battle will return some stuff
        return self.scrape_input()
    def step(self, action):
        # Obscure method of writing to user input.
        self.proc.sendline(action)
        # Wait for the Pokemon simulator to do its thing. This is not very efficient
        # but it does allow human input.
        time.sleep(2)
        return self.scrape_input(), 42, self.done, "NotUsed"
    def scrape_input(self):
        retval = ""
        temp = "."
        while ("|turn|" not in temp):
            temp = self.proc.readline().decode()
            retval += temp
        return retval
    def pokemon_wrapper(self):
       self.proc = pexpect.spawn("node ./Pokemon-Showdown/.sim-dist/examples/test_random_player.js")
