#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
from fpga_interchange.chip_info import ChipInfo, BelInfo, TileTypeInfo, \
        TileWireInfo, BelPort, PipInfo, TileInstInfo, SiteInstInfo, NodeInfo, \
        TileWireRef

from fpga_interchange.nextpnr import PortType
from enum import Enum
from collections import namedtuple

class FlattenedWireType(Enum):
    TILE_WIRE = 0
    SITE_WIRE = 1

class FlattenedPipType(Enum):
    TILE_PIP = 0
    SITE_PIP = 1
    SITE_PIN = 2


def direction_to_type(direction):
    if direction == 'input':
        return PortType.PORT_IN
    elif direction == 'output':
        return PortType.PORT_OUT
    else:
        assert direction == 'inout'
        return PortType.PORT_INOUT


BelPin = namedtuple('BelPin', 'port type wire')

class FlattenedBel(namedtuple('FlattenedBel', 'name type site_index bel_index is_routing')):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ports = []

    def add_port(self, device, bel_pin, wire_index):
        self.ports.append(BelPin(
                port=device.strs[bel_pin.name],
                type=direction_to_type(bel_pin.dir),
                wire=wire_index))


# Object that represents a flattened wire.
class FlattenedWire(namedtuple('FlattenedWire', 'type name wire_index site_index')):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bel_pins = []
        self.pips_uphill = []
        self.pips_downhill = []


class FlattenedPip(namedtuple('FlattenedPip', 'type src_index dst_index site_index pip_index')):
    pass


class FlattenedSite(namedtuple('FlattenedSite', 'site_in_type_index site_type_index site_type site_variant bel_to_bel_index bel_pin_to_site_wire_index bel_pin_index_to_bel_index')):
    pass


class FlattenedTileType():
    def __init__(self, device, tile_type_index, tile_type):
        self.tile_type_name = device.strs[tile_type.name]
        self.tile_type = tile_type

        self.sites = []
        self.bels = []
        self.wires = []

        self.pips = []

        # Add tile wires
        self.tile_wire_to_wire_in_tile_index = {}
        for wire_in_tile_index, wire in enumerate(tile_type.wires):
            name = device.strs[wire]
            self.tile_wire_to_wire_in_tile_index[name] = wire_in_tile_index

            flat_wire = FlattenedWire(
                    type=FlattenedWireType.TILE_WIRE,
                    name=name,
                    tile_type_index=tile_type_index,
                    wire_index=wire_in_tile_index,
                    site_type_index=None,
                    site_in_type_index=None,
                    site_index=None,
                    site_variant=None)
            self.add_wire(flat_wire)

        # Add pips
        for idx, pip in enumerate(tile_type.pips):
            # TODO: Handle pseudoCells
            self.add_tile_pip(idx, pip.wire0, pip.wire1)

            if not pip.directional:
                self.add_tile_pip(idx, pip.wire1, pip.wire0)

        # Add all site variants
        for site_in_type_index, siteTypeInTileType in enumerate(tile_type.siteTypes):
            site_type_index = siteTypeInTileType.primaryType
            site_variant = -1
            site_type = device.device_resource_capnp.siteTypeList[site_type_index]

            primary_site_type = self.add_site_type(device, siteTypeInTileType, site_in_type_index, site_type_index, site_variant)

            for site_variant, alt_site_type_index in enumerate(site_type.altSiteTypes):
                self.add_site_type(device, tile_type, site_in_type_index, site_type_index, site_variant, primary_site_type)

    def add_wire(self, wire):
        wire_index = len(self.wires)
        self.wires.append(wire)

        return wire_index

    def add_pip_common(self, flat_pip):
        pip_index = len(self.pips)

        self.pips.append(flat_pip)

        self.wires[flat_pip.src_index].pips_downhill.append(pip_index)
        self.wires[flat_pip.dst_index].pips_uphill.append(pip_index)

    def add_tile_pip(self, tile_pip_index, src_wire, dst_wire):
        assert self.wires[src_wire].type == FlattenedPipType.TILE_WIRE
        assert self.wires[dst_wire].type == FlattenedPipType.TILE_WIRE

        flat_pip = FlattenedPip(
                type=FlattenedPipType.TILE_PIP,
                src_index=src_wire,
                dst_index=dst_wire,
                site_index=None,
                pip_index=tile_pip_index)

        self.add_pip_common(flat_pip)

    def add_site_type(self, device, site_type_in_tile_type, site_in_type_index, site_type_index, site_variant, primary_site_type=None):
        if site_variant == -1:
            assert primary_site_type is None
        else:
            assert primary_site_type is not None

        site_index = len(self.sites)

        bel_to_bel_index = {}
        bel_pin_to_site_wire_index = {}
        bel_pin_index_to_bel_index = {}

        site_type = device.device_resource_capnp.siteTypeList[site_type_index]

        self.sites.append(FlattenedSite(
            site_in_type_index=site_in_type_index,
            site_type_index=site_type_index,
            site_type=site_type,
            site_variant=site_variant,
            bel_to_bel_index=bel_to_bel_index,
            bel_pin_to_site_wire_index=bel_pin_to_site_wire_index,
            bel_pin_index_to_bel_index=bel_pin_index_to_bel_index
            ))

        # Add site wires
        for idx, site_wire in enumerate(site_type.siteWires):
            wire_name = device.strs[site_wire.name]
            flat_wire = FlattenedWire(
                    type=FlattenedWireType.SITE_WIRE,
                    name=wire_name,
                    wire_index=idx,
                    site_index=site_index)

            site_wire_index = self.add_wire(flat_wire)
            for pin in site_wire.pins:
                assert pin not in bel_pin_to_site_wire_index
                bel_pin_to_site_wire_index[pin] = site_wire_index

        # Add BELs
        for bel_idx, bel in enumerate(site_type.bels):
            # Site ports are just modelled as an edge between the site wire
            # and tile wire, no need to emit the Bel at all.
            if bel.category != 'sitePort':
                flat_bel = None
            else:
                flat_bel = FlattenedBel(
                        name=device.strs[bel.name],
                        type=device.strs[bel.type],
                        site_index=site_index,
                        bel_index=bel_idx,
                        is_routing=bel.category=='routing')
                bel_index = len(self.bels)
                bel_to_bel_index[bel_idx] = bel_index
                self.bels.append(flat_bel)

            for pin_idx, pin in enumerate(bel.pins):
                assert pin not in bel_pin_index_to_bel_index
                bel_pin_index_to_bel_index[pin] = bel_idx, pin_idx

                if flat_bel is not None:
                    wire_idx = bel_pin_to_site_wire_index[pin]
                    flat_bel.add_port(site_type.belPins[pin], wire_idx)
                    self.wires[wire_idx].bel_pins.append((bel_index, pin_idx))

        # Add site pips
        for idx, site_pip in enumerate(site_type.sitePips):
            src_bel_pin = site_pip.inpin
            bel_idx, src_pin_idx = bel_pin_index_to_bel_index[src_bel_pin]
            src_site_wire_idx = bel_pin_to_site_wire_index[src_bel_pin]

            dst_bel_pin = site_pip.outpin
            dst_site_wire_idx = bel_pin_to_site_wire_index[dst_bel_pin]

            self.add_site_pip(
                src_site_wire_idx,
                dst_site_wire_idx,
                site_index,
                idx)

        # Add site pins
        for idx, site_pin in enumerate(site_type.pins):
            site_wire = bel_pin_to_site_wire_index[site_pin.belpin]

            if site_variant != -1:
                # This is an alternative site, map to primary pin first
                parent_pins = site_type_in_tile_type.altPinsToPrimaryPins[site_variant]
                primary_idx = parent_pins[idx]
            else:
                # This is the primary site, directly lookup site tile wire.
                primary_idx = idx

            tile_wire_name = device.strs[site_type_in_tile_type.primaryPinsToTileWires[primary_idx]]
            tile_wire = self.tile_wire_to_wire_in_tile_index[tile_wire_name]

            if site_pin.dir == 'input':
                # Input site pins connect tile wires to site wires
                src_wire = tile_wire
                dst_wire = site_wire
            else:
                assert site_pin.dir == 'output'
                # Output site pins connect site wires to tile wires
                src_wire = site_wire
                dst_wire = tile_wire

            self.add_site_pin(
                src_wire,
                dst_wire,
                site_index,
                idx)


    def add_site_pip(self, src_wire, dst_wire, site_index, site_pip_index):
        assert self.wires[src_wire].type == FlattenedPipType.SITE_WIRE
        assert self.wires[dst_wire].type == FlattenedPipType.SITE_WIRE

        flat_pip = FlattenedPip(
                type=FlattenedPipType.SITE_PIP,
                src_index=src_wire,
                dst_index=dst_wire,
                site_index=site_index,
                pip_index=site_pip_index)

        self.add_pip_common(flat_pip)

    def add_site_pin(self, src_wire, dst_wire, site_index, site_pin_index):
        if self.wires[src_wire].type == FlattenedPipType.SITE_WIRE:
            assert self.wires[dst_wire].type == FlattenedPipType.TILE_WIRE
        else:
            assert self.wires[src_wire].type == FlattenedPipType.TILE_WIRE
            assert self.wires[dst_wire].type == FlattenedPipType.SITE_WIRE

        flat_pip = FlattenedPip(
                type=FlattenedPipType.SITE_PIN,
                src_index=src_wire,
                dst_index=dst_wire,
                site_index=site_index,
                pip_index=site_pin_index)

        self.add_pip_common(flat_pip)

    def create_tile_type_info(self):
        tile_type = TileTypeInfo()
        tile_type.name = self.name
        tile_type.number_sites = len(self.sites)

        for bel in self.bels:
            bel_info = BelInfo()
            bel_info.name = bel.name
            bel_info.type = bel.type

            for port in bel.ports:
                bel_info.ports.append(port.port)
                bel_info.types.append(port.type.value)
                bel_info.wires.append(port.wire)

            bel_info.site = bel.site_index
            bel_info.site_variant = self.sites[bel.site_index].site_variant
            bel_info.is_routing = bel.is_routing

            tile_type.bel_data.append(bel_info)

        for wire in self.wires:
            wire_info = TileWireInfo()
            wire_info.name = wire.name
            wire_info.pips_uphill = wire.pips_uphill
            wire_info.pips_downhill = wire.pips_downhill

            for (bel_index, port) in wire.bel_pins:
                bel_port = BelPort()
                bel_port.bel_index = bel_index
                bel_port.port = port

                wire_info.bel_pins.append(bel_port)

            if wire.site_index is not None:
                wire_info.site = wire.site_index
                wire_info.site_variant = self.sites[wire.site_index].site_variant
            else:
                wire_info.site = -1
                wire_info.site_variant = -1

            tile_type.wire_data.append(wire_info)

        for pip in self.pips:
            pip_info = PipInfo()

            pip_info.src_index = pip.src_index
            pip_info.dst_index = pip.dst_index

            if pip.site_index is not None:
                site = self.sites[pip.site_index]
                site_type = site.site_type

                pip_info.site = pip.site_index
                pip_info.site_variant = site.site_variant

                if pip.type == FlattenedPipType.SITE_PIP:
                    site_pip = site_type.sitePips[pip.pip_index]
                    bel_idx, pin_idx = site.bel_pin_index_to_bel_index[site_pip.inpin]
                    pip_info.bel = site.bel_to_bel_index[bel_idx]
                    pip_info.extra_data = pin_idx
                else:
                    assert pip.type == FlattenedPipType.SITE_PIN
                    site_pin = site_type.pins[pip.pip_index]
                    bel_idx, pin_idx = site.bel_pin_index_to_bel_index[site_pin.belpin]
                    pip_info.bel = site.bel_to_bel_index[bel_idx]
                    pip_info.extra_data = pin_idx
            else:
                assert pip.type == FlattenedPipType.TILE_PIP
                pip_info.site = -1
                pip_info.site_variant = -1


def populate_chip_info(device, chip_info):

    chip_info = ChipInfo()

    tile_wire_to_wire_in_tile_index = []
    num_tile_wires = []

    for tile_type_index, tile_type in enumerate(device.device_resource_capnp.tileTypeList):
        flattened_tile_type = FlattenedTileType(device, tile_type_index, tile_type)

        tile_type_info = flattened_tile_type.create_tile_type_info()
        chip_info.tile_types.append(tile_type_info)

        # Create map of tile wires to wire in tile id.
        per_tile_map = {}
        for idx, wire in enumerate(tile_type_info.wire_data):
            if wire.site != -1:
                # Only care about tile wires!
                break

            assert wire.name not in per_tile_map
            per_tile_map[wire.name] = idx

        tile_wire_to_wire_in_tile_index.append(per_tile_map)
        num_tile_wires.append(max(per_tile_map.values()))

    tiles = {}
    tile_name_to_tile_index = {}

    for tile_index, tile in enumerate(device.device_resource_capnp.tileList):
        tile_info = TileInstInfo()

        tile_info.name = device.strs[tile.name]
        tile_info.type = tile.type
        tile_info.tile_wire_to_node = list([-1 for _ in range(num_tile_wires[tile.type])])

        tile_type = device.device_resource_capnp.tileTypeList[tile.type]

        for site_type_in_tile_type, site in enumerate(tile_type.siteTypes, tile.sites):
            site_name = device.strs[site.name]

            site_info = SiteInstInfo()
            site_type = device.device_resource_capnp.siteTypeList[site_type_in_tile_type.primaryType]
            site_type_name = device.strs[site_type.name]
            site_info.name = '{}.{}'.format(site_name, site_type_name)
            site_info.site_type = site_type_name

            tile_info.sites.append(len(chip_info.sites))
            chip_info.sites.append(site_info)

        assert len(tile_info.sites) == chip_info.tile_types[tile.type].number_sites

        # (x, y) = (col, row)
        tiles[(tile.col, tile.row)] = (tile_index, tile_info)

    # Compute dimensions of grid
    xs, ys = zip(*tiles.keys())
    width = max(xs)
    height = max(ys)

    # Add tile instances to chip_info in row major order (per arch.h).
    for y in range(height):
        for x in range(width):
            key = x, y

            _, tile_info = tiles[key]
            tile_name_to_tile_index[tile_info.name] = len(chip_info.tiles)
            chip_info.tiles.append(tile_info)

    # Output nodes
    for node in device.device_resource_capnp.nodes:
        # Skip nodes with only 1 wire!
        if len(node.wires) == 1:
            continue

        node_info = NodeInfo()
        node_index = len(chip_info.nodes)
        chip_info.nodes.append(node_info)

        for wire in node.wires:
            tile_name = device.strs[wire.tile]
            wire_name = device.strs[wire.wire]

            tile_index = tile_name_to_tile_index[tile_name]
            tile_info = chip_info.tiles[tile_index]

            # Make reference from tile to node.
            wire_in_tile_id = tile_wire_to_wire_in_tile_index[tile_info.type][wire_name]
            assert tile_info.tile_wire_to_node[wire_in_tile_id] == -1
            tile_info.tile_wire_to_node[wire_in_tile_id] = node_index

            # Make reference from node to tile.
            tile_wire = TileWireRef()
            tile_wire.tile = tile_index
            tile_wire.index = wire_in_tile_id

            node_info.append(tile_wire)

    return chip_info