""" preprocess_observation for env_pkmn_smogon. Kept in its own separate file because it is long and has very little repeated code. """
import numpy as np
from pokedex import pokedex
from game_model import *

p1a_indices = {}
p2a_indices = {}
combinedIndices = {}
for i in range(6):
    p1a_indices[OUR_TEAM[i]] = i
    p1a_indices[i] = pokedex[OUR_TEAM[i]]['num']
    p2a_indices[OPPONENT_TEAM[i]] = i
    p2a_indices[i] = pokedex[OPPONENT_TEAM[i]]['num']
    combinedIndices[OUR_TEAM[i]] = OFFSET_HEALTH+i
    combinedIndices[OPPONENT_TEAM[i]] = OFFSET_HEALTH+i+6
status_flags = [False for i in range(OFFSET_STAT_BOOSTS-OFFSET_STATUS_CONDITIONS)]
fs = False

def preprocess_observation(I):
    # In this case, the string we get back from the Pokemon simulator does not give us the entire state
    # of the game. Instead it gives us the change in the state. So return a list.
    # Each element of the list contains two elements, the index of the state to update
    # and the value to update it to.
    retval = []
    # We also need to report the Pokemon that is on the field. Critically, we need to remember this from
    # turn to turn because we only get the Pokemon on the field when that Pokemon changes.
    # We could use this by encapsulating this in a class and using self.retval2, but I went with using global variables.
    global retval2
    global retval3
    global status_flags
    global fs
    # Force switch flag
    if (fs):
        retval3 += 10
    fs = False
    I = I.splitlines()
    for line in I:
        split_line = line.split('|')
        if 'forceswitch' in line.lower():  # TODO: SOMETHING A BIT LESS DRASTIC THAN LOWER? NOWADAYS I AM GETTING forceSwitch, WHICH IS WHY I ADDED THIS
            fs = True
        elif ('switch|' in line) or ('drag|' in line):
            # There is a new Pokemon on the field.
            if '|p1a' in line:
                assert '|p2a' not in line, line
                # This relevant_indices solution is not markedly more elegant than what it replaced.
                # In that respect, despite the rewrite, this section is still unsatisfying.
                # It should be easier to maintain, however.
                relevant_indices = p1a_indices
                relevant_offsets = [0,0]
            else:
                assert '|p2a' in line, line
                relevant_indices = p2a_indices
                relevant_offsets = [TEAM_SIZE, NUM_STATUS_CONDITIONS*TEAM_SIZE]
            # Update the pokemon on field
            name = split_line[2][5:].lower()
            index = pokedex[name]['num']
            for i in range(6):
                if relevant_indices[i] == index:
                    if relevant_indices == p1a_indices:
                        retval2 = i
                    else:
                        assert(relevant_indices == p2a_indices)
                        retval3 = i
            # And the health
            condition = split_line[4].split('/')[0].split(' ')
            health = int(condition[0])/([OUR_TEAM_MAXHEALTH, OPPONENT_TEAM_MAXHEALTH]['p2a' in line][relevant_indices[name]])
            assert health <= 1.0, health
            retval.append([OFFSET_HEALTH + relevant_offsets[0] + relevant_indices[name], health])
            # Remove status conditions which are removed by switch out TODO: EXPAND THIS
            for i in range(6):
                status_flags[relevant_offsets[1] + NUM_STATUS_CONDITIONS * i + STATUS_DICT["leechseed"]] = False
                status_flags[relevant_offsets[1] + NUM_STATUS_CONDITIONS * i + STATUS_DICT["confusion"]] = False
        elif 'damage|' in line or 'heal|' in line:
            if 'Substitute' not in line: #TODO: HANDLE SUBSTITUTE
                name = split_line[2][5:].lower()
                if '|p1a' in line:
                    assert '|p2a' not in line, line
                    # This relevant_indices solution is not markedly more elegant than what it replaced.
                    # In that respect, despite the rewrite, this section is still unsatisfying.
                    # It should be easier to maintain, however.
                    relevant_indices = p1a_indices
                    relevant_offsets = [0,0]
                else:
                    assert '|p2a' in line, line
                    relevant_indices = p2a_indices
                    relevant_offsets = [TEAM_SIZE, NUM_STATUS_CONDITIONS*TEAM_SIZE]

                if split_line[-1][0] == '[':
                    # The simulator is telling us the source of the damage
                    health = 0
                    if 'fnt' not in split_line[3]:
                        print(split_line)
                        health = int(split_line[3].split('/')[0])/([OUR_TEAM_MAXHEALTH, OPPONENT_TEAM_MAXHEALTH]['p2a' in line][relevant_indices[name]])
                    else:
                        # Remove all status conditions
                        for i in range(NUM_STATUS_CONDITIONS):
                            status_flags[relevant_offsets[1] + NUM_STATUS_CONDITIONS * relevant_indices[name] + i] = False
                    assert health <= 1.0, health
                    retval.append([combinedIndices[name], health])
                else:
                    if 'fnt' in split_line[-1]:
                        health = 0
                        retval.append([combinedIndices[name], health])
                        for i in range(NUM_STATUS_CONDITIONS):
                            status_flags[relevant_offsets[1] + NUM_STATUS_CONDITIONS * relevant_indices[name] + i] = False
                    else:
                        health = int(split_line[-1].split('/')[0])/([OUR_TEAM_MAXHEALTH, OPPONENT_TEAM_MAXHEALTH]['p2a' in line][relevant_indices[name]])
                        assert health <= 1.0, health
                        retval.append([combinedIndices[name], health])
        elif 'status|' in line:
            name = split_line[2][5:].lower()
            if '|p1a' in line:
                assert '|p2a' not in line, line
                relevant_indices = p1a_indices
                relevant_offset = 0
            else:
                assert '|p2a' in line, line
                relevant_indices = p2a_indices
                relevant_offset =NUM_STATUS_CONDITIONS*TEAM_SIZE
            # Assert that if we are curing a status, then we have that status to begin with.
            if 'curestatus|' in line:
                assert(status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[split_line[3]]])
            else:
                assert not status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[split_line[3]]], str(relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[split_line[3]]) + " " + str(status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[split_line[3]]])
            # If status is in the line, either the status has started or it has been cured. If it started, then curestatus is not in the line.
            status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[split_line[3]]] =  'curestatus|' not in line
        elif 'unboost|' in line:
            # Note: this gives relative boost, not absolute.
            name = split_line[2][5:].lower()
            retval.append([OFFSET_STAT_BOOSTS + ('|p2a' in line)*NUM_STAT_BOOSTS + BOOST_DICT[split_line[3]], -1 * float(split_line[4])])
        elif 'boost|' in line:
            if 'Swarm' not in line:
                name = split_line[2][5:].lower()
                retval.append([OFFSET_STAT_BOOSTS + ('|p2a' in line)*NUM_STAT_BOOSTS + BOOST_DICT[split_line[3]], float(split_line[4])])
        elif 'weather|' in line:
            if 'upkeep' in line:
                # the weather has stopped
                retval.append([OFFSET_WEATHER, 1])
                for i in range(1, NUM_WEATHER):
                    retval.append([OFFSET_WEATHER + i, 0])
            else:
                # The weather has started
                retval.append([OFFSET_WEATHER, 0])
                for i in range(1, NUM_WEATHER):
                    retval.append([OFFSET_WEATHER + i, i == WEATHER_DICT[split_line[2][:-1].lower()]])
        elif 'fieldstart|' in line:
            retval.append([OFFSET_TERRAIN +0, 0])
            for i in range(1, NUM_TERRAIN):
                retval.append([OFFSET_TERRAIN+i, TERRAIN_LOOKUP[split_line[2]] == i])
        elif 'fieldend|' in line:
            retval.append([OFFSET_TERRAIN, 1])
            for i in range(1,NUM_TERRAIN):
                retval.append([OFFSET_TERRAIN+i, 0])
        elif 'sidestart|' in line:
            #hazard = split_line[-1][:-1].lower()  # TODO: FIGURE OUT WHY THIS [:-1] WAS EVER THERE
            hazard = split_line[-1].lower()
            retval.append([OFFSET_HAZARDS + HAZARD_LOOKUP[hazard] + NUM_HAZARDS * ('|p2' in line), 1])
            assert (('|p2' in line) != ('|p1' in line)), line
        elif 'sideend|' in line:
            hazard = split_line[-1][:-1].lower()
            retval.append([OFFSET_HAZARDS + HAZARD_LOOKUP[hazard] + NUM_HAZARDS * ('|p2' in line), 0])
            assert (('|p2' in line) != ('|p1' in line)), line
        elif 'enditem|' in line:
            name = split_line[2][5:].lower()
            if '|p1a' in line:
                # This relevant_indices solution is not markedly more elegant than what it replaced.
                # In that respect, despite the rewrite, this section is still unsatisfying.
                # It should be easier to maintain, however.
                relevant_indices = p1a_indices
            else:
                assert '|p2a' in line, line
                relevant_indices = p2a_indices
            retval.append([OFFSET_ITEM + ('|p2a' in line) * TEAM_SIZE + relevant_indices[name], False])
            assert (('|p2a' in line) != ('|p1a' in line)), line
        elif '-start' in line:
            # Leech seed? Maybe wrap.
            name = split_line[2][5:].lower()
            if '|p1a' in line:
                assert '|p2a' not in line, line
                relevant_indices = p1a_indices
                relevant_offset = 0
            else:
                assert '|p2a' in line, line
                relevant_indices = p2a_indices
                relevant_offset =NUM_STATUS_CONDITIONS*TEAM_SIZE
            # Assert that if we have a new condition, we don't already have that condition.
            if split_line[3].find(" ") != -1:
                split_line[3] = split_line[3][split_line[3].index(" "):]
            condition = split_line[3].lower().replace(" ", "")
            assert(not status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[condition]])
            status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[condition]] =  True
            if len(split_line) == 5:
                if split_line[4] == "[fatigue]":
                    status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT["lockedmove"]] =  False

        elif "|-end|" in line:
            name = split_line[2][5:].lower()
            if '|p1a' in line:
                assert '|p2a' not in line, line
                relevant_indices = p1a_indices
                relevant_offset = 0
            else:
                assert '|p2a' in line, line
                relevant_indices = p2a_indices
                relevant_offset =NUM_STATUS_CONDITIONS*TEAM_SIZE
            if split_line[3].find(" ") != -1:
                split_line[3] = split_line[3][split_line[3].index(" "):]
            # Assert that if we are losing a condition, we already have that condition.
            condition = split_line[3].lower().replace(" ", "")
            assert(status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[condition]])
            status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT[condition]] =  False
        elif "|move|" in line:
            # A lot of this code is repeated. Refactor???
            move = split_line[3].lower()
            if move in LOCKED_MOVES: # This will almost never be true. But when it is, it is important because we have no other clues that the opponent is locked into outrage.
                name = split_line[2][5:].lower()
                if 'p1a' in split_line[2]:
                    assert 'p2a' not in split_line[2], line
                    relevant_indices = p1a_indices
                    relevant_offset = 0
                else:
                    assert 'p2a' in split_line[2], line
                    relevant_indices = p2a_indices
                    relevant_offset =NUM_STATUS_CONDITIONS*TEAM_SIZE
                # We don't assert this flag isn't already true, because it might be
                status_flags[relevant_offset + NUM_STATUS_CONDITIONS * relevant_indices[name] + STATUS_DICT['lockedmove']] =  True


    # Technically, there is also a -prepare flag we might theoretically need to check for. But whenever such a flag is in use, we have only one option on the next turn. So how about let's not implement that?
    # We don't need a force switch flag in preprocess_observation since we have an action space.
    # So communicate this to the bookkeeper by making retval3 illegal.
    if fs:
        retval3 -= 10
    for i in range(OFFSET_STATUS_CONDITIONS, OFFSET_STAT_BOOSTS):
        retval.append([i, status_flags[i - OFFSET_STATUS_CONDITIONS]])
    return retval, retval2, retval3
