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
import argparse
import os

from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.converters import Enumerator
from fpga_interchange.nextpnr import BbaWriter
from fpga_interchange.populate_chip_info import populate_chip_info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--device')

    args = parser.parse_args()
    interchange = Interchange(args.schema_dir)

    const_ids = Enumerator()

    with open(args.device, 'rb') as f:
        device = interchange.read_device_resource(f)

    chip_info = populate_chip_info(device)

    with open(os.path.join(args.output_dir, 'chipdb.bba'), 'w') as f:
        bba = BbaWriter(f, const_ids)
        bba.pre("#include \"nextpnr.h\"")
        bba.pre("NEXTPNR_NAMESPACE_BEGIN")
        bba.post("NEXTPNR_NAMESPACE_END")
        bba.push("push chipdb_blob")
        bba.println("offset32");

        root_prefix = 'chip_info'
        bba.ref(root_prefix, root_prefix)
        chip_info.append_bba(bba, root_prefix)
        bba.pop()

    with open(os.path.join(args.output_dir, 'constids.inc'), 'w') as f:
        for s in const_ids.values:
            print('X({})'.format(s), file=f)

if __name__ == "__main__":
    main()