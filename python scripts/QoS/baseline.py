#!/usr/bin/env python3

from mininet.log import setLogLevel, info
from mininet.node import Controller
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi
from mn_wifi.node import OVSKernelAP
from mn_wifi.link import wmediumd
from mn_wifi.wmediumdConnector import interference
from mn_wifi.sumo.runner import sumo
import time

MIN_X, MIN_Y, MAX_X, MAX_Y = -100.0, -400.0, 500.0, 200.0
PAD = 20.0

SUMO_CFG = "/home/wifi/mininet-wifi/mn_wifi/sumo/data/girogiro.sumocfg"


def topology():
    info("\n*** USING FORCED BOTTLENECK BASELINE ***\n")

    net = Mininet_wifi(controller=Controller,
                       accessPoint=OVSKernelAP,
                       link=wmediumd, wmediumd_mode=interference)

    net.setPropagationModel(model="logDistance", exp=3.4, sL=2)

    info("*** Creating 7 vehicles (cars)\n")
    cars = []
    for i in range(7):
        c = net.addCar(f'car{i+1}', wlans=1,
                       ip=f'10.0.0.{i+1}/24',
                       position='0,0,0', range=60)
        cars.append(c)

    info("*** Creating 6 RSUs in a 3x2 grid\n")
    rsu1 = net.addAccessPoint('rsu1', ssid='vanet', mode='g', channel='1',
                              position='0,100,0', range=170,
                              failMode='standalone')
    rsu2 = net.addAccessPoint('rsu2', ssid='vanet', mode='g', channel='1',
                              position='200,100,0', range=170,
                              failMode='standalone')
    rsu3 = net.addAccessPoint('rsu3', ssid='vanet', mode='g', channel='1',
                              position='400,100,0', range=170,
                              failMode='standalone')
    rsu4 = net.addAccessPoint('rsu4', ssid='vanet', mode='g', channel='1',
                              position='0,-300,0', range=170,
                              failMode='standalone')
    rsu5 = net.addAccessPoint('rsu5', ssid='vanet', mode='g', channel='1',
                              position='200,-300,0', range=170,
                              failMode='standalone')
    rsu6 = net.addAccessPoint('rsu6', ssid='vanet', mode='g', channel='1',
                              position='400,-300,0', range=170,
                              failMode='standalone')

    aps = [rsu1, rsu2, rsu3, rsu4, rsu5, rsu6]

    info("*** Creating backhaul with FORCED bottleneck\n")
    srv = net.addHost('srv', ip='10.0.0.254/24')

    # Two switches only:
    # s2 = agg1 (all RSUs)
    # s3 = agg2 (towards server)
    agg1 = net.addSwitch('s2', failMode='standalone')
    agg2 = net.addSwitch('s3', failMode='standalone')

    info("*** Linking ALL RSUs to agg1 (s2)\n")
    for ap in aps:
        net.addLink(ap, agg1, bw=20, delay='5ms', use_htb=True)

    info("*** Adding NASTY bottleneck link agg1 <-> agg2\n")
    net.addLink(agg1, agg2,
                bw=2, delay='80ms', loss=5,
                max_queue_size=20, use_htb=True)

    info("*** Linking agg2 directly to server (good link)\n")
    net.addLink(agg2, srv, bw=50, delay='2ms', use_htb=True)

    info("*** Configuring wifi nodes\n")
    net.configureWifiNodes()

    info(f"*** SUMO config: {SUMO_CFG}\n")
    net.useExternalProgram(
        program=sumo,
        config_file=SUMO_CFG,
        port=8813,
        extra_params=["--start", "--delay", "200", "--step-length", "0.1"],
        clients=1,
        exec_order=0
    )

    info("*** Starting network (NO SDN)\n")
    c0 = net.addController('c0')
    net.build()

    for ap in aps:
        ap.start([])
    agg1.start([])
    agg2.start([])

    info("*** Configuring AP bridges with NORMAL\n")
    for ap in aps:
        ap.cmd(f'ovs-vsctl -- if-exists del-port {ap.name} {ap.name}-wlan2')
        ap.cmd(f'ovs-vsctl --may-exist add-port {ap.name} {ap.name}-wlan1')
        info(ap.cmd(f'ovs-vsctl list-ports {ap.name}'))
        ap.cmd(
            f'ovs-ofctl -O OpenFlow13 add-flow {ap.name} "actions=NORMAL" || '
            f'ovs-ofctl -O OpenFlow10 add-flow {ap.name} "actions=NORMAL"'
        )

    info("*** Installing NORMAL flows on agg1 and agg2\n")
    for br in [agg1, agg2]:
        br.cmd(
            f'ovs-ofctl -O OpenFlow13 add-flow {br.name} "actions=NORMAL" || '
            f'ovs-ofctl -O OpenFlow10 add-flow {br.name} "actions=NORMAL"'
        )

    time.sleep(2.0)

    info("*** Enabling telemetry\n")
    nodes = cars + aps
    net.telemetry(nodes=nodes, data_type='position',
                  min_x=MIN_X - PAD, min_y=MIN_Y - PAD,
                  max_x=MAX_X + PAD, max_y=MAX_Y + PAD)

    net.plotGraph(max_x=MAX_X + PAD, max_y=MAX_Y + PAD)

    info("*** Running CLI (BASELINE)\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    topology()
