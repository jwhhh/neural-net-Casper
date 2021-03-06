"""
This script builds a neural network with CasPer technique
for classifying forest supra-type based on dataset: GIS.

The dataset is naturally a classification problem, however, we modify it into
a regression problem by equilateral coding, to avoid difficult learning.
"""

from preprocessing import pre_process
from NN import confusion_matrix, train_data, test_data
from GA import GA_model

import numpy as np
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
import math

plot_each_run = False

# hyper parameters
DNA_size = 42
pop_size = 10
cross_rate = 0.8
mutation_rate = 0.001
n_generations = 20

# fixed hyper parameters for CasPer
output_size = 4
k_cross_validation = 5

# define loss function
loss_func = nn.MSELoss()


# define regression model
class Regression(nn.Module):
    def __init__(self, input_size, output_size, all_losses, num_neurons, p_value, lr_1, lr_2, lr_3):
        super(Regression, self).__init__()
        self.test = False
        self.input_size = input_size
        self.output_size = output_size
        self.n_hidden = 0
        self.losses = all_losses
        self.num_neurons = num_neurons
        self.p = p_value    # used to determine whether to install a new neuron
        self.lr_1 = lr_1
        self.lr_2 = lr_2
        self.lr_3 = lr_3
        self.input_to_output = nn.Linear(input_size, output_size)
        # all_to_output: a list containing all Linears from all neurons to output neurons
        self.all_to_output = []
        # all_to_hidden: a list containing all Linears from previous neurons to a hidden neuron
        self.all_to_hidden = []

        # define optimizer
        self.optimizers = []
        optimizer = torch.optim.Rprop(self.parameters(), lr=lr_1)
        self.optimizers.append(optimizer)

    def forward(self, x):   # size of x: (152, 20)
        if self.n_hidden == 0 or len(self.losses) < 2:
            self.install = True
        elif self.current_neuron_epoch<15+self.p*self.n_hidden:
            self.install = False
        elif self.current_neuron_epoch>100:
            self.install = True
        else:
            loss1 = self.losses[-1]
            loss2 = self.losses[-2]
            rms1 = math.sqrt(loss1)
            rms2 = math.sqrt(loss2)
            decrease = (rms2 - rms1) / rms2
            self.install = decrease >= 0.01

        if self.install and not self.test:
            if self.n_hidden == self.num_neurons:
                return None
            all_to_new = nn.Linear(self.input_size+self.n_hidden, 1)
            self.all_to_hidden.append(all_to_new)
            new_to_output = nn.Linear(1, self.output_size, bias=False)
            self.all_to_output.append(new_to_output)

            # change learning rate of optimizers
            if len(self.optimizers) == 1:
                optim = self.optimizers[0]
                for g in optim.param_groups:
                    g['lr'] = self.lr_3
            else:
                optim = self.optimizers[-2]
                for g in optim.param_groups:
                    g['lr'] = self.lr_3
                optim = self.optimizers[-1]
                for g in optim.param_groups:
                    g['lr'] = self.lr_3
            self.optimizers.append(torch.optim.Rprop([new_to_output.weight], lr=self.lr_2))
            self.optimizers.append(torch.optim.Rprop([all_to_new.weight, all_to_new.bias], lr=self.lr_1))

            self.n_hidden += 1
            self.current_neuron_epoch = 0

        # perform forward propagation from all previous neurons to each hidden neuron
        neurons_all = x
        for i in range(self.n_hidden):
            linear = self.all_to_hidden[i]
            neuron = linear(neurons_all[:, :i+self.input_size])
            neurons_all = torch.cat((neurons_all, neuron), 1)

        # perform forward propagation from all neurons to output neurons
        logic = self.input_to_output(x)
        for i in range(self.n_hidden):
            logic = logic + self.all_to_output[i](neurons_all[:, i+self.input_size].unsqueeze(1))
        out = torch.sigmoid(logic)      # this is where the activation function, sigmoid, is used

        self.current_neuron_epoch += 1

        return out

    # clear gradients, used before backward
    def clear_grad(self):
        for optimizer in self.optimizers:
            optimizer.zero_grad()

    # this is used for updating parameters
    def step(self):
        for optimizer in self.optimizers:
            optimizer.step()


# train the model, given X and Y
def train(X, Y, num_neurons, p_value, lr_1, lr_2, lr_3, plot=False, to_print=False):
    # store all losses for visualisation
    all_losses = []

    # define regression model
    reg_model = Regression(X.size(1), output_size, all_losses, num_neurons, p_value, lr_1, lr_2, lr_3)

    # start training
    while True:
        # perform forward pass: compute predicted y by passing x to the model
        Y_predicted = reg_model(X)

        if Y_predicted is None:
            break

        # Y_predicted = Y_predicted.view(len(Y_predicted))
        # compute loss
        loss = loss_func(Y_predicted, Y)
        all_losses.append(loss.item())

        # print every neuron
        if reg_model.install and reg_model.n_hidden != 1 and to_print:
            print('Training Neuron: [%d/%d], Loss: %.4f' % (reg_model.n_hidden, num_neurons, all_losses[-2]))

        # clear gradients before backward pass
        reg_model.clear_grad()
        # perform backward pass
        loss.backward()
        # update parameters
        reg_model.step()

    # plot the accuracy of model on training data
    if plot:
        plt.figure()
        plt.plot(all_losses)
        plt.title('losses of model on training data')
        plt.show()

    # print confusion matrix and correct percentage
    reg_model.test = True
    Y_predicted = reg_model(X)
    loss = loss_func(Y_predicted, Y)
    total_num = Y_predicted.size(0)
    confusion = confusion_matrix(Y, Y_predicted)
    correctness = (100 * float(confusion[1])) / total_num
    if to_print:
        print('Confusion matrix for training:')
        print(confusion[0])
        print('Correct percentage in training data:', (100*float(confusion[1]))/total_num)

    return reg_model, loss, correctness


# perform testing on trained model, print test loss, confusion matrix and correctness
def test(X_test, Y_test, reg_model, to_print=False):
    Y_predicted_test = reg_model(X_test)
    test_loss = loss_func(Y_predicted_test, Y_test)
    if to_print:
        print('test loss: %f' % test_loss.item())
    total_num = Y_test.size(0)
    confusion = confusion_matrix(Y_predicted_test, Y_test)
    correctness = (100*float(confusion[1]))/total_num
    if to_print:
        print('Confusion matrix for testing:')
        print(confusion[0])
        print('Correct percentage in testing data:', correctness)
    return test_loss, correctness

def cross_validation(hyper_parameters):
    # extract hyper parameters of the neural net
    features = hyper_parameters[0]
    num_neurons = hyper_parameters[1]
    p_value = hyper_parameters[2]
    lr_1 = hyper_parameters[3]
    lr_2 = hyper_parameters[4]
    lr_3 = hyper_parameters[5]

    # start training and testing
    # pre-process the data, using the function defined in preprocessing.py
    data = pre_process()

    # keep only chosen features
    columns = np.append(features, [1]*output_size)
    features_idx = [i for i, x in enumerate(columns) if x == 1]
    data = data.iloc[:, features_idx]

    # split data for later use (k cross validation)
    splitted_data = np.split(data, k_cross_validation)

    # train using cross validation
    all_train_losses = []
    all_test_losses = []
    all_train_correctness = []
    all_test_correctness = []
    for i in range(k_cross_validation):
        # extract train and test data, split input and target
        X_train, Y_train = train_data(splitted_data, i)
        X_test, Y_test = test_data(splitted_data, i)

        # train the model and print loss, confusion matrix and correctness
        reg_model, loss, correctness = train(X_train, Y_train, num_neurons, p_value, lr_1, lr_2, lr_3)

        # test the model on test data
        test_loss, test_correctness = test(X_test, Y_test, reg_model)

        # append losses and correctness
        all_train_losses.append(loss)
        all_test_losses.append(test_loss)
        all_train_correctness.append(correctness)
        all_test_correctness.append(test_correctness)

    # print average loss and correctness on training and testing data
    train_loss_avg = (sum(all_train_losses) / len(all_train_losses)).item()
    test_loss_avg = (sum(all_test_losses) / len(all_test_losses)).item()
    print('average loss on training data', train_loss_avg)
    print('average loss on testing data', test_loss_avg)
    train_correctness_avg = sum(all_train_correctness) / len(all_train_correctness)
    test_correctness_avg = sum(all_test_correctness) / len(all_test_correctness)
    print('average correctness on training data', train_correctness_avg)
    print('average correctness on testing data', test_correctness_avg)
    print('')

    # display performance of each model
    if plot_each_run:
        # losses
        plt.figure()
        plt.plot(all_train_losses, label='training data', color='blue')
        plt.plot(all_test_losses, label='testing data', color='red')
        plt.axhline(y=train_loss_avg, linestyle=':', label='training data average loss', color='blue')
        plt.axhline(y=test_loss_avg, linestyle=':', label='testing data average loss', color='red')
        plt.legend()
        plt.title('losses of model on training and testing data')
        plt.show()
        # correctness
        plt.figure()
        plt.plot(all_train_correctness, label='training data', color='blue')
        plt.plot(all_test_correctness, label='testing data', color='red')
        plt.axhline(y=train_correctness_avg, linestyle=':', label='training data average correctness', color='blue')
        plt.axhline(y=test_correctness_avg, linestyle=':', label='testing data average correctness', color='red')
        plt.legend()
        plt.title('correctness of model on training and testing data')
        plt.show()

    print("settings: ", features_idx, num_neurons, p_value, lr_1, lr_2, lr_3)
    print("---------------------------------------\n")

    return test_correctness_avg, train_correctness_avg, test_loss_avg, train_loss_avg

################################ main ###################################
if __name__ == "__main__":
    # initialize a genetic algorithm model
    ga = GA_model(DNA_size, pop_size, cross_rate, mutation_rate, n_generations, cross_validation)

    # start trainign the genetic algorithm model
    ga.train(plot=True)