# Core imports
import os
import time
import random

# Third party imports
import geopandas as gpd
import pandas as pd
import yaml
# import gptables as gpt

# Module imports
import geospatial_mods as gs
import data_transform as dt
import data_output as do

start_time = time.time()

# Data imports
from eng_wales_pre_process import stops_geo_df
from eng_wales_pre_process import ew_urb_rur_df
from eng_wales_pre_process import ew_la_df
from eng_wales_pre_process import ew_oa_la_lookup_df
from eng_wales_pre_process import ew_oa_boundaries_df
from eng_wales_pre_process import ew_pop_df
from eng_wales_pre_process import ew_pop_wtd_centr_df
from eng_wales_pre_process import ew_disability_df
from eng_wales_pre_process import ew_urb_rur_df


# get current working directory
CWD = os.getcwd()

# Load config
with open(os.path.join(CWD, "config.yaml"), encoding="utf-8") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)
    module = os.path.basename(__file__)
    print(f"Config loaded in {module}")


# Years
# Getting the year for population data
CALCULATION_YEAR = str(config["calculation_year"])

# Constants
lad_col = f'LAD{CALCULATION_YEAR[-2:]}NM'

if __name__ == "__main__":
        
    # Merge datasets into PWCs ready for analysis

    # 1 output area boundaries
    ew_df = ew_pop_wtd_centr_df.merge(
        ew_oa_boundaries_df, on="OA11CD", how='left')
    
    # 2 Rural urban classification
    ew_df = ew_df.merge(ew_urb_rur_df, on="OA11CD", how='left')
    
    # 3 Population data
    # First join output area lookup onto popualtion data
    ew_pop_df = ew_pop_df.merge(ew_oa_la_lookup_df, on='OA11CD', how='left')
    # Then add into PWC
    ew_df = ew_df.join(ew_pop_df.set_index('OA11CD'), on='OA11CD', how='left')

    # 5 local authority boundaries
    ew_df = ew_df.merge(ew_la_df, how='right', left_on=lad_col,
                        right_on=lad_col, suffixes=('_pop', '_la'))

    # Unique list of LA's to iterate through
    list_local_auth = ew_la_df[lad_col].unique()
    
    # selecting random LA for dev purposes
    # eventually will iterate through all LA's
    random_la = random.choice(list_local_auth)
    
    #list_local_auth = [random_la]
    list_local_auth = ['Hastings']
    
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
    
        # Creating a Geo Dataframe of only stops in slected la
        stops_in_la_poly = gs.find_points_in_poly(geo_df=stops_geo_df,
                                                 polygon_obj=la_poly)
    
        # Subset population data to local authority
        ew_df = ew_df.loc[ew_df[lad_col] == local_auth]
    
        # Group and reformat age data
        # ---------------------------
        # Get a list of ages from config
        age_lst = config['age_lst']
    
        # Get a datframe limited to the data ages columns only
        ew_age_df = dt.slice_age_df(ew_df, age_lst)
    
        # Create a list of tuples of the start and finish indexes for the age bins
        age_bins = dt.get_col_bins(age_lst)
    
        # get the ages in the age_df binned, and drop the original columns
        ew_age_df = dt.bin_pop_ages(ew_age_df, age_bins, age_lst)
    
        # Ridding the la_pop df of the same cols
        ew_df.drop(age_lst, axis=1, inplace=True)
    
        # merging summed+grouped ages back in
        ew_df = pd.merge(ew_df, ew_age_df, left_index=True, right_index=True)
    
        # Convert new population df into a geodataframe
        ew_df = gpd.GeoDataFrame(ew_df, geometry='geometry_pop', crs='EPSG:27700')
    
        # create a buffer around the stops
        stops_in_la_poly_buffer = gs.buffer_points(stops_in_la_poly)
    
        # Diasggregate disability data and join into population df
        # --------------------------------------------------------
        ew_df = dt.disab_disagg(ew_disability_df, ew_df)
    
        # renaming the dodgy col names with their replacements
        replacements = {"males_pop": "male",
                        "fem_pop": "female"}
        ew_df.rename(columns=replacements, inplace=True)
    
        # # merge the sex data with the rest of the population data
        # bham_pop_df = bham_pop_df.merge(sex_df, on='OA11CD', how='left')
    
        # Make a polygon object from the geometry column of the stops df
        # all_stops_poly = gs.poly_from_polys(birmingham_stops_geo_df)
    
        # find all the pop centroids which are in the la_stops_geo_df
        pwc_in_poly_df = gs.find_points_in_poly(ew_df,
                                                stops_in_la_poly_buffer)
    
        # Dedupe the df because many OAs are appearing multiple times
        # (i.e. they are served by multiple stops)
        pwc_in_poly_df = pwc_in_poly_df.drop_duplicates(subset="OA11CD")
    
        # Count the population served by public transport
        served = pwc_in_poly_df.pop_count.sum()
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
    
        # Re-orienting the df to what's accepted by the reshaper and renaming col
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
    
        # # Disaggregations!
        # pd.set_option("precision", 1)
    
        # Calculating those served and not served by age
        age_bins_ = ['0-4', '5-9', '10-14', '15-19', '20-24',
                    '25-29', '30-34', '35-39', '40-44', '45-49', '50-54',
                    '55-59', '60-64', '65-69', '70-74', '75-79',
                    '80-84', '85-89', '90+']
    
        age_servd_df = dt.served_proportions_disagg(pop_df=eng_wales_la_pop_df,
                                                    pop_in_poly_df=pop_in_poly_df,
                                                    cols_lst=age_bins_)
    
        # Feeding the results to the reshaper
        age_servd_df_out = do.reshape_for_output(age_servd_df,
                                                id_col="Age",
                                                local_auth=local_auth)
    
        # Output this local auth's age df to the dict
        age_df_dict[local_auth] = age_servd_df_out
    
        # print(age_servd_df)
    
        # # Calculating those served and not served by sex
        sex_cols = ['male', 'female']
    
        sex_servd_df = dt.served_proportions_disagg(pop_df=eng_wales_la_pop_df,
                                                    pop_in_poly_df=pop_in_poly_df,
                                                    cols_lst=sex_cols)
    
        # Feeding the results to the reshaper
        sex_servd_df_out = do.reshape_for_output(sex_servd_df,
                                                id_col="Sex",
                                                local_auth=local_auth)
    
        # Output this iteration's sex df to the dict
        sex_df_dict[local_auth] = sex_servd_df_out
    
        # Calculating those served and not served by disability
        disab_cols = ["number_disabled"]
    
        disab_servd_df = (
            dt.served_proportions_disagg(pop_df=eng_wales_la_pop_df,
                                        pop_in_poly_df=pop_in_poly_df,
                                        cols_lst=disab_cols)
        )
    
        # Feeding the results to the reshaper
        disab_servd_df_out = do.reshape_for_output(disab_servd_df,
                                                id_col=disab_cols[0],
                                                local_auth=local_auth,
                                                id_rename="Disability Status")
    
        # The disability df is unusual. I think all rows correspond to people with
        # disabilities only. There is no "not-disabled" status here (I think)
        disab_servd_df_out.replace(to_replace="number_disabled",
                                value="Disabled",
                                inplace=True)
    
        # Output this iteration's sex df to the dict
        sex_df_dict[local_auth] = sex_servd_df_out
    
        # Calculating non-disabled people served and not served
        # Disability disaggregation - get disability results in disab_df_dict
        disab_df_dict = dt.disab_dict(eng_wales_la_pop_df, pop_in_poly_df, disab_df_dict, local_auth)

        # Calculating those served and not served by urban/rural
        urb_col = ["urb_rur_class"]
    
        # Filtering by urban and rural to make 2 dfs
        urb_df = eng_wales_la_pop_df[eng_wales_la_pop_df.urb_rur_class == "urban"]
        rur_df = eng_wales_la_pop_df[eng_wales_la_pop_df.urb_rur_class == "rural"]
    
        # Because these dfs a filtered to fewer rows, the pop_in_poly_df must be
        # filtered in the same way
        urb_pop_in_poly_df = (urb_df.merge(pop_in_poly_df,
                                        on="OA11CD", how="left")
                            .loc[:, ['OA11CD', 'pop_count_y']])
        urb_pop_in_poly_df.rename(
            columns={'pop_count_y': 'pop_count'}, inplace=True)
        rur_pop_in_poly_df = (rur_df.merge(pop_in_poly_df,
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
    
        # Output this iteration's urb and rur df to the dict
        urb_rur_df_dict[local_auth] = urb_rur_servd_df_out
    
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
    final_result["Year"] = POP_YEAR
    
    # Resetting index for gptables
    final_result.reset_index(inplace=True)
    
    
    # Outputting to CSV
    final_result = do.reorder_final_df(final_result)
    output_path = os.path.join(OUTPUT_DIR, OUTFILE)
    final_result.to_csv(output_path, index=False)
    
    print(f"Time taken is {time.time()-start_time:.2f} seconds")
    