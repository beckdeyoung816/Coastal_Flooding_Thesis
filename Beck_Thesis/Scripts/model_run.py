# -*- coding: utf-8 -*-
"""
Using machine learning to predict coastal hydrographs

Timothy Tiggeloven and Anaïs Couasnon
"""
import logging
import logging.handlers
import os
import sys
import numpy as np
import pandas as pd
import keras
import tensorflow as tf
import time
import datetime
import xarray as xr

from CHNN import ANN
from CHNN import to_learning
from CHNN import performance


def set_logger(arg_start, arg_end, verbose=True):
    """
    Set-up the logging system, exit if this fails
    """
    # assign logger file name and output directory
    datelog = time.ctime()
    datelog = datelog.replace(':', '_')
    reference = f'ML_stormsurges_loop_{arg_start}-{arg_end}'


    logfilename = ('logger' + os.sep + reference + '_logfile_' + 
                   str(datelog.replace(' ', '_')) + '.log')

    # create output directory if not exists
    if not os.path.exists('logger'):
        os.makedirs('logger')

    # create logger and set threshold level, report error if fails
    try:
        logger = logging.getLogger(reference)
        logger.setLevel(logging.DEBUG)
    except IOError:
        sys.exit('IOERROR: Failed to initialize logger with: ' + logfilename)

    # set formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s -'
                                  '%(levelname)s - %(message)s')

    # assign logging handler to report to .log file
    ch = logging.handlers.RotatingFileHandler(logfilename,
                                              maxBytes=10*1024*1024,
                                              backupCount=5)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # assign logging handler to report to terminal
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # start up log message
    logger.info('File logging to ' + logfilename)

    return logger, ch


def ensemble(station, variables, ML, tt_value, input_dir, resample, resample_method, scaler_type,
             batch, n_layers, neurons, filters, dropout, drop_value, activation, optimizer,
             batch_normalization, loss, epochs, loop=5, n_ncells=2, l1=0.00, l2=0.01, frac_ens=0.5, logger=False, complexity=False,
             year='last', fn_exp='Models', arg_count=0, verbose=2, mask_val=-999, hyper_opt=False, NaN_threshold=0):

    start1 = time.time()
    if ML in ['all', 'All', 'ALL']:
        ML_list = ['CNN', 'LSTM', 'ANN', 'ConvLSTM']
    else:
        ML_list = [ML]
    print('ML_list is:', ML_list)
    
    df, lat_list, lon_list, direction, scaler, reframed, test_dates, i_test_dates = to_learning.prepare_station(station, variables, ML, input_dir, resample, resample_method,
                                                                                                                cluster_years=5, extreme_thr=0.02, sample=False, make_univariate=False,
                                                                                                                scaler_type=scaler_type, year = year, scaler_op=True, n_ncells=n_ncells, mask_val=mask_val, logger=logger)

    if resample == 'hourly':                            
       batch = batch * 24
    
    # split testing phase year    
    test_year = reframed.iloc[i_test_dates].copy()
    
    #NaN masking the complete test year 
    reframed.iloc[i_test_dates] = np.nan  

    for ML in ML_list:
        if not logger:
            print(f'\nStart ensemble run for {ML}\n')
        start2 = time.time()

        # create model output directory
        # model_dir = os.path.join('Models', 'Ensemble_run', station, ML)
        model_dir = os.path.join(fn_exp, 'Ensemble_run', station, ML)
        if complexity == 'spatial':
            model_dir = os.path.join(fn_exp, 'spatial_extend_run', station, f'n_ncells_{n_ncells:02d}', ML)
        elif complexity == 'hyper':
            df_hyper = pd.read_csv(os.path.join('Hyper_opt', 'complexity', station, ML, 'results.csv'))
            n_layers = df_hyper.loc[df_hyper['Objective'].argmin()]['hidden']
            neurons = df_hyper.loc[df_hyper['Objective'].argmin()]['neurons']
            if ML == 'CNN' or ML == 'ConvLSTM':
                filters = df_hyper.loc[df_hyper['Objective'].argmin()]['filters']
        if not os.path.exists(model_dir):
            os.makedirs(model_dir)

        # reframe ML station data
        test_year.loc[test_year.iloc[:,-1].isna(),'values(t)'] = mask_val #Changing all NaN values in residual testing year to masking_val                                                                                                                                            
        _, _, test_X, test_y, _ = to_learning.splitting_learning(test_year, df, 0, ML, variables, direction, lat_list, lon_list, batch, n_train=False)

        result_all = dict()
        result_all['data'] = dict()
        result_all['train_loss'] = dict()
        result_all['test_loss'] = dict()
        for i in range(loop):
            if not logger:
                print(f'\nEnsemble loop: {i + 1}\n')
            tf.keras.backend.clear_session()
            name_model = f'{ML}_ensemble_{i + 1}'

            # shuffle df
            reframed_ensemble = reframed.copy()
            reframed_draw, n_train = to_learning.select_ensemble(reframed_ensemble, 'values(t)', ML, batch, tt_value=tt_value, frac_ens = frac_ens, mask_val=mask_val, NaN_threshold=NaN_threshold) 

            # We modify the input data so that it is masked        
            reframed_draw = reframed_draw.reset_index(drop=True).copy()
            reframed_draw[reframed_draw.iloc[:,-1]==mask_val] = mask_val
            # print('There are so many Nan: ', sum(reframed_draw.iloc[:,-1]==mask_val))
            
            # reframe ML station data
            train_X, train_y, val_X, val_y, n_train = to_learning.splitting_learning(reframed_draw, df, tt_value, ML, variables, direction, lat_list, lon_list, batch, n_train=n_train)
            
            # Hyperparameter optimization
            if hyper_opt:
                sherpa_output = os.path.join('Hyper_opt', 'complexity', station, ML)
                if not os.path.exists(sherpa_output):
                    os.makedirs(sherpa_output)
                ANN.hyper_opt(train_X, train_y, val_X, val_y, l1, l2, activation, loss, optimizer,
                              neurons, drop_value, epochs, batch, verbose, model_dir, name_model,
                              ML, filters, dropout, n_layers, variables, batch_normalization, sherpa_output, logger)
                continue

            # design network
            model = ANN.design_network(n_layers, neurons, filters, train_X, dropout, drop_value, variables,
                                       batch_normalization, name_model, ML=ML, loss=loss,
                                       optimizer=optimizer, activation=activation, l1=l1, l2=l2) #mask_val to add
            
            # fit network
            model, train_loss, test_loss = ANN.train_model(model, epochs, batch, train_X, train_y, val_X,
                                                           val_y, ML, name_model, model_dir, validation='select', verbose=verbose)
            result_all['train_loss'][i] = train_loss
            result_all['test_loss'][i] = test_loss

            # make a prediction
            inv_yhat, inv_y = ANN.predict(model, test_X, test_year.replace(to_replace=mask_val, value=np.nan), scaler, 0)

            # plot results
            df_all = performance.store_result(inv_yhat, inv_y)
            df_all = df_all.set_index(df.iloc[i_test_dates,:].index, drop = True)                                                                    
            
            result_all['data'][i] = df_all.copy()
            
            # if os.path.exists(os.path.join(model_dir, name_model)):
            #     os.remove(os.path.join(model_dir, name_model))
            #     # os.rmdir(os.path.join(model_dir, name_model))
            model.save(os.path.join(model_dir, name_model), include_optimizer=True , overwrite=True)
            del(model)
            
            tf.keras.backend.clear_session()
            keras.backend.clear_session()
            tf.compat.v1.reset_default_graph()

        #model = keras.models.load_model(os.path.join(model_dir, name_model))
        
        if not hyper_opt:
            # plot results
            df_result, df_train, df_test =  performance.ensemble_handler(result_all, station, neurons, epochs, 
                                                                        batch, resample, tt_value, len(variables), 
                                                                        model_dir, layers=n_layers, ML=ML, 
                                                                        test_on='ensemble', plot=True, save=True)
        
        if logger:
            logger.info(f'{arg_count}: {ML} - {station} - {round((time.time() - start2) / 60, 2)} min')
        else:
            print(f'\ndone ensemble run for {ML}: {round((time.time() - start2) / 60, 2)} min\n')
    
    if logger:
        logger.info(f'{arg_count}: Done - {station} - {round((time.time() - start1) / 60, 2)} min')
        return None
    else:
        print(f'\ndone ensemble runs for {ML_list}: {round((time.time() - start1) / 60, 2)} min\n')
        return df_result, df_train, df_test

def post_process_ensemble_handler():
    ML_sel='all'
    fn_ens = 'Models/Ensemble_run'
    fn_out = 'Results'
    sel_metric = 'CRPS' #'MAE', 'NSE', 'RMSE'

    # load prescreening check
    df_prescreening = pd.read_csv('prescreening_station_parametrization.csv')
    station_list = df_prescreening['station'][df_prescreening['available'] == True].values

    for station in station_list:
        station = 'cuxhaven-cuxhaven-germany-bsh'
        print(f'Start ML ensemble run for station: {station}')
        post_process(station, ML_sel, fn_ens, fn_out, sel_metric)
        sys.exit(0)

def post_process(station, ML_sel, fn_ens, fn_out, sel_metric):
    
    if ML_sel.lower() == 'all':
        ML_list = ['CNN', 'LSTM', 'ANN', 'ConvLSTM']
    else:
        ML_list = [ML_sel]
    
    date_parser = lambda x: datetime.datetime.strptime(x, "%Y-%m-%d %H:%M:%S")
    
    metric= pd.DataFrame(index=ML_list, columns=[station], data=None)
    metric.index.name = sel_metric
    
    for ML in ML_list:
        fn = os.path.join(fn_ens, station, ML, station + '_' + ML + '_prediction.csv')
        df_result = pd.read_csv(fn, index_col='time', date_parser=date_parser)        
        if sel_metric == 'CRPS':
            metric.loc[ML,station] = performance.crps_metrics(df_result.dropna(axis=0, how='any'))    
        if sel_metric == 'NSE':
            _, metric.loc[ML,station], _, _ = performance.ens_metrics(df_result.dropna(axis=0, how='any'))
        if sel_metric == 'RMSE':
            metric.loc[ML,station], _, _, _ = performance.ens_metrics(df_result.dropna(axis=0, how='any'))
        if sel_metric == 'MAE':
            _, _, _, metric.loc[ML,station] = performance.ens_metrics(df_result.dropna(axis=0, how='any'))
        
    metric[station] = pd.to_numeric(metric[station], errors='coerce')
    
    if (sel_metric == 'CRPS') or (sel_metric == 'MAE') or (sel_metric == 'RMSE'):
        best_metric = metric.idxmin() #Minimum value is best
    else:
        best_metric = metric.idxmax() #Minimum value is best  
        
    best_metric.name = 'best'
    metric = metric.append(best_metric) 
    
    model_dir = os.path.join(fn_out, sel_metric)        
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
        
    metric.transpose().to_csv(os.path.join(model_dir, station+'.csv'), index_label = sel_metric)

def post_process_global():
    fn_ens = 'Models/Ensemble_run'
    df_prescreening = pd.read_csv('prescreening_station_t0_batch10.csv')
    station_list = df_prescreening['station'][df_prescreening['available'] == True].values
    ML_list = ['CNN', 'LSTM', 'ANN', 'ConvLSTM']
    
    date_parser = lambda x: datetime.datetime.strptime(x, "%Y-%m-%d %H:%M:%S")
    metric = pd.DataFrame(index=station_list, data=None)
    df_loc = pd.read_excel(os.path.join('Coast_orientation', 'stations.xlsx'))
    df_loc = df_loc.set_index('Station')
    metric = metric.merge(df_loc[['Lat', 'Lon']], how='left', left_index=True, right_index=True)
    
    for station in station_list:
        print(station)
        # station = 'cuxhaven-cuxhaven-germany-bsh'
        ML_list_plus = ML_list.copy()
        ML_list_plus.append('Persistence')
        for ML in ML_list_plus:
            if ML == 'Persistence':
                fn = os.path.join(fn_ens, station, 'ANN', station + '_' + 'ANN' + '_prediction.csv')
                df_result = pd.read_csv(fn, index_col='time', date_parser=date_parser)
                model = 'persistence'

                # calculate persistence
                df_copy = df_result.copy()
                df_result = df_copy.iloc[1:].copy()
                df_result['Modelled'] = df_copy['Observed'].iloc[:-1].values
            else:
                fn = os.path.join(fn_ens, station, ML, station + '_' + ML + '_prediction.csv')
                df_result = pd.read_csv(fn, index_col='time', date_parser=date_parser)
                model = 'ensemble'      
            metric.loc[station, f'{ML}_CRPS'] = performance.crps_metrics(df_result.dropna(axis=0, how='any'), model=model)
            rmse, NSE, r2, mae, corrcoef = performance.ens_metrics(df_result.dropna(axis=0, how='any'), model=model)
            metric.loc[station, f'{ML}_RMSE'] = rmse
            metric.loc[station, f'{ML}_NSE'] = NSE
            metric.loc[station, f'{ML}_NNSE'] = 1 / (2 - NSE)
            metric.loc[station, f'{ML}_R2'] = r2
            metric.loc[station, f'{ML}_corrcoef'] = corrcoef[0][1]
            metric.loc[station, f'{ML}_MAE'] = mae
    
        # metric.loc[station] = pd.to_numeric(metric.loc[station], errors='coerce')
        for sel_metric in ['CRPS', 'RMSE', 'NSE', 'NNSE', 'R2', 'MAE', 'corrcoef']:
            sel_columns = [f'{ML}_{sel_metric}' for ML in ML_list]
            if (sel_metric == 'CRPS') or (sel_metric == 'MAE') or (sel_metric == 'RMSE'):
                metric.loc[station, f'Best_{sel_metric}'] = metric.loc[station][sel_columns].astype(float).idxmin()
                metric.loc[station, f'Best_{sel_metric}_val'] = metric.loc[station][sel_columns].astype(float).min()
            else:
                metric.loc[station, f'Best_{sel_metric}'] = metric.loc[station][sel_columns].astype(float).idxmax()
                metric.loc[station, f'Best_{sel_metric}_val'] = metric.loc[station][sel_columns].astype(float).max()
        
    metric.to_csv(os.path.join('Results', 'Global_performance_metrics.csv')) 
    
def clim_mean():
    logger, ch = set_logger(0, 0)
    df_global = pd.read_csv(os.path.join('Results', 'Global_performance_metrics.csv'), index_col='Unnamed: 0') 
    df_global['CM_CRPS'] = np.nan


    df_prescreening = pd.read_csv('prescreening_station_t0_batch10.csv')
    station_list = df_prescreening['station'][df_prescreening['available'] == True].values
    for station in station_list:
        logger.info(station)
        filename = os.path.join('Input_nc_all_detrend_all', f'{station}.nc')
        ds = xr.open_dataset(filename)
        df = ds['residual'].to_dataframe()
        df = df.rolling('12H').mean()
        win_type = 'gaussian'
        df[win_type] = df.rolling(24*30, win_type=win_type, center=True).mean(std=72)['residual'].values

        filename = os.path.join('Models', 'Ensemble_run', station, 'CNN', f'{station}_CNN_prediction.csv')
        df_nn = pd.read_csv(filename, parse_dates=True , index_col='time')
        del df_nn.index.name
        df[win_type].loc[df_nn.index.values] = np.nan

        quantile_list = np.arange(0.025, 1, 0.05)
        sample_columns = [f'Modelled_{i}' for i in range(20)]
        df = pd.concat([df,pd.DataFrame(columns=sample_columns)])
        for month in range(1, 13):
            df_month = df[win_type][df.index.month == month]
            sample_vals = df_month.quantile(quantile_list).values
            tile = np.tile(sample_vals, ((df.index.month == month).sum(), 1))
            df_a = pd.DataFrame(tile, index=df[df.index.month == month].index, columns=sample_columns)
            df.update(df_a.copy())

        df_nn.update(df.loc[df_nn.index.values].copy())
        df_nn = df_nn.astype(float)
        df_nn = df_nn.drop(['max', 'min', 'median'], axis=1)

        filename = os.path.join('Models', 'Ensemble_run', station, 'CM', f'{station}_CM_prediction.csv')
        if not os.path.exists(os.path.split(filename)[0]):
            os.makedirs(os.path.split(filename)[0])
        df_nn.to_csv(filename)

        df_global.loc[station, 'CM_CRPS'] = performance.crps_metrics(df_nn.dropna(axis=0, how='any'))

    df_global.to_csv(os.path.join('Results', 'Global_performance_metrics_CM.csv')) 
