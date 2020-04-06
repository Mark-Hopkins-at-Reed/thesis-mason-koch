""" Trains an agent with stochastic policy gradients on Pokemon. Interface inspired by OpenAI Gym.
    Some elements of https://gist.github.com/karpathy/a4166c7fe253700972fcbc77e4ea32c5 made their way in here.
"""
import numpy as np
import pickle
import sys
import os
assert(len(sys.argv) <= 2)
if len(sys.argv) == 2:
    assert(sys.argv[1] == "smogon")
    # It drives me nuts that this variables is in the global namespace,
    # yet it is so
    from env_pkmn_smogon import Env as pkmn_env
    from preprocess_observation_smogon import preprocess_observation
else:
    from env_pkmn import Env as pkmn_env
    from preprocess_observation import preprocess_observation
from bookkeeper import Bookkeeper
from game_model import *
from interpret_state import interpret_state
# hyperparameters
H = 64       # number of hidden layer neurons
H2 = 32      # number of hidden layer neurons in second layer
A = 10       # number of actions (one of which, switching to the current pokemon, is always illegal)
batch_size = 1000 # every how many episodes to do a param update?
learning_rate = 1e-9
gamma = 0.99 # discount factor for reward
decay_rate = 0.99 # decay factor for RMSProp leaky sum of grad^2
exploration_threshold = 28 # 28 is mostly exploitation. 29 is more exploration.
max_gradient_norm = 1e0
np.random.seed(108)
env_seed = 42
resume = True        # resume from previous checkpoint?
debug = False         # print debug info
subtract_mean = False # subtract the mean of the last thousand rewards from the reward.
std_div = True        # if true, divide discounted rewards by their standard deviation.
div_prob = True       # if true, divide rewards by probability of the action taken
use_rmsprop = False   # if true, use rmsprop. If false, use standard gradient descent.
default_starting_pokemon = True # if true, return team 123. Else, try to learn which team to start with.
learning_by_pair = False  # if true, adjust the learning rate for neural net [i][j] by how often it was picked. Ultimately I did not take this route.
dlrflag = False           # if true, multiply gradients for each of our Pokemon by the relevant entry. Ultimately I did not take this route.
grad_clip = True          # if true, declare there to be a maximum norm for any given gradient
opponent_exploration = True # If true, the opponent has the same exploration threshold as the AI that is training.
dlr = [100.0, 100.0, np.NaN, 1.0, 100.0, np.NaN]
# This could be done in the if statement above, but keeping the flags together in one place is nice
if len(sys.argv) == 2:
    debug = True

# relu hidden layer. should be easily swappable with, for instance, sigmoid_hidden_layer (not included).
def relu_hidden_layer(weights, biases, x):
    # Assert that the inputs have the right shape. e.g. shape of (9,) is not allowed.
    assert(len(weights.shape) == 2)
    assert(len(biases.shape) == 2 and biases.shape[1] == 1)
    assert(len(x.shape) == 2 and x.shape[1] == 1)
    retval = weights @ x + biases
    retval[retval<0] = 0
    return retval

# the counterpart of relu_hidden_layer
def backprop_relu_hidden_layer(delta, weights, h):
    # Assert that the inputs have the right shape. (Not checking that, for instance, h and retval have
    # the same shape. That would be pointless extra code).
    assert(len(delta.shape) == 2)
    assert(len(weights.shape) == 2)
    assert(len(h.shape) == 2)
    retval = weights.T @ delta
    retval[h <= 0] = 0
    return retval

# this assumes the game has a reward only at the end, which is not unusual.
# this code is much better suited to rewards that are sparse or have more
# than one game. it would be cleaner to change this, although this is
# low priority.
def discount_rewards(r):
    """ take 1D float array of rewards and compute discounted reward """
    discounted_r = np.zeros_like(r)
    running_add = 0
    for t in reversed(range(0, r.size)):
        if r[t] != 0: running_add = 0 # reset the sum, since this was a game boundary.
        running_add = running_add * gamma + r[t]
        discounted_r[t] = running_add
    return discounted_r

def policy_forward(x, cur_model):
    # Neural network begins here
    h = relu_hidden_layer(cur_model['W1'], cur_model['b1'], x)
    h2 = relu_hidden_layer(cur_model['W2'], cur_model['b2'], h)
    # Neural network ends here.
    # Output layer.
    pvec = np.dot(cur_model['W3'], h2) + cur_model['b3']
    # Return the probability vector and the hidden state. 
    # The latter is not strictly necessary, but it will make our lives easier
    return pvec, h, h2

def policy_backward(bookkeeper):
    retval = [[{} for i in range(TEAM_SIZE)] for j in range(TEAM_SIZE)]
    # Load data from bookkeeper
    xs = bookkeeper.xs
    hs = bookkeeper.hs
    h2s = bookkeeper.h2s
    # This is a fancy way of getting pvecs to be equal to bookkeeper.pvecs the value, but not equal to bookkeeper.pvecs the object.
    pvecs = [x + 0.0 for x in bookkeeper.pvecs]
    actions = np.vstack(bookkeeper.actions)
    rewards = np.vstack(bookkeeper.rewards)
    our_actives = bookkeeper.our_actives
    opponent_actives = bookkeeper.opponent_actives
    assert(np.sum(rewards) == 1.0 or np.sum(rewards) == -1.0)
    assert(rewards[-1] == 1.0 or rewards[-1] == -1.0)
    if subtract_mean: rewards[-1] -= np.mean(bookkeeper.reward_list)  # Subtract mean of the last thousand rewards.
    discounted_rewards = discount_rewards(rewards.ravel())
    if std_div: discounted_rewards /= np.std(discounted_rewards) # Candidate for deletion
    # Assert they are all the same length
    assert(len(xs) == len(hs))
    assert(len(xs) == len(h2s))
    assert(len(xs) == len(pvecs))
    assert(len(xs) == len(actions))
    assert(len(xs) == len(rewards))
    assert(len(xs) == len(our_actives))
    assert(len(xs) == len(opponent_actives))
    # The idea is similar to https://web.stanford.edu/class/cs224n/readings/gradient-notes.pdf?fbclid=IwAR2pPF1cbaCMVrdi0qM8lj4xHDDA0uzZem2sjNReUtzdNDKDe7gg5h70sco.
    # We don't know what y is, but we can guess based on whether we won or lost.
    for i in range(discounted_rewards.shape[0]):
        assert(pvecs[i][actions[i][0]] == bookkeeper.pvecs[i][actions[i][0]])
        pvecs[i][actions[i][0]] -= discounted_rewards[i]
        assert(pvecs[i][actions[i][0]] != bookkeeper.pvecs[i][actions[i][0]])
        if div_prob: pvecs[i] /= bookkeeper.pvecs[i][actions[i][0]]
    # Weight the gradients with respect to each action with respect to how often they were legal.
    # So, if an action was mostly illegal, its gradients will be puffed up bigly. This code might
    # make it in to the final version, it might not.
    #for i in range(A):
    #    if bookkeeper.legal_action_lists[our_active][opponent_active][i] != 0:
    #        for pvec in pvecs:
    #            pvec[i] *= bookkeeper.legal_counts[our_active][opponent_active] / bookkeeper.legal_action_lists[our_active][opponent_active][i]
    for i in range(len(xs)):
        # The naming conventions are different from the cs224 notes. The ordering of the delta is reversed.
        delta3 = pvecs[i]
        delta2 = backprop_relu_hidden_layer(delta3, list_of_models[our_actives[i]][opponent_actives[i]]['W3'], h2s[i])
        dW3 = delta3 @ h2s[i].T
        db3 = np.sum(delta3,1)  #MAYBE NOT NEEDED???
        db3.shape = (db3.shape[0], 1)
        delta1 = backprop_relu_hidden_layer(delta2, list_of_models[our_actives[i]][opponent_actives[i]]['W2'], hs[i])
        dW2 = delta2 @ hs[i].T
        db2 = np.sum(delta2,1)
        db2.shape = (db2.shape[0], 1)
        dW1 = delta1 @ xs[i].T
        db1 = np.sum(delta1,1)
        db1.shape = (db1.shape[0], 1)
        if 'W1' not in retval[our_actives[i]][opponent_actives[i]]:
            retval[our_actives[i]][opponent_actives[i]] = {'W1':dW1, 'W2':dW2, 'W3':dW3, 'b1': db1, 'b2':db2, 'b3':db3}
        else:
            for k in retval[our_actives[i]][opponent_actives[i]]:
                retval[our_actives[i]][opponent_actives[i]][k] += {'W1':dW1, 'W2':dW2, 'W3':dW3, 'b1': db1, 'b2':db2, 'b3':db3}[k]
    return retval

def construct_environment():
    env = pkmn_env()
    env.seed(env_seed)
    if len(sys.argv) == 2:
        # env_smogon's reset does not accept any arguments.
        observation = env.reset()
    else:
        # env.reset accepts an argument, namely your team selection.
        # This is more convenient than having a special team-selection
        # method that only runs once.
        observation = env.reset(choose_starting_pokemon())
    return env, observation

class RmsProp:
    def __init__(self, cur_model):
       self.grad_buffer = [[{ k : np.zeros_like(v) for k,v in cur_model.items() } for i in range(6)] for j in range(6)]
       if use_rmsprop: self.rmsprop_cache = [[{ k : np.zeros_like(v) for k,v in cur_model.items() } for i in range(6)] for j in range(6)]
       self.games_won = 0
    # this function is specific to rmsprop.
    def step(self, grad, reward, bookkeeper):
        for i in range(6):
            for j in range(6):
                mult = 1.0
                if learning_by_pair: mult /= (np.sum([bookkeeper.our_actives[l] == i and bookkeeper.opponent_actives[l] == j for l in range(len(bookkeeper.our_actives))])/len(bookkeeper.our_actives))
                for k in grad[i][j]:
                    self.grad_buffer[i][j][k] += grad[i][j][k]*mult
        # Increment the number of games we have played with this lead by 1.
        starting_pokemon_wincount[our_pvec_index[0]][1] += 1.0 
        if reward == 1.0:
            self.games_won += reward
            # If we won, increment the number of games we have won with this lead by 1.
            starting_pokemon_wincount[our_pvec_index[0]][0] += reward
        else:
            assert(reward == -1.0)
        if bookkeeper.episode_number % batch_size == 0:
            print(self.games_won)
            self.games_won = 0
            for i in range(6):
                for j in range(6):
                    mult = 1.0
                    if dlrflag: mult *= dlr[i]
                    if grad_clip:
                        ss = 0.0
                        for k in self.grad_buffer[i][j]:
                            ss += np.sum(np.square(self.grad_buffer[i][j][k]))
                        if (np.sqrt(ss)/batch_size) * learning_rate > max_gradient_norm:
                            mult *= max_gradient_norm/np.sqrt(ss)
                    for k,v in list_of_models[i][j].items():
                        g = self.grad_buffer[i][j][k] * mult # gradient
                        if use_rmsprop:
                            self.rmsprop_cache[i][j][k] = decay_rate * self.rmsprop_cache[i][j][k] + (1 - decay_rate) * g**2
                            list_of_models[i][j][k] -= learning_rate * g / (np.sqrt(self.rmsprop_cache[i][j][k]) + 1e-5)
                            self.grad_buffer[i][j][k] = np.zeros_like(v) # reset batch gradient buffer
                        else:
                            list_of_models[i][j][k] -= learning_rate * g

def choose_action(x, bookkeeper, action_space):
    #if len(action_space) == 1: # This code also might or might not make it into the final version.
    #    return action_space[0]
    # This neural network outputs the log probabilities of taking each action.
    cur_model = list_of_models[bookkeeper.our_active][bookkeeper.opponent_active]
    pvec, h, h2 = policy_forward(x, cur_model)
    # This assumes, of course, a specific team.
    # Remove illegal actions from our probability vector and then normalise it.
    if len(sys.argv) == 2:
        # Don't switch to the current Pokemon
        for i in range(12):
            print(x[i])
        pvec[4+bookkeeper.our_active] = float("-inf")
        for i in range(6):
            if x[i] == 0:
                # Don't switch to a fainted Pokemon
                pvec[4+i]=float("-inf")
                # If the fainted Pokemon is the active Pokemon, we cannot use moves either
                if i == bookkeeper.our_active:
                    for j in range(4):
                        pvec[j] = float("-inf")
        # check for force switch flag
        if bookkeeper.fs:
            for j in range(4):
                pvec[j] = float("-inf")
        # check for running out of pp or being trapped
        for i in range(A):
            assert(len(action_space) == A)
            if action_space[i]:
                pvec[i] = float("-inf")
    else:
        for i in range(len(POSSIBLE_ACTIONS)):
            if POSSIBLE_ACTIONS[i] not in action_space:
                pvec[i] = float("-inf")
    pvec_max = np.max(pvec)
    for i in range(len(pvec)):
        if pvec[i] != float("-inf"):
            # This ensures that there is at least one action of value 32, and no actions
            # with values greater than 32.
            pvec[i] -= pvec_max - 32
            # If we are training, we can do some exploration instead of exploitation.
            # If we have 9 legal actions (the most possible) and one of them is clearly
            # superior, then that action will be picked ~87% of the time. This should be
            # enough for some exploration but mostly exploitation.
            if len(sys.argv) == 1:
                pvec[i] = max(pvec[i], exploration_threshold)
    pvec = np.exp(pvec)
    if debug:
        print("OUR SIDE PVEC")
        print(pvec)
    pvec = pvec/np.sum(pvec)
    if __name__ != '__main__':
        return pvec
    #legal_action_list = [] # This might make it in to the final version, might not.
    #for i in range(len(POSSIBLE_ACTIONS)):
    #    legal_action_list.append(POSSIBLE_ACTIONS[i] in action_space)
    # Ravel because np.random.choice does not recognise an nx1 matrix as a vector.
    action_index = np.random.choice(range(A), p=pvec.ravel())
    bookkeeper.report(x, h, h2, pvec, action_index)#,legal_action_list)
    return POSSIBLE_ACTIONS[action_index]

def opponent_choose_action(x, bookkeeper, action_space):
    cur_opponent_model = list_of_opponent_models[bookkeeper.opponent_active][bookkeeper.our_active]
    # like choose_action, except we use a different model, cite different constants,
    # and don't report anything to the bookkeeper
    pvec, h, h2 = policy_forward(x, cur_opponent_model)
    for i in range(len(OPPONENT_POSSIBLE_ACTIONS)):
        if OPPONENT_POSSIBLE_ACTIONS[i] not in action_space:
            pvec[i] = float("-inf")
    pvec_max = np.max(pvec)
    for i in range(len(pvec)):
        if pvec[i] != float("-inf"):
            # This ensures that there is at least one action of value 32, and no actions
            # with values greater than 32.
            pvec[i] -= pvec_max - 32
            if opponent_exploration:
                pvec[i] = max(pvec[i], exploration_threshold)
    pvec = np.exp(pvec)
    if debug:
        print("OPPONENT SIDE PVEC")
        print(pvec)
    pvec = pvec/np.sum(pvec)
    if __name__ != '__main__':
        return pvec
    action_index = np.random.choice(range(A), p=pvec.ravel())
    return OPPONENT_POSSIBLE_ACTIONS[action_index]

def run_reinforcement_learning():
    env, observation = construct_environment()
    report_observation = bookkeeper.construct_observation_handler()
    grad_descent = RmsProp(list_of_models[0][0])  # The [0][0] model is arbitrary, we are using it for its items
    while True:
        if len(sys.argv) == 2:
            x, _ = report_observation(observation)
            print(interpret_state(x, bookkeeper.our_active, bookkeeper.opponent_active, OUR_TEAM, OPPONENT_TEAM))
            if len(env.action_space) == A:
                action = choose_action(x, bookkeeper, env.action_space)
                observation, reward, done, info = env.step(action)
            else:
                assert(len(env.action_space) == 0)
                observation, reward, done, info = env.step("nothing")
        else:
            assert(len(env.action_space) + len(env.opponent_action_space) > 0)
            x, opp_x = report_observation(observation)
            if debug:
                interpretation = interpret_state(x, bookkeeper.our_active, bookkeeper.opponent_active, OUR_TEAM, OPPONENT_TEAM).split("\n")
                opponent_interpretation = interpret_state(opp_x, bookkeeper.opponent_active, bookkeeper.our_active, OPPONENT_TEAM, OUR_TEAM).split("\n")
                assert interpretation[0] == opponent_interpretation[1], str(interpretation) + str(opponent_interpretation)
                assert interpretation[1] == opponent_interpretation[0], str(interpretation) + str(opponent_interpretation)
                assert interpretation[2] == opponent_interpretation[2], str(interpretation) + str(opponent_interpretation)
                print(interpretation)
            if len(env.action_space) > 0:
                # Our AI needs to choose a move
                action = choose_action(x, bookkeeper, env.action_space)
            else:
                action = ''
            if len(env.opponent_action_space) > 0:
                # Our opponent needs to make a move
                opponent_action = opponent_choose_action(opp_x, bookkeeper, env.opponent_action_space)
            else:
                opponent_action = ''
            if debug: print(opponent_action + "|" + action)
            # We want to remember if we took an action when we report the reward. 
            # Need to remember this because the length of the action space will change.
            lenenv = len(env.action_space)
            observation, reward, done, info = env.step(opponent_action + "|" + action)
            bookkeeper.report_reward(reward, lenenv > 0)#1) # 1 might make it in to the final version, might not.
        if done: # an episode finished
            if len(sys.argv) == 2:
                break
            # Give backprop everything it could conceivably need
            grad = policy_backward(bookkeeper)
            grad_descent.step(grad, reward, bookkeeper)
            observation = env.reset(choose_starting_pokemon()) # reset env
            report_observation = bookkeeper.construct_observation_handler()
            bookkeeper.signal_episode_completion(starting_pokemon_wincount)
def choose_starting_pokemon():
    assert(len(starting_pokemon_wincount) == len(opponent_starting_pokemon_wincount))
    # Our x vector will always be the same here (we are in team preview).
    # This method of deciding is arbitrary.
    our_pvec = [(starting_pokemon_wincount[i][0] / starting_pokemon_wincount[i][1])*(starting_pokemon_wincount[i][0] / starting_pokemon_wincount[i][1]) for i in range(len(starting_pokemon_wincount))]
    our_pvec /= np.sum(our_pvec)
    opponent_pvec = [(opponent_starting_pokemon_wincount[i][0] / opponent_starting_pokemon_wincount[i][1]) * (opponent_starting_pokemon_wincount[i][0] / opponent_starting_pokemon_wincount[i][1]) for i in range(len(opponent_starting_pokemon_wincount))]
    opponent_pvec /= np.sum(opponent_pvec)
    our_pvec_index[0] = np.random.choice(range(len(our_pvec)), p=our_pvec)
    opponent_pvec_index = np.random.choice(range(len(opponent_pvec)), p=opponent_pvec)
    if default_starting_pokemon: return ["team 1234", "team 2134", "team 3124", "team 4123"][0] + "|" + ["team 1234", "team 2134", "team 3124", "team 4123"][0]
    return ["team 1234", "team 2134", "team 3124", "team 4123"][our_pvec_index[0]] + "|" + ["team 1234", "team 2134", "team 3124", "team 4123"][opponent_pvec_index]


# model initialization. this will look very different game to game. 
# personally I would define a numpy array W and access its elements 
# like W[1] and W[2], but a dictionary is not strictly wrong.
if resume:
    list_of_models, our_team1, opponent_team1, starting_pokemon_wincount = pickle.load(open('save.p', 'rb'))
    list_of_opponent_models, opponent_team2, our_team2, opponent_starting_pokemon_wincount = pickle.load(open('save_opponent.p', 'rb'))
    # check for loaded file compatibility
    assert(np.all(our_team1 == our_team2))
    assert(np.all(opponent_team1 == opponent_team2))
    assert(np.all(our_team1 == OUR_TEAM))
    assert(np.all(opponent_team1 == OPPONENT_TEAM))
    our_pvec_index = [""]      # It is easier to make these variables global. Because they are!
    opponent_pvec_index = "" # This one doesn't strictly need to be global?
else:
    assert(not os.path.isfile('save.p'))
    assert(not os.path.isfile('save_opponent.p'))
    # Food for thought: turn this into a really ugly list comprehension?
    list_of_models = []
    list_of_opponent_models = []
    for i in range(6):
        model_row = []
        opponent_model_row = []
        for j in range(6):
            _ = {}
            MULT=1.0
            _['W1'] = MULT*np.random.randn(H,N) / np.sqrt(N) # "Xavier" initialization
            _['b1'] = MULT*np.random.randn(H) / np.sqrt(H)
            _['b1'].shape = (H,1)  # Stop numpy from projecting this vector onto matrices
            _['W2'] = MULT*np.random.randn(H2,H) / np.sqrt(H2)
            _['b2'] = MULT*np.random.randn(H2) / np.sqrt(H2)
            _['b2'].shape = (H2,1)
            _['W3'] = MULT*np.random.randn(A, H2) / np.sqrt(H2)
            _['b3'] = MULT*np.random.randn(A) / np.sqrt(A)
            _['b3'].shape = (A,1)
            model_row.append(_)

            MULT = 1.0 # Make our opponent more random
            _ = {}
            _['W1'] = MULT*np.random.randn(H,N) / np.sqrt(N)
            _['b1'] = MULT*np.random.randn(H) / np.sqrt(H)
            _['b1'].shape = (H,1)
            _['W2'] = MULT*np.random.randn(H2,H) / np.sqrt(H2)
            _['b2'] = MULT*np.random.randn(H2) / np.sqrt(H2)
            _['b2'].shape = (H2,1)
            _['W3'] = MULT*np.random.randn(A, H2) / np.sqrt(H2)
            _['b3'] = MULT*np.random.randn(A) / np.sqrt(A)
            _['b3'].shape = (A,1)
            opponent_model_row.append(_)
        list_of_models.append(model_row)
        list_of_opponent_models.append(opponent_model_row)
    starting_pokemon_wincount = [[1.0,2.0], [1.0,2.0], [1.0,2.0]]
    opponent_starting_pokemon_wincount = [[1.0,2.0], [1.0,2.0], [1.0,2.0]]
    our_pvec_index = [""]      # It is easier to make these variables global. Because they are!
    opponent_pvec_index = ""   # This one doesn't strictly need to be global.
    pickle.dump((list_of_models, OUR_TEAM, OPPONENT_TEAM, starting_pokemon_wincount), open('save.p', 'wb'))
    pickle.dump((list_of_opponent_models, OPPONENT_TEAM, OUR_TEAM, opponent_starting_pokemon_wincount), open('save_opponent.p', 'wb'))


bookkeeper = Bookkeeper(list_of_models, preprocess_observation, len(sys.argv) == 2)
if __name__ == '__main__':
   run_reinforcement_learning()
