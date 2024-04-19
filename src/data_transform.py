from typing import List
import pandas as pd
from convertbng.util import convert_bng
import logging
import os

# Our modules
import data_output as do

# Get CWD
CWD = os.getcwd()


# Create logger
logger = logging.getLogger(__name__)


# Get CWD
CWD = os.getcwd()


# Create logger
logger = logging.getLogger(__name__)


def slice_age_df(df: pd.DataFrame, col_nms: List[str]):
    """Slices a dataframe according to the list of column names provided.

    Args:
        df (pd.DataFrame): DataFrame to be sliced.
        col_nms (List[str]): column names as string in a list.

    Returns:
        pd.DataFrame: A dataframe sliced down to only the columns required.
    """
    age_df = df.loc[:, col_nms]
    return age_df


# type hint '-> List[tuple]' causing this doctring not to work
def get_col_bins(col_nms: List[str]):
    """Function to group/bin the ages together in 5 year steps.

    Starts the sequence at age 0.
        Will return the ages in a list of tuples.
        The 0th position of the tuple being the lower limit
        of the age bin, the 1st position of the tuple being
        the upper limit.

    Args:
        col_nms (list of str): a list of the age columns as strings.

    Returns:
        list of tuples: a list of the ages with 5 year gaps.
    """

    # Make a lists of starting and finishing indexes
    cols_start = col_nms[0::5]
    cols_fin = col_nms[4::5]
    # Generating a list of tuples which will be the age groupings
    col_bins = [(s, f) for s, f in zip(cols_start, cols_fin)]
    # Again adding "90+", doubling it so it's doubled, like the other tuples
    col_bins.append((cols_start[-1:] * 2))
    # TODO: make this more intelligent. Only if there is one col name left
    # over it should be doubled.
    return col_bins


def bin_pop_ages(age_df, age_bins, col_nms):
    """ Bins the ages in the age_df in 5 year spans from 0 to 90+,
    sums the counts in those bins
    and drops the original age columns.

    Args:
        df (pd.DataFrame): A dataframe of population data
            containing only the age columns.

    Returns:
        pd.DataFrame: Returns the age_df with bins.
    """
    # Grouping ages in 5 year brackets

    # cleaning scottish data and changing dtype to float
    original_columns = age_df.columns
    for col in original_columns:
        if age_df[col].dtypes == "O":
            age_df[col] = age_df[col].str.replace('-', '0')
            age_df[col] = age_df[col].astype(int)

    def _age_bin(age_df, age_bins):
        """Function sums the counts for corresponding age-bins and assigns
        them a column in age_df."""
        for bin in age_bins:
            age_df[f"{bin[0]}-{bin[1]}"] = (
                age_df.loc[:, bin[0]:bin[1]].sum(axis=1))
        return age_df

    # create 90+ column for when there are more columns than 90
    if len(age_df.columns) > 91:
        # create 90+ column summing all those from 90 and above.
        age_df['90+'] = age_df.iloc[:, 90:].sum(axis=1)
        age_df = _age_bin(age_df, age_bins)
        # drop the original age columns
        age_df.drop(col_nms, axis=1, inplace=True)
        # drop the columns that we are replacing with 90+
        age_df.drop(age_df.iloc[:, 19:], axis=1, inplace=True)
        # moving first column to last so 90+ at the end.
        temp_cols = age_df.columns.tolist()
        new_cols = temp_cols[1:] + temp_cols[0:1]
        age_df = age_df[new_cols]
    else:
        age_df = _age_bin(age_df, age_bins)
        # drop the original age columns
        age_df.drop(col_nms, axis=1, inplace=True)
        # rename the 90+ column
        age_df.rename(columns={'90+-90+': '90+'}, inplace=True)
    # age df has now been binned and cleaned
    return round(age_df)


def served_proportions_disagg(pop_df: pd.DataFrame,
                              pop_in_poly_df: pd.DataFrame,
                              cols_lst: List[str]):
    """Calculates the number of people in each category, as specified by the column
    (e.g age range, or disability status) who are served and not served by
    public transport, and gives those as a proportion of the total.

    Note: the numeric values in the dataframe are return as strings for
    formatting reasons

    Args:
        pop_df (pd.DataFrame): population dataframe.
        pop_in_poly_df (pd.DataFrame): dataframe resulting in the points
            in polygons enquiry to count (sum) the population within the
            service area polygon.
        cols_lst (List[str]): a list of the column names in the population
            dataframe supplied which contain population figures, and are to
            be summed and assessed as served/unserved by public transport.

    Returns:
        pd.DataFrame: a dataframe summarising
        i) the total number of people that column (e.g. age range, sex)
        ii) the number served by public transport
        iii) the proportion who are served by public transport
        iv) the proportion who are not served by public transport
    """
    # First list the age bin columns

    pop_sums = {}
    for col in cols_lst:
        if col == "male":
            pop_df_col = "males_pop"
        elif col == "female":
            pop_df_col = "fem_pop"
        else:
            pop_df_col = 'pop_count'
        # Total pop
        total_pop = int(pop_df[pop_df_col].sum())
        # Served pop
        servd_pop = int(pop_in_poly_df[col].sum())
        # Unserved pop
        unsrvd_pop = int(total_pop - servd_pop)
        if total_pop == 0:
            # If the total population for that column is 0
            # this standard of zeros and Nones is returned
            pop_sums[col] = {"Total": str(total_pop),
                             "Served": str(servd_pop),
                             "Unserved": str(unsrvd_pop),
                             "Percentage served": "None",
                             "Percentage unserved": "None"}
        elif total_pop > 0:
            pop_sums[col] = _calc_proprtn_srvd_unsrvd(total_pop,
                                                      servd_pop,
                                                      unsrvd_pop)

    # Make a df from the total and served pop
    tot_servd_df = pd.DataFrame(pop_sums)
    return tot_servd_df


def _calc_proprtn_srvd_unsrvd(total_pop,
                              servd_pop,
                              unsrvd_pop):
    """Calculates proportions of people served and unserved by public transport.

    Args:
        total_pop (int):  The total population for that category.
        servd_pop (int):  Of the population, those who are served
            by public transport.
        unsrvd_pop (int): Of the population, those who are NOT served
            by public transport.

    Returns:
        dict: A dictionary with the following:
                i) the total number of people that column (e.g. age range, sex)
                ii) the number served by public transport
                iii) the percentage of who are served by public transport
                iv) the percentage ofwho are not served by public transport
    """
    # Get proportion served
    pct_servd = round((servd_pop / total_pop) * 100, 2)
    # Get proportion unserved
    pct_unserved = round(((total_pop - servd_pop) / total_pop) * 100, 2)
    results_dict = {"Total": str(total_pop),
                    "Served": str(servd_pop),
                    "Unserved": str(unsrvd_pop),
                    "Percentage served": str(pct_servd),
                    "Percentage unserved": str(pct_unserved)}
    return results_dict


def disab_disagg(disability_df, la_pop_df):
    """Calculates number of people in the population that are classified as
        disabled or not disabled and this is merged onto the local authority
        population dataframe.
    Args:
        disability_df (pd.DataFrame): Dataframe that includes disability
                                    estimates for each output area.
        la_pop_df (gpd.GeoDataFrame): GeoPandas Dataframe that includes
                                output area codes and population estimates.
    Returns:
        gpd.GeoDataFrame: GeoPandas Dataframe that includes population
                        estimates, geographical location, and proportion
                        of disabled/non-disabled for each output area in
                        the local authority chosen.
    """
    # Getting the disab total
    disability_df["disb_total"] = (disability_df["disab_ltd_lot"]
                                   + disability_df["disab_ltd_little"])

    # Calcualting the total "non-disabled"
    la_pop_only = la_pop_df[['OA11CD', 'pop_count']]
    disability_df = la_pop_only.merge(disability_df, on="OA11CD")
    # Putting the result back into the disability df
    disability_df["non-disabled"] = disability_df["pop_count"] - \
        disability_df['disb_total']

    # Calculating the proportion of disabled people in each OA
    disability_df["proportion_disabled"] = (
        disability_df['disb_total']
        /
        disability_df['pop_count']
    )

    # Calcualting the proportion of non-disabled people in each OA
    disability_df["proportion_non-disabled"] = (
        disability_df['non-disabled']
        /
        disability_df['pop_count']
    )

    # Slice disability df that only has the proportion disabled column and the
    # OA11CD col
    disab_prop_df = disability_df[[
        'OA11CD', 'proportion_disabled', 'proportion_non-disabled']]

    # Drop any rows in the la_pop_df with None values in the OA11CD col
    la_pop_df = la_pop_df.dropna(subset=["OA11CD"])

    # Merge the proportion disability df into main the pop df with a left join
    la_pop_df = la_pop_df.merge(disab_prop_df, on='OA11CD', how="left")

    # Make the calculation of the number of people with disabilities in the
    # year of the population estimates
    la_pop_df["number_disabled"] = (
        round
        (la_pop_df["pop_count"]
         *
         la_pop_df["proportion_disabled"])
    )
    # la_pop_df["number_disabled"] = la_pop_df["number_disabled"].astype(int)

    # Make the calculation of the number of non-disabled people in the year
    # of the population estimates
    la_pop_df["number_non-disabled"] = (
        round
        (la_pop_df["pop_count"]
         *
         la_pop_df["proportion_non-disabled"])
    )
    la_pop_df["number_non-disabled"] = la_pop_df["number_non-disabled"].astype(
        int)

    return la_pop_df


def disab_dict(la_pop_df, pop_in_poly_df, disability_dict, local_auth):
    """Creates the dataframe including those who are and are not served by
    public transport and places it into a disability dictionary for each
    local authority of interest for the final csv output.

    Args:
        la_pop_df (gpd.GeoDataFrame): GeoPandas Dataframe that includes
                                    output area codes and population estimates.
        pop_in_poly_df (gpd.GeoDataFrame): A geodata frame with the points
                                            inside the polygon.
        disability_dict (dict): Dictionary to store the disability
                                    dataframe.
        local_auth (str): The local authority of interest.

    Returns:
        disability_dict (dict): Dictionary with a disability total dataframe
                            for unserved and served populations for all given
                            local authorities.
    """
    # Calculating those served and not served by disability
    disab_cols = ["number_disabled"]

    disab_servd_df = served_proportions_disagg(la_pop_df,
                                               pop_in_poly_df,
                                               disab_cols)

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

    # Calculating non-disabled people served and not served
    non_disab_cols = ["number_non-disabled"]

    non_disab_servd_df = served_proportions_disagg(
        pop_df=la_pop_df,
        pop_in_poly_df=pop_in_poly_df,
        cols_lst=non_disab_cols)

    # Feeding the results to the reshaper
    non_disab_servd_df_out = do.reshape_for_output(
        non_disab_servd_df,
        id_col=disab_cols[0],
        local_auth=local_auth,
        id_rename="Disability Status")

    # The disability df is unusual. I think all rows correspond to people with
    # disabilities only. There is no "not-disabled" status here (I think)
    non_disab_servd_df_out.replace(to_replace="number_non-disabled",
                                   value="Non-disabled",
                                   inplace=True)

    # Concatting non-disabled and disabled dataframes
    non_disab_disab_servd_df_out = pd.concat(
        [non_disab_servd_df_out, disab_servd_df_out])

    # Output this local auth's disab df to the dict
    disability_dict[local_auth] = non_disab_disab_servd_df_out

    return disability_dict


def urban_rural_results(la_pop_df, pop_in_poly_df, urb_rur_dict, local_auth):
    """
    Creates two dataframes, urban and rural and classifies proportion
    of people served and not served by public transport. This is placed into
    a urban rural dictionary for each local authority of interest for the
    final csv output.

    Args:
        la_pop_df (gpd.GeoDataFrame): GeoPandas Dataframe that includes
                                    output area codes and population estimates.
        pop_in_poly_df (gpd.GeoDataFrame): A geodata frame with the points
                                            inside the polygon.
        urb_rur_dict (dict): Dictionary to store the urban rural dataframe.
        local_auth (str): The local authority of interest.

    Returns:
        urb_rur_dict (dict): Dictionary with a disability total dataframe for
                            unserved and served populations for all given
                            local authorities.

    """
    # Urban/Rural disaggregation
    # split into two different dataframes
    urb_df = la_pop_df[la_pop_df.urb_rur_class == "urban"]
    rur_df = la_pop_df[la_pop_df.urb_rur_class == "rural"]

    urb_df_poly = pop_in_poly_df[pop_in_poly_df.urb_rur_class == "urban"]
    rur_df_poly = pop_in_poly_df[pop_in_poly_df.urb_rur_class == "rural"]

    urb_servd_df = served_proportions_disagg(pop_df=urb_df,
                                             pop_in_poly_df=urb_df_poly,
                                             cols_lst=['pop_count'])

    rur_servd_df = served_proportions_disagg(pop_df=rur_df,
                                             pop_in_poly_df=rur_df_poly,
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
    urb_rur_dict[local_auth] = urb_rur_servd_df_out

    return urb_rur_dict


def create_tiploc_col(naptan_df):
    """Creates a Tiploc column from the ATCOCode column, in the NaPTAN dataset.

    Args:
        naptan_df (pd.Dataframe): Naptan dataset

    Returns:
        pd.Dataframe (naptan_df): Naptan dataset with the new tiploc column
        added for train stations
    """
    # Applying only to train stations, RLY is the stop type for train stations
    rail_filter = naptan_df.StopType == "RLY"

    # Create a new pd.Dataframe for Tiploc by extracting upto 7 alpha
    # characters
    tiploc_col = (naptan_df.loc[rail_filter]
                  .ATCOCode
                  .str.extract(r'([A-Za-z]{1,7})')
                  )
    tiploc_col.columns = ["tiploc_code"]

    # Merge the new Tiploc column with the naptan_df
    naptan_df = naptan_df.merge(
        tiploc_col, how='left', left_index=True, right_index=True)

    return naptan_df


def convert_east_north(df, long, lat):
    """
    Converts latitude and longitude coordinates to British National Grid
    Args:
        df (pd.DataFrame): df including the longitude and latitude coordinates
        long(str): The name of the longitude column in df
        lat (str): The name of the latitude column in df
    Returns:
        pd.DataFrame: dataframe including easting and northing coordinates.
    """
    df['Easting'], df['Northing'] = convert_bng(df[long], df[lat])
    return df

def mid_year_age_estimates(age_df, pop_estimates_df, pop_year):
    """
    Takes mid-year population estimates for each small area in NI and uses proportions
    to calculate mid-year estimates for each age.
    Args:
        age_df (pd.DataFrame): Census 2011 age estimates dataframe
        pop_estimates_df (pd.DataFrame): population estimates for each small area dataframe
        pop_year (str): population year """
    # get all age columns in a list
    age_cols = [str(y) for y in range(101)]
    # iterate through each age
    for age in range(len(age_cols)):
        # calculates the proportions for each age and each SA code
        age_df[age_cols[age]] = age_df[age_cols[age]]/age_df['All usual residents']
    age_df.drop(['SA', 'All usual residents'], axis=1, inplace=True)
    # merges pop df and proportions together
    pop_estimates_df = pop_estimates_df.merge(age_df.reset_index(), left_on='Area_Code', right_on='SA Code', how='left')
    # calculates pop estimates for each age in each small area using proportions
    for age in range(len(age_cols)):   
        pop_estimates_df[age_cols[age]] = pop_estimates_df[age_cols[age]]*pop_estimates_df[pop_year]
    pop_estimates_df.set_index('Area_Code', inplace=True)
    return pop_estimates_df
    