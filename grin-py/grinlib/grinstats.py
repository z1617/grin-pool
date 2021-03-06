#!/usr/bin/env python

# Copyright 2018 Blade M. Doyle
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Routines for working with grin_stats records
#

import sys
import time
import requests
import json

from grinlib import lib
from grinlib import grin

from grinbase.model.blocks import Blocks
from grinbase.model.grin_stats import Grin_stats
from grinbase.model.gps import Gps

# MOVE TO CONFIG - Tromps magic numbers
SECONDARY_SIZE = 29
NUM_BLOCKS_WEEK = 10080
BASE_EDGE_BITS = 24
DIFFICULTY_ADJUST_WINDOW = 60


# secondary pow ratio at a specific height
def secondary_pow_ratio(height):
    # I have no idea, Tromp likes secrets and/or hates documentation,
    #   and im too slow to understand it
    return max(0, 90 - int(height / NUM_BLOCKS_WEEK))

# I have no idea
def graph_weight(edge_bits):
    return (2 << (edge_bits - BASE_EDGE_BITS)) * edge_bits

# Calculate GPS for window[-1] for all graph sizes and return it as a list of tuples [(edge_bits, gps_estimate ,), ...]
def estimate_all_gps(window):
    gps = []
    # Calcualte the gps for each graph size in the recnt blocks list
    # Based on jaspervdm code - https://github.com/jaspervdm/grin_mining_sim

    height = window[-1].height
    # Get the difficulty of the most recent block
    difficulty = window[-1].total_difficulty - window[-2].total_difficulty
    # Get secondary_scaling value for the most recent block
    secondary_scaling = window[-1].secondary_scaling
    # Count the total number of each solution size in the window
    counts = {}
    counts[SECONDARY_SIZE] = 0
    for block in window:
        if block.edge_bits not in counts:
            counts[block.edge_bits] = 1
        else:
            counts[block.edge_bits] += 1
    # Get total counts for primary and secondary POWs
    count_secondary = counts[SECONDARY_SIZE]
    count_primary = sum(counts.values()) - count_secondary
    percent_primary = int(count_primary / len(window)*100)
    # ratios
    q = secondary_pow_ratio(height)/100
    r = 1 - q
    # Calculate the GPS
    all_gps = []
    for edge_bits in counts:
        gps = 0
        if edge_bits == SECONDARY_SIZE:
            gps = 42 * difficulty * q / secondary_scaling / 60
        else:
            count_ratio = counts[edge_bits] / count_primary
            print("count_ratio={}".format(count_ratio))
            print("gps = 42 * {} * {} * {} / {} / 60".format(difficulty, r, count_ratio, graph_weight(edge_bits)))
            gps = 42 * difficulty * r * count_ratio / graph_weight(edge_bits) / 60
        all_gps.append((edge_bits, gps, ))
    return all_gps
    

# Calculate the grin stats for the specified height
# Return a Grin_stats object
# Raises AssertionError
def calculate(height, avg_range=DIFFICULTY_ADJUST_WINDOW):
    # Get the most recent blocks from which to generate the stats
    recent_blocks = []
    previous_stats_record = Grin_stats.get_by_height(height-1)
    print("XXX: {}".format(previous_stats_record))
    assert previous_stats_record is not None, "No provious stats record found" 
    recent_blocks = Blocks.get_by_height(height, avg_range)
    if len(recent_blocks) < min(avg_range, height):
        # We dont have all of these blocks in the DB
        raise AssertionError("Missing blocks in range: {}:{}".format(height-avg_range, height))
    assert recent_blocks[-1].height == height, "Invalid height in recent_blocks[-1]" 
    assert recent_blocks[-2].height == height - 1, "Invalid height in recent_blocks[-2]: {} vs {}".format(recent_blocks[-2].height, height - 1) 
    # Calculate the stats data
    first_block = recent_blocks[0]
    last_block = recent_blocks[-1]
    timestamp = last_block.timestamp
    difficulty = recent_blocks[-1].total_difficulty - recent_blocks[-2].total_difficulty
    new_stats = Grin_stats(
        height = height,
        timestamp = timestamp,
        difficulty = difficulty,
    )
    # Caclulate estimated GPS for recent edge_bits sizes
    all_gps = estimate_all_gps(recent_blocks)
    for gps in all_gps:
        gps_rec = Gps(
            edge_bits = gps[0],
            gps = gps[1],
        )
        new_stats.gps.append(gps_rec)
    return new_stats


# Initialize Grin_stats
# No return value
def initialize():
    database = lib.get_db()
    # Special case for new pool startup - Need 3 stats records to bootstrap
    block_zero = Blocks.get_by_height(0)
    seed_stat0 = Grin_stats(
        height=0,
        timestamp=block_zero.timestamp,
        difficulty=block_zero.total_difficulty)
    database.db.createDataObj(seed_stat0)
    block_one = Blocks.get_by_height(1)
    seed_stat1 = Grin_stats(
        height=1,
        timestamp=block_one.timestamp,
        difficulty=block_one.total_difficulty - block_zero.total_difficulty)
    database.db.createDataObj(seed_stat1)
    block_two = Blocks.get_by_height(2)
    seed_stat2 = Grin_stats(
        height=2,
        timestamp=block_two.timestamp,
        difficulty=block_two.total_difficulty - block_one.total_difficulty)
    database.db.createDataObj(seed_stat2)

