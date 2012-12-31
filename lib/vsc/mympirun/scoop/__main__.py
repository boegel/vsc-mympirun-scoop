#!/usr/bin/env python
#
#    This file is part of Scalable COncurrent Operations in Python (SCOOP).
#
#    SCOOP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    SCOOP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with SCOOP. If not, see <http://www.gnu.org/licenses/>.
#
"""
Some modifications for mympirun to bootstrap.__main__
    Stijn De Weirdt 2012
    It seems impossible to start it from the myscoop itself
"""
# from __future__ has to be first entry, otherwise SyntaxError
from __future__ import print_function
import sys
import os
import functools
import argparse
import scoop
from distutils.version import LooseVersion
from vsc.utils import affinity
from vsc.mympirun.scoop.worker_utils import set_scoop_env, make_worker_log

if LooseVersion(".".join(["%s" % x for x in sys.version_info])) < LooseVersion('2.7'):
    import backportRunpy as runpy
else:
    import runpy

def make_parser():
    """scoop.bootstrap.__main__ parser"""
    parser = argparse.ArgumentParser(description='Starts the executable.',
                                     prog=("{0} -m scoop.bootstrap"
                                           ).format(sys.executable))

    parser.add_argument('--origin',
                        help="To specify that the worker is the origin",
                        action='store_true')
    parser.add_argument('--workerName', help="The name of the worker",
                        default="worker0")
    parser.add_argument('--brokerName', help="The name of the broker",
                        default="broker")
    parser.add_argument('--brokerAddress',
                        help="The tcp address of the broker written "
                             "tcp://address:port",
                        default="")
    parser.add_argument('--metaAddress',
                        help="The tcp address of the info written "
                             "tcp://address:port",
                        default="")
    parser.add_argument('--size',
                        help="The size of the worker pool",
                        type=int,
                        default=1)
    parser.add_argument('--debug',
                        help="Activate the debug",
                        action='store_true')
    parser.add_argument('--profile',
                        help="Activate the profiler",
                        action='store_true')
    parser.add_argument('executable',
                        nargs=1,
                        help='The executable to start with scoop')
    parser.add_argument('args',
                        nargs=argparse.REMAINDER,
                        help='The arguments to pass to the executable',
                        default=[])
    parser.add_argument('--echoGroup',
                        help="Echo the process Group ID before launch",
                        action='store_true')
    ## custom options
    parser.add_argument('--startfrom', help="Change to this directory on start", action='store', default=None)
    parser.add_argument('--nice', help="Set this nice level", action='store', default=0, type=int)
    parser.add_argument('--affinity', help="Use this cpu affinity", action='store', default=None)

    return parser

def main(args=None):
    """The scoop.bootstrap.__main__ main()"""
    if args is None:
        parser = make_parser()
        args = parser.parse_args()

    if args.nice is not None:
        try:
            affinity.setpriority(int(args.nice))
        except:
            _logger.exception("main bootstrap failed nice/setpriority")

    if args.affinity is not None:
        try:
            cs = affinity.cpu_set_t()
            cs.convert_hr_bits("%s" % args.affinity)
            cs.set_bits()
            affinity.sched_setaffinity(cs)
        except:
            _logger.exception("main bootstrap failed affinity/sched_setaffinity")

    if args.startfrom is not None:
        try:
            os.chdir(args.startfrom)
        except:
            _logger.exception("main bootstrap failed startfrom/chdir")


    # Setup the SCOOP constants
    scoop.IS_ORIGIN = args.origin
    scoop.WORKER_NAME = args.workerName.encode()
    scoop.BROKER_NAME = args.brokerName.encode()
    scoop.BROKER_ADDRESS = args.brokerAddress.encode()
    scoop.META_ADDRESS = args.metaAddress.encode()
    scoop.SIZE = args.size
    scoop.DEBUG = args.debug
    scoop.worker = (scoop.WORKER_NAME, scoop.BROKER_NAME)
    # custom
    scoop.IS_ORIGIN = args.origin
    scoop.VALID = True

    _logger.debug("main: workerName %s executable %s args %s" % (args.workerName, args.executable, args.args))
    _logger.debug("main: startfrom %s nice %s affinity %s" % (args.startfrom, args.nice, args.affinity))

    profile = True if args.profile else False

    # get the module path in the Python path
    md_path = os.path.join(os.getcwd(), 
                           os.path.dirname(args.executable[0])
                           )
    if not md_path in sys.path:
        sys.path.append(md_path)

    # temp values to keep the args
    executable = args.executable[0]

    # Add the user arguments to argv
    sys.argv = sys.argv[:1]
    sys.argv += args.args

    # Show the current process Group ID if asked
    if args.echoGroup:
        sys.stdout.write(str(os.getpgrp()) + "\n")
        sys.stdout.flush()

    # import the user module into the global dictionary
    # equivalent to from {user_module} import *
    try:
        user_module = __import__(os.path.basename(executable)[:-3])
    except ImportError as e:
        # Could not find 
        sys.stderr.write('{0}\nIn path: {1}\n'.format(
            str(e),
            sys.path[-1],
            )
        )
        sys.stderr.flush()
        sys.exit(-1)
    try:
        attrlist = user_module.__all__
    except AttributeError:
        attrlist = dir(user_module)
    for attr in attrlist:
        globals()[attr] = getattr(user_module, attr)

    # Start the user program
    from scoop import futures
    if not profile:
        futures._startup(
            functools.partial(
                runpy.run_path,
                executable,
                init_globals=globals(),
                run_name="__main__"
            )
        )
    else:
        import cProfile
        cProfile.run("""futures._startup(
                functools.partial(
                    runpy.run_path,
                   "{0}",
                   init_globals=globals(),
                   run_name="__main__",
                )
            )""".format(executable),
            scoop.WORKER_NAME)

    # custom
    _logger.debug("main: bootstrap main ended")
    
if __name__ == "__main__":
    # custom
    NAME = "MYSCOOPBOOTSTRAP"

    parser = make_parser()
    args = parser.parse_args()

    _logger = make_worker_log(NAME, debug=args.debug, logfn_name=args.workerName)
    set_scoop_env('worker_name', args.workerName)
    set_scoop_env('worker_origin', int(args.origin))

    try:
        main(args)
    except:
        _logger.exception("main bootstrap failed attempt")
