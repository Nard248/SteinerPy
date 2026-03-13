import geopandas as gpd
import shapely
import pandas as pd
from fiona.drvsupport import supported_drivers
import sys
import os
import subprocess as sub
import numpy as np
from scipy.spatial import cKDTree
import xlwings as xw
import psycopg2
import time
from sqlalchemy import create_engine
# import plotly.graph_objs as go
import matplotlib.pyplot as plt



def call_qgis_for_steiner(project_name , steiner, drop_length, UCDs, railroad_path, tunnel_path, bridges_path,save_path, snap_point= "", polygon = "", 
        invalid_points = "", set_atributes = "True"):

        my_call = [r"C:\OSGeo4W\OSGeo4W.bat", r"python-qgis", r"C:\OSGeo4W\processing_utilities\save_qgz.py",
                   project_name,snap_point, drop_length,steiner,invalid_points,polygon,UCDs,railroad_path,
                     tunnel_path, bridges_path,save_path,set_atributes]
        p = sub.Popen(my_call, stdout=sub.PIPE, stderr=sub.PIPE)
        stdout, stderr = p.communicate()





def to_excel_or_csv_without_colors(points,acces_fiber_miles,drop_length,project_name,save_path,info_for_crossing_rail_tun_bridge,
                                   csv_excel_type):
    

    columns_of_excel_sheet = ["Cluster Name","Number of Locations",
                        "Access Road Miles","Trunk Miles","Location/Access Road Mile",
                        "Location/Mile(Access+Trunk)","Unit Count",
                "Unit Count/Access Road Mile", "Aerial Access Fiber Miles",
                        "UG Access Fiber Miles","Aerial Trunk Miles","UG Trunk Miles", "Average Drop Length (In Miles)",
                        "Number of Railroad Crossings",  "Number of Tunnels","Number of Bridges"]
    
    df_excel = pd.DataFrame(columns = columns_of_excel_sheet, index=[0])
    
    df_excel["Cluster Name"] = project_name
    df_excel["Number of Locations"] = len(points)
    df_excel["Access Road Miles"] = round(sum(acces_fiber_miles.length)/1609.344 ,2)
    df_excel["Number of Railroad Crossings"] = info_for_crossing_rail_tun_bridge['railroad_number']
    df_excel[ "Number of Tunnels"] = info_for_crossing_rail_tun_bridge[ "Number of Tunnels"]
    df_excel["Number of Bridges"] = info_for_crossing_rail_tun_bridge["Number of Bridges"]



    try:

               points.unit_count = points.unit_count.astype("int64")
               num_unit_count = sum(points.unit_count)
               unit_count_access_road_mile = round(num_unit_count/(sum(acces_fiber_miles.length)/1609.344) ,2)
               df_excel["Unit Count"] = num_unit_count
               df_excel["Unit Count/Access Road Mile"] = unit_count_access_road_mile

    except:
         
         Exception
                   
    df_excel["Location/Access Road Mile"] =  round(len(points)/(sum(acces_fiber_miles.length)/1609.344) ,2)
    df_excel["Location/Mile(Access+Trunk)"] =  round(len(points)/(sum(acces_fiber_miles.length)/1609.344),2)
    df_excel["Average Drop Length (In Miles)"] = round((sum(drop_length.length)/1609.344) /len(points),2)
    df_excel = df_excel.set_index("Cluster Name")


    if csv_excel_type=='excel':
     df_excel.to_excel(os.path.join(save_path,f"{project_name} ExcelSummary.xlsx"))

    elif csv_excel_type=='csv':
     
     df_excel.to_csv(os.path.join(save_path,f"{project_name} CSVSummary.csv"))



def to_excel(points,acces_fiber_miles,drop_length,project_name,save_path,info_for_crossing_rail_tun_bridge,
             polygon,provider_chart,info_needed_for_excel):

    columns_of_excel_sheet = ["Cluster Name","Number of Locations",
                        "Access Road Miles","Trunk Miles","Location/Access Road Mile",
                        "Location/Mile(Access+Trunk)","Unit Count",
                "Unit Count/Access Road Mile" ,"Aerial Access Fiber Miles",
                        "UG Access Fiber Miles","Aerial Trunk Miles","UG Trunk Miles", "Average Drop Length (In Miles)"
                        , "Number of Railroad Crossings", "Number of Tunnels","Number of Bridges"]
    
    df_excel = pd.DataFrame(columns = columns_of_excel_sheet, index=[0])

    try:      
          
            #we are not handling nones, if there is none value it will not show the unit_count
               points.unit_count = points.unit_count.astype("int64")
               num_unit_count = sum(points.unit_count)
               unit_count_access_road_mile = round(num_unit_count/(sum(acces_fiber_miles.length)/1609.344) ,2)
               df_excel["Unit Count"] = num_unit_count
               df_excel["Unit Count/Access Road Mile"] = unit_count_access_road_mile
    except:
         Exception
         
    df_excel["Cluster Name"] = project_name
    df_excel["Number of Locations"] = len(points)
    df_excel["Access Road Miles"] = round(sum(acces_fiber_miles.length)/1609.344 ,2)
    df_excel["Location/Access Road Mile"] =  round(len(points)/(sum(acces_fiber_miles.length)/1609.344) ,2)
    df_excel["Location/Mile(Access+Trunk)"] =  round(len(points)/(sum(acces_fiber_miles.length)/1609.344),2)
    df_excel["Average Drop Length (In Miles)"] = round((sum(drop_length.length)/1609.344) /len(points),2)
    df_excel["Number of Railroad Crossings"] = info_for_crossing_rail_tun_bridge['railroad_number']
    df_excel[ "Number of Tunnels"] = info_for_crossing_rail_tun_bridge[ "Number of Tunnels"]
    df_excel["Number of Bridges"] = info_for_crossing_rail_tun_bridge["Number of Bridges"]
    df_excel['Total Locations Count'] = info_needed_for_excel

    df_excel = df_excel.set_index("Cluster Name")

    app = xw.App(visible=False)
    wb = xw.Book()

    sht = wb.sheets[0]
    sht.range("A1").value = df_excel
    sht.name = "Summary"
    for i in range(len(df_excel.columns)+1):
                                l = [
                                ["A1" ,"#00FF00"],
                                ["B1", "#00FF00"],
                                ["C1","#00FF00"],
                                ["D1","#FFFF99"],
                                [ "E1","#00FF00"],
                                ["F1", 	"#00FF00"],
                                    ["G1", "#00FF00"], 
                                    ["H1", "#00FF00"],
                                    ["I1", "#00FF00"], 
                                    ["J1", "#00FF00"],
                                   ["K1", "#00FF00"],
                                    ["L1", "#00FF00"],
                                        ["M1", "#CCFFFF"],
                                        ["N1", "#00FF00"],
                                        ["O1", "#00FF00"],
                                        ["P1", "#00FF00"],
                                        ["Q1", "#00FF00"]
                                    ]
                                sht.range(f"{l[i][0]}").color = l[i][1]
                                sht.range(f"{l[i][0]}").font.bold = True
                                sht.range(f"{l[i][0]}").column_width = 30
    if provider_chart == '0':
        fig = create_chart(polygon)
        #fig.write_image(os.path.join(save_path,'chart.png'))
        fig.savefig(os.path.join(save_path,'chart.png'))
        sht.pictures.add(os.path.join(save_path,'chart.png'), name='Plot', update=True, left=sht.range('B5').left, top=sht.range('B5').top)
        os.remove(os.path.join(save_path,'chart.png'))


    wb.save(os.path.join(save_path,f"{project_name} ExcelSummary.xlsx"))
    wb.close()

    

def fetch_column_names(cursor):
    """Fetch column names from cursor description."""
    return [desc[0] for desc in cursor.description]

def create_chart(polygon):

    # Create a connection to your database
    conn = psycopg2.connect(database="wiroidb2",user ="postgresqlwireless2020",password= "software2020!!",
                                    host="wirelesspostgresqlflexible.postgres.database.azure.com", port="5432")
    cursor = conn.cursor()

    #checking whether, on how many locations user can run the steiner
  
    polygon = polygon.to_crs("EPSG:4326")
    for index, row in polygon.iterrows():

        simplified_geometry = row['geometry'].simplify(tolerance=0.001, preserve_topology=True)

        poly = shapely.to_wkt(simplified_geometry) # Convert geometry to well-known text
        query = f"""    
WITH filtered_blocks AS 
(    SELECT *
    FROM us_blocks20_coordinates
    WHERE geom && ST_GeomFromText('{poly}',4326)
)
SELECT  c_b_data.provider_name, c_b_data.block_code, c_b_cord.geom,c_b_cord.block_code
FROM filtered_blocks AS c_b_cord
LEFT JOIN us_census_block_data AS c_b_data
ON c_b_cord.block_code = c_b_data.block_code
WHERE ST_Intersects(c_b_cord.geom, ST_GeomFromText('{poly}', 4326)
) 
"""
    cursor.execute(query)
    intersected_data = cursor.fetchall()
    col_names = fetch_column_names(cursor)
    
    intersected_df = gpd.GeoDataFrame(intersected_data, columns=col_names)
    needed_df = intersected_df.drop_duplicates(subset = ['geom','block_code','provider_name'])
    needed_df['geometry'] = needed_df['geom'].apply(lambda x : shapely.from_wkb(x))
    needed_df = gpd.GeoDataFrame(needed_df, geometry='geometry')
    needed_df['area'] = needed_df.geometry.area

    needed_df = needed_df.set_crs("EPSG:4326")
    needed_df = needed_df.to_crs("ESRI:102008")
    polygon = polygon.set_crs("EPSG:4326")
    polygon = polygon.to_crs("ESRI:102008")

    area_of_steiner = round(polygon.area.sum()/1609.344,2)
    for ind,row in  needed_df.iterrows():
        pol = polygon['geometry'].intersection(row['geometry'])
        needed_df.at[ind,'area_of_intersect'] = round(pol.area.sum()/1609.344,2)
        needed_df.at[ind,'area_of_intersect_percentage'] =  round(pol.area.sum()/1609.344,2)/area_of_steiner

    # Count frequencies of provider IDs
    # Get provider names
    provider_counts = needed_df.groupby('provider_name')['area_of_intersect_percentage'].sum()
    provider_counts_d = provider_counts.to_dict()
    starlink = provider_counts.to_dict().get('Starlink')
    viasat = provider_counts.to_dict().get('Viasat')
    hughesnet = provider_counts.to_dict().get('HughesNet')
    try:
     #most probably old data here
     del provider_counts_d['Viasat, Inc.']

    except:
       provider_counts_d['Viasat']
    
    del provider_counts_d['Starlink'],provider_counts_d['HughesNet']

    provider_counts_d = dict(sorted(provider_counts_d.items(), key=lambda item: item[1]))
    provider_counts_d['Starlink'] = starlink
    provider_counts_d['Viasat'] = viasat
    provider_counts_d['HughesNet'] = hughesnet

    fig, ax = plt.subplots()
    ax.bar(provider_counts_d.keys(), provider_counts_d.values(), color='blue')

    # Set the title and labels
    ax.set_title('Area of intersection')
    ax.set_xlabel('Provider Name')
    ax.set_ylabel('Percentage')
    plt.xticks(rotation=35, ha='right')
    # Increase bottom margin to make room for the labels
    plt.subplots_adjust(bottom=0.3)

    plt.tight_layout()

    return fig





def export_files(save_path,project_name,
                 export_type,  sten,
                   df_for_railroad_bridges_tunnel,drop_length,locations_final,
                   snap,invalid_points
                   ): # gdf.to_file('file.shp', driver='ESRI Shapefile')
    
    supported_drivers[export_type] = 'rw'

    export_type_dict = {"shp" : ["shp",'ESRI Shapefile'],
                         'sqlite' : ['sqlite','sqlite'], 'KML' : ['KML',"KML"]}

    polygon_for_steiner_path = os.path.join(save_path,
                                            f"{project_name} Polygon.{export_type_dict[export_type][0]}"
                                            )
    
    polygon_for_steiner = gpd.GeoDataFrame({"geometry":
                                            sten.buffer(100).unary_union},
                                            crs = "ESRI:102008",index=[0])
    polygon_for_steiner = polygon_for_steiner.to_crs("EPSG:4326")
    polygon_for_steiner.to_file(polygon_for_steiner_path,driver = export_type_dict[export_type][1])

    path_sten = os.path.join(save_path,
                             f"{project_name} Access Fiber Miles.{export_type_dict[export_type][0]}")
    sten = sten.to_crs("EPSG:4326")
    sten.to_file(path_sten,driver = export_type_dict[export_type][1])

    try:
        df_for_railroad_bridges_tunnel = df_for_railroad_bridges_tunnel.set_crs("ESRI:102008")
        df_for_railroad_bridges_tunnel = df_for_railroad_bridges_tunnel.to_crs("EPSG:4326")

    except: Exception
    
    for infrastructure in ["Railroad","Tunnels",'Bridges']:
        ls_of_inf = {"Railroad" : '',"Tunnels" :"",'Bridges' : ''}
        try:
            path_of_infastr = os.path.join(save_path,
                                             f"{project_name} {infrastructure}.{export_type_dict[export_type][0]}")
            if len(list(df_for_railroad_bridges_tunnel[
                 df_for_railroad_bridges_tunnel["type"]==infrastructure]["geometry"]))>0:
                
                gpd.GeoDataFrame({"geometry" :
                                list(df_for_railroad_bridges_tunnel[
                                     df_for_railroad_bridges_tunnel["type"]==infrastructure]["geometry"])
                                }
                                ).to_file(os.path.join(save_path,
                                                    f"{project_name} {infrastructure}.{export_type_dict[export_type][0]}"),
                                        driver=export_type_dict[export_type][1])
                ls_of_inf[infrastructure] = path_of_infastr

        except: Exception

 
    
    path_drop_length = os.path.join(save_path,
                                    f"{project_name} Drop Length.{export_type_dict[export_type][0]}")
    
    drop_length = drop_length.to_crs("EPSG:4326")
    drop_length.to_file(path_drop_length,driver = export_type_dict[export_type][1])

    path_points = os.path.join(save_path,
                               f"{project_name} UCDs.{export_type_dict[export_type][0]}")
    locations_final = locations_final.to_crs("EPSG:4326")
    locations_final.to_file(path_points,driver = export_type_dict[export_type][1])

    path_snap_points = os.path.join(save_path,
                                    f"{project_name} Snapped Points.{export_type_dict[export_type][0]}")
    snap = snap.to_crs("EPSG:4326")
    snap.to_file(path_snap_points,driver = export_type_dict[export_type][1])

    path_invalid_points = ""

    if invalid_points is not None:
            
            path_invalid_points = os.path.join(save_path,
                                               f"{project_name} Invalid Points.{export_type_dict[export_type][0]}")
            invalid_points = invalid_points.to_crs("EPSG:4326")
            invalid_points.to_file(path_invalid_points,driver= export_type_dict[export_type][1])

    try:
        call_qgis_for_steiner(project_name=project_name, steiner = path_sten,drop_length=path_drop_length,
                            UCDs = path_points,
                            railroad_path = ls_of_inf['Railroad'],tunnel_path=ls_of_inf['Tunnels'],bridges_path=ls_of_inf['Bridges'], save_path = save_path,snap_point = path_snap_points,polygon = polygon_for_steiner_path,
                                invalid_points = path_invalid_points)
    except:Exception

    def call_arcgis_for_steiner(project_name, steiner ,drop_length,
                            UCDs ,
                            railroad_path ,tunnel_path,bridges_path, save_path,snap_point = '',polygon = '',
                                invalid_points = ''):
        
        my_call = [r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe", r"path to arcgis project run",
                   project_name,snap_point, drop_length,steiner,invalid_points,polygon,UCDs,railroad_path,
                     tunnel_path, bridges_path,save_path]
        
        p = sub.Popen(my_call, stdout=sub.PIPE, stderr=sub.PIPE)
        stdout, stderr = p.communicate()

     

    if export_type == 'shp':
         call_arcgis_for_steiner(project_name=project_name, steiner = path_sten,drop_length=path_drop_length,
                            UCDs = path_points,
                            railroad_path = ls_of_inf['Railroad'],tunnel_path=ls_of_inf['Tunnels'],bridges_path=ls_of_inf['Bridges'], 
                            save_path = save_path,snap_point = path_snap_points,polygon = polygon_for_steiner_path,
                              invalid_points = path_invalid_points
                )
         