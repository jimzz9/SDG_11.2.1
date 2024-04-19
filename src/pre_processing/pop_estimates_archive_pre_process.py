# """This program is used to pre-process the population estimates archive data.
# The archived data is in a different format than the current data. It has many years's data in one file for each region.
# Also the data is a long format, so it needs to be pivoted to a wide format."""

import pathlib as pl
import duckdb
import uuid
from typing import List, Dict
from duckdb import DuckDBPyConnection
import logging
import pandas as pd
import yaml

# load config
with open("config.yaml") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)

# Define the input and output file paths
input_folder = "data/population_estimates/2002-2012"


# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

# Create logger
duckdbLogger = logging.getLogger(__name__)

db_file_path = "data/population_estimates/2002-2012/pop_est_2002-2012.db"

# Define the input and output file paths
input_folder = "data/population_estimates/2002-2012"

# Define the years to process
# years = list(range(2002, 2013))
years = [2011]

# Define an empty dictionary to store the dataframes for each year
year_data = {}

# Define the column name for the year
year_cols = [f"Population_{year}" for year in years]


column_types = {
    "OA11CD": "TEXT",
    "Sex": "INTEGER",
    "Age": "INTEGER",
    "LAD11CD": "TEXT",
    "Population_2002": "INTEGER",
    "Population_2003": "INTEGER",
    "Population_2004": "INTEGER",
    "Population_2005": "INTEGER",
    "Population_2006": "INTEGER",
    "Population_2007": "INTEGER",
    "Population_2008": "INTEGER",
    "Population_2009": "INTEGER",
    "Population_2010": "INTEGER",
    "Population_2011": "INTEGER",
    "Population_2012": "INTEGER"
}


def make_non_existent_folder(folder_path: pl.Path) -> None:
    """Creates a folder if it doesn't exist."""
    if not folder_path.exists():
        duckdbLogger.info(f"Folder {folder_path} does not exist. Creating it now.")
        folder_path.mkdir(parents=True)
        # Add a .gitkeep file to the folder so it gets pushed to GitHub
        (folder_path / ".gitkeep").touch()
    return None

def create_connection(database_path: str) -> DuckDBPyConnection:
    """Creates a connection to a DuckDB database and returns the connection object."""
    
    # Check if the folder for the database exists, and create it if it doesn't
    make_non_existent_folder(pl.Path(database_path).parent)
    
    con = duckdb.connect(database_path)
    return con


def load_all_csvs(con, csv_folder, output_table_name):
    """Loads all the population csv files in a folder into a DuckDB database.
    
    Lists all the csv files in the csv_folder, and loads them into a DuckDB database.
    Counts the number of records loaded into the database and logs the result.
    Also returns the name of the table that the data was loaded into.
    """

    # Check that csv folder exists
    if not pl.Path(csv_folder).exists():
        raise ValueError(f"Folder {csv_folder} does not exist.")

    duckdbLogger.info(f"Loading all csv files")
    
    # List all the csvs in the csv_folder
    csv_files = list(pl.Path(csv_folder).glob("*.csv"))
    duckdbLogger.info(f"Found {csv_files} in {csv_folder}")
    
    
    load_csv_query = f"""
    CREATE TABLE IF NOT EXISTS {output_table_name}
    AS SELECT *
    FROM read_csv_auto('{csv_folder}/*.csv', header=true, columns={column_types}, delim=',', auto_detect=false);
    """
    # This code currently gives an empty dataframe
    #
    con.execute(load_csv_query)

    # SQL query to count the unique codes in column "OA11CD" in the table
    count_query = f"SELECT COUNT(DISTINCT OA11CD) FROM {output_table_name};"
    
    # Log how many records have been loaded
    duckdbLogger.info(f"Loaded {con.execute(count_query).fetchall()} records into {output_table_name}")

    duckdbLogger.info(f"Finished loading all csv files in {csv_folder} into {output_table_name}")
    
    return output_table_name


def query_database(con, query, year=None):
    """Queries a DuckDB database and returns the name of a temporary table.

    This function takes a DuckDB connection object and a SQL query as input,
    and creates a temporary tcable with the results of the query. The function
    returns the *name* of the temporary table, which can be passed to the next function.
    """
    # Generate a unique name for the temporary table
    table_name = f"table_{uuid.uuid4().hex}_{year}"

    # Create the temporary table and insert the query results
    con.execute(f"CREATE TEMPORARY TABLE {table_name} AS {query}")

    duckdbLogger.info(f"Created temporary table. Returning table name as {table_name}")
    
    # Return the name of the temporary table
    return table_name

def query_database_as_view(con: DuckDBPyConnection, query: str, view_name: str) -> None:
    """Queries a DuckDB database and creates or updates a view with the results.

    This function takes a DuckDB connection object, a SQL query, and a view name as input,
    and creates or updates a view with the results of the query. The function returns the view object,
    which can be used in subsequent queries.
    """
    # Create or update the view with the results of the query
    con.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query};")

    # Return the updated view object
    return con.view(view_name)


def pivot_sex_tables(con, tables_dict: Dict[str, str], year: str):
    """Pivots the sex-specific tables using SQL.

    Args:
        con: A DuckDB connection object.
        male_table: A string representing the name of the males sex-specific table.
        female_table: A string representing the name of the females sex-specific table.
        persons_table: A string representing the name of the both sex-specific table.
        year_col: A string representing the name of the column containing the population data.

    Returns:
        Three dataframes representing the pivoted males, females, and both sex-specific tables.
    """
    
    year_col=f"Population_{year}"
    
    duckdbLogger.info(f"Starting the pivot process. Year column is: {year_col}")
     
    # Construct the SQL query to pivot the males sex-specific table
    male_query = f"""PIVOT {tables_dict['males']} ON Age USING SUM({year_col}) GROUP BY OA11CD;
    """
 
    # Construct the SQL query to pivot the females sex-specific table
    female_query = f"""PIVOT {tables_dict['females']} ON Age USING SUM({year_col}) GROUP BY OA11CD;
    """

    # Construct the SQL query to pivot the both sex-specific table
    persons_query = f"""PIVOT {tables_dict['persons']} ON Age USING SUM({year_col}) GROUP BY OA11CD;
    """

    # Execute the SQL queries and get dataframes for each sex-specific table
    duckdbLogger.info("Executing SQL queries to pivot males table")
    male_table = query_database(con, male_query, year)
    duckdbLogger.info("Executing SQL queries to pivot females table")
    female_table = query_database(con, female_query, year)
    duckdbLogger.info("Executing SQL query to pivot table for both sexes")
    persons_sexes_table = query_database(con, persons_query, year)
            
    return {"persons": persons_sexes_table, "males": male_table, "females": female_table}

def create_all_ages_col(con: DuckDBPyConnection, table_name: str, year: int, config: dict) -> None:
    ages_col_str = [f'"{str(age)}"' for age in config["age_lst"]]
    ages_col_str = "+".join(ages_col_str)

    # SQL query to add a new column "All Ages"
    add_column_query = f"ALTER TABLE {table_name} ADD COLUMN \"All Ages\" INTEGER"

    # Execute the query
    con.execute(add_column_query)
    
    # SQL query to update the "All Ages" column with the sum of the other columns
    update_query = f"UPDATE {table_name} SET \"All Ages\" = {ages_col_str}"
    
    # Execute the query to update the "All Ages" column
    con.execute(update_query)

def rename_table_column(con, table_name, old_col_name, new_col_name):
    
    duckdbLogger.info(f"Renaming table column {old_col_name} to {new_col_name}")
    
    if old_col_name in con.execute(f"SELECT * FROM {table_name} LIMIT 0").df():
        duckdbLogger.debug(f"{old_col_name} exists in {table_name}. Renaming column")
        query = f"ALTER TABLE {table_name} RENAME COLUMN \"{old_col_name}\" TO \"{new_col_name}\";"
        con.execute(query)
    else:
        duckdbLogger.debug(f"{old_col_name} does not exist in {table_name}")
        
def age_pop_by_sex(con: duckdb.DuckDBPyConnection, table_name, year: int):
    """"Uses SQL to get the data for three sex groups and drops the sex column.

    Args:
        con: A DuckDB connection object.
        table_name: The name of the table which corresponds to one year of data
        year: An integer representing the year to query.
    """
    # Generate a unique name for the temporary table
    # table_name = f"temp_{uuid.uuid4().hex}"

    # Construct the SQL query for the males sex group
    male_query = f"""
        SELECT OA11CD, Age, LAD11CD, Population_{year}
        FROM {table_name}
        WHERE Sex = 1;"""

    # Construct the SQL query for the females sex group
    female_query = f"""
        SELECT OA11CD, Age, LAD11CD, Population_{year}
        FROM {table_name}
        WHERE Sex = 2;"""
    # Construct the SQL query for both sex groups
    persons_query = f"""
        SELECT OA11CD, Age, LAD11CD, Population_{year}
        FROM {table_name};"""

    # Get a dataframe for sex == 1
    duckdbLogger.info("Executing query for males table")
    male_table = query_database(con, male_query, year)

    # Get a dataframe for sex == 2, females
    duckdbLogger.info("Executing query for females table")
    female_table = query_database(con, female_query, year)

    # Get combined sexes dataframe
    duckdbLogger.info("Executing query for table for both sexes")
    persons_table = query_database(con, persons_query, year)

    duckdbLogger.info("Finished executing queries. Returning three tables")
    return male_table, female_table, persons_table


    # Get combined sexes dataframe
    persons_table = query_database(con, persons_query)
    
    return male_table, female_table, persons_table



def create_output_folder(year: int) -> pl.Path:
    """Create the output folder for a given year if it doesn't exist."""
    output_folder = pl.Path(f"data/population_estimates/{year}")
    if not output_folder.exists():
        duckdbLogger.info(f"Folder {output_folder} does not exist. Creating it now.")
        output_folder.mkdir(parents=True)
    return output_folder


def write_table_to_csv(con: DuckDBPyConnection, 
                       args: Dict,
                       output_folder: pl.Path,
                       year: int) -> None:
    """
    Writes the specified tables in a DuckDB database to CSV files.

    This function takes a DuckDB connection object, a dictionary containing the tables, 
    an output folder path, and a year as input. For each table name, it executes a COPY 
    command to write the table to a CSV file in the specified output folder. 
    
    The CSV file is named 'pop_estimate_{year}.csv', where {year} is the 
    specified year. The function does not return a value.

    Parameters:
    con (DuckDBPyConnection): The DuckDB connection object.
    *args (dictionary): A dictionary containing the table names as keys and the table names as values.
    output_folder (Path): The path to the output folder.
    year (int): The year to include in the CSV file names.

    Returns:
    None
    """
    for table_name in args:
        query = f"""
            COPY {args[table_name]}
            TO '{output_folder}/pop_estimate_{table_name}_{year}.csv'
            (FORMAT CSV, DELIMITER ',', HEADER);"""
        
        con.execute(query)
    
    return None

def write_table_to_xlsx(con: DuckDBPyConnection,
                        table_dict: Dict[str, duckdb.table],
                        output_folder: pl.Path,
                        year: int) -> None:
    """Writes a list of tables in a DuckDB database to an Excel file,
        writing each table to a different tab in the sheet.

    Args:
        con (DuckDBPyConnection): Connection to the DuckDB database.
        table_dict: Dict[str, duckdb.table]: A dictionary containing the name references as keys and the table names as values.
        output_folder (pl.Path): The path to the output folder.
        year (int): The year which is being processed. Will form part of the path, filename and tab name. 
    """
    with pd.ExcelWriter(output_folder / f"pop_estimate_{year}.xlsx") as writer:
        duckdbLogger.info(f"Writing tables to Excel file for year {year}")
        for t_name, table in table_dict.items():
            tab_name = f"Mid-{year} {t_name.title()}"
            df = con.execute(f"SELECT * FROM {table}").fetch_df()
            df.to_excel(writer, sheet_name=tab_name, index=False, startrow=4)
    

def main():
    """This is executed when run from the command line."""
    # Create connection
    con = create_connection(db_file_path)

    # Run query to load all the csv data in one go and create the table
    table_name = load_all_csvs(con, input_folder, "all_pop_estimates")


    # For each of those years, load the data for all regions into a temp table
    # and return the name of the temp table
    duckdbLogger.info("Starting to load data for each year into a temp table")
    for year in years[:1]:
        duckdbLogger.info(f"Extracting data for year {year}")

        year_col=f"Population_{year}"

        # Get the three sex disaggregated tables
        persons_table, male_table, female_table = age_pop_by_sex(con, table_name, year)

        # Pack names and tables into a dictionary
        all_three_tables = {"persons": persons_table, "males": male_table, "females": female_table}

        # Pivot the dataframe to a wide format
        all_three_tables = pivot_sex_tables(con, all_three_tables, year)
        
        
        for name in all_three_tables.keys():
        
            # Rename the 90+ col and get rid of leading zeros
            rename_table_column(con, all_three_tables[name], "90", "90+")
                        
            for i in range(10):
                old_column_name = f"{i:02d}"  # This will be '00', '01', '02', ..., '09'
                new_column_name = str(i)  # This will be '0', '1', '2', ..., '9'
                rename_table_column(con, all_three_tables[name], old_column_name, new_column_name)
                            
            create_all_ages_col(con, all_three_tables[name], year, config)
        
            
            
        # Create the folder for the year, and return its path
        output_folder = create_output_folder(year)

        # Write out the pivoted tables as CSV files
        # write_table_to_csv(con, all_three_tables,
        #                    output_folder=output_folder,
        #                    year=year)
        
        write_table_to_xlsx(con = con,
                        table_dict = all_three_tables,
                        output_folder = output_folder,
                        year=year)
    
    # drop the all pop estimates table so it can be run again
    con.execute(f"""DROP TABLE all_pop_estimates;""")

    # Close the connection
    con.close()

if __name__ == "__main__":
    """This is executed when run from the command line!"""
    main()
