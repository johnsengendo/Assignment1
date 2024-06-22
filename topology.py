#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import subprocess
import sys
import time
import threading

from comnetsemu.cli import CLI, spawnXtermDocker
from comnetsemu.net import Containernet, VNFManager
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.node import Controller


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script for running the video streaming app.')
    parser.add_argument('--autotest', dest='autotest', action='store_const', const=True, default=False,
                        help='test the topology building and close the app.')
    args = parser.parse_args()

    # read the command-line arguments
    bandwidth = 10
    delay = 5
    autotest = args.autotest

    # create the directory that will be shared with the services docker containers
    script_dir = os.path.abspath(os.path.join('./', os.path.dirname(sys.argv[0])))
    shared_dir = os.path.join(script_dir, 'pcap')
    os.makedirs(shared_dir, exist_ok=True)

    # set the logging level
    setLogLevel('info')

    # instantiate the network and the VNF manager objects
    net = Containernet(controller=Controller, link=TCLink, xterms=False)
    mgr = VNFManager(net)

    # add the controller to the network
    info('*** Add controller\n')
    net.addController('c0')

    # add the hosts (server and client) to the network
    info('*** Creating hosts\n')
    server = net.addDockerHost(
        'server', dimage='dev_test', ip='10.0.0.1', docker_args={'hostname': 'server'}
    )
    client = net.addDockerHost(
        'client', dimage='dev_test', ip='10.0.0.2', docker_args={'hostname': 'client'}
    )

    # add switches and links to the network
    info('*** Adding switches and links\n')
    switch1 = net.addSwitch('s1')
    switch2 = net.addSwitch('s2')
    net.addLink(switch1, server)
    middle_link = net.addLink(switch1, switch2, bw=bandwidth, delay=f'{delay}ms')
    net.addLink(switch2, client)

    # start the network
    info('\n*** Starting network\n')
    net.start()
    print()

    info("*** Client host pings the server to test for connectivity: \n")
    reply = client.cmd("ping -c 5 10.0.0.1")
    print(reply)
    
    # add the video streaming (server and client) services
    streaming_server = mgr.addContainer(
        'streaming_server', 'server', 'video_streaming_server', '', docker_args={
            'volumes': {
                shared_dir: {'bind': '/home/pcap/', 'mode': 'rw'}
            }
        }
    )
    streaming_client = mgr.addContainer(
        'streaming_client', 'client', 'video_streaming_client', '', docker_args={
            'volumes': {
                shared_dir: {'bind': '/home/pcap/', 'mode': 'rw'}
            }
        }
    )

    def start_server():
            subprocess.run(['docker', 'exec', '-it', 'streaming_server', 'bash', '-c', 'cd /home && ./video_streaming.py'])

    def start_client():
            subprocess.run(['docker', 'exec', '-it', 'streaming_client', 'bash', '-c', 'cd /home && ./get_video_streamed.py'])

    server_thread = threading.Thread(target=start_server)
    client_thread = threading.Thread(target=start_client)

    server_thread.start()
    client_thread.start()

    server_thread.join()
    client_thread.join()
    # if it is an auto-test execution, skip the interactive part
    if not autotest:
        CLI(net)



    # perform the closing operations
    mgr.removeContainer('streaming_server')
    mgr.removeContainer('streaming_client')
    net.stop()
    mgr.stop()
