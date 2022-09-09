# core imports
import os

# third party import 
import yaml
import pandas as pd

# module imports
import data_ingest as di

# get current working directory
CWD = os.getcwd()

# Load config
with open(os.path.join(CWD, "config.yaml")) as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)
    module = os.path.basename(__file__)
    print(f"Config loaded in {module}")

# Years
# Getting the year for population data
pop_year = str(config["calculation_year"])

# Load config
with open(os.path.join(CWD, "config.yaml")) as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)
    module = os.path.basename(__file__)
    print(f"Config loaded in {module}")

# gets the northern ireland bus stops data from the api
ni_bus_stop_url = config["NI_bus_stops_data"]
output_ni_bus_csv = os.path.join(CWD,"data","Stops","NI","bus_stops_ni.csv")

# reads in the NI bus stop data as geo df and saves bus data if it has not been saved
ni_bus_stops = di.read_ni_stops(ni_bus_stop_url, output_ni_bus_csv)

# gets the northern ireland train stops data from the api
ni_train_stop_url = config["NI_train_stops_data"]
output_ni_train_csv = os.path.join(CWD,"data","Stops","NI","train_stops_ni.csv")

# reads in the NI train  stop data as geo df and saves train data if it has not been saved
ni_train_stops = di.read_ni_stops(ni_train_stop_url, output_ni_train_csv)

# Get usual population for Northern Ireland (Census 2011 data)
whole_NI_df = pd.read_csv(os.path.join(CWD, "data", "KS101NI.csv"),
                             header=2)
# Only use columns that we need
cols_NI_df = ["SA Code", "All usual residents","Usual residents: Males","Usual residents: Females"]
census_ni_df = whole_NI_df[cols_NI_df]

# Read in mid-year population estimates for Northern Ireland
pop_files = pd.read_csv(os.path.join(CWD, 
                                     "data", "population_estimates", 
                                     "SAPE20-SA-Totals.csv"),
                        header=7)

# Filter to small area code and population year columns only
estimate_cols = ["Area_Code", pop_year]
estimate_pop_NI = pop_files[estimate_cols]



