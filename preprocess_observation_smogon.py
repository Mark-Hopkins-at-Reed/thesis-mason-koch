""" preprocess_observation for env_pkmn_smogon. Kept in its own separate file because it is long and has very little repeated code. """
import numpy as np
from pokedex import pokedex
from game_model import *
from moves import BattleMoveDex

p1a_indices = {}
p2a_indices = {}
combinedIndices = {}
for i in range(6):
    p1a_indices[OUR_TEAM[i]] = i
    p1a_indices[i] = pokedex[OUR_TEAM[i].replace(" ", "")]['num']
    p2a_indices[OPPONENT_TEAM[i]] = i
    p2a_indices[i] = pokedex[OPPONENT_TEAM[i].replace(" ", "")]['num']
    combinedIndices[OUR_TEAM[i]] = OFFSET_HEALTH+i
    combinedIndices[OPPONENT_TEAM[i]] = OFFSET_HEALTH+i+6
status_flags = [False for i in range(OFFSET_STAT_BOOSTS-OFFSET_STATUS_CONDITIONS)]
fs = False

def handle_status(line, split_line, truth_value):
    name = split_line[2][5:].lower()
    if 'p1a' in split_line[2]:
        assert 'p2a' not in split_line[2], line
    else:
        assert 'p2a' in split_line[2], line
    # Convert move: Attract into Attract
    if split_line[3].find(" ") != -1 and split_line[3][0] == 'm':
        split_line[3] = split_line[3][split_line[3].index(" "):]
    # Remove dashes and spaces
    split_line[3] = split_line[3].lower().replace(" ", "").replace("-", "")
    # Handling mummy would be a good idea, but there is no time to implement this
    if 'mummy' not in split_line[3]: status_flags[NUM_STATUS_CONDITIONS * combinedIndices[name] + STATUS_DICT[split_line[3]]] =  truth_value
    # Handle fatigue
    if len(split_line) == 5:
        if split_line[4] == "[fatigue]":
            status_flags[NUM_STATUS_CONDITIONS * combinedIndices[name] + STATUS_DICT["lockedmove"]] = False
def handleMove(split_line):
    if 'p1a' in split_line[2]:
        assert 'p2a' not in split_line[2], line
    else:
        assert 'p2a' in split_line[2], line
    split_line[3] = split_line[3].lower()
    # Convert move: Attract into Attract
    if split_line[3].find(" ") != -1 and split_line[3][0:4] == 'move':
        split_line[3] = split_line[3][split_line[3].index(" "):]
    split_line[3] = split_line[3].replace(" ", "").replace("-", "")
    return [OFFSET_MOVE + ('p2a' in split_line[2]), BattleMoveDex[split_line[3]]]

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
    # These conditions go away unless done repeatedly. TODO: BUT WHAT IT THIS IS AN OPPONENT'S SWITCH REQUEST?
    for condition in REPEATED_STATUS_CONDITIONS:
        for i in range(TEAM_SIZE*2):
            status_flags[i * NUM_STATUS_CONDITIONS + STATUS_DICT[condition]] = False
    # Set the last move to -1 (i.e. no move). If we use a move, this update will be overriden.
    retval.append([OFFSET_MOVE, -1])
    retval.append([OFFSET_MOVE+1, -1])
    I = I.splitlines()
    for v in range(len(I)):
        line = I[v]
        split_line = line.split('|')
        if 'forceswitch' in line.lower():
            fs = True
        elif ('switch|' in line and 'voltswitch|' not in line) or ('drag|' in line):
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
            index = pokedex[name.replace(" ", "")]['num'] # Handle tapu koko
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
                # There is an edge case where we cure a relative status and then get it again. Handle that edge case here.
                retval.append([OFFSET_STATUS_CONDITIONS + relevant_offset + relevant_indices[name] + STATUS_DICT[split_line[3]], False])
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
            assert split_line[2].lower() in WEATHER_DICT, line
            for i in range(0, NUM_WEATHER):
                retval.append([OFFSET_WEATHER + i, i == WEATHER_DICT[split_line[2].lower()]])
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
            hazard = split_line[-1].lower()
            retval.append([OFFSET_HAZARDS + HAZARD_LOOKUP[hazard] + NUM_HAZARDS * ('|p2' in line), 0])
            assert (('|p2' in line) != ('|p1' in line)), line
        elif 'enditem|' in line:
            name = split_line[2][5:].lower()
            if '|p1a' in line:
                assert '|p2a' not in line, line
            else:
                assert '|p2a' in line, line
            retval.append([OFFSET_ITEM + combinedIndices[name], False])
            if split_line[3] == "Micle Berry":
                if len(split_line) == 5 and split_line[4] == "[eat]":
                    status_flags[NUM_STATUS_CONDITIONS * combinedIndices[name] + STATUS_DICT['micleberry']] = True
        elif '-start' in line or "|-activate|" in line:
            handle_status(line, split_line, True)
        elif "|-end|" in line:
            # Future Sight and Doom Desire are a dumb special case we can't really handle in handle_status
            # because it starts on one team and ends on the other
            name = split_line[2][5:].lower()
            if split_line[3] == "move: Future Sight" or split_line[3] == "move: Doom Desire":
                # We don't know who started this move, so set them all to false
                for i in range(TEAM_SIZE):
                    status_flags[('p1a' in line)*NUM_STATUS_CONDITIONS*TEAM_SIZE + NUM_STATUS_CONDITIONS * i + STATUS_DICT['futuremove']] =  False
            else:
                handle_status(line, split_line, False)
        elif "|move|" in line:
            move = split_line[3].lower()
            move = move.replace(" ", "").replace("-", "")
            retval.append(handleMove(split_line))
            if move in LOCKED_MOVES:
                handle_status(line, split_line, True)
            elif move in STALL_MOVES:
                handle_status(line, split_line, 'fail' not in I[v+1])
            elif move == 'iceball':
                handle_status(line, split_line, 'debug' in I[v+1])
            elif move == 'furycutter':
                handle_status(line, split_line, ('activate' not in I[v+1]) and ('miss' not in I[v+1])) # Check for protect and missing
        elif "|-endability|" in line:
            handle_status(line, split_lines, False)
    # Technically, there is also a -prepare flag we might theoretically need to check for. But whenever such a flag is in use, we have only one option on the next turn. So how about let's not implement that?
    # We don't need a force switch flag in preprocess_observation since we have an action space.
    # So communicate this to the bookkeeper by making retval3 illegal.
    if fs:
        retval3 -= 10
    for i in range(OFFSET_STATUS_CONDITIONS, OFFSET_STAT_BOOSTS):
        retval.append([i, status_flags[i - OFFSET_STATUS_CONDITIONS]])
    return retval, retval2, retval3
