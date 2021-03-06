# -*- coding: utf-8 -*-
"""
Using machine learning to predict coastal hydrographs

Timothy Tiggeloven and Anaïs Couasnon
"""
import os
import sys

# os.chdir('./Beck_Thesis/')
from CHNN import model_run_Beck as mrB


# parameters and variables
station = sys.argv[1]
ML = sys.argv[2]
loss = sys.argv[3]

# station = 'cuxhaven-cuxhaven-germany-bsh'  # 'Cuxhaven' 'Hoek van Holland', Puerto Armuelles
# ML = 'ANN'  # 'LSTM', 'CNN', 'ConvLSTM', 'ANN', 'ALL', 'LSTM_TCN'
# loss = 'gumbel' #'mae'  # 'mae', 'mean_squared_logarithmic_error', 'mean_squared_error'

resample = 'hourly' # 'hourly' 'daily'
resample_method = 'rolling_mean'  # 'max' 'res_max' 'rolling_mean' ## res_max for daily and rolling_mean for hourly
variables = ['msl', 'grad', 'u10', 'v10', 'rho', 'sst']  # 'grad', 'rho', 'phi', 'u10', 'v10', 'uquad', 'vquad'
tt_value = 0.67  # train-test value
scaler = 'std_normal'  # std_normal, MinMax
n_ncells = 0
epochs = 25
batch = 100
batch_normalization = False
neurons = 48
filters = 8
n_layers = 1  # now only works for uniform layers with same settings
activation = 'relu'  # 'relu', 'swish', 'Leaky ReLu', 'sigmoid', 'tanh'
optimizer = 'adam'  # SGD(lr=0.01, momentum=0.9), 'adam'
dropout = True
drop_value = 0.2
l1, l2 = 0, 0.01

model_dir = os.path.join(os.getcwd(), 'Models')
name_model = '{}_surge_ERA5_test'.format(ML)
input_dir = 'Input_nc_sst'
output_dir = 'ML_model'
figures_dir = 'Figures'
year = 'last'
frac_ensemble = 0.5

loop = 2

logger, ch = mrB.set_logger(loop, n_ncells)
mrB.ensemble(station, variables, ML, tt_value, input_dir, resample, resample_method, scaler,
                   batch, n_layers, neurons, filters, dropout, drop_value, activation, optimizer,
                   batch_normalization, loss, epochs, loop=loop, n_ncells=n_ncells, l1=l1, l2=l2,
                   frac_ens=frac_ensemble, logger=logger, verbose=0, validation='select')
