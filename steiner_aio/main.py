from components.export_data import *
from components.read_data import *
from components.preprocessing import *
from components.postgresql_calls import *


"""

this version includes new delete_disconnected_road function in preprocessing as some small number of locations can be
snapped to disconnected componnent of the road and be deleted which caused an issue

also in steiner code itself when locations are small portion it caeuses smaller node id issue 

"""

if "__main__" == __name__:

    #bulk 1 means export excel without colors
    #bulk 0 means export excel with colors

    #filter_road_boolean 0 run fitler 1 not to run

    read_start = time.time()

    project_name = f"App-000403"
    location_layer_path = fr"/Users/levon/SW2020 Dropbox/SW2020/Workspaces/Luiza/Split Eligible Locations/App-000403.sqlite"
    path = fr"/Users/levon/SW2020 Dropbox/SW2020/Workspaces/Luiza/Split Eligible Locations"
    client_name = "SW2020"
    bulk = '0'
    filter_road_boolean = '1'
    export_type = 'sqlite' #shp KML sqlite
    provider_chart = '0'
    fabric_data = '0'
    buffer_size_for_chart = 5000



    
    # project_name = sys.argv[1]
    # location_layer_path = sys.argv[2]
    # path = sys.argv[3]
    # client_name = sys.argv[4]
    # bulk = sys.argv[5]
    # filter_road_boolean = sys.argv[6]
    # export_type = sys.argv[7]
    # provider_chart = sys.argv[8]
    # fabric_data = sys.argv[9]
    # buffer_size_for_chart = sys.argv[10]


    os.mkdir(os.path.join(path,"results Inga"))
    save_path = os.path.join(path,"results Inga")

    if location_layer_path.endswith(".sqlite"):

            supported_drivers['sqlite'] = 'rw'
            location_data= gpd.read_file(location_layer_path)
            #checking wether point type is valid or not (Point or MultiPoint)
            location_data = check_geometry_type(location_data,save_path)
            location_data= put_crs(location_data, save_path)
            
    elif location_layer_path.endswith(".kml"):
            
            supported_drivers['KML'] = 'rw'
            location_data= gpd.read_file(location_layer_path)
            #checking wether point type is valid or not (Point or MultiPoint)
            location_data = check_geometry_type(location_data,save_path)

            location_data= put_crs(location_data, save_path)

    elif location_layer_path.endswith(".shp"):
            
            location_data= gpd.read_file(location_layer_path)
            #checking wether point type is valid or not (Point or MultiPoint)
            location_data = check_geometry_type(location_data,save_path)

            location_data= put_crs(location_data, save_path)
            
    #checking privileges     

    check_boolean, func_name,state_name_from_check = check_user_privileges(client_name=client_name,
                                                             location_df=location_data,path_for_log=save_path)
    
    read_end = time.time()

    query_start = time.time()
    polygon = create_polygon(location_data,buffer_distance=1000)
    #creates linestringkml for input of query
    line_string_kml = create_linering_from_polygon(polygon)
    #query from database
    output = query_for_road_network(input = line_string_kml,database="wiroidb2",user ="postgresqlwireless2020",password= "software2020!!",
                                    host="wirelesspostgresqlflexible.postgres.database.azure.com", port="5432",function_name=func_name,path_for_log = save_path)
    
    
    #creates dataframe from output
    road_data = output_hadndler(output)
    output_for_railroad_bridges_tunnel = query_for_road_network(input = line_string_kml,database="wiroidb2",user ="postgresqlwireless2020",password= "software2020!!",
                                host="wirelesspostgresqlflexible.postgres.database.azure.com", port="5432",function_name="wwl_select_tunnels_railroads_birdges",path_for_log = save_path)
    
    if filter_road_boolean=='0':
         
         optss= ['S1100' ,'S1200', 'S1400', 'S1500' , 'S1640',  'S1730']
         road_data_filtered = road_data[(road_data['road_type']!='I')]
         road_data_filtered = road_data_filtered[road_data_filtered['mtfcc'].isin(optss)]
         road_data_filtered['road_type'] = road_data_filtered['road_type'].fillna('Nan')
         road_data_filtered = road_data_filtered[road_data_filtered['road_type']!='Nan']

         road_data_filtered = road_data_filtered.reset_index(drop=True)
        #  road_data_filtered.to_file(os.path.join(save_path,"road_filtered"))
    else:
         road_data_filtered = road_data

         
     
    query_end = time.time()

    disconnected_start = time.time()
    #Checks validity of data, crs
    #creates conncted and disconected components of road network
    roads_connected, roads_disconnected = disconnected_islands(road_data)
    # roads_connected.to_file(os.path.join(save_path,"roads_conn"))
    disconnected_end = time.time()


    
    
#this blog is new 
    snap_check = snap_points_new(road_data_filtered,location_data)

    if delete_disconnected_road(roads_connected, snap_check):
         roads_connected = roads_connected
    else:
         roads_connected = roads_disconnected
    

    val_inval_start = time.time()
    valid_points, invalid_points = valid_invalid(roads_connected,location_data)
    val_inval_end = time.time()
    
    snap_start = time.time()
    snap = snap_points_new(road_data_filtered,valid_points)
    snap_end = time.time()

    drop_length_start = time.time()
    drop_length = drop_lengths(valid_points,snap)
    drop_length_end = time.time()

    split_with_lines_start = time.time()
    road = split_with_lines(roads_connected)
    split_with_lines_end = time.time()
    print("here")
    steiner_start = time.time()
    sten = steiner(road,snap)
    steiner_end = time.time()     
    print("done st")
    drop_length_calc_start = time.time()
    drop_length["length"] = drop_length.length
    drop_length_calc_end = time.time()

    steiner_calc_start = time.time()
    sten["length"] = sten.length
    steiner_calc_end = time.time()
    df_for_railroad_bridges_tunnel, dict_for_railroad_tunnel_bridges = output_handler_for_railroad_bridges_tunnel(output_for_railroad_bridges_tunnel,
                                                                                                                  sten)

    files_saved_start =time.time()

    try: 
         
         locations_final = valid_points.merge(location_data[["geometry","unit_count"]],on ='geometry',how= 'left')

    except:
         
         locations_final = valid_points


    polygon_for_steiner = gpd.GeoDataFrame({"geometry":
                                            sten.buffer(100).unary_union},
                                             crs = "ESRI:102008",index=[0])
    
    info_needed_for_excel = None

    if fabric_data == '0':
      try:
       
       fabric_data_ , info_needed_for_excel = export_fabric_locations(polygon_for_steiner)
    
       fabric_data_.to_file(os.path.join(save_path,"Total Fabric Locations.sqlite"),driver='sqlite')

      except: 
        f = open(os.path.join(save_path, "log.txt"), "a")
                        # writing in the file
        f.write("""We couldn't find Fabric locations in the area of interest.\n""")
                        # closing the file
        f.close()

    print("excel start ")
    if bulk=='1':
       
            to_excel_or_csv_without_colors(locations_final,sten,drop_length,project_name,save_path,dict_for_railroad_tunnel_bridges,'excel'
                                           )

    elif bulk=='0':

        try:
            polygon_for_chart = gpd.GeoDataFrame({"geometry":
                                            sten.buffer(float(buffer_size_for_chart)).unary_union},
                                             crs = "ESRI:102008",index=[0])

            to_excel(locations_final,sten,drop_length,project_name,save_path,dict_for_railroad_tunnel_bridges,
                     polygon = polygon_for_chart, provider_chart = provider_chart, info_needed_for_excel = info_needed_for_excel )

        except Exception:

               to_excel_or_csv_without_colors(locations_final,sten,drop_length,project_name,save_path,dict_for_railroad_tunnel_bridges,'excel',
                                          )

    export_files(save_path,project_name,export_type,sten,df_for_railroad_bridges_tunnel,
                 drop_length,locations_final,snap,invalid_points)

    files_saved_end = time.time()

    f = open(os.path.join(save_path, "log.txt"), "a")
                    # writing in the file
    f.write(
f"""{round(read_end - read_start,2)}s: reading data\n
{len(location_data)} locations in {state_name_from_check}\n
{round(query_end - query_start,2)}s: Query road data by Polygon\n
{round(snap_end - snap_start + (drop_length_end - drop_length_start),2)}s: Get drop lines and snap points completed\n
{round(drop_length_calc_end - drop_length_calc_start,2)}s: Add length to drop lines completed\n
{round(disconnected_end - disconnected_start,2)}s: Remove disconnected islands PY completed\n
{round(val_inval_end - val_inval_start,2)}s: Get invalid points completed\n 
{round(steiner_end - steiner_start,2)}s: Steiner complete\n
{round(steiner_calc_end - steiner_calc_start,2)}s: Add length to Steiner completed\n
{round(files_saved_end - files_saved_start,2)}s: Saving files complete\n
Total execution time : {round(files_saved_end - read_start,2)}s
                    """)
                    # closing the file
    f.close()      
#should also add new save_qgz file which will add bridge tunnel and railroad data