import xarray as xr
import to_learning
import pandas as pd
import os

os.chdir('..')

def merge_sst_ds(station):

    df, ds, dir = to_learning.load_file(station, input_dir = '../Input_nc_all_detrend_all')
    
    sst_ds = xr.open_dataset('Input_sst_data/' + station + '_sst.nc')
    
    sst_ds = xr.merge([ds, sst_ds]) # Merge datasets
        
    print('Writing')
    sst_ds.to_netcdf('Input_nc_detrend_sst/' + station + '.nc') # Write to a new file


stations = pd.read_csv('Coast_orientation/Selected_Stations_dates.csv').dropna().reset_index(drop=True)

for index, station in stations.iterrows():
    print(f'Merging SST for Station {index}: {station["Station"]}\n')
    
    if os.path.exists('Input_nc_detrend_sst/' + station['Station'] + '.nc'):
        print('File already exists')
        continue
    else:
        merge_sst_ds(station['Station'])