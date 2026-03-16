import geopandas as gpd
import shapely
import pandas as pd
from fiona.drvsupport import supported_drivers
import sys
import os
import subprocess as sub
from geopandas import GeoDataFrame
import numpy as np
import psycopg2
from shapely.geometry import LineString,Point
# import pcst_fast
import time


def output_handler_for_railroad_bridges_tunnel(row,road_data):
    """
    A function to handle the output of the SQL query.

    Attributes:
    -----------
    row : list of tuple
        The output from the SQL query in the form of a list of tuples. Each tuple contains three values: 
    """

    df = gpd.GeoDataFrame(row, columns = ["type","geom","length"])


    df["geometry"] = df['geom'].apply(lambda x : shapely.wkt.loads(f"Point({x})"))

    road_data_buffer = gpd.GeoDataFrame({"geometry" : road_data.buffer(20)})
    df_new = gpd.sjoin(df,road_data_buffer)


    df_new.drop(["index_right"],axis=1,inplace=True)
    df_new = df_new.drop_duplicates()
    
    info_dict = {}
    info_dict["railroad_number"] = len(df_new[df_new["type"]=="Railroad"])
    info_dict["Number of Tunnels"] = len(df_new[df_new["type"]=="Tunnel"])
    info_dict["Number of Bridges"] = len(df_new[df_new["type"]=="Bridges"])

    return df_new,info_dict




def check_geometry_type(geodataframe,path_for_log):

    # Check if the GeoDataFrame contains a 'geometry' column
    if 'geometry' not in geodataframe.columns:
        f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
        f.write(f"""Geometry column missing. Location Data must contain a 'geometry' column.""")
                    # closing the file
        f.close()   

        raise ValueError("GeoDataFrame must contain a 'geometry' column.")

    # Get the geometry types for all geometries in the 'geometry' column
    geometry_types = geodataframe['geometry'].geom_type.unique()

    # Check if the GeoDataFrame contains only 'Point' geometry
    if len(geometry_types) == 1 and 'Point' in geometry_types:

        return geodataframe
    
    # Check if the GeoDataFrame contains only 'MultiPoint' geometry
    elif len(geometry_types) == 1 and 'MultiPoint' in geometry_types:

        geodataframe = geodataframe.explode(index_parts=False)

        return geodataframe

    # If the GeoDataFrame contains a mix of geometry types, raise an exception
    else:

        f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
        f.write(f"""Location data contains a mix of different geometry types.""")
                    # closing the file
        f.close()   

        raise ValueError("Location data contains a mix of different geometry types.")
    

def check_user_privileges(client_name,location_df,path_for_log):

    """
This function performs checks and validations to ensure the client is authorized to use Steiner tool on specified locations.

Requirements:
1. The client name must be from the 'clients' column in the 'us_wiroidb_2_1_privileges_limits' table.
2. The coordinate reference system (CRS) of the input data (df) must be 102008.
3. The production database must have the following tables:
   - us_wiroidb_2_1_privileges_limits
   - us_wiroidb_2_1_privileges_features
   - us_wiroidb_2_1_privileges_states
   - Functions:
       - ws_get_all_roads_in_polygons (for US roads)
       - ws_get_all_roads_in_polygon_from_canada (for Canadian roads)

Steps:
1. Check if the client name exists in the 'clients' column of 'us_wiroidb_2_1_privileges_limits' table.
2. If the client exists, verify if they are allowed to run the Steiner tool on the specified locations.
3. If allowed, check whether the client is permitted to use the Steiner tool on the locations from the corresponding state.
4. If the locations don't belong to any of the US states, check whether they are allowed to run Canadian road and try to run the Steiner tool for Canada.
    """
   
    number_of_locations = len(location_df)

    
    conn = psycopg2.connect(database="wiroidb2",user ="postgresqlwireless2020",password= "software2020!!",
                                    host="wirelesspostgresqlflexible.postgres.database.azure.com", port="5432")
    cursor = conn.cursor()

    #checking whether, on how many locations user can run the steiner
    cursor.execute("SELECT client FROM us_wiroidb_2_1_privileges_limits")
    client_names = cursor.fetchall()

    if client_name not in list(pd.DataFrame(client_names,columns=['a'])["a"]):

        cursor.close()
        conn.close()

        f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
        f.write(f"""
Client not found:
The provided client name, {client_name}, does not exist in our records. 
Please double-check the spelling or contact our support team for assistance.""")
                    # closing the file
        f.close()

        raise Exception("client name does not exists")
        

    #checking whether, on how many locations user can run the steiner
    cursor.execute(
        "SELECT steiner_aio_locations FROM us_wiroidb_2_1_privileges_limits WHERE client = %s",
        (client_name,),
    )
    
    number_of_locations_allowed = int(cursor.fetchone()[0])

    
    if number_of_locations > number_of_locations_allowed:
       
       cursor.close()
       conn.close()

       f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
       f.write(f"""
Location Access Denied: You are attempting to run the algorithm for {number_of_locations} locations,
but you are only authorized to use {number_of_locations_allowed} locations. Please ensure that you are using the
approved number of locations for running the algorithm. Please contact Wireless 20|20 support 
for further assistance.""")
                    # closing the file
       f.close()

       raise Exception("Location Access Denied")
    
    
    #checking wether users has access to the state where they are running steiner
    #the df crs should be native
    centroid_latitude = location_df.geometry.x.mean()
    centroid_longitude = location_df.geometry.y.mean()

    p = Point(centroid_latitude,centroid_longitude)
    wkb_location = p.wkb
    query = """
SELECT state_abbr
FROM us_state_coordinates
WHERE ST_Contains(geom, ST_SetSRID(ST_GeomFromWKB(%s), 102008))
"""
    cursor.execute(query, (wkb_location,))


    result = cursor.fetchone()

    if result == None: #result None means that locations are not US
        cursor.execute(
            "SELECT steiner_canadian_access FROM us_wiroidb_2_1_privileges_features WHERE client = %s",
            (client_name,),
        )

        canadian_road_access = cursor.fetchone()[0]
        if canadian_road_access == True:
            cursor.close()
            conn.close()
            return (True,"ws_get_all_roads_in_polygon_from_canada","Canada")
        
        elif canadian_road_access == False:
             cursor.close()
             conn.close()
             
             
             f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
             f.write(f"""
Canadian road Access Denied: No access for Canadian road network. 
Please contact Wireless 20|20 support 
for further assistance.""")
                    # closing the file
             f.close()

             raise Exception("Canadian Access Denied")
        
    else:

        state_abbr = result[0]

        dict_of_cilents = {"Cox": "fox", "SW2020" : "sw2020", "Mediacom" : "mdc", "Redzone" : "redzone"}
        
        if client_name not in list(dict_of_cilents.keys()):
            
            dict_of_cilents[client_name] = client_name

        # Column name comes from a controlled whitelist dict so it is safe to
        # interpolate; only the WHERE value is user-supplied and parameterized.
        col = dict_of_cilents[client_name]
        cursor.execute(
            f"SELECT {col} FROM us_wiroidb_2_1_privileges_states WHERE state_abbr = %s",
            (state_abbr,),
        )
    
        state_allowed = cursor.fetchone()[0]

        if state_allowed == True:
           cursor.close()
           conn.close()
           
           return (True,"ww_get_all_roads_in_poly",state_abbr) #changed func name ws_get_all_roads_in_polygons
        
        elif state_allowed == False:
             cursor.close()
             conn.close()
             
             f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
             f.write(f"""
State Access Denied: No access for this state. 
Please contact Wireless 20|20 support 
for further assistance.""")
                    # closing the file
             f.close()

             raise Exception("State Access Denied")



def put_crs(df, path_for_log):

    """
    df : GeoDataFrame with geometry column

    df should have one of those CRSs -->> EPSG:4326 OR ESRI:102008

    any other crs will be defined as unknown

    returns df with Native CRS ESRI:102008
    """

    
    #checks if x bound is KML bound 
    if (-180<df.geometry.x).all() and (df.geometry.x<180).all():

        try:
          #allow_override is added for the shapfile input, in handles wrong putten crs in the case when it is EPSG4326
          df = df.set_crs("EPSG:4326", allow_override = True)
          df = df.to_crs("ESRI:102008")
 
          return df
        
        except Exception:

            f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
            f.write(f"""CRS ISSUE. Make sure crs is ESRI:102008 or EPSG:4326""")
                    # closing the file
            f.close()   

            raise "CRS ERROR"   
    else:
        try:
          df = df.set_crs("ESRI:102008")
          return df
        
        except Exception:
            f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
            f.write(f"""CRS ISSUE. Make sure crs is ESRI:102008 or EPSG:4326""")
                    # closing the file
            f.close()    
            raise  "CRS ERROR"
        



def query_for_road_network(database, user, password, 
                        host, port,input, function_name,path_for_log):

        """
            Executes a SQL query and returns the results as a pandas DataFrame.

            Args:
                sql_query (str): The SQL query to execute.
                host (str): The database server hostname or IP address.
                port (int): The port number to use for the database connection.
                database (str): The name of the database to connect to.
                user (str): The username to use for authentication.
                password (str): The password to use for authentication.

            Returns:

                A list of tuples representing the results of the SQL query.
        """
        try:
            
            conn = psycopg2.connect(database=database, user=user, password=password, 
                                host=host, port=port)
            
            # Create a cursor object
            cur = conn.cursor()
            
            cur.callproc(function_name, (input,))

            row = cur.fetchall()
            cur.close()
            return row

        except (Exception, psycopg2.DatabaseError) as error:
            f = open(os.path.join(path_for_log, "log.txt"), "a")
                    # writing in the file
            f.write(f"""Query failed. Make sure your internet connection is not interupted""")
                    # closing the file
            f.close()    
            raise  "DATABASE ERROR"


def output_hadndler(row):
    """
    A function to handle the output of the SQL query.

    Attributes:
    -----------
    row : list of tuple
        The output from the SQL query in the form of a list of tuples. Each tuple contains three values: 
    """

    def func(ls):
            newls = [i.split() for i in ls]
            return newls
        
    def func2(ls):
            new_ls = []
            for i in range(len(ls)):
                 new_ls.append((float(ls[i][0]),float(ls[i][1])))
            return tuple(new_ls)
        

    df = pd.DataFrame(row, columns = ["geom","road_type","States","mtfcc"])

    df["geometry0"] = df['geom'].apply(lambda x : x.split(","))
    df["geometry00"] = df.geometry0.apply(func)
 
    df["geometry"] = df.geometry00.apply(func2)
    df["geometry"] = df["geometry"].apply(lambda x :LineString(x)) 
    df.drop(["geometry0","geom","geometry00"],axis=1,inplace=True)

    return gpd.GeoDataFrame(df,crs= "ESRI:102008")

