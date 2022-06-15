""" 
This script contains the Coastal_Model class
It contains methods such as designing a network for a TCN, LSTM, and ANN model.
Then compiling and training the model.

"""

import keras
from keras import layers
from keras import models
from keras.backend import sigmoid
from keras import utils
from keras.callbacks import EarlyStopping, TensorBoard, ModelCheckpoint, ProgbarLogger
import os

import sherpa
import tensorflow as tf
from tensorflow import math as tfm
import numpy as np
import random
import keras.backend as K
import tcn

def reset_seeds():
    #Solution to reset random states from: https://stackoverflow.com/questions/58453793/the-clear-session-method-of-keras-backend-does-not-clean-up-the-fitting-data 
    np.random.seed(1)
    random.seed(2)
    if tf.__version__[0] == '2':
        tf.random.set_seed(3)
    else:
        tf.set_random_seed(3)
    print("RANDOM SEEDS RESET")


def swish_func(x, beta = 1):
    return (x * sigmoid(beta * x))


def relu_advanced_func(x, threshold = -3):
    return keras.activations.relu(x, threshold=threshold)


class swish(layers.Activation):
    def __init__(self, activation, **kwargs):
        super(swish, self).__init__(activation, **kwargs)
        self.__name__ = 'swish'


class relu_advanced(layers.Activation):
    def __init__(self, activation, **kwargs):
        super(relu_advanced, self).__init__(activation, **kwargs)
        self.__name__ = 'relu_advanced'


class Coastal_Model(keras.layers.LSTM):
    def __init__(self, loss, n_layers, neurons, activation, train_X, train_y, dropout, drop_value, 
                 hyper_opt, validation, test_X, test_y,
                 val_X, val_y, optimizer, epochs, batch, verbose, model_dir, name_model, ML, filters, 
                 variables, batch_normalization, sherpa_output, logger,
                 alpha=13, s=1.7, gamma=1.1, l1=0.01, l2=0.01, mask_val=-999):
        
        # Model parameters
        self.ML = ML
        self.n_layers = n_layers
        self.neurons = neurons
        self.activ = activation
        self.train_X = train_X
        self.train_y = train_y
        self.test_X = test_X
        self.test_y = test_y
        self.drop_out = dropout
        self.drop_value = drop_value
        self.l1 = l1
        self.l2 = l2
        self.mask_val = mask_val
        self.hyp_opt = hyper_opt
        self.validation = validation
        self.filters = filters
        self.optimizer = optimizer
        self.epochs = epochs
        self.verbose = verbose
        
        # Loss function parameters
        if loss == 'Gumbel':
            self.gamma = gamma
            self.custom_loss_fn = self.gumbel_loss_hyper(gamma=gamma)
            
        elif loss == 'Frechet':
            self.alpha = alpha
            self.s = s
            self.custom_loss_fn = self.frechet_loss()
        else:
            self.custom_loss_fn = 'mse'
            
        
        # Data & Misc
        
        self.val_X = val_X
        self.val_y = val_y
        self.batch_size = batch
        self.model_dir = model_dir
        self.name_model = name_model
        self.batch_norm = batch_normalization
        self.vars = variables
        self.sherpa_output = sherpa_output
        self.logger = logger
    
    
    
    def ANN_model(self):
        """
        Design an ANN model
        """

        model = models.Sequential()
        model.add(layers.Dense(self.neurons, kernel_regularizer=keras.regularizers.l1_l2(l1=self.l1, l2=self.l2), activation=self.activ, input_dim=self.train_X.shape[1]))
        for i in range(self.n_layers - 1):
            model.add(layers.Dense(self.neurons, kernel_regularizer=keras.regularizers.l1_l2(l1=self.l1, l2=self.l2), activation=self.activ))
            
        if self.drop_out:
            model.add(layers.Dropout(self.drop_value))
            
        model.add(layers.Dense(1))
        self.model = model
    
    def LSTM_model(self):
        """
        Design an LSTM model
        """
        input_shape = (self.train_X.shape[1], self.train_X.shape[2])
        # model = models.Sequential()
        # # model.add(layers.Masking(mask_value=mask_val, input_shape=input_shape))
        # for i in range(self.n_layers):
        #     rs = False if i == self.n_layers - 1 else True
        #     if self.activ == 'Leaky ReLu':
        #         model.add(layers.LSTM(self.neurons, input_shape=input_shape, return_sequences=rs, activation=self.activ,  # added this activation to be sure, but not yet tested
        #                             stateful=False, recurrent_activation='hard_sigmoid'))  # neurons refers to cells
        #         model.add(layers.LeakyReLU(alpha=0.1))
        #         # if self.dropout:
        #         #     model.add(layers.Dropout(self.drop_value))
        #     else:
        #         model.add(layers.LSTM(self.neurons, input_shape=input_shape, activation=self.activ, 
        #                 return_sequences=rs, recurrent_activation='hard_sigmoid'))  # recurrent_dropout=drop_value
        #         # if self.dropout:
        #         #     model.add(layers.Dropout(self.drop_value))
        # model.add(layers.Dense(self.neurons, activation=self.activ, kernel_regularizer=keras.regularizers.l1_l2(l1=self.l1, l2=self.l2)))  # hidden layers
        # if self.drop_out:
        #     model.add(layers.Dropout(self.drop_value))
        # model.add(layers.Dense(1, activation=self.activ)) #output layer

        model = models.Sequential()
        model.add(layers.LSTM(self.neurons, input_shape=input_shape, activation=self.activ, return_sequences=True))
        # model.add(layers.Dropout(.2))
        model.add(layers.LSTM(self.neurons, activation=self.activ, return_sequences=False))
        model.add(layers.Dropout(self.drop_value))
        model.add(layers.Dense(self.neurons, activation=self.activ))
        model.add(layers.Dropout(self.drop_value))
        model.add(layers.Dense(1)) 
        
        self.model = model
        
        
    def TCN_model(self):
        """
        Design a TCN-LSTM model
        """
        input_shape = (self.train_X.shape[1], self.train_X.shape[2])
        
        model = models.Sequential()
        model.add(tcn.TCN(48, input_shape=input_shape, activation='relu', return_sequences=True,
                    dilations=(1,2,4,8), dropout_rate=.2, kernel_size=3))
        model.add(layers.LSTM(24, activation='relu', return_sequences=False))
        # tcn_model.add(layers.Dropout(.2))
        model.add(layers.Dense(10, activation='relu'))
        # model.add(layers.Dense(5, activation='tanh'))
        model.add(layers.Dense(1))
        
        self.model = model
    
    def design_network(self):
        """
        Design desired network type based on the ML parameter
        """
        
        # design Network
            
        # if self.activ == 'swish':
        #     utils.generic_utils.get_custom_objects().update({'swish': swish(swish_func)})

        # if self.activ == 'relu':
        #     self.activ = 'relu_advanced'
        #     utils.generic_utils.get_custom_objects().update({'relu_advanced': relu_advanced(relu_advanced_func)})
        
        if self.ML == 'ANN':
            self.ANN_model()
        elif self.ML == 'LSTM':
            self.LSTM_model()
        elif self.ML == 'TCN':
            self.TCN_model()
            
            
    def compile(self):
        self.model.compile(loss=self.custom_loss_fn, optimizer=self.optimizer)
        self.model.summary()
        
    
    def gumbel_loss_hyper(self, gamma=1.1):
        def gumbel_loss(y_true, y_pred):
            u = y_pred - y_true
            
            a = 1 - K.exp(-K.pow(u, 2))
            b= K.pow(a, gamma)
            c = tf.multiply(b, K.pow(u,2))
            d =K.exp(-c)
            e = K.mean(d)

            ll = -K.log(e)
            return ll
    
        return gumbel_loss

    def frechet_loss(self):
        def frechet_loss_fn(y_true, y_pred):
            delta = y_pred - y_true
        
            delta_S = (delta + self.s*(self.alpha/(1+self.alpha) ** (1/self.alpha))) / self.s

            loss = (-1-self.alpha) * (-delta_S) ** (-self.alpha) + \
                tfm.log(delta_S)
            
            # return tf.reduce_mean(loss)
            return K.mean(tf.where(delta < 0, 0, loss))
        
        return frechet_loss_fn
    
    def train_model(self, hyper_opt=False):
            
        my_callbacks = [EarlyStopping(monitor='val_loss', min_delta=0, patience=3, mode="auto", restore_best_weights = 'True'),
                        ModelCheckpoint(filepath=os.path.join(self.model_dir, self.name_model), monitor='val_loss', save_best_only=True, save_weights_only=False, mode='auto', period=1)] # ProgbarLogger(count_mode="steps", stateful_metrics=None), , ModelCheckpoint(filepath=os.path.join(model_dir, name_model), monitor='loss', save_best_only=True, save_weights_only=False, mode='auto', period=1),
        # my_callbacks = [ModelCheckpoint(filepath=os.path.join(model_dir, name_model), monitor='val_loss', save_best_only=True, save_weights_only=False, mode='auto', period=1)]
        
        if hyper_opt:
            my_callbacks.append(self.hyper_opt)

        if self.ML == 'LSTM' or self.ML == 'TCN':
            shuffle = False #'batch'
        else:
            shuffle= True
        
        # fit network
        if self.validation == 'split':
            self.history = self.model.fit(self.train_X, self.train_y, epochs=self.epochs, batch_size=self.batch_size, 
                                validation_split=0.3, callbacks=my_callbacks, verbose=self.verbose, shuffle=shuffle)
        elif self.validation == 'select':
            self.history = self.model.fit(self.train_X, self.train_y, epochs=self.epochs, batch_size=self.batch_size,
                                validation_data=(self.val_X, self.val_y), callbacks=my_callbacks, verbose=self.verbose, shuffle=shuffle)
        else:
            raise ValueError('Validation must be either "split" or "select"')

        self.model.save(os.path.join(self.model_dir, self.name_model), include_optimizer=True, overwrite=True)

        # Store loss values
        self.train_loss = self.history.history['loss']
        self.test_loss = self.history.history['val_loss']
        del(self.history)
    
    def hyper_opt(self):
        # setup sherpa object
        if self.ML == 'LSTM':
            parameters = [sherpa.Ordinal(name='neurons', range=[24, 48, 96, 192]),
                        sherpa.Ordinal(name='hidden', range=[1, 2, 3, 4, 5])]
        elif self.ML == 'CNN':
            parameters = [sherpa.Ordinal(name='filters', range=[8, 16, 24]),
                        sherpa.Ordinal(name='neurons', range=[24, 48, 96, 192]),
                        sherpa.Ordinal(name='hidden', range=[1, 2, 3, 4, 5])]
            
        # if self.loss_fn == 'gumbel':
        #     parameters.append(sherpa.Ordinal(name='gamma', range=[0.1, 0.5, 1, 2, 5, 10]))
        # elif self.loss_fn == 'frechet':
        #     parameters.append(sherpa.Ordinal(name='alpha', range=[0.1, 0.5, 1, 2, 5, 10]))
        #     parameters.append(sherpa.Ordinal(name='s', range=[0.1, 0.5, 1, 2, 5, 10]))

        alg = sherpa.algorithms.RandomSearch(max_num_trials=100)
        study = sherpa.Study(parameters=parameters, algorithm=alg, lower_is_better=True, disable_dashboard=True)

        count = 1
        for trial in study:
            self.neurons = trial.parameters['neurons']
            if self.ML == 'CNN' or self.ML == 'ConvLSTM':
                self.filters = trial.parameters['filters']
            self.n_layers = trial.parameters['hidden']
            # drop_value = trial.parameters['dropout']
            # l2 = trial.parameters['l2']
            # batch = trial.parameters['batch']
            self.batch_size = 10 * 24

            self.design_network()
            self.compile()
            # fit network
            self.train_model(hyper_opt=study.keras_callback(trial, objective_name='val_loss'))

            study.finalize(trial)
            if self.logger:
                self.logger.info(f'Trial {self.ML}: {count}')
            else:
                print(f'\nTrial {self.ML}: {count}\n')
            count += 1
        if self.logger:
            self.logger.info(study.get_best_result())
        else:
            print(study.get_best_result())
        study.save(self.sherpa_output)
        # sherpa.Study.load_dashboard(".")
        # ssh -L 8000:localhost:8880 timothyt@cartesius.surfsara.nl
        # model.compile(optimizer='adam',
        #           loss=gumbel_loss(layer), # Call the loss function with the selected layer))
        
        
        
    def predict(self, reframed_df, scaler, n_train_final):
        df = reframed_df[n_train_final:].copy()

        # make a prediction
        yhat = self.model.predict(self.test_X)

        # invert scaling for observed surge
        inv_y = scaler.inverse_transform(df.values)[:,-1]

        # invert scaling for modelled surge
        df.loc[:,'values(t)'] = yhat
        inv_yhat = scaler.inverse_transform(df.values)[:,-1]

        return inv_yhat, inv_y


