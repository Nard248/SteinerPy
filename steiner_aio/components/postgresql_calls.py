import geopandas as gpd
import shapely
import pandas as pd
import sys
import os
import subprocess as sub
import numpy as np
import psycopg2
import time
from sqlalchemy import create_engine
import plotly.graph_objs as go

def fetch_column_names(cursor):
    """Fetch column names from cursor description."""
    return [desc[0] for desc in cursor.description]

def connect_to_db_query(query):

    conn = psycopg2.connect(database="wiroidb2",user ="postgresqlwireless2020",password= "software2020!!",
                                    host="wirelesspostgresqlflexible.postgres.database.azure.com", port="5432")
    cursor = conn.cursor()
    cursor.execute(query)
    data = cursor.fetchall()
    col_names = fetch_column_names(cursor)
    # data = {"fcc_ids" : [i for i in range(0,1000)]}

    df = pd.DataFrame(data, columns=col_names)
    # col_names = []
    # df = pd.DataFrame(data = data)

    #checks if geom is in column list
    if 'geom' in col_names:
        df['geometry'] = df['geom'].apply(lambda x : shapely.from_wkb(x))
        df = gpd.GeoDataFrame(df, geometry='geometry')

    return df



"""
WITH input_polygon AS (
    SELECT ST_SetSRID(ST_GeomFromText('{poly}'), 4326) AS polygon_geom
)
SELECT loc.*, tag.*
FROM us_sw2020_fabric_harvested_rel4_full loc
INNER JOIN fcc_bdc_fabric_rel4 tag ON loc.fcc_location_id = tag.fcc_location_id
WHERE ST_Intersects(loc.geom, (SELECT polygon_geom FROM input_polygon));
"""

def export_fabric_locations(polygon):
    # Create a connection to your database

    polygon = polygon.to_crs("EPSG:4326")

    for index, row in polygon.iterrows():

        simplified_geometry = row['geometry'].simplify(tolerance=0.001, preserve_topology=True)

        poly = shapely.to_wkt(simplified_geometry) # Convert geometry to well-known text

        query = f"""WITH input_polygon AS (
    SELECT ST_SetSRID(ST_GeomFromText('{poly}'), 4326) AS polygon_geom
)
SELECT loc.fcc_location_id,loc.geom, tag.*
FROM us_sw2020_fabric_harvested_rel4_full loc
INNER JOIN fcc_bdc_fabric_rel4 tag ON loc.fcc_location_id = tag.fcc_location_id
WHERE ST_Intersects(loc.geom, (SELECT polygon_geom FROM input_polygon));
"""
    

    df = connect_to_db_query(query)
    df = df.T.drop_duplicates().T
    
    df = gpd.GeoDataFrame(df)
    
    return df , len(df['fcc_location_id'].unique())

