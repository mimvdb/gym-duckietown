#!/usr/bin/env python3
import argparse
import yaml
import logging
import os
from random import Random
from duckietown_world import (
    get_DB18_nominal,
    get_DB18_uncalibrated,
    get_texture_file,
    MapFormat1,
    MapFormat1Constants,
    MapFormat1Constants as MF1C,
    MapFormat1Object,
    SE2Transform,
)

import networkx as nx

from typing import List, Tuple

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="overwrite existing maps")
parser.add_argument("--width", default=5, help="width of the map to generate")
parser.add_argument("--height", default=5, help="height of the map to generate")
parser.add_argument("--seed", default=None, help="seed for random generator")
parser.add_argument("--file-name", default="generated.yaml")
args = parser.parse_args()

rand = Random()

TILE_SIZE = 0.585

def save_map(map_path: str, map_data: MapFormat1):
    assert map_path.endswith(".yaml")
    if os.path.exists(map_path) and os.path.isfile(map_path):
        logging.warning("Map already exists")
        if not args.force:
            logging.warning("Skipping")
            return
    logging.debug(f"Writing map to {map_path}")

    with open(map_path, "w") as f:
        yaml.dump(map_data, f, default_flow_style=None)

def neighs(x: int, y: int):
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

def is_set(l: List[List[bool]], x: int, y: int) -> bool:
    if x < 0 or y < 0 or x >= args.width or y >= args.height:
        return False
    else:
        return l[y][x]

def gen_cycle() -> List[List[bool]]:
    cycle_map = []
    for i in range(args.height):
        cycle_map.append([False] * args.width)
    prevX = rand.randrange(args.width)
    prevY = rand.randrange(args.height)
    track = [(prevX, prevY)]
    visited = {(prevX, prevY)}
    cycle_map[prevY][prevX] = True

    while (sum([i in visited for i in neighs(prevX, prevY)]) < 2):
        x, y = rand.choice(neighs(prevX, prevY))
        if x < 0 or y < 0 or x >= args.width or y >= args.height or len(track) > 1 and(x, y) == track[-2]:
            continue
        track.append((x, y))
        visited.add((x, y))
        cycle_map[y][x] = True
        prevX, prevY = x, y
    
    for x, y in neighs(prevX, prevY):
        if (x, y) in visited and (x, y) not in track[-2:]:
            for revX, revY in track[:track.index((x, y))]:
                cycle_map[revY][revX] = False

    return cycle_map

def gen_cycle2() -> List[List[bool]]:
    cycle_map = []
    for i in range(args.height):
        cycle_map.append([False] * args.width)
    prevX = rand.randrange(args.width)
    prevY = rand.randrange(args.height)
    candidates = {(prevX, prevY)}
    cycle_map[prevY][prevX] = True

    while candidates:
        prevX, prevY = candidates.pop()
        if (sum([is_set(cycle_map, xz, yz) for xz, yz in neighs(prevX, prevY)]) < 2):
            x, y = rand.choice(neighs(prevX, prevY))
            if x < 0 or y < 0 or x >= args.width or y >= args.height:
                candidates.add((prevX, prevY))
                continue
            candidates.add((x, y))
            cycle_map[y][x] = True
        if (sum([is_set(cycle_map, xz, yz) for xz, yz in neighs(prevX, prevY)]) < 2):
            candidates.add((prevX, prevY))


    return cycle_map

def full() -> List[List[Tuple[int, int, int, int]]]:
    cycle_map = []
    for i in range(args.height):
        cycle_map.append([(i != 0, True, i != args.height - 1, False)] + [(i != 0, True, i != args.height - 1, True)] * (args.width - 2) + [(i != 0, False, i != args.height - 1, True)])
    return cycle_map

def empty() -> List[List[Tuple[int, int, int, int]]]:
    cycle_map = []
    for i in range(args.height):
        # cycle_map.append([(i != 0, True, i != args.height - 1, False)] + [(i != 0, True, i != args.height - 1, True)] * (args.width - 2) + [(i != 0, False, i != args.height - 1, True)])
        cycle_map.append([(False, False, False, False)] * args.width)
    return cycle_map

def edge_path_to_grid(edges: List[Tuple[int, int]]) -> List[List[Tuple[int, int, int, int]]]:
    c_len = len(edges)
    cycle_map = empty()
    for i in range(c_len):
        neighs = [edges[i - 1], edges[(i + 1) % c_len]]
        x, y = edges[i]
        cycle_map[y][x] = ((x, y - 1) in neighs, (x + 1, y) in neighs, (x, y + 1) in neighs, (x - 1, y) in neighs)
    return cycle_map

def all_loops() -> List[List[Tuple[int, int, int, int]]]:
    grid = nx.grid_2d_graph(args.width, args.height, create_using=nx.DiGraph)
    # Not uniform over same shape cycles, for example there are lots of 2x2 cycles.
    # Furthermore, they are directed, so all undirected cycles appear twice
    # (unsure if different starting points count as distinct cycles, assuming not)
    return list(nx.simple_cycles(grid))

def check(bool_map: List[List[bool]], x: int, y: int, n: int, e: int, s: int, w: int) -> bool:
    ee = bool_map[y][x + 1] if x + 1 < args.width else 0
    ww = bool_map[y][x - 1] if x - 1 >= 0 else 0
    ss = bool_map[y + 1][x] if y + 1 < args.height else 0
    nn = bool_map[y - 1][x] if y - 1 >= 0 else 0
    return ee == e and ww == w and nn == n and ss == s

def map_transform(bool_map: List[List[bool]]) -> List[List[str]]:
    tile_map = []
    for i in range(args.height):
        tile_map.append(["grass"] * args.width)
    
    for y in range(args.height):
        for x in range(args.width):
            if bool_map[y][x]:
                if check(bool_map, x, y, 0, 1, 0, 1):
                    tile_map[y][x] = "straight/E"
                elif check(bool_map, x, y, 1, 0, 1, 0):
                    tile_map[y][x] = "straight/S"
                elif check(bool_map, x, y, 1, 1, 0, 0):
                    tile_map[y][x] = "curve_left/S"
                elif check(bool_map, x, y, 0, 1, 1, 0):
                    tile_map[y][x] = "curve_left/W"
                elif check(bool_map, x, y, 0, 0, 1, 1):
                    tile_map[y][x] = "curve_left/N"
                elif check(bool_map, x, y, 1, 0, 0, 1):
                    tile_map[y][x] = "curve_left/E"
                elif check(bool_map, x, y, 1, 1, 1, 0):
                    tile_map[y][x] = "3way_left/S"
                elif check(bool_map, x, y, 0, 1, 1, 1):
                    tile_map[y][x] = "3way_left/W"
                elif check(bool_map, x, y, 1, 0, 1, 1):
                    tile_map[y][x] = "3way_left/N"
                elif check(bool_map, x, y, 1, 1, 0, 1):
                    tile_map[y][x] = "3way_left/E"
                elif check(bool_map, x, y, 1, 1, 0, 1):
                    tile_map[y][x] = "4way/E"
                else:
                    tile_map[y][x] = ""
                    logging.error(f"Unknown tile: {x} {y}")
    return tile_map

def graph_transform(conn_map: List[List[Tuple[int, int, int, int]]]) -> List[List[str]]:
    tile_map = []
    for _ in range(args.height):
        tile_map.append(["grass"] * args.width)
    
    for y in range(args.height):
        for x in range(args.width):
            if conn_map[y][x] == (False,False,False,False):
                tile_map[y][x] = "grass"
            elif conn_map[y][x] == (False, True, False, True):
                tile_map[y][x] = "straight/E"
            elif conn_map[y][x] == (True, False, True, False):
                tile_map[y][x] = "straight/S"
            elif conn_map[y][x] == (True, True, False, False):
                tile_map[y][x] = "curve_left/S"
            elif conn_map[y][x] == (False, True, True, False):
                tile_map[y][x] = "curve_left/W"
            elif conn_map[y][x] == (False, False, True, True):
                tile_map[y][x] = "curve_left/N"
            elif conn_map[y][x] == (True, False, False, True):
                tile_map[y][x] = "curve_left/E"
            elif conn_map[y][x] == (True, True, True, False):
                tile_map[y][x] = "3way_left/S"
            elif conn_map[y][x] == (False, True, True, True):
                tile_map[y][x] = "3way_left/W"
            elif conn_map[y][x] == (True, False, True, True):
                tile_map[y][x] = "3way_left/N"
            elif conn_map[y][x] == (True, True, False, True):
                tile_map[y][x] = "3way_left/E"
            elif conn_map[y][x] == (True, True, False, True):
                tile_map[y][x] = "4way/E"
            else:
                tile_map[y][x] = ""
                logging.error(f"Unknown tile: {x} {y}")
    return tile_map

def object_placement(n: int, min_dist: float, possible_tiles: List[Tuple[int, int]]) -> List[Tuple[float, float]]:
    ducks = []
    min_dist_sq = min_dist * min_dist
    for _ in range(n):
        for _ in range(50): # Max tries
            xoff = rand.random() * TILE_SIZE
            yoff = rand.random() * TILE_SIZE
            startX, startY = rand.choice(possible_tiles)
            x, y = startX * TILE_SIZE + xoff, startY * TILE_SIZE + yoff
            if (all(map(lambda o: (x-o[0])**2 + (y-o[1])**2 > min_dist_sq, ducks))):
                ducks.append((x, y))
                break
    return ducks

def gen_map():
    map_dict: MapFormat1 = {}

    map_dict["tile_size"] = TILE_SIZE
    edges = rand.choice(all_loops())
    map_dict["tiles"] = graph_transform(edge_path_to_grid(edges))
    
    map_dict["objects"] = list(map(lambda x: {
        "height": 0.06,
        "kind": "duckie",
        "optional": False,
        "pos": [x[0], x[1]],
        "rotate": rand.randrange(0, 360),
        "static": True
    }, object_placement(5, 10, edges)))
    return map_dict


save_map(args.file_name, gen_map())