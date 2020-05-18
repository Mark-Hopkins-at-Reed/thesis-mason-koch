import numpy as np
import pickle
from game_model import *

class Bookkeeper:
    def __init__(self, list_of_models, prep, smog):
        self.reset()
        self.episode_number = 1
        self.list_of_models = list_of_models
        self.preprocess_observation = prep
        self.reward_list = np.zeros(1000)
        self.smogon = smog
    def reset(self):
        self.xs,self.hs,self.h2s,self.pvecs,self.actions,self.rewards,self.our_actives,self.opponent_actives=[],[],[],[],[],[],[],[]#,self.legal_action_lists, self.legal_counts = [],[],[],[],[],[],[[np.zeros(10) for i in range(TEAM_SIZE)] for j in range(TEAM_SIZE)], [[0.0 for i in range(TEAM_SIZE)] for j in range(TEAM_SIZE)]
    def signal_episode_completion(self, starting_pokemon_wincount):
        assert(self.rewards[-1] != 0)
        self.reward_list[self.episode_number % 1000] = self.rewards[-1]
        self.episode_number += 1
        self.reset()
        if self.episode_number % 300 == 0: pickle.dump((self.list_of_models, OUR_TEAM, OPPONENT_TEAM, starting_pokemon_wincount), open(str(self.episode_number)+'save.p', 'wb'))
    def report(self, x, h, h2, pvec, action):#,legal_action_list):
        # Turn our matrices back into vectors so that np.vstack behaves nicely.
        self.xs.append(x)
        self.hs.append(h) # We don't strictly need to remember h or h2
        self.h2s.append(h2) # or pvecs, but it will make our lives easier
        self.pvecs.append(pvec)
        self.actions.append(action)
        #self.legal_action_lists[our_active][opponent_active] += legal_action_list # Might make it in to the final version, might not
        #self.legal_counts[our_active][opponent_active] += 1.0
        self.our_actives.append(self.our_active)  # We only want to remember these two when our AI took an action.
        self.opponent_actives.append(self.opponent_active)
    def report_reward(self, reward, took_action):
        if took_action:
            self.rewards.append(reward)
        else:
            if reward != 0:
                self.rewards[-1] += reward
    def construct_observation_handler(self):
        # Since the state is a vector which we are treating as a matrix to make life easier,
        # the order does not matter. However we will eventually want to put our x vectors
        # together into a bigger matrix, and we want each column to be an x vector. Therefore
        # we want column-major order for our x vectors.
        self.state = np.zeros((N,1), order = 'F')
        self.opp_state = np.zeros((N,1), order = 'F')
        # Only necessary for Smogon, but it doesn't hurt to run these two for loops anyway
        for i in range(6):
            self.state[OFFSET_HEALTH + i] = (OUR_TEAM_MAXHEALTH[i] != 0)*1.0
            self.state[OFFSET_HEALTH + TEAM_SIZE + i] = (OPPONENT_TEAM_MAXHEALTH[i] != 0)*1.0
            self.opp_state[OFFSET_HEALTH + TEAM_SIZE + i] = (OUR_TEAM_MAXHEALTH[i] != 0)*1.0
            self.opp_state[OFFSET_HEALTH + i] = (OPPONENT_TEAM_MAXHEALTH[i] != 0)*1.0
        for i in range(12):
            self.state[OFFSET_ITEM + i] = True
            self.opp_state[OFFSET_ITEM + i] = True
        def report_observation(observation):
            state_updates, self.our_active, self.opponent_active = self.preprocess_observation(observation)
            # Set force switch flag. pkmn will rely on this. 
            # It might be more efficient to just keep this in preprocess_observation_smogon.
            if self.opponent_active < 0:
                self.opponent_active += 10
                self.fs = True
            else:
                self.fs = False
            assert self.our_active in range(6), self.our_active
            assert self.opponent_active in range(6), self.opponent_active
            if (self.smogon):
                # check for a new Pokemon switching in. if it did, reset the stat boosts on the relevant side of the field.
                # This is irrelevant for the local version since we get the stat boosts as absolute numbers, but it is important for Smogon.
                # POSSIBLE BUG: WHAT IF IT GETS A STAT BOOST AND THEN SWITCHES OUT? THAT STAT BOOST WILL STILL BE APPLIED LATER.
                if len(self.our_actives) != 0 and self.our_active != self.our_actives[-1]:
                    for i in range(NUM_STAT_BOOSTS):
                        self.state[OFFSET_STAT_BOOSTS + i] = 0.0
                        self.opp_state[OFFSET_STAT_BOOSTS + NUM_STAT_BOOSTS + i] = 0.0
                if len(self.opponent_actives) != 0 and self.opponent_active != self.opponent_actives[-1]:
                    for i in range(NUM_STAT_BOOSTS):
                        self.state[OFFSET_STAT_BOOSTS + NUM_STAT_BOOSTS + i] = 0.0
                        self.opp_state[OFFSET_STAT_BOOSTS + i] = 0.0
            for update in state_updates:
                index, value = update
                if index >= OFFSET_MOVE and index < N:
                    # The value is the number of the last moves used. This takes values in the hundreds, so we better scale it down a little.
                    value = float(value)/1000.0
                # preprocess_observation returns its absolute stat boosts as integers,
                # while preprocess_observation_smogon returns its relative stat boosts as floats.
                if self.smogon and index >= OFFSET_STAT_BOOSTS and index < OFFSET_WEATHER:
                    assert(type(value) == float)
                    self.state[index] += float(value)
                else:
                    if index >= OFFSET_STATUS_CONDITIONS and index < OFFSET_STAT_BOOSTS and STATUS_LOOKUP[(index - OFFSET_STATUS_CONDITIONS) % NUM_STATUS_CONDITIONS] in RELATIVE_STATUS_CONDITIONS:
                        # We have a relative status condition. Is this Pokemon on the field?
                        temp = (index - OFFSET_STATUS_CONDITIONS) % NUM_STATUS_CONDITIONS
                        index_of_pokemon = ((index - OFFSET_STATUS_CONDITIONS - temp)/NUM_STATUS_CONDITIONS) % 6
                        if not (index_of_pokemon == self.our_active or index_of_pokemon == self.opponent_active):
                            # Status conditions largely do not increment if the Pokemon is not active
                            doNothing = True
                        elif value == 0.0:
                            self.state[index] = 0.0
                        else:
                            assert int(value) == 1, str(index) + " " + str(value)
                            self.state[index] += float(value)
                    else:
                        self.state[index] = float(value)
                # Switch around the index so it indexes into the opp_state correctly.
                # You could do this with modular arithmetic... but it's not clear that would be cleaner.
                if index < OFFSET_HEALTH + TEAM_SIZE:
                    index += TEAM_SIZE
                elif index < OFFSET_STATUS_CONDITIONS:
                    index -= TEAM_SIZE
                elif index < OFFSET_STATUS_CONDITIONS + TEAM_SIZE * NUM_STATUS_CONDITIONS:
                    index += TEAM_SIZE * NUM_STATUS_CONDITIONS
                elif index < OFFSET_STAT_BOOSTS:
                    index -= TEAM_SIZE * NUM_STATUS_CONDITIONS
                elif index < OFFSET_STAT_BOOSTS + NUM_STAT_BOOSTS:
                    index += NUM_STAT_BOOSTS
                elif index < OFFSET_WEATHER:
                    index -= NUM_STAT_BOOSTS
                elif index < OFFSET_TERRAIN:
                    # Weather and terrain are all-field things, we don't need to reverse them
                    doNothing = True
                elif index < OFFSET_HAZARDS:
                    doNothing = True
                elif index < OFFSET_HAZARDS + NUM_HAZARDS:
                    index += NUM_HAZARDS
                elif index < OFFSET_ITEM:
                    index -= NUM_HAZARDS
                elif index < OFFSET_ITEM + TEAM_SIZE:
                    index += TEAM_SIZE
                elif index < OFFSET_TRICK_ROOM:
                    index -= TEAM_SIZE
                elif index < OFFSET_GRAVITY:
                    doNothing = True
                elif index < OFFSET_MOVE:
                    doNothing = True
                elif index < OFFSET_MOVE + 1:
                    index += 1
                elif index < N:
                    index -= 1

                # Do the same thing we just did, except with opp_state.
                if self.smogon and index >= OFFSET_STAT_BOOSTS and index < OFFSET_WEATHER:
                    assert(type(value) == float)
                    self.opp_state[index] += float(value)
                else:
                    if index >= OFFSET_STATUS_CONDITIONS and index < OFFSET_STAT_BOOSTS and STATUS_LOOKUP[(index - OFFSET_STATUS_CONDITIONS) % NUM_STATUS_CONDITIONS] in RELATIVE_STATUS_CONDITIONS:
                        # We have a relative status condition. Is this Pokemon on the field?
                        temp = (index - OFFSET_STATUS_CONDITIONS) % NUM_STATUS_CONDITIONS
                        index_of_pokemon = ((index - OFFSET_STATUS_CONDITIONS - temp)/NUM_STATUS_CONDITIONS) % 6
                        if not(index_of_pokemon == self.our_active or index_of_pokemon == self.opponent_active):
                            # Status conditions largely do not increment if the Pokemon is not active
                            doNothing = True
                        elif value == 0:
                            self.opp_state[index] = 0.0
                        else:
                            assert int(value) == 1, str(index) + " " + str(value)
                            self.opp_state[index] += float(value)
                    else:
                        self.opp_state[index] = float(value)

            return self.state, self.opp_state
        return report_observation


