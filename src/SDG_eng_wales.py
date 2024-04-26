# Core imports
import os
import time
import random

# Third party imports
import geopandas as gpd
import pandas as pd
import yaml

# Module imports
import geospatial_mods as gs
import data_transform as dt
import data_output as do
import data_ingest as di


# Start pipeline
start_time = time.time()

# Get current working directory
CWD = os.getcwd()

# Load config
with open(os.path.join(CWD, "config.yaml"), encoding="utf-8") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)
    module = os.path.basename(__file__)
    print(f"Config loaded in {module}")


# Load years
CALCULATION_YEAR = str(config["calculation_year"])

# Load constants
OUTPUT_DIR = config["data_output"]
OUTFILE = config['outfile']
DEFAULT_CRS = config['default_crs']
ENG_WALES_PREPROCESSED_OUTPUT = config["eng_wales_preprocessed_output"]


# Load preprocessed datasets
# --------------------------

stops_geo_df_path = os.path.join(ENG_WALES_PREPROCESSED_OUTPUT,
                                 'stops_geo_df.geojson')

# Raise error if the file does not exist (should have been created by preprocessing)


# Define paths to preprocessed data
stops_geo_df_path = os.path.join(ENG_WALES_PREPROCESSED_OUTPUT, 'stops_geo_df.geojson')
ew_la_df_path = os.path.join(ENG_WALES_PREPROCESSED_OUTPUT, 'ew_la_df.geojson')
ew_df_path = os.path.join(ENG_WALES_PREPROCESSED_OUTPUT, 'ew_df.geojson')
ew_disability_df_path = os.path.join(ENG_WALES_PREPROCESSED_OUTPUT, 'ew_disability_df.feather')

# Create the dataframes
stops_geo_df = di.read_file_if_exists(stops_geo_df_path, gpd.read_file)
ew_la_df = di.read_file_if_exists(ew_la_df_path, gpd.read_file)
ew_df = di.read_file_if_exists(ew_df_path, gpd.read_file)
ew_disability_df = di.read_file_if_exists(ew_disability_df_path, lambda path: di.feath_to_df('ew_disability_df', path))



if __name__ == "__main__":

    lad_col = f'LAD{CALCULATION_YEAR[-2:]}NM'

    # Unique list of LA's to iterate through
    list_local_auth = ew_la_df[lad_col].unique()

    # selecting random LA for dev purposes
    # eventually will iterate through all LA's
    # random_la = random.choice(list_local_auth)

    # list_local_auth = ["Middlesborough"]


    # define output dicts to capture dfs
    total_df_dict = {}
    sex_df_dict = {}
    urb_rur_df_dict = {}
    disab_df_dict = {}
    age_df_dict = {}

    for local_auth in list_local_auth:

        print(f"Processing: {local_auth}")

        # Get a polygon of the selected local authority
        la_poly = gs.get_polygons_of_loccode(geo_df=ew_la_df,
                                             dissolveby=lad_col,
                                             search=local_auth)

        # Creating a Geo Dataframe of only stops in selected la
        stops_in_la_poly = gs.find_points_in_poly(geo_df=stops_geo_df,
                                                  polygon_obj=la_poly)

        # Create a buffer around the stops
        stops_in_la_poly_buffer = gs.buffer_points(stops_in_la_poly)

        # Subset population data to local authority
        local_df = ew_df.loc[ew_df[lad_col] == local_auth]

        # Convert population df into a geodataframe
        local_df = gpd.GeoDataFrame(ew_df, geometry='geometry', crs=DEFAULT_CRS)

        # Diasggregate disability data and join into population df
        # --------------------------------------------------------
        local_df = dt.disab_disagg(ew_disability_df, local_df)

        # renaming the dodgy col names with their replacements
        replacements = {"males_pop": "male",
                        "fem_pop": "female"}
        local_df.rename(columns=replacements, inplace=True)

        # Extract the population served by public transport
        # -------------------------------------------------

        # find all the pop centroids which are in the buffered stops
        pwc_in_stops_buffer_df = (
            gs.find_points_in_poly(local_df, stops_in_la_poly_buffer)
        )

        # Dedupe the df because many OAs are appearing multiple times
        # (i.e. they are served by multiple stops)
        pwc_in_stops_buffer_df = (
            pwc_in_stops_buffer_df.drop_duplicates(subset="OA11CD"))
        
        # Rename male female columns in pwc_in_stops_buffer_df
        pwc_in_stops_buffer_df.rename(columns=replacements, inplace=True)

        # Count the p.opulation served by public transport
        served = pwc_in_stops_buffer_df.pop_count.sum()
        full_pop = ew_df.pop_count.sum()
        not_served = full_pop - served
        pct_not_served = "{:.2f}".format(not_served / full_pop * 100)
        pct_served = "{:.2f}".format(served / full_pop * 100)

        print(
            f"""The number of people who are served by public transport is {served}.\n
                The full population of {local_auth} is calculated as {full_pop}
                While the number of people who are not served is {not_served}""")

        la_results_df = pd.DataFrame({"All_pop": [full_pop],
                                      "Served": [served],
                                      "Unserved": [not_served],
                                      "Percentage served": [pct_served],
                                      "Percentage unserved": [pct_not_served]})

        # Reformat data for output
        # ------------------------

        # Re-orienting the df to what's accepted by the reshaper and renaming
        # col
        la_results_df = la_results_df.T.rename(columns={0: "Total"})

        # Feeding the la_results_df to the reshaper
        la_results_df_out = do.reshape_for_output(la_results_df,
                                                  id_col="Total",
                                                  local_auth=local_auth)

        # Finally for the local authority totals the id_col can be dropped
        # That's because the disaggregations each have their own column,
        # but "Total" is not a disaggregation so doesn't have a column.
        # It will simply show up as blanks (i.e. Total) in all disagg columns
        la_results_df_out.drop("Total", axis=1, inplace=True)

        # Output this iteration's df to the dict
        total_df_dict[local_auth] = la_results_df_out

        # Run the disaggregations
        # -----------------------
        # Age
        # ---
        grouped_age_bins = ['0-4', '5-9', '10-14', '15-19', '20-24',
                            '25-29', '30-34', '35-39', '40-44', '45-49', '50-54',
                            '55-59', '60-64', '65-69', '70-74', '75-79',
                            '80-84', '85-89', '90+']

        age_servd_df = (
            dt.served_proportions_disagg(pop_df=ew_df,
                                         pop_in_poly_df=pwc_in_stops_buffer_df,
                                         cols_lst=grouped_age_bins)
        )

        # Feeding the results to the reshaper
        age_servd_df_out = do.reshape_for_output(age_servd_df,
                                                 id_col="Age",
                                                 local_auth=local_auth)

        age_df_dict[local_auth] = age_servd_df_out

        # Sex
        # ---
        sex_cols = ['male', 'female']

        sex_servd_df = dt.served_proportions_disagg(pop_df=ew_df,
                                                    pop_in_poly_df=pwc_in_stops_buffer_df,
                                                    cols_lst=sex_cols)

        # Feeding the results to the reshaper
        sex_servd_df_out = do.reshape_for_output(sex_servd_df,
                                                 id_col="Sex",
                                                 local_auth=local_auth)

        sex_df_dict[local_auth] = sex_servd_df_out

        # Disabled
        # --------
        disab_cols = ["number_disabled"]

        disab_servd_df = (
            dt.served_proportions_disagg(pop_df=ew_df,
                                         pop_in_poly_df=pwc_in_stops_buffer_df,
                                         cols_lst=disab_cols)
        )

        # Feeding the results to the reshaper
        disab_servd_df_out = do.reshape_for_output(
            disab_servd_df,
            id_col=disab_cols[0],
            local_auth=local_auth,
            id_rename="Disability Status")

        # The disability df is unusual. I think all rows correspond to people
        # with disabilities only. There is no "not-disabled" status here
        disab_servd_df_out.replace(to_replace="number_disabled",
                                   value="Disabled",
                                   inplace=True)

        disab_df_dict[local_auth] = disab_servd_df_out

        # Not disabled
        # ------------
        # Disability disaggregation - get disability results in disab_df_dict
        disab_df_dict = dt.disab_dict(ew_df,
                                      pwc_in_stops_buffer_df,
                                      disab_df_dict,
                                      local_auth)

        # Urban and rural
        # ---------------
        urb_col = ["urb_rur_class"]

        # Filtering by urban and rural to make 2 dfs
        urb_df = ew_df[ew_df.urb_rur_class == "urban"]
        rur_df = ew_df[ew_df.urb_rur_class == "rural"]

        # Because these dfs a filtered to fewer rows, the
        # pwc_in_stops_buffer_df must be filtered in the same way
        urb_pop_in_poly_df = (urb_df.merge(pwc_in_stops_buffer_df,
                                           on="OA11CD", how="left")
                              .loc[:, ['OA11CD', 'pop_count_y']])

        urb_pop_in_poly_df.rename(
            columns={'pop_count_y': 'pop_count'}, inplace=True)

        rur_pop_in_poly_df = (rur_df.merge(pwc_in_stops_buffer_df,
                                           on="OA11CD", how="left")
                              .loc[:, ['OA11CD', 'pop_count_y']])

        rur_pop_in_poly_df.rename(
            columns={'pop_count_y': 'pop_count'}, inplace=True)

        urb_servd_df = dt.served_proportions_disagg(
            pop_df=urb_df,
            pop_in_poly_df=urb_pop_in_poly_df,
            cols_lst=['pop_count'])

        rur_servd_df = dt.served_proportions_disagg(
            pop_df=rur_df,
            pop_in_poly_df=rur_pop_in_poly_df,
            cols_lst=['pop_count'])

        # Renaming pop_count to either urban or rural
        urb_servd_df.rename(columns={"pop_count": "Urban"}, inplace=True)
        rur_servd_df.rename(columns={"pop_count": "Rural"}, inplace=True)

        # Sending each to reshaper
        urb_servd_df_out = do.reshape_for_output(urb_servd_df,
                                                 id_col="Urban",
                                                 local_auth=local_auth)
        rur_servd_df_out = do.reshape_for_output(rur_servd_df,
                                                 id_col="Rural",
                                                 local_auth=local_auth)
        # Renaming their columns to Urban/Rural
        urb_servd_df_out.rename(columns={"Urban": "Urban/Rural"}, inplace=True)
        rur_servd_df_out.rename(columns={"Rural": "Urban/Rural"}, inplace=True)

        # Combining urban and rural dfs
        urb_rur_servd_df_out = pd.concat([urb_servd_df_out, rur_servd_df_out])

        urb_rur_df_dict[local_auth] = urb_rur_servd_df_out

    # Outputting results to CSV
    # -------------------------
    # Create dataframes for dissaggregations accross all local authorities
    all_la = pd.concat(total_df_dict.values())
    sex_all_la = pd.concat(sex_df_dict.values())
    urb_rur_all_la = pd.concat(urb_rur_df_dict.values())
    disab_all_la = pd.concat(disab_df_dict.values())
    age_all_la = pd.concat(age_df_dict.values())

    output_tabs = {}

    # Stacking the dataframes
    all_results_dfs = [
        all_la,
        sex_all_la,
        urb_rur_all_la,
        disab_all_la,
        age_all_la]
    final_result = pd.concat(all_results_dfs)
    final_result["Year"] = CALCULATION_YEAR

    # Resetting index for gptables
    final_result.reset_index(inplace=True)

    # Outputting to CSV
    final_result = do.reorder_final_df(final_result)
    output_path = os.path.join(OUTPUT_DIR, OUTFILE)
    final_result.to_csv(output_path, index=False)

    print(f"Time taken is {time.time()-start_time:.2f} seconds")
