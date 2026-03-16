import geopandas as gpd
import shapely
from geopandas import GeoDataFrame
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
# import pcst_fast
from shapely.ops import  split
import pandas as pd
from collections import namedtuple



def delete_disconnected_road(road_segment, snap): #not that valid function 

    buffer_distance = 10  # e.g., 10 meters

    # Create buffered geometries around each road segment
    road_segment['buffered_geometry'] = road_segment['geometry'].buffer(buffer_distance)

    # Now check if each point in `snap` is within any buffered road segment
    snap['on_road'] = snap['geometry'].apply(lambda point: any(road_segment['buffered_geometry'].contains(point)))

    # Optionally, you can also use spatial join for efficiency if there are many points and roads
    buffered_roads = road_segment.set_geometry('buffered_geometry')
    points_on_roads = gpd.sjoin(snap, buffered_roads, predicate='within', how='left')

    on_road_points = points_on_roads[points_on_roads['index_right'].notna()]
    if on_road_points['on_road'].sum()>len(snap)/2:
         
         return True
    else:
         return False
    
def tc(g):
    """Given a graph @g, returns the transitive closure of @g"""
    ret = {}
    for scc in tarjan(g):
        ws = set()
        ews = set()
        for v in scc:
            ws.update(g[v])
        for w in ws:
            assert w in ret or w in scc
            ews.add(w)
            ews.update(ret.get(w, ()))
        if len(scc) > 1:
            ews.update(scc)
        ews = tuple(ews)
        for v in scc:
            ret[v] = ews
    return ret

TarjanContext = namedtuple(
    "TarjanContext",
    [
        "g",  # the graph
        "S",  # The main stack of the alg.
        "S_set",  # == set(S) for performance
        "index",  # { v : <index of v> }
        "lowlink",  # { v : <lowlink of v> }
        "T",  # stack to replace recursion
        "ret",
    ],
)  # return code


def _tarjan_head(ctx, v):
    """Used by @tarjan and @tarjan_iter.  This is the head of the
    main iteration"""
    ctx.index[v] = len(ctx.index)
    ctx.lowlink[v] = ctx.index[v]
    ctx.S.append(v)
    ctx.S_set.add(v)
    it = iter(ctx.g.get(v, ()))
    ctx.T.append((it, False, v, None))


def _tarjan_body(ctx, it, v):
    """Used by @tarjan and @tarjan_iter.  This is the body of the
    main iteration"""
    for w in it:
        if w not in ctx.index:
            ctx.T.append((it, True, v, w))
            _tarjan_head(ctx, w)
            return
        if w in ctx.S_set:
            ctx.lowlink[v] = min(ctx.lowlink[v], ctx.index[w])
    if ctx.lowlink[v] == ctx.index[v]:
        scc = []
        w = None
        while v != w:
            w = ctx.S.pop()
            scc.append(w)
            ctx.S_set.remove(w)
        ctx.ret.append(scc)


def tarjan_iter(g):
    """Returns the strongly connected components of the graph @g
    in a topological order.

        @g is the graph represented as a dictionary
                { <vertex> : <successors of vertex> }.

    This function does not recurse.  It returns an iterator."""
    ctx = TarjanContext(g=g, S=[], S_set=set(), index={}, lowlink={}, T=[], ret=[])
    main_iter = iter(g)
    while True:
        try:
            v = next(main_iter)
        except StopIteration:
            return
        if v not in ctx.index:
            _tarjan_head(ctx, v)
        while ctx.T:
            it, inside, v, w = ctx.T.pop()
            if inside:
                ctx.lowlink[v] = min(ctx.lowlink[w], ctx.lowlink[v])
            _tarjan_body(ctx, it, v)
            if ctx.ret:
                assert len(ctx.ret) == 1
                yield ctx.ret.pop()


def tarjan(g):
    """Returns the strongly connected components of the graph @g
    in a topological order.

        @g is the graph represented as a dictionary
                { <vertex> : <successors of vertex> }.

    This function does not recurse."""
    ctx = TarjanContext(g=g, S=[], S_set=set(), index={}, lowlink={}, T=[], ret=[])
    main_iter = iter(g)
    while True:
        try:
            v = next(main_iter)
        except StopIteration:
            return ctx.ret
        if v not in ctx.index:
            _tarjan_head(ctx, v)
        while ctx.T:
            it, inside, v, w = ctx.T.pop()
            if inside:
                ctx.lowlink[v] = min(ctx.lowlink[w], ctx.lowlink[v])
            _tarjan_body(ctx, it, v)


def tarjan_recursive(g):
    """Returns the strongly connected components of the graph @g
    in a topological order.

        @g is the graph represented as a dictionary
                { <vertex> : <successors of vertex> }.

    This function recurses --- large graphs may cause a stack
    overflow."""
    S = []
    S_set = set()
    index = {}
    lowlink = {}
    ret = []
    def visit(v):
        index[v] = len(index)
        lowlink[v] = index[v]
        S.append(v)
        S_set.add(v)
        for w in g.get(v, ()):
            if w not in index:
                visit(w)
                lowlink[v] = min(lowlink[w], lowlink[v])
            elif w in S_set:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            scc = []
            w = None
            while v != w:
                w = S.pop()
                scc.append(w)
                S_set.remove(w)
            ret.append(scc)
    for v in g:
        if v not in index:
            visit(v)
    return ret

def steiner(roads,pts,tolerance = 0.1,overlap_tolerance = 1e-6 ,prize_value = 99999999999):
    """    
    roads : type GeoDataFrame crs : ESRI:102008
    pts : type GeoDataFrame  crs : ESRI:102008


    """
   
    #making MULTYLINESTRING to LINESTRING
    #this step is done outside
    # roads = roads.explode()

    #make sure that crs is our native
    # proj4_102008 = "+proj=aea +lat_1=20 +lat_2=60 +lat_0=40 +lon_0=-96 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs"
    # roads = roads.set_crs(proj4_102008)
    # pts = pts.set_crs(proj4_102008)
    # roads = roads.to_crs(proj4_102008)
    # pts = pts.to_crs(proj4_102008)
    pts = pts.copy()

    ### Add tiny 1 meter segments at point splits
    pts_buffer = pts.copy()
    pts_buffer['geometry'] = pts_buffer.geometry.buffer(tolerance)
    pts_sindex = pts_buffer.sindex
    
    def split_road_segment(segment, points):
        
        candidates_idx = list(pts_sindex.intersection(segment.bounds))
        candidates = points.loc[candidates_idx]

        split_segments = [segment]

        for _, point in candidates.iterrows():
            if segment.intersects(point.geometry):
                new_split_segments = []
                for split_segment in split_segments:
                    if split_segment.intersects(point.geometry):
                        split_result = split(split_segment, point.geometry)
                        new_split_segments.extend([geom for geom in split_result.geoms if geom.geom_type == 'LineString'])

                    else:
                        new_split_segments.append(split_segment)
                split_segments = new_split_segments

        return split_segments

    new_roads = []

    for _, road in roads.iterrows():
        split_segments = split_road_segment(road.geometry, pts_buffer)
        new_roads.extend(split_segments)

    roads_split = roads.iloc[[0] * len(new_roads)].copy()
    roads_split['geometry'] = new_roads

    ### Add segment length, source and target coords attributes

    roads = roads_split.copy().reset_index()
    roads['length'] = roads.geometry.length
    lens = list(roads.length.copy())
    roads['source'] = roads.geometry.apply(lambda x: Point(x.coords[0]))
    roads['target'] = roads.geometry.apply(lambda x: Point(x.coords[-1]))


    ### Create unique dict of form {node_id : Point coord geo}

    all_points = np.vstack([roads['source'].apply(lambda p: (p.x, p.y)).tolist(),
                            roads['target'].apply(lambda p: (p.x, p.y)).tolist()])

    unique_points, inverse_indices = np.unique(all_points, axis=0, return_inverse=True)

    # Create a dictionary from the unique points
    node_dict = {i: Point(coord) for i, coord in enumerate(unique_points)}

    # Get the source and target IDs
    source_ids = inverse_indices[:len(roads)]
    target_ids = inverse_indices[len(roads):]

    # Replace the 'source' and 'target' columns with the corresponding IDs
    roads['source_id'] = source_ids
    roads['target_id'] = target_ids

    # Create a new column in the roads GeoDataFrame to store the vertex label
    roads['vertex_label'] = "0"

    # Create a spatial index for the roads GeoDataFrame
    roads_sindex = roads.sindex

    for idx, pt in pts.iterrows():
        # Find the bounding box of the buffered point
        pt_buffered = pt.geometry.buffer(overlap_tolerance)
        bounding_box = pt_buffered.bounds

        # Use the spatial index to find the road segments that intersect the bounding box
        possible_matches_idx = list(roads_sindex.intersection(bounding_box))
        possible_matches = roads.loc[possible_matches_idx]

        # Initialize the closest vertex and distance variables
        closest_vertex = None
        closest_distance = float('inf')

        # Iterate over the possible matches to find the closest vertex
        for idx_r, road in possible_matches.iterrows():
            distance = road.geometry.distance(pt.geometry)

            if distance < closest_distance:
                closest_distance = distance
                closest_vertex = idx_r

        # Update the closest vertex's label in the roads GeoDataFrame
        if closest_vertex is not None:
            roads.at[closest_vertex, 'vertex_label'] = f"Vertex_{idx}"
    
    ### Define PCST input parameters
            
    node_selection = list(roads[roads.vertex_label != "0"].source_id.unique()) 
    edge_list = roads[['source_id', 'target_id']].values.tolist()
    costs = list(roads.length)
    prizes = [0]*len(costs)
    for n in node_selection:
        prizes[n] = prize_value
    root = -1
    num_clusters = 1


    ### Run PCST

    try:

        vertices1, eg1 = pcst_fast.pcst_fast(edge_list, prizes, costs, root, num_clusters, "gw",
                                             1)  ### runs the actual Steiner
    except ValueError:
        ls = max(edge_list)
        print("maximum list is : ",ls)
        max_v = ls[0] if ls[0]>ls[1] else ls[1]
        print("max_ val is ;",max_v)


        while len(prizes) <= max_v:
            prizes.append(0)

        vertices1, eg1 = pcst_fast.pcst_fast(edge_list, prizes, costs, root, num_clusters, "gw",
                                             1)  ### runs the actual Steiner

    eg1 = [edge_list[v] for v in eg1]

    df = pd.DataFrame(eg1, columns=['source_id', 'target_id'])
    out_df = pd.merge(roads, df, on=['source_id', 'target_id']) # merge the dataframes on source_id and target_id
    out_df = out_df.set_crs("ESRI:102008")

    return out_df[["geometry", "length"]]






def disconnected_islands(data,return_two_dfs = True):

        """
        Uses Tarjan's algorithm to find disjoint networks in the road data.

        Args:
            return_two_dfs (bool): Whether to return the fully connected network and disconnected networks separately.

        Returns:
            If `return_two_dfs` is True, returns a tuple containing two GeoDataFrames: the fully connected network and
            the disconnected networks. If `return_two_dfs` is False, returns a single GeoDataFrame representing the fully
            connected network.
        """

        disjoint_list = {}

        #iterates thorugh road data and finds for each road its joined one
        for _, i in  data.iterrows():

            states = list( data.geometry.disjoint( data["geometry"][_]))
            disjoint_list[_] = np.where(np.array(states) == False)[0].tolist()

        #gives this add node in graph to which one its connected and as an output there is dict of each node and its connected compoments
        list_of_connected_components = tc(disjoint_list)

        #creates dict of indexes  
        df_of_indexes = gpd.GeoDataFrame({"indexes" : list_of_connected_components.keys(),
                                        "value" : list_of_connected_components.values()})
        
        #counts the lenght of connected components
        df_of_indexes["lenght_of_connected_components"] = df_of_indexes.value.apply(lambda  x : len(x))

        #if there is no disconnected islands it returns road network itself
        if len(df_of_indexes["lenght_of_connected_components"].unique()) == 1:
            if return_two_dfs == True:
                return data,None
            return data
        
        df_of_indexes = df_of_indexes.sort_values("indexes")
        #finds the biggest connected component containing network

        df_new_road_network = data[data.index.isin(list(
            df_of_indexes[df_of_indexes["lenght_of_connected_components"] == max(list(df_of_indexes["lenght_of_connected_components"]))
                        ].indexes)
            )].reset_index(drop=True)
        
        if return_two_dfs==True:
            #finds the disconnected islands 
            small_components = df_of_indexes[df_of_indexes["lenght_of_connected_components"] < 
                                            max(list(df_of_indexes["lenght_of_connected_components"]))]
            df_of_small_components = data[data.index.isin(list(small_components.indexes))].reset_index(drop=True)

            #returns both new road network and disconnected islands
            return df_new_road_network, df_of_small_components
        
        else:

            return df_new_road_network
        

def split_with_lines(data):
        """
        Splits the road network into a GeoDataFrame of individual lines.

        Returns:
            A GeoDataFrame containing each individual line segment of the road network.
        """

        return gpd.GeoDataFrame({"geometry" : shapely.ops.unary_union(list(data.geometry))},index = [0]).explode()


def L_super_fast_drop_length(df1,df2):

    nA = np.array(list(df1.geometry.apply(lambda x: (x.x, x.y))))
    nB = np.array(list(df2.geometry.apply(lambda x: (x.x, x.y))))
    btree = cKDTree(nB)
    dist, idx = btree.query(nA, k=1)
    k = df2.iloc[idx].reset_index(drop=True)
    return k


    
def drop_lengths(points,snap):

    try:  geom_s = gpd.GeoDataFrame(geometry = shapely.wkb.loads(shapely.wkb.dumps(snap.geometry, output_dimension=2)))
    except: geom_s =  gpd.GeoDataFrame(geometry = snap.geometry)

    try:  geom = gpd.GeoDataFrame(geometry = shapely.wkb.loads(shapely.wkb.dumps(points.geometry, output_dimension=2)))
    except: geom =  gpd.GeoDataFrame(geometry = points.geometry)

    drop_length = gpd.GeoDataFrame(geometry=[shapely.geometry.LineString(xy) for xy in zip(geom_s.geometry, geom.geometry)], 
                                        crs="ESRI:102008")
    
    return drop_length


       
def create_polygon(points, buffer_distance):
        """
        Create a polygon from the buffered convex hull of all points.

        Buffering individual points only covers a 1000m radius around each
        location; roads that run *between* far-apart locations are missed.
        Buffering the convex hull ensures the entire corridor between all
        locations is included in the road-network query.
        """
        done = False
        while done != True:
            try:
                # Convex hull covers the space between all locations, not just
                # circles around each one.  For a single point it degenerates to
                # a point, for two points to a line — buffer() makes both into a
                # valid polygon regardless.
                hull = points.unary_union.convex_hull
                buffered_geom = hull.buffer(buffer_distance)

                polygon = gpd.GeoDataFrame(
                    {"geometry": [buffered_geom]},
                    crs="ESRI:102008",
                    index=[0],
                )
                polygon = polygon.to_crs("EPSG:4326")
                x, y = polygon.geometry[0].exterior.xy
                done = True

            except Exception:
                buffer_distance += 500

        if not isinstance(polygon.geometry[0], shapely.geometry.polygon.Polygon):
            raise ValueError("Cannot create polygon from point data.")

        return polygon


def create_linering_from_polygon(polygon):
        """
        Create a linestring from the polygon boundary.

        """
        x,y = polygon.geometry[0].exterior.xy

        temp_df = pd.DataFrame({"x" : list(x), "y" : list(y)})
        temp_df = temp_df.astype({"x" : str, "y" :str})
        temp_df["x,y"] = temp_df["x"] + "," +temp_df["y"] + ",0\n"
        var_of_values  = "".join(temp_df["x,y"].to_list())
        
        input_ = [f"""<Polygon xmlns="http://www.opengis.net/kml/2.2">
        <outerBoundaryIs>
            <LinearRing>
            <coordinates>
                    {var_of_values}
                    </coordinates>
            </LinearRing>
        </outerBoundaryIs>
        </Polygon>"""]

        return input_

def valid_invalid(road_network, locations_data , buffer_size = 50000):
    """

    road network : connected components result from disconnected islands (fully connected road data) crs : ESRI:102008
    locations_data : location data of your input from user crs : ESRI:102008


    """
    points_without_duplicate = gpd.GeoDataFrame({"geometry" : locations_data.geometry.unique()},crs="ESRI:102008")
    buffered_road_network = gpd.GeoDataFrame(geometry = road_network.buffer(buffer_size),crs="ESRI:102008")

    valid_points = gpd.sjoin(points_without_duplicate,buffered_road_network)
    valid_points = gpd.GeoDataFrame({"geometry" : valid_points.geometry.unique()},crs="ESRI:102008")
    
    if len(list(points_without_duplicate[points_without_duplicate["geometry"].isin(
                                               valid_points.geometry)].index)) ==len(points_without_duplicate):
            return valid_points,None
    else:
          invalid = points_without_duplicate.drop(list(points_without_duplicate[points_without_duplicate["geometry"].isin(
                                               valid_points.geometry)].index))
          return valid_points,invalid
    




def explode_points_from_line(line, distance):
        
        points = []
        i = 0
        while i <= line.length:
            point = line.interpolate(i)
            points.append(point)
            i += distance
        return points

def snap_points_new(road_network,location_data):
    
    exploded_points = []

    for _, row in road_network.iterrows():
        line = row['geometry']
        points = explode_points_from_line(line, 3)
        exploded_points.extend(points)
    # Convert the exploded points to a GeoDataFrame
    
    exploded_gdf = gpd.GeoDataFrame(geometry=exploded_points)

    snapps = L_super_fast_drop_length(location_data,exploded_gdf)
    snapps = snapps.set_crs("ESRI:102008")

    return snapps