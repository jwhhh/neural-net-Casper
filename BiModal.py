"""
This script builds a neural network for classifying forest supra-type based on
dataset: GIS. Additionally, Bimodal Distribution Removal technique is applied.

The dataset is naturally a classification problem, however, we modify it into
a regression problem by equilateral coding, to avoid difficult learning.
"""

from preprocessing import pre_process, interpret_output
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import matplotlib.pyplot as plt


# hyper parameters
input_size = 20
hidden_size = 12
output_size = 4
num_epochs = 1000
learning_rate = 0.01
k_cross_validation = 5

# parameters for Bimodal Distribution Removal
variance_thresh = 0.00001
variance_thresh_halting = 0.000001
alpha = 0.5

# define loss function
loss_func = nn.MSELoss(reduction='none')


# get train data, used in k-fold cross validation
def train_data(splitted_dt, i):
    # extract train data
    train_dt = pd.concat([x for j,x in enumerate(splitted_dt) if j!=i])
    # divide into input and target
    train_input = train_dt.iloc[:, :input_size]
    train_target = train_dt.iloc[:, input_size:]
    # create Tensors to hold inputs and outputs
    X = torch.Tensor(train_input.values)
    Y = torch.Tensor(train_target.values)
    return X, Y


# get test data, used in k-fold cross validation
def test_data(splitted_dt, i):
    # extract test data
    test_dt = splitted_dt[i]
    # divide into input and target
    test_input = test_dt.iloc[:, :input_size]
    test_target = test_dt.iloc[:, input_size:]
    # create Tensors to hold inputs and outputs
    X = torch.Tensor(test_input.values)
    Y = torch.Tensor(test_target.values)
    return X, Y


# define regression model
class Regression(nn.Module):
    def __init__(self, input_size, output_size):
        super(Regression, self).__init__()
        self.linear1 = nn.Linear(input_size, hidden_size)
        self.linear2 = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out = torch.sigmoid(self.linear1(x))
        out = torch.sigmoid(self.linear2(out))
        return out


# train the model, given X and Y
def train(X, Y, plot=True, to_print=False):
    # define regression model
    reg_model = Regression(input_size, output_size)
    # define optimiser
    optimizer = torch.optim.Adam(reg_model.parameters(), lr=learning_rate)
    # store all losses for visualisation
    all_losses = []

    # start training
    for epoch in range(num_epochs):
        # perform forward pass: compute predicted y by passing x to the model
        Y_predicted = reg_model(X)

        # compute loss
        loss = loss_func(Y_predicted, Y)
        loss_avg = torch.mean(loss)
        all_losses.append(loss_avg.item())

        # print every 100 epochs
        if (epoch + 1) % 100 == 0 and to_print:
            print('Training Epoch: [%d/%d], Loss: %.4f' % (epoch+1, num_epochs, loss.item()))

        # clear gradients before backward pass
        optimizer.zero_grad()

        # perform backward pass
        loss_avg.backward()

        # update parameters
        optimizer.step()

        # apply the techinqiue: Bimodal Distribution Removal
        if epoch % 50 == 0:
            losses = torch.mean(loss, dim=1)
            # plt.figure()
            # plt.hist(x=losses.detach().numpy(), bins='auto')
            # plt.show()
            variance = torch.var(losses)
            if variance.item() < variance_thresh_halting:
                break  # halt to avoid overfitting
            std = torch.std(loss)
            error_thresh = loss_avg + std.item() * alpha
            survived_indices = [i for i in range(len(loss)) if losses[i].item() < error_thresh]
            indices = torch.LongTensor(survived_indices)
            X = X[indices]
            Y = Y[indices]

    # plot the accuracy of model on training data
    if plot:
        plt.figure()
        plt.plot(all_losses)
        plt.title('losses of model on training data')
        plt.show()

    # print confusion matrix and correct percentage
    Y_predicted = reg_model(X)
    loss = loss_func(Y_predicted, Y)
    loss_avg = torch.mean(loss).item()
    total_num = Y_predicted.size(0)
    confusion = confusion_matrix(Y, Y_predicted)
    correctness = (100 * float(confusion[1])) / total_num
    if to_print:
        print('Confusion matrix for training:')
        print(confusion[0])
        print('Correct percentage in training data:', (100*float(confusion[1]))/total_num)

    return reg_model, loss_avg, correctness


# perform testing on trained model, print test loss, confusion matrix and correctness
def test(X_test, Y_test, reg_model, to_print=False):
    Y_predicted_test = reg_model(X_test)
    test_loss = loss_func(Y_predicted_test, Y_test)
    test_loss_avg = torch.mean(test_loss).item()
    if to_print:
        print('test loss: %f' % test_loss.item())
    total_num = Y_test.size(0)
    confusion = confusion_matrix(Y_predicted_test, Y_test)
    correctness = (100*float(confusion[1]))/total_num
    if to_print:
        print('Confusion matrix for testing:')
        print(confusion[0])
        print('Correct percentage in testing data:', correctness)
    return test_loss_avg, correctness


# calculate confusion matrix, need to interpret output data into category
def confusion_matrix(Y, Y_predicted):
    confusion = torch.zeros(5, 5)
    correct_num = 0
    for i in range(Y.shape[0]):
        actual_class = interpret_output(Y[i])
        predicted_class = interpret_output(Y_predicted[i])
        confusion[actual_class[1]][predicted_class[1]] += 1
        if actual_class == predicted_class:
            correct_num += 1
    return confusion, correct_num


################################ main ###################################
if __name__ == "__main__":
    # pre-process the data, using the function defined in preprocessing.py
    data = pre_process()

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
        reg_model, loss, correctness = train(X_train, Y_train, plot=False)

        # test the model on test data
        test_loss, test_correctness = test(X_test, Y_test, reg_model)

        # append losses and correctness
        all_train_losses.append(loss)
        all_test_losses.append(test_loss)
        all_train_correctness.append(correctness)
        all_test_correctness.append(test_correctness)

    # print average loss and correctness on training and testing data
    print(all_train_losses)
    train_loss_avg = (sum(all_train_losses) / len(all_train_losses))
    test_loss_avg = (sum(all_test_losses) / len(all_test_losses))
    print('average loss on training data', train_loss_avg)
    print('average loss on testing data', test_loss_avg)
    train_correctness_avg = sum(all_train_correctness) / len(all_train_correctness)
    test_correctness_avg = sum(all_test_correctness) / len(all_test_correctness)
    print('average correctness on training data', train_correctness_avg)
    print('average correctness on testing data', test_correctness_avg)

    # display performance of each model
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
